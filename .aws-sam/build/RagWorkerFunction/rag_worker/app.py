import re
import time
from typing import Any, Dict, List

import boto3

from common.ai_router import AIRouter
from common.bedrock_client import BedrockClient
from common.gemini_client import GeminiClient
from common.logger import get_logger
from common.secrets import get_secret
from common.settings import load_settings
from common.structured_analyst import (
    build_structured_prompt,
    classify_query_intent,
    get_structured_context,
    load_structured_reports_json,
    resolve_target_weeks,
)
from common.weekly_analyst import apply_prompt_budget
from common.whatsapp_client import WhatsAppClient

logger = get_logger(__name__)
settings = load_settings()

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|salam|مرحبا|السلام عليكم|good\s*(morning|afternoon|evening)|howdy|greetings)[!.,\s]*$",
    re.IGNORECASE,
)

_GREETING_REPLY = (
    "Hi! I am your AI Reporting Assistant.\n\n"
    "You can ask me questions like:\n"
    "- Summary of overall updates from last 4 weeks\n"
    "- Insights into trends or anomalies in last 3 weeks\n"
    "- Progress comparisons across different weeks\n"
    "- Identification of delayed or pending initiatives from last 3 months"
)


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_RE.match(text.strip()))


def _normalize_whatsapp_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines: List[str] = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        line = re.sub(r"^[*•]\s+", "- ", line)
        line = re.sub(r"\s+", " ", line)
        line = re.sub(r"\*{2,}", "*", line)
        line = re.sub(r"\*(.*?)\*", r"\1", line)
        if line.strip() == "*":
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+\*\s*$", "", text).strip()
    text = re.sub(r"^(here(?:'s| is)\s+(?:your\s+)?.*?:\s*)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[\-–—:\s]+", "", text)
    text = re.sub(r"[🚨✅❗⚠️📌📍📊📈📉]+", "", text)

    if not text:
        text = "I found relevant context, but I couldn't format a clean response. Please ask again in one line."
    return text


def _enforce_instruction_output(answer: str) -> str:
    lowered = " ".join(answer.lower().split())
    insuff_phrases = [
        "i don't have enough information",
        "i do not have enough information",
    ]
    if any(phrase in lowered for phrase in insuff_phrases):
        if len(answer.strip()) <= 120 or any(lowered.startswith(p) for p in insuff_phrases):
            return "I don't have enough information."
    return answer


def _extract_gcto_fields(text: str) -> Dict[str, str]:
    """Extract structured fields from a labelled GCTO card string."""
    lines = [" ".join(ln.split()).strip() for ln in (text or "").splitlines() if ln.strip()]
    fields: Dict[str, str] = {"status": "N/A", "owner": "N/A", "due_date": "N/A", "update": "N/A"}
    title_lines: List[str] = []

    for line in lines:
        low = line.lower()
        if low.startswith("status:"):
            fields["status"] = line[7:].strip() or "N/A"
        elif low.startswith("owner:"):
            fields["owner"] = line[6:].strip() or "N/A"
        elif low.startswith("due date:") or low.startswith("due_date:"):
            fields["due_date"] = re.split(r":", line, 1)[1].strip() or "N/A"
        elif low.startswith("title:"):
            title_lines.append(line[6:].strip())
        else:
            title_lines.append(line)

    if title_lines:
        fields["update"] = " ".join(title_lines).strip() or "N/A"
    return fields


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    stage_start = time.perf_counter()
    sender = (event or {}).get("sender")
    user_text = ((event or {}).get("text") or "").strip()
    message_id = (event or {}).get("message_id", "")
    correlation_id = (event or {}).get("correlation_id") or message_id or sender or "unknown"

    if not sender or not user_text:
        logger.warning("Missing sender or user text", extra={"extra": {"event": event}})
        return {"status": "ignored"}

    logger.info(
        "Worker received message",
        extra={"extra": {"sender": sender, "message_id": message_id, "correlation_id": correlation_id}},
    )

    # ── Secrets ──────────────────────────────────────────────────────────────
    meta_secret = get_secret(settings.meta_secret_name)
    whatsapp_token = meta_secret.get("access_token")
    phone_number_id = meta_secret.get("phone_number_id")

    if not whatsapp_token or not phone_number_id:
        logger.error("Missing required Meta secrets")
        return {"status": "error", "reason": "missing_secrets"}

    whatsapp = WhatsAppClient(
        access_token=whatsapp_token,
        phone_number_id=phone_number_id,
        graph_version=settings.whatsapp_graph_version,
    )

    # ── Greeting shortcut ─────────────────────────────────────────────────────
    if _is_greeting(user_text):
        whatsapp.send_text_message(sender, _GREETING_REPLY)
        logger.info("Sent greeting reply", extra={"extra": {"sender": sender}})
        return {"status": "ok", "reason": "greeting"}

    # ── AI clients ────────────────────────────────────────────────────────────
    gemini_api_key = ""
    try:
        gemini_secret = get_secret(settings.gemini_secret_name)
        gemini_api_key = gemini_secret.get("api_key", "")
    except Exception:
        logger.warning("Gemini secret unavailable")

    bedrock = BedrockClient(
        region=settings.aws_region,
        generation_model=settings.generation_model,
        embedding_model=settings.embedding_model,
    )
    gemini = None
    if gemini_api_key:
        gemini = GeminiClient(
            api_key=gemini_api_key,
            generation_model=settings.fallback_generation_model,
            embedding_model=settings.fallback_embedding_model,
        )
    ai_client = AIRouter(
        primary_provider=settings.primary_provider,
        bedrock_client=bedrock,
        gemini_client=gemini,
    )

    # ── Load structured reports ───────────────────────────────────────────────
    s3_client = boto3.client("s3", region_name=settings.aws_region)
    structured_reports = load_structured_reports_json(
        s3_client,
        settings.source_bucket_name,
        settings.structured_reports_key,
    )

    if not structured_reports:
        whatsapp.send_text_message(sender, "I don't have enough information.")
        return {"status": "ok", "reason": "no_structured_data"}

    # ── Intent + context ──────────────────────────────────────────────────────
    intent_result = classify_query_intent(user_text)
    intent = intent_result.get("intent", "weekly_summary")
    available_weeks = [r.get("week_label", "") for r in structured_reports if r.get("week_label")]
    target_weeks = resolve_target_weeks(user_text, available_weeks, intent)
    structured_context = get_structured_context(intent, target_weeks, structured_reports, user_text)

    logger.info(
        "Intent classified",
        extra={"extra": {"correlation_id": correlation_id, "intent": intent, "target_weeks": target_weeks}},
    )

    # ── GCTO direct render (no LLM needed) ───────────────────────────────────
    if intent == "gcto_updates":
        evidence = structured_context.get("evidence", []) or []
        latest_week = target_weeks[-1] if target_weeks else "WK-NA"
        gcto_body = ""
        for item in evidence:
            parts = item.split("|", 2)
            if len(parts) >= 3 and parts[2].strip():
                gcto_body = parts[2].strip()
                break

        if gcto_body:
            fields = _extract_gcto_fields(gcto_body)
            direct_text = "\n".join([
                f"Latest GCTO Updates ({latest_week})",
                f"- Status: {fields['status']}",
                f"- Owner: {fields['owner']}",
                f"- Due Date: {fields['due_date']}",
                f"- Update: {fields['update']}",
            ])
            final_text = _normalize_whatsapp_text(direct_text)
            whatsapp.send_text_message(sender, final_text)
            total_ms = int((time.perf_counter() - stage_start) * 1000)
            logger.info(
                "Answered (gcto direct)",
                extra={"extra": {"sender": sender, "total_latency_ms": total_ms}},
            )
            return {"status": "ok", "reason": "gcto_direct"}

    # ── LLM generation ────────────────────────────────────────────────────────
    prompt = build_structured_prompt(user_text, intent, structured_context)
    prompt = apply_prompt_budget(prompt, max_chars=6500)

    try:
        generation = ai_client.generate_answer(prompt)
        final_text = _normalize_whatsapp_text(_enforce_instruction_output(generation.text))
        send_stats = whatsapp.send_text_message(sender, final_text)
        total_ms = int((time.perf_counter() - stage_start) * 1000)
        logger.info(
            "Answered user message",
            extra={
                "extra": {
                    "sender": sender,
                    "message_id": message_id,
                    "correlation_id": correlation_id,
                    "intent": intent,
                    "target_weeks": target_weeks,
                    "evidence_count": len(structured_context.get("evidence", [])),
                    "final_output_length": len(final_text),
                    "outbound_chunk_count": send_stats.get("chunk_count"),
                    "total_latency_ms": total_ms,
                }
            },
        )
        return {"status": "ok"}
    except Exception:
        logger.exception("Generation or send failed")
        try:
            whatsapp.send_text_message(
                sender,
                "I couldn't complete the response right now. Please retry in a moment.",
            )
        except Exception:
            logger.exception("Failed to send failure notification")
        return {"status": "error", "reason": "generation_failed"}

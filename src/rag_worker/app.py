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
from common.agent_graph import run_graph
from common.structured_analyst import (
    load_structured_reports_json,
)
from common.whatsapp_client import WhatsAppClient

logger = get_logger(__name__)
settings = load_settings()

_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|salam|مرحبا|السلام عليكم|good\s*(morning|afternoon|evening)|howdy|greetings)[!.,\s]*$",
    re.IGNORECASE,
)

# Phone number → display name mapping. Add more entries as needed.
# Numbers should match the sender ID format from Meta (no + prefix, digits only).
KNOWN_USERS: Dict[str, str] = {
    "966547924981": "Anis",
    "966530922088": "Usman",
    "966530174097": "Abu Bilal",
    "966565663662": "Abu Bandar",
    "966533247804": "Ghulam",
}

_GREETING_REPLY_BODY = (
    " I am your AI Reporting Assistant.\n\n"
    "You can ask me questions like:\n"
    "- Summary of overall updates from last 4 weeks\n"
    "- Insights into trends or anomalies in last 3 weeks\n"
    "- Progress comparisons across different weeks\n"
    "- Identification of delayed or pending initiatives from last 3 months"
)


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_RE.match(text.strip()))


def _build_greeting_reply(sender: str) -> str:
    name = KNOWN_USERS.get(sender.lstrip("+"))
    salutation = f"Hi {name}!" if name else "Hi!"
    return salutation + _GREETING_REPLY_BODY


def _normalize_whatsapp_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines: List[str] = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        # Convert markdown bullet points to dashes
        line = re.sub(r"^[•]\s+", "- ", line)
        # Collapse markdown **bold** → *bold* (WhatsApp bold syntax)
        line = re.sub(r"\*\*(.*?)\*\*", r"*\1*", line)
        # Collapse markdown ### headings → *Heading* (WhatsApp bold)
        line = re.sub(r"^#{1,3}\s+(.*)", r"*\1*", line)
        # Collapse 3+ asterisks to 1
        line = re.sub(r"\*{3,}", "*", line)
        # Collapse lone asterisk lines
        if line.strip() == "*":
            continue
        # Normalize whitespace within line
        line = re.sub(r"\s+", " ", line).strip()
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
        whatsapp.send_text_message(sender, _build_greeting_reply(sender))
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

    try:
        # ── Agent Graph (LangGraph orchestration) ────────────────────────────────
        # run_graph() encapsulates the full agentic pipeline:
        #   classify_intent → route_retriever → structured_rag/web_search
        #   → merge_context → generate_answer → validate_answer → format_output
        #
        # If LangGraph is installed: runs as an explicit StateGraph with named nodes
        # and conditional edges. If not: runs the same logic via manual fallback.
        # Either way, behavior is identical — LangGraph is a structural choice.
        graph_result = run_graph(
            query=user_text,
            sender=sender,
            structured_reports=structured_reports,
            ai_client=ai_client,
            tavily_api_key=settings.tavily_api_key,
            tokemizer_api_key=settings.tokemizer_api_key,
        )

        intent = graph_result.get("intent", "unknown")
        target_weeks = graph_result.get("target_weeks", [])
        evidence_count = graph_result.get("evidence_count", 0)
        raw_answer = graph_result.get("final_answer", "")
        graph_error = graph_result.get("error")

        logger.info(
            "Graph execution complete",
            extra={"extra": {
                "correlation_id": correlation_id,
                "intent": intent,
                "target_weeks": target_weeks,
                "retrieval_source": graph_result.get("retrieval_source", "structured"),
            }},
        )

        # ── GCTO direct render (no LLM needed) ───────────────────────────────────
        # GCTO is handled inside the graph but we keep this fast-path for
        # the structured card format which doesn't need LLM generation.
        if intent == "gcto_updates" and not raw_answer:
            from common.structured_analyst import (
                classify_query_intent, get_structured_context, resolve_target_weeks
            )
            intent_result = classify_query_intent(user_text)
            available_weeks = [r.get("week_label", "") for r in structured_reports if r.get("week_label")]
            tw = resolve_target_weeks(user_text, available_weeks, intent)
            structured_context = get_structured_context(intent, tw, structured_reports, user_text)
            evidence = structured_context.get("evidence", []) or []
            latest_week = tw[-1] if tw else "WK-NA"
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
                logger.info("Answered (gcto direct)", extra={"extra": {"sender": sender, "total_latency_ms": total_ms}})
                return {"status": "ok", "reason": "gcto_direct"}

        # ── Deliver answer ────────────────────────────────────────────────────────
        if graph_error and not raw_answer:
            raise RuntimeError(graph_error)

        final_text = _normalize_whatsapp_text(_enforce_instruction_output(raw_answer))
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
                    "evidence_count": evidence_count,
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

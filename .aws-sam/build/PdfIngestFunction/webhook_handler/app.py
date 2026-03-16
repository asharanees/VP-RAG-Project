import json
from typing import Any, Dict, Optional

import boto3

from common.logger import get_logger
from common.secrets import get_secret
from common.settings import load_settings

logger = get_logger(__name__)
settings = load_settings()
lambda_client = boto3.client("lambda", region_name=settings.aws_region)


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _parse_json_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _extract_first_text_message(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    entries = payload.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                continue

            for msg in messages:
                if msg.get("type") != "text":
                    continue
                sender = msg.get("from")
                message_id = msg.get("id")
                text = msg.get("text", {}).get("body", "").strip()
                if sender and text:
                    return {"sender": sender, "text": text, "message_id": message_id or ""}
    return None


def _handle_get(event: Dict[str, Any]) -> Dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    expected = get_secret(settings.verify_token_secret_name).get("verify_token")
    if mode == "subscribe" and token and token == expected:
        logger.info("Webhook verification succeeded")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": challenge or "",
        }

    logger.warning("Webhook verification failed")
    return _response(403, {"error": "Forbidden"})


def _invoke_worker_async(sender: str, text: str, message_id: str) -> None:
    payload = {
        "sender": sender,
        "text": text,
        "message_id": message_id,
        "correlation_id": message_id or sender,
    }
    lambda_client.invoke(
        FunctionName=settings.worker_function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "POST"))
        .upper()
    )

    if method == "GET":
        return _handle_get(event)

    if method != "POST":
        return _response(405, {"error": "Method not allowed"})

    try:
        payload = _parse_json_body(event)
    except Exception:
        logger.exception("Invalid JSON payload")
        return _response(200, {"status": "ignored"})

    extracted = _extract_first_text_message(payload)
    if not extracted:
        logger.info("Ignoring non-message or non-text webhook event")
        return _response(200, {"status": "ignored"})

    try:
        logger.info(
            "Dispatching message to worker",
            extra={"extra": {"sender": extracted["sender"], "message_id": extracted.get("message_id", "")}},
        )
        _invoke_worker_async(extracted["sender"], extracted["text"], extracted.get("message_id", ""))
    except Exception:
        logger.exception("Failed to invoke rag worker")

    return _response(200, {"status": "accepted"})

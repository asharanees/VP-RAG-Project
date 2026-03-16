import requests
import os
from typing import Dict, List

from common.logger import get_logger

logger = get_logger(__name__)


class WhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str, graph_version: str):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.graph_version = graph_version

    def _chunk_message(self, message: str, max_chars: int = 3200) -> List[str]:
        text = (message or "").strip()
        if not text:
            return [""]
        if len(text) <= max_chars:
            return [text]

        chunks: List[str] = []
        remaining = text
        while len(remaining) > max_chars:
            split_at = remaining.rfind("\n\n", 0, max_chars)
            if split_at == -1:
                split_at = remaining.rfind("\n", 0, max_chars)
            if split_at == -1:
                split_at = remaining.rfind(" ", 0, max_chars)
            if split_at == -1:
                split_at = max_chars

            chunk = remaining[:split_at].strip()
            if not chunk:
                chunk = remaining[:max_chars].strip()
                split_at = max_chars

            chunks.append(chunk)
            remaining = remaining[split_at:].strip()

        if remaining:
            chunks.append(remaining)
        return chunks

    def send_text_message(self, recipient: str, message: str, timeout: int = 20) -> Dict[str, int]:
        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        chunks = self._chunk_message(message)
        total_chars = 0
        for idx, chunk in enumerate(chunks, start=1):
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "text": {"body": chunk},
            }
            total_chars += len(chunk)

            if os.getenv("LOG_WHATSAPP_PAYLOAD", "false").lower() == "true":
                logger.info(
                    "WhatsApp outbound payload",
                    extra={
                        "extra": {
                            "recipient": recipient,
                            "chunk_index": idx,
                            "chunk_count": len(chunks),
                            "chunk_length": len(chunk),
                            "payload": payload,
                        }
                    },
                )

            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

        return {"chunk_count": len(chunks), "total_chars": total_chars}

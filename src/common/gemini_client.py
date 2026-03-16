from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import os

import requests

from common.logger import get_logger

logger = get_logger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


@dataclass
class GenerationResult:
    text: str
    finish_reason: Optional[str]
    usage: Dict[str, Any]
    raw_response: Dict[str, Any]


def parse_provider_response(payload: Dict[str, Any]) -> GenerationResult:
    if "candidates" in payload:
        candidates = payload.get("candidates", [])
        if not candidates:
            return GenerationResult(
                text="I could not generate an answer right now.",
                finish_reason=None,
                usage=payload.get("usageMetadata", {}),
                raw_response=payload,
            )
        first = candidates[0]
        parts = first.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        return GenerationResult(
            text=text,
            finish_reason=first.get("finishReason"),
            usage=payload.get("usageMetadata", {}),
            raw_response=payload,
        )

    choices = payload.get("choices", [])
    if choices:
        first_choice = choices[0]
        message = first_choice.get("message", {})
        content = message.get("content", "")
        finish_reason = first_choice.get("finish_reason")
        usage = payload.get("usage", {})
        return GenerationResult(
            text=content.strip(),
            finish_reason=finish_reason,
            usage=usage,
            raw_response=payload,
        )

    return GenerationResult(
        text="I could not generate an answer right now.",
        finish_reason=None,
        usage={},
        raw_response=payload,
    )


class GeminiClient:
    def __init__(self, api_key: str, generation_model: str, embedding_model: str, timeout: int = 30):
        self.api_key = api_key
        self.generation_model = generation_model
        self.embedding_model = embedding_model
        self.timeout = timeout

    def embed_text(self, text: str) -> List[float]:
        url = f"{GEMINI_BASE_URL}/models/{self.embedding_model}:embedContent"
        payload = {
            "model": f"models/{self.embedding_model}",
            "content": {"parts": [{"text": text}]},
        }
        attempts = 6
        backoff_seconds = 2.0
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                return data["embedding"]["values"]
            except requests.HTTPError as err:
                status = err.response.status_code if err.response is not None else None
                retryable = status in {429, 500, 502, 503, 504}
                if not retryable or attempt == attempts:
                    raise

                retry_after = 0.0
                if err.response is not None:
                    header = err.response.headers.get("Retry-After")
                    if header:
                        try:
                            retry_after = float(header)
                        except ValueError:
                            retry_after = 0.0
                logger.warning(
                    "Gemini embedding retry",
                    extra={"extra": {"attempt": attempt, "status_code": status, "retry_after": retry_after}},
                )
                sleep_for = max(backoff_seconds, retry_after)
                time.sleep(sleep_for)
                backoff_seconds = min(backoff_seconds * 2, 20.0)
            except requests.RequestException:
                if attempt == attempts:
                    raise
                logger.warning(
                    "Gemini embedding request retry",
                    extra={"extra": {"attempt": attempt}},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 20.0)
        raise RuntimeError("Embedding request failed after retries")

    def generate_answer(self, prompt: str) -> GenerationResult:
        url = f"{GEMINI_BASE_URL}/models/{self.generation_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2000,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        attempts = 4
        backoff_seconds = 2.0
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                break
            except requests.HTTPError as err:
                status = err.response.status_code if err.response is not None else None
                retryable = status in {429, 500, 502, 503, 504}
                last_error = err
                if not retryable or attempt == attempts:
                    raise
                logger.warning(
                    "Gemini generation retry",
                    extra={"extra": {"attempt": attempt, "status_code": status}},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 8.0)
            except requests.RequestException as err:
                last_error = err
                if attempt == attempts:
                    raise
                logger.warning(
                    "Gemini generation request retry",
                    extra={"extra": {"attempt": attempt}},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 8.0)

        if last_error and "data" not in locals():
            raise last_error

        result = parse_provider_response(data)
        if os.getenv("LOG_LLM_RAW", "false").lower() == "true":
            logger.info(
                "LLM raw response",
                extra={"extra": {"provider": "gemini", "raw_response": result.raw_response}},
            )
        return result

import json
import time
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common.gemini_client import GenerationResult
from common.logger import get_logger

logger = get_logger(__name__)


class BedrockClient:
    def __init__(self, region: str, generation_model: str, embedding_model: str, timeout_seconds: int = 30):
        self.region = region
        self.generation_model = generation_model
        self.embedding_model = embedding_model
        self.timeout_seconds = timeout_seconds
        self.runtime = boto3.client("bedrock-runtime", region_name=region)

    def embed_text(self, text: str) -> List[float]:
        payload = {
            "inputText": text,
            "dimensions": 1024,
            "normalize": True,
        }
        attempts = 4
        backoff_seconds = 1.5

        for attempt in range(1, attempts + 1):
            try:
                response = self.runtime.invoke_model(
                    modelId=self.embedding_model,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload),
                )
                body = json.loads(response["body"].read())
                embedding = body.get("embedding") or body.get("embeddings")
                if isinstance(embedding, list) and embedding:
                    return embedding
                if isinstance(embedding, dict) and "float" in embedding:
                    return embedding["float"]
                raise RuntimeError("Bedrock embedding response missing embedding vector")
            except (ClientError, BotoCoreError, ValueError, RuntimeError) as err:
                if attempt == attempts:
                    raise
                logger.warning(
                    "Bedrock embedding retry",
                    extra={"extra": {"attempt": attempt, "error": str(err)[:180]}},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 8.0)

        raise RuntimeError("Bedrock embedding failed after retries")

    def generate_answer(self, prompt: str) -> GenerationResult:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1400,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }

        attempts = 4
        backoff_seconds = 1.5
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                response = self.runtime.invoke_model(
                    modelId=self.generation_model,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload),
                )
                body = json.loads(response["body"].read())
                text_parts = [
                    item.get("text", "")
                    for item in body.get("content", [])
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                text = "".join(text_parts).strip()
                usage = body.get("usage", {})
                stop_reason = body.get("stop_reason")
                return GenerationResult(
                    text=text or "I could not generate an answer right now.",
                    finish_reason=stop_reason,
                    usage=usage,
                    raw_response=body,
                )
            except (ClientError, BotoCoreError, ValueError) as err:
                last_error = err
                if attempt == attempts:
                    raise
                logger.warning(
                    "Bedrock generation retry",
                    extra={"extra": {"attempt": attempt, "error": str(err)[:180]}},
                )
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 8.0)

        if last_error:
            raise last_error
        raise RuntimeError("Bedrock generation failed")

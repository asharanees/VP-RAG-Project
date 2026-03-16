from typing import Optional

from common.bedrock_client import BedrockClient
from common.gemini_client import GeminiClient, GenerationResult
from common.logger import get_logger

logger = get_logger(__name__)


class AIRouter:
    def __init__(
        self,
        primary_provider: str,
        bedrock_client: Optional[BedrockClient] = None,
        gemini_client: Optional[GeminiClient] = None,
    ):
        self.primary_provider = (primary_provider or "bedrock").lower()
        self.bedrock_client = bedrock_client
        self.gemini_client = gemini_client

    def _primary(self):
        if self.primary_provider == "gemini":
            return self.gemini_client
        return self.bedrock_client

    def _fallback(self):
        if self.primary_provider == "gemini":
            return self.bedrock_client
        return self.gemini_client

    def embed_text(self, text: str):
        primary = self._primary()
        fallback = self._fallback()

        if primary is not None:
            try:
                return primary.embed_text(text)
            except Exception as err:
                logger.warning("Primary embedding provider failed", extra={"extra": {"provider": self.primary_provider, "error": str(err)[:180]}})

        if fallback is not None:
            logger.warning("Using fallback embedding provider")
            return fallback.embed_text(text)

        raise RuntimeError("No embedding provider available")

    def generate_answer(self, prompt: str) -> GenerationResult:
        primary = self._primary()
        fallback = self._fallback()

        if primary is not None:
            try:
                return primary.generate_answer(prompt)
            except Exception as err:
                logger.warning("Primary generation provider failed", extra={"extra": {"provider": self.primary_provider, "error": str(err)[:180]}})

        if fallback is not None:
            logger.warning("Using fallback generation provider")
            return fallback.generate_answer(prompt)

        raise RuntimeError("No generation provider available")

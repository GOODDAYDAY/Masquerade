"""LLM client wrapper — unified OpenAI-compatible API interface."""

from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.core.exceptions import LLMClientError
from backend.core.logging import get_logger

logger = get_logger("agent.llm_client")

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_TIMEOUT = 60


class LLMResponse(BaseModel):
    """Parsed response from an LLM call."""

    content: str = ""
    tool_calls: list[dict] = []
    raw_response: dict = {}


class LLMClient:
    """Async LLM client supporting chat via OpenAI-compatible API."""

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key,
            timeout=timeout,
        )
        logger.info("LLMClient initialized: model=%s, api_base=%s", model, api_base)

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> str:
        """Simple chat completion, returns text content."""
        return await self._chat_with_retries(messages, temperature)

    async def _chat_with_retries(
        self, messages: list[dict], temperature: float,
    ) -> str:
        """Execute chat completion with retry logic."""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(
                    "LLM chat attempt %d/%d failed: %s", attempt, self.max_retries, e
                )
                if attempt == self.max_retries:
                    raise LLMClientError(
                        "LLM chat failed after %d retries: %s" % (self.max_retries, e)
                    ) from e

        return ""

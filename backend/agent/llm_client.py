"""LLM client wrapper — unified OpenAI-compatible API interface."""

import json

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
    """Async LLM client supporting chat and tool-calling via OpenAI-compatible API."""

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

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Chat completion with function calling / tool use."""
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=temperature,
                )
                message = response.choices[0].message

                parsed_tool_calls = []
                if message.tool_calls:
                    for tc in message.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse tool call args: %s", tc.function.arguments)
                            args = {}
                        parsed_tool_calls.append({
                            "name": tc.function.name,
                            "arguments": args,
                        })

                return LLMResponse(
                    content=message.content or "",
                    tool_calls=parsed_tool_calls,
                    raw_response={"finish_reason": response.choices[0].finish_reason},
                )

            except Exception as e:
                logger.warning(
                    "LLM tool call attempt %d/%d failed: %s", attempt, self.max_retries, e
                )
                if attempt == self.max_retries:
                    raise LLMClientError(
                        "LLM tool call failed after %d retries: %s" % (self.max_retries, e)
                    ) from e

        return LLMResponse()

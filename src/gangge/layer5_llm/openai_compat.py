"""OpenAI-compatible adapter.

Supports OpenAI, DeepSeek, Ollama — any provider that implements
the OpenAI Chat Completions API.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from gangge.layer5_llm.base import (
    BaseLLM,
    ContentBlock,
    ContentType,
    LLMResponse,
    Message,
    Role,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAICompatLLM(BaseLLM):
    """OpenAI-compatible LLM adapter (OpenAI / DeepSeek / Ollama)."""

    def __init__(self, base_url: str, api_key: str = "not-needed", **kwargs: Any):
        super().__init__(**kwargs)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    def _convert_messages(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Convert Gangge internal messages to OpenAI API format."""
        result = []
        pending_tool_calls = False  # track if last msg had tool_calls

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue

            if msg.role == Role.TOOL:
                # Each tool result block becomes a separate tool message
                for block in msg.content:
                    cid = block.tool_call_id
                    if not cid:
                        continue
                    result.append({
                        "role": "tool",
                        "tool_call_id": cid,
                        "content": block.text or "",
                    })
                pending_tool_calls = False
                continue

            if msg.role == Role.USER:
                texts = [b.text for b in msg.content if b.text]
                combined = "".join(texts) if texts else ""
                result.append({"role": "user", "content": combined})
                pending_tool_calls = False
                continue

            if msg.role == Role.ASSISTANT:
                texts = []
                tool_calls = []
                for block in msg.content:
                    if block.type in (ContentType.TEXT, ContentType.THINKING):
                        if block.text:
                            texts.append(block.text)
                    elif block.type == ContentType.TOOL_USE and block.tool_call_id:
                        tool_calls.append({
                            "id": block.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": block.tool_name,
                                "arguments": json.dumps(block.tool_input, ensure_ascii=False),
                            },
                        })
                oa_msg: dict[str, Any] = {"role": "assistant"}
                if tool_calls:
                    # When tool_calls present, omit content entirely
                    oa_msg["tool_calls"] = tool_calls
                    pending_tool_calls = True
                elif texts:
                    oa_msg["content"] = "".join(texts)
                else:
                    oa_msg["content"] = ""
                result.append(oa_msg)
                continue

        return result

    def _convert_tools(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in tools]

    def _parse_response(self, raw: Any) -> LLMResponse:
        choice = raw.choices[0]
        blocks = []
        message = choice.message

        if message.content:
            blocks.append(ContentBlock(type=ContentType.TEXT, text=message.content))

        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append(
                    ContentBlock(
                        type=ContentType.TOOL_USE,
                        tool_call_id=tc.id,
                        tool_name=tc.function.name,
                        tool_input=args,
                    )
                )

        stop_reason = choice.finish_reason or "stop"
        stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        stop_reason = stop_map.get(stop_reason, "end_turn")

        usage = {}
        if raw.usage:
            usage = {
                "input_tokens": raw.usage.prompt_tokens or 0,
                "output_tokens": raw.usage.completion_tokens or 0,
            }

        return LLMResponse(
            content=blocks,
            stop_reason=stop_reason,
            usage=usage,
            model=raw.model or self.model,
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
    ) -> LLMResponse:
        converted = self._convert_messages(messages)
        if system:
            converted.insert(0, {"role": "system", "content": system})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        raw = await self.client.chat.completions.create(**kwargs)
        return self._parse_response(raw)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str = "",
    ) -> AsyncIterator[ContentBlock]:
        converted = self._convert_messages(messages)
        if system:
            converted.insert(0, {"role": "system", "content": system})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": converted,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        current_tool_id = ""
        current_tool_name = ""
        current_tool_input = ""

        stream = await self.client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                yield ContentBlock(type=ContentType.TEXT, text=delta.content)

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id:
                        current_tool_id = tc.id
                    if tc.function and tc.function.name:
                        current_tool_name = tc.function.name
                    if tc.function and tc.function.arguments:
                        current_tool_input += tc.function.arguments

            finish = chunk.choices[0].finish_reason
            if finish == "tool_calls" and current_tool_name:
                try:
                    parsed = json.loads(current_tool_input)
                except json.JSONDecodeError:
                    parsed = {}
                yield ContentBlock(
                    type=ContentType.TOOL_USE,
                    tool_call_id=current_tool_id,
                    tool_name=current_tool_name,
                    tool_input=parsed,
                )
                current_tool_name = ""
                current_tool_input = ""

    async def close(self) -> None:
        await self.client.close()

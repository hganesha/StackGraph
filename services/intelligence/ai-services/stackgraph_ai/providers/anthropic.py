from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from stackgraph_ai.errors import ProviderResponseError
from stackgraph_ai.models import ModelMessage, ModelRequest, ModelResponse, TokenUsage, ToolCall
from stackgraph_ai.providers.base import (
    HTTPProvider,
    json_mapping,
    parse_structured_text,
    raise_for_provider_status,
)


class AnthropicAdapter(HTTPProvider):
    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com/v1",
        api_version: str = "2023-06-01",
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 45,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key must not be empty")
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _system(messages: tuple[ModelMessage, ...]) -> str | None:
        content = [
            message.content
            for message in messages
            if message.role in {"system", "developer"} and message.content
        ]
        return "\n\n".join(content) or None

    @staticmethod
    def _messages(messages: tuple[ModelMessage, ...]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        for message in messages:
            if message.role in {"system", "developer"}:
                continue
            role = "user" if message.role in {"user", "tool"} else "assistant"
            blocks: list[dict[str, Any]] = []
            if message.role == "tool":
                if not message.tool_call_id:
                    raise ValueError("Tool result messages require tool_call_id")
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content,
                    }
                )
            elif message.content:
                blocks.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": dict(call.arguments),
                    }
                )
            if not blocks:
                continue
            if translated and translated[-1]["role"] == role:
                translated[-1]["content"].extend(blocks)
            else:
                translated.append({"role": role, "content": blocks})
        return translated

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._messages(request.messages),
            "max_tokens": request.max_output_tokens,
        }
        system = self._system(request.messages)
        if system:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools and request.tool_choice != "none":
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "strict": tool.strict,
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = {
                "type": "any" if request.tool_choice == "required" else "auto"
            }
        if request.output_schema is not None:
            payload["output_config"] = {
                "format": {"type": "json_schema", "schema": request.output_schema}
            }

        response = await self._post(
            f"{self.base_url}/messages",
            headers=self._headers(),
            payload=payload,
        )
        raise_for_provider_status(self.provider_name, response)
        body = json_mapping(response.json(), provider=self.provider_name, context="response body")
        content = body.get("content")
        if not isinstance(content, list):
            raise ProviderResponseError("anthropic returned no content array")
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in content:
            if not isinstance(block, Mapping):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use":
                arguments = block.get("input")
                if not isinstance(arguments, Mapping):
                    raise ProviderResponseError("anthropic returned invalid tool input")
                tool_calls.append(
                    ToolCall(
                        id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        arguments=arguments,
                    )
                )
        text = "".join(text_parts).strip() or None
        if text is None and not tool_calls:
            raise ProviderResponseError("anthropic returned neither text nor tool calls")
        usage = body.get("usage") if isinstance(body.get("usage"), Mapping) else {}
        input_tokens = _integer(usage.get("input_tokens"))
        output_tokens = _integer(usage.get("output_tokens"))
        return ModelResponse(
            provider=self.provider_name,
            model=str(body.get("model") or request.model),
            text=text,
            structured_output=(
                parse_structured_text(text, provider=self.provider_name)
                if request.output_schema is not None and text is not None
                else None
            ),
            tool_calls=tuple(tool_calls),
            finish_reason=str(body.get("stop_reason")) if body.get("stop_reason") else None,
            provider_request_id=str(body.get("id")) if body.get("id") else None,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None
                    else None
                ),
            ),
            raw_metadata={
                "stop_sequence": body.get("stop_sequence"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            },
        )


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) else None

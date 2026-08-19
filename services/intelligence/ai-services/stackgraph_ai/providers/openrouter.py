from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from stackgraph_ai.errors import ProviderResponseError
from stackgraph_ai.models import ModelRequest, ModelResponse, TokenUsage, ToolCall
from stackgraph_ai.providers.base import (
    HTTPProvider,
    json_mapping,
    parse_structured_text,
    parse_tool_arguments,
    raise_for_provider_status,
)


class OpenRouterAdapter(HTTPProvider):
    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        site_url: str | None = None,
        site_name: str = "StackGraph",
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 45,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key must not be empty")
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.site_url = site_url
        self.site_name = site_name

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.site_name,
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        return headers

    @staticmethod
    def _messages(request: ModelRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content or None}
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, separators=(",", ":")),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(item)
        return messages

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._messages(request),
            "max_tokens": request.max_output_tokens,
            "stream": False,
            "provider": {
                "data_collection": (
                    "allow" if request.data_policy.allow_provider_data_collection else "deny"
                ),
                "zdr": request.data_policy.require_zero_data_retention,
            },
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools and request.tool_choice != "none":
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                        "strict": tool.strict,
                    },
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = request.tool_choice
        if request.output_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.output_schema_name,
                    "strict": True,
                    "schema": request.output_schema,
                },
            }
            payload["provider"]["require_parameters"] = True

        response = await self._post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            payload=payload,
        )
        raise_for_provider_status(self.provider_name, response)
        body = json_mapping(response.json(), provider=self.provider_name, context="response body")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderResponseError("openrouter returned no choices")
        choice = choices[0]
        message = json_mapping(choice.get("message"), provider=self.provider_name, context="message")
        content = message.get("content")
        text = content.strip() if isinstance(content, str) and content.strip() else None
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise ProviderResponseError("openrouter returned invalid tool_calls")
        tool_calls: list[ToolCall] = []
        for item in raw_calls:
            if not isinstance(item, Mapping):
                raise ProviderResponseError("openrouter returned an invalid tool call")
            function = json_mapping(
                item.get("function"), provider=self.provider_name, context="tool function"
            )
            tool_calls.append(
                ToolCall(
                    id=str(item.get("id") or ""),
                    name=str(function.get("name") or ""),
                    arguments=parse_tool_arguments(function.get("arguments"), provider=self.provider_name),
                )
            )
        if text is None and not tool_calls:
            raise ProviderResponseError("openrouter returned neither text nor tool calls")

        usage = body.get("usage") if isinstance(body.get("usage"), Mapping) else {}
        cost = usage.get("cost")
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
            finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") else None,
            provider_request_id=str(body.get("id")) if body.get("id") else None,
            usage=TokenUsage(
                input_tokens=_integer(usage.get("prompt_tokens")),
                output_tokens=_integer(usage.get("completion_tokens")),
                total_tokens=_integer(usage.get("total_tokens")),
                actual_cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
            ),
        )


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) else None

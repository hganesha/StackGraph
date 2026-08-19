from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from stackgraph_ai.errors import ProviderResponseError
from stackgraph_ai.models import ModelMessage, ModelRequest, ModelResponse, TokenUsage, ToolCall
from stackgraph_ai.providers.base import (
    HTTPProvider,
    json_mapping,
    parse_structured_text,
    parse_tool_arguments,
    raise_for_provider_status,
)


class OpenAIAdapter(HTTPProvider):
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        organization: str | None = None,
        project: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 45,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be empty")
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.organization = organization
        self.project = project

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project
        return headers

    @staticmethod
    def _input(messages: tuple[ModelMessage, ...]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                if not message.tool_call_id:
                    raise ValueError("Tool result messages require tool_call_id")
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
                continue
            if message.content:
                items.append({"role": message.role, "content": message.content})
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
                    }
                )
        return items

    async def complete(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": self._input(request.messages),
            "max_output_tokens": request.max_output_tokens,
            "store": request.data_policy.store_provider_response,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools and request.tool_choice != "none":
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                    "strict": tool.strict,
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = request.tool_choice
        if request.output_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.output_schema_name,
                    "schema": request.output_schema,
                    "strict": True,
                }
            }

        response = await self._post(
            f"{self.base_url}/responses",
            headers=self._headers(),
            payload=payload,
        )
        raise_for_provider_status(self.provider_name, response)
        body = json_mapping(response.json(), provider=self.provider_name, context="response body")
        output = body.get("output")
        if not isinstance(output, list):
            raise ProviderResponseError("openai returned no output array")

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for item in output:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=str(item.get("call_id") or item.get("id") or ""),
                        name=str(item.get("name") or ""),
                        arguments=parse_tool_arguments(item.get("arguments"), provider=self.provider_name),
                    )
                )
            if item.get("type") == "message":
                for content in item.get("content") or []:
                    if isinstance(content, Mapping) and content.get("type") == "output_text":
                        text_parts.append(str(content.get("text") or ""))

        text = "".join(text_parts).strip() or None
        if text is None and not tool_calls:
            raise ProviderResponseError("openai returned neither text nor tool calls")
        usage = body.get("usage") if isinstance(body.get("usage"), Mapping) else {}
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
            finish_reason=str(body.get("status")) if body.get("status") else None,
            provider_request_id=str(body.get("id")) if body.get("id") else None,
            usage=TokenUsage(
                input_tokens=_integer(usage.get("input_tokens")),
                output_tokens=_integer(usage.get("output_tokens")),
                total_tokens=_integer(usage.get("total_tokens")),
            ),
        )


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) else None

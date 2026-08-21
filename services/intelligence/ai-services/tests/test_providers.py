from __future__ import annotations

import json
import unittest

import httpx

from stackgraph_ai.errors import ProviderRequestError, ProviderResponseError
from stackgraph_ai.models import ModelMessage, ModelRequest, ToolDefinition
from stackgraph_ai.providers import AnthropicAdapter, OpenAIAdapter, OpenRouterAdapter, RetryingProvider


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def request(**overrides) -> ModelRequest:
    values = {
        "model": "test-model",
        "messages": (
            ModelMessage(role="system", content="Use evidence."),
            ModelMessage(role="user", content="Question"),
        ),
        "max_output_tokens": 500,
        "temperature": 0.1,
    }
    values.update(overrides)
    return ModelRequest(**values)


class ProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_translates_to_responses_api_and_parses_structured_output(self) -> None:
        def handler(http_request: httpx.Request) -> httpx.Response:
            payload = json.loads(http_request.content)
            self.assertEqual(http_request.url.path, "/v1/responses")
            self.assertFalse(payload["store"])
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            return httpx.Response(
                200,
                json={
                    "id": "resp_123",
                    "model": "resolved-openai-model",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": '{"answer":"yes"}'}],
                        }
                    ],
                    "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.test"
        ) as client:
            response = await OpenAIAdapter(
                "secret", base_url="https://api.openai.test/v1", client=client
            ).complete(request(output_schema=SCHEMA))

        self.assertEqual(response.structured_output, {"answer": "yes"})
        self.assertEqual(response.provider_request_id, "resp_123")
        self.assertEqual(response.usage.total_tokens, 12)

    async def test_openrouter_normalizes_tool_calls(self) -> None:
        tool = ToolDefinition(
            name="query_estate",
            description="Query deterministic estate facts",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        )

        def handler(http_request: httpx.Request) -> httpx.Response:
            payload = json.loads(http_request.content)
            self.assertEqual(http_request.url.path, "/api/v1/chat/completions")
            self.assertEqual(payload["tools"][0]["function"]["name"], "query_estate")
            self.assertEqual(payload["provider"]["data_collection"], "deny")
            self.assertTrue(payload["provider"]["zdr"])
            return httpx.Response(
                200,
                json={
                    "id": "or_123",
                    "model": "resolved-router-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {"name": "query_estate", "arguments": '{"limit":10}'},
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11, "cost": 0.001},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await OpenRouterAdapter("secret", client=client).complete(
                request(tools=(tool,), tool_choice="required")
            )

        self.assertEqual(response.tool_calls[0].name, "query_estate")
        self.assertEqual(response.tool_calls[0].arguments, {"limit": 10})
        self.assertEqual(response.usage.actual_cost_usd, 0.001)

    async def test_openrouter_accepts_one_markdown_fenced_structured_result(self) -> None:
        def handler(http_request: httpx.Request) -> httpx.Response:
            payload = json.loads(http_request.content)
            self.assertEqual(payload["response_format"]["type"], "json_schema")
            self.assertTrue(payload["provider"]["require_parameters"])
            return httpx.Response(200, json={
                "id": "or_structured",
                "model": "resolved-router-model",
                "choices": [{
                    "finish_reason": "stop",
                    "message": {
                        "content": "**Result**\n```json\n{\"answer\":\"yes\"}\n```",
                    },
                }],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await OpenRouterAdapter("secret", client=client).complete(
                request(output_schema=SCHEMA)
            )

        self.assertEqual(response.structured_output, {"answer": "yes"})

    async def test_openrouter_accepts_one_unfenced_json_payload_in_prose(self) -> None:
        def handler(_http_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "Result: {\"answer\":\"yes\"} End."},
                }],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await OpenRouterAdapter("secret", client=client).complete(
                request(output_schema=SCHEMA)
            )

        self.assertEqual(response.structured_output, {"answer": "yes"})

    async def test_openrouter_rejects_ambiguous_embedded_json_payloads(self) -> None:
        def handler(_http_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "First {\"answer\":\"yes\"}; second {\"answer\":\"no\"}."},
                }],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ProviderResponseError, "exactly one JSON payload"):
                await OpenRouterAdapter("secret", client=client).complete(
                    request(output_schema=SCHEMA)
                )

    async def test_openrouter_rejects_ambiguous_multiple_json_fences(self) -> None:
        def handler(_http_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "```json\n{\"answer\":\"yes\"}\n```\n```json\n{}\n```"},
                }],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ProviderResponseError, "exactly one JSON payload"):
                await OpenRouterAdapter("secret", client=client).complete(
                    request(output_schema=SCHEMA)
                )

    async def test_anthropic_translates_system_and_structured_output(self) -> None:
        def handler(http_request: httpx.Request) -> httpx.Response:
            payload = json.loads(http_request.content)
            self.assertEqual(http_request.url.path, "/v1/messages")
            self.assertEqual(payload["system"], "Use evidence.")
            self.assertEqual(payload["output_config"]["format"]["type"], "json_schema")
            return httpx.Response(
                200,
                json={
                    "id": "msg_123",
                    "model": "resolved-claude-model",
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": '{"answer":"yes"}'}],
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await AnthropicAdapter(
                "secret", base_url="https://api.anthropic.test/v1", client=client
            ).complete(request(output_schema=SCHEMA))

        self.assertEqual(response.structured_output, {"answer": "yes"})
        self.assertEqual(response.usage.total_tokens, 10)

    async def test_retry_decorator_retries_only_retryable_provider_errors(self) -> None:
        class Flaky:
            provider_name = "flaky"

            def __init__(self):
                self.calls = 0

            async def complete(self, model_request):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderRequestError(
                        provider="flaky",
                        code="RATE_LIMIT",
                        message="retry",
                        retryable=True,
                        status_code=429,
                    )
                return sentinel

        flaky = Flaky()
        sentinel = object()

        async def no_sleep(_):
            return None

        result = await RetryingProvider(flaky, max_attempts=2, sleep=no_sleep).complete(request())
        self.assertIs(result, sentinel)
        self.assertEqual(flaky.calls, 2)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from stackgraph_ai.catalog import CompositePromptCatalog, LocalPromptCatalog, PostgresPromptCatalog
from stackgraph_ai.errors import PromptNotFoundError, PromptRenderError
from stackgraph_ai.models import ModelResponse, ModelRoute, TokenUsage
from stackgraph_ai.registry import ModelRouteRegistry, ProviderRegistry
from stackgraph_ai.service import AIService


def prompt_record(*, version: str = "1.0.0", status: str = "ACTIVE") -> dict:
    return {
        "key": "test.prompt",
        "version": version,
        "status": status,
        "input_variables": ["question"],
        "messages": [
            {"role": "system", "content": "Answer from evidence."},
            {"role": "user", "content": "Question: ${question}"},
        ],
        "model_parameters": {"max_output_tokens": 77, "temperature": 0.1},
        "metadata": {"policy_version": "test/v1"},
    }


class FakePromptDatabase:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.calls: list[tuple] = []

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.calls.append((query, params, tenant_id))
        return self.row


class FakeProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ModelResponse(
            provider=self.provider_name,
            model=request.model,
            text="Evidence-backed answer",
            usage=TokenUsage(input_tokens=10, output_tokens=3, total_tokens=13),
        )


class FakeRecorder:
    def __init__(self) -> None:
        self.invocation_id = uuid4()
        self.events = []

    async def start(self, **kwargs):
        self.events.append(("start", kwargs))
        return self.invocation_id

    async def succeed(self, invocation_id, **kwargs):
        self.events.append(("succeed", {"invocation_id": invocation_id, **kwargs}))

    async def fail(self, invocation_id, **kwargs):
        self.events.append(("fail", {"invocation_id": invocation_id, **kwargs}))


class PromptCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_deployable_prompt_catalog_is_valid(self) -> None:
        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"

        prompts = LocalPromptCatalog(prompts_dir).definitions()

        self.assertEqual(
            {prompt.key for prompt in prompts},
            {"ask.estate", "ask.explain", "capability.inference"},
        )
        explanation = next(prompt for prompt in prompts if prompt.key == "ask.explain")
        self.assertIsNotNone(explanation.output_schema)
        self.assertEqual(
            explanation.metadata["policy_version"],
            "evidence-first-explanation/v1",
        )

    async def test_local_catalog_resolves_active_and_exact_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prompts.json").write_text(
                json.dumps(
                    [
                        prompt_record(version="1.0.0", status="RETIRED"),
                        prompt_record(version="1.1.0", status="ACTIVE"),
                    ]
                ),
                encoding="utf-8",
            )
            catalog = LocalPromptCatalog(root)

            active = await catalog.get("test.prompt")
            retired = await catalog.get("test.prompt", version="1.0.0")

            self.assertEqual(active.version, "1.1.0")
            self.assertEqual(retired.status, "RETIRED")
            self.assertTrue(active.content_hash.startswith("sha256:"))
            self.assertEqual(
                active.render({"question": "What changed?"})[1].content,
                "Question: What changed?",
            )

    async def test_render_rejects_missing_and_unexpected_variables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.json"
            path.write_text(json.dumps(prompt_record()), encoding="utf-8")
            prompt = await LocalPromptCatalog(path.parent).get("test.prompt")
            with self.assertRaises(PromptRenderError):
                prompt.render({})
            with self.assertRaises(PromptRenderError):
                prompt.render({"question": "x", "source": "y"})

    async def test_postgres_catalog_prefers_tenant_record_returned_by_database(self) -> None:
        tenant_id = UUID("00000000-0000-4000-8000-000000000101")
        row = {
            **prompt_record(),
            "prompt_key": "test.prompt",
            "tenant_id": tenant_id,
        }
        database = FakePromptDatabase(row)

        prompt = await PostgresPromptCatalog(database).get("test.prompt", tenant_id=tenant_id)

        self.assertEqual(prompt.tenant_id, tenant_id)
        self.assertEqual(database.calls[0][2], tenant_id)

    async def test_composite_falls_back_only_when_prompt_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.json"
            path.write_text(json.dumps(prompt_record()), encoding="utf-8")
            catalog = CompositePromptCatalog(
                PostgresPromptCatalog(FakePromptDatabase(None)),
                LocalPromptCatalog(path.parent),
            )
            self.assertEqual((await catalog.get("test.prompt")).version, "1.0.0")
            with self.assertRaises(PromptNotFoundError):
                await catalog.get("missing.prompt")


class AIServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_keeps_prompt_provider_and_audit_boundaries_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt.json"
            path.write_text(json.dumps(prompt_record()), encoding="utf-8")
            provider = FakeProvider()
            recorder = FakeRecorder()
            service = AIService(
                prompts=LocalPromptCatalog(path.parent),
                providers=ProviderRegistry([provider]),
                routes=ModelRouteRegistry(
                    [ModelRoute(name="default", provider="fake", model="fake-model-v1")]
                ),
                invocation_recorder=recorder,
            )

            result = await service.invoke(
                "test.prompt",
                {"question": "What changed?"},
                tenant_id=UUID("00000000-0000-4000-8000-000000000101"),
            )

            self.assertEqual(result.response.text, "Evidence-backed answer")
            self.assertEqual(result.invocation_id, recorder.invocation_id)
            self.assertTrue(result.input_fingerprint.startswith("sha256:"))
            self.assertEqual(provider.requests[0].model, "fake-model-v1")
            self.assertEqual(provider.requests[0].messages[1].content, "Question: What changed?")
            self.assertEqual([event[0] for event in recorder.events], ["start", "succeed"])


if __name__ == "__main__":
    unittest.main()

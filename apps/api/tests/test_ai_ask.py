import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai_ask import (
    AIAskOrchestrator, ESTATE_QUERY_TOOL, QUERY_KINDS, RESOLVE_ENTITIES_TOOL,
)
from app.errors import APIError
from app.models import (
    AskRequest, AskResponse, Citation, EntitySummary, SemanticSearchHit,
    SemanticSearchResponse,
)
from stackgraph_ai.errors import ProviderRequestError
from stackgraph_ai.catalog import LocalPromptCatalog
from stackgraph_ai.models import ModelResponse, ModelRoute, ToolCall
from stackgraph_ai.registry import ModelRouteRegistry, ProviderRegistry
from stackgraph_ai.service import AIService


FACT_ID = UUID("00000000-0000-4000-8000-000000000701")
TENANT_ID = UUID("00000000-0000-4000-8000-000000000101")


class StubDeterministicAsk:
    def __init__(self) -> None:
        self.requests: list[tuple[AskRequest, UUID | None]] = []

    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        self.requests.append((request, tenant_id))
        return AskResponse(
            text="Billing API depends on Node.js.",
            citations=[Citation(fact_id=FACT_ID, label="package-lock.json")],
            result_kind="TABLE",
            rows=[{"application": "Billing API", "technology": "Node.js"}],
        )


class StubAI:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict, dict]] = []

    async def invoke(self, prompt_key, variables, **kwargs):
        self.calls.append((prompt_key, dict(variables), kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(response=response)


class SequenceProvider:
    provider_name = "fake"

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = responses
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def selection(query_kind: str = "dependencies") -> object:
    return SimpleNamespace(
        tool_calls=(ToolCall(id="call-1", name="query_estate", arguments={"query_kind": query_kind}),),
        structured_output=None,
    )


def explanation(*, text: str = "Billing API uses Node.js.", fact_ids: list[str] | None = None) -> object:
    return SimpleNamespace(
        tool_calls=(),
        structured_output={
            "text": text,
            "citation_fact_ids": fact_ids if fact_ids is not None else [str(FACT_ID)],
        },
    )


def test_ai_ask_resolves_named_entity_before_deterministic_query() -> None:
    entity_id=UUID("00000000-0000-4000-8000-000000000201")

    class ResolvingAsk(StubDeterministicAsk):
        async def semantic_search(self,request,*,tenant_id):
            return SemanticSearchResponse(
                space_id=UUID("00000000-0000-4000-8000-000000000801"),
                space_key="semantic-v1",model_or_algorithm="local-v1",
                template_version="semantic-entity/v1",query_hash="sha256:"+"a"*64,
                hits=[SemanticSearchHit(
                    entity=EntitySummary(id=entity_id,kind="Application",name="Billing API"),
                    score=0.91,input_hash="sha256:"+"b"*64,sensitivity="INTERNAL",
                    matched_terms=["billing"],
                )],as_of=datetime.now(UTC),
            )

    resolution=SimpleNamespace(
        tool_calls=(ToolCall(
            id="resolve-1",name="resolve_entities",
            arguments={"text_span":"Billing API","entity_types":["Application"]},
        ),),structured_output=None,
    )
    deterministic=ResolvingAsk()
    ai=StubAI([resolution,selection(),explanation()])

    result=asyncio.run(AIAskOrchestrator(
        deterministic=deterministic,ai=ai,
    ).ask(AskRequest(question="What does Billing API use?"),tenant_id=TENANT_ID))

    assert deterministic.requests[0][0].context_entity_ids==[entity_id]
    assert result.resolved_entities[0].entity.id==entity_id
    assert result.resolved_entities[0].score==0.91
    assert ai.calls[0][0]=="ask.resolve"
    assert ai.calls[0][2]["tools"]==(RESOLVE_ENTITIES_TOOL,)


def test_ai_ask_selects_deterministic_tool_and_validates_explanation_citations() -> None:
    deterministic = StubDeterministicAsk()
    ai = StubAI([selection(), explanation()])
    orchestrator = AIAskOrchestrator(deterministic=deterministic, ai=ai, route="high-confidence")
    request = AskRequest(
        question="What does Billing API use?",
        context_entity_ids=[UUID("00000000-0000-4000-8000-000000000201")],
    )

    result = asyncio.run(orchestrator.ask(request, tenant_id=TENANT_ID))

    assert result.text == "Billing API uses Node.js."
    assert result.rows == [{"application": "Billing API", "technology": "Node.js"}]
    assert result.citations[0].fact_id == FACT_ID
    assert deterministic.requests[0][0].question.startswith("dependencies:")
    assert deterministic.requests[0][0].context_entity_ids == request.context_entity_ids
    assert deterministic.requests[0][1] == TENANT_ID
    assert [call[0] for call in ai.calls] == ["ask.estate", "ask.explain"]
    assert ai.calls[0][2]["tools"] == (ESTATE_QUERY_TOOL,)
    assert ai.calls[0][2]["tool_choice"] == "required"
    assert ai.calls[0][2]["route"] == "high-confidence"
    assert str(FACT_ID) in ai.calls[1][1]["query_result"]


@pytest.mark.parametrize(
    ("query_kind", "expected_prefix"),
    [
        ("systemic_dependency_risk", "systemic dependency risk top 20:"),
        ("reachable_vulnerabilities", "reachable vulnerabilities in code-declared production Tier-1 applications:"),
        ("duplicate_capability_implementations", "independently implemented same capability:"),
        ("modernization_blockers", "unsupported dependency modernization blockers:"),
        ("package_business_blast_radius", "package business capability blast radius:"),
        ("technology_diversity", "package category unnecessary technology diversity:"),
        ("internal_library_standards", "internal libraries enterprise standards:"),
        ("custom_to_internal_platform", "custom implementations replace with existing internal platforms:"),
        ("application_retirement_consolidation", "application retirement consolidation candidates:"),
        ("standardization_initiatives", "top 10 engineering standardization initiatives enterprise payoff:"),
    ],
)
def test_ai_ask_routes_enterprise_intelligence_queries_to_deterministic_templates(
    query_kind: str, expected_prefix: str,
) -> None:
    deterministic = StubDeterministicAsk()
    orchestrator = AIAskOrchestrator(
        deterministic=deterministic,
        ai=StubAI([selection(query_kind), explanation()]),
    )

    asyncio.run(orchestrator.ask(AskRequest(question="Enterprise question"), tenant_id=TENANT_ID))

    assert deterministic.requests[0][0].question.startswith(expected_prefix)
    assert query_kind in QUERY_KINDS
    assert query_kind in ESTATE_QUERY_TOOL.input_schema["properties"]["query_kind"]["enum"]


def test_ai_ask_integrates_real_catalog_and_provider_neutral_service() -> None:
    configured_prompts_dir = os.environ.get("STACKGRAPH_AI_PROMPTS_DIR")
    prompts_dir = (
        Path(configured_prompts_dir)
        if configured_prompts_dir
        else Path(__file__).resolve().parents[3] / "services/intelligence/ai-services/prompts"
    )
    provider = SequenceProvider([
        ModelResponse(
            provider="fake",
            model="fake-model",
            text=None,
            tool_calls=(
                ToolCall(id="call-1", name="query_estate", arguments={"query_kind": "dependencies"}),
            ),
        ),
        ModelResponse(
            provider="fake",
            model="fake-model",
            text='{"text":"Billing API uses Node.js.","citation_fact_ids":["'
            + str(FACT_ID)
            + '"]}',
            structured_output={
                "text": "Billing API uses Node.js.",
                "citation_fact_ids": [str(FACT_ID)],
            },
        ),
    ])
    ai = AIService(
        prompts=LocalPromptCatalog(prompts_dir),
        providers=ProviderRegistry([provider]),
        routes=ModelRouteRegistry([
            ModelRoute(name="default", provider="fake", model="fake-model"),
        ]),
    )

    result = asyncio.run(AIAskOrchestrator(
        deterministic=StubDeterministicAsk(), ai=ai,
    ).ask(AskRequest(question="What does Billing API use?"), tenant_id=TENANT_ID))

    assert result.text == "Billing API uses Node.js."
    assert len(provider.requests) == 2
    assert provider.requests[0].tools == (ESTATE_QUERY_TOOL,)
    assert provider.requests[0].tool_choice == "required"
    assert provider.requests[1].output_schema is not None


def test_ai_ask_rejects_citations_not_returned_by_deterministic_tool() -> None:
    deterministic = StubDeterministicAsk()
    ai = StubAI([
        selection(),
        explanation(fact_ids=["00000000-0000-4000-8000-000000000999"]),
    ])

    result = asyncio.run(AIAskOrchestrator(deterministic=deterministic, ai=ai).ask(
        AskRequest(question="What does Billing API use?"), tenant_id=TENANT_ID,
    ))

    assert result.text == "Billing API depends on Node.js."
    assert len(deterministic.requests) == 1


def test_ai_ask_falls_back_to_original_request_when_provider_is_unavailable() -> None:
    deterministic = StubDeterministicAsk()
    provider_error = ProviderRequestError(
        provider="openrouter",
        code="PROVIDER_UNAVAILABLE",
        message="unavailable",
        retryable=True,
        status_code=503,
    )
    request = AskRequest(question="What does Billing API use?")

    result = asyncio.run(AIAskOrchestrator(
        deterministic=deterministic, ai=StubAI([provider_error]),
    ).ask(request, tenant_id=TENANT_ID))

    assert result.text == "Billing API depends on Node.js."
    assert deterministic.requests == [(request, TENANT_ID)]


def test_ai_ask_can_fail_closed_when_fallback_is_disabled() -> None:
    deterministic = StubDeterministicAsk()
    provider_error = ProviderRequestError(
        provider="openai", code="TIMEOUT", message="timeout", retryable=True,
    )

    with pytest.raises(APIError) as raised:
        asyncio.run(AIAskOrchestrator(
            deterministic=deterministic,
            ai=StubAI([provider_error]),
            fallback_enabled=False,
        ).ask(AskRequest(question="What changed?"), tenant_id=TENANT_ID))

    assert raised.value.status_code == 503
    assert raised.value.code == "AI_ASK_UNAVAILABLE"
    assert deterministic.requests == []


def test_ai_ask_context_limit_prevents_sending_oversized_tool_results() -> None:
    deterministic = StubDeterministicAsk()
    ai = StubAI([selection()])

    result = asyncio.run(AIAskOrchestrator(
        deterministic=deterministic,
        ai=ai,
        max_evidence_chars=10,
    ).ask(AskRequest(question="What does Billing API use?"), tenant_id=TENANT_ID))

    assert result.text == "Billing API depends on Node.js."
    assert [call[0] for call in ai.calls] == ["ask.estate"]

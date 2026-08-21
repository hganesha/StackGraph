from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from psycopg import Error as PsycopgError

from app.errors import APIError
from app.models import AskRequest, AskResponse, Citation
from stackgraph_ai.errors import AIServiceError
from stackgraph_ai.models import PromptInvocation, ToolDefinition


logger = logging.getLogger(__name__)

QUERY_KINDS = (
    "estate_summary",
    "dependencies",
    "indirect_dependents",
    "unsupported_runtimes",
    "viability",
    "modernization",
    "systemic_dependency_risk",
    "reachable_vulnerabilities",
    "duplicate_capability_implementations",
    "modernization_blockers",
    "package_business_blast_radius",
    "technology_diversity",
    "internal_library_standards",
    "custom_to_internal_platform",
    "application_retirement_consolidation",
    "standardization_initiatives",
)

ESTATE_QUERY_TOOL = ToolDefinition(
    name="query_estate",
    description=(
        "Select one deterministic StackGraph estate query. The server executes the query; "
        "the model cannot provide SQL, entity IDs, or estate facts."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query_kind": {
                "type": "string",
                "enum": list(QUERY_KINDS),
                "description": "The allowlisted deterministic query that best answers the question.",
            },
        },
        "required": ["query_kind"],
        "additionalProperties": False,
    },
)


class DeterministicAskService(Protocol):
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...


class AIInvoker(Protocol):
    async def invoke(
        self,
        prompt_key: str,
        variables: Mapping[str, Any],
        *,
        route: str = "default",
        tenant_id: UUID | None = None,
        tools: tuple[ToolDefinition, ...] = (),
        tool_choice: str = "auto",
        metadata: Mapping[str, Any] | None = None,
    ) -> PromptInvocation: ...


@dataclass(slots=True)
class TenantConfiguredAIAskService:
    """Resolve a tenant's encrypted provider configuration at request time."""

    database: Any
    deterministic: DeterministicAskService
    encryption_key: str
    environment_fallback: DeterministicAskService | None = None
    fallback_enabled: bool = True
    max_evidence_chars: int = 50_000

    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        if tenant_id is None:
            return await self._fallback(request, tenant_id=tenant_id)
        try:
            row = await self.database.fetch_one(
                """
                SELECT c.provider,c.model,c.enabled,
                  pgp_sym_decrypt(s.ciphertext,%s)::text AS api_key
                FROM tenant_ai_configuration c
                LEFT JOIN tenant_secret s ON s.id=c.credential_secret_id
                """,
                (self.encryption_key,), tenant_id=tenant_id,
            )
        except PsycopgError:
            logger.warning("Tenant AI configuration unavailable; using Ask fallback")
            return await self._fallback(request, tenant_id=tenant_id)
        if not row or not row["enabled"] or not row["model"] or not row["api_key"]:
            return await self._fallback(request, tenant_id=tenant_id)

        from stackgraph_ai import AISettings, build_ai_service

        ai = build_ai_service(
            AISettings.for_provider(row["provider"], row["model"], row["api_key"]),
            database=self.database,
        )
        return await AIAskOrchestrator(
            deterministic=self.deterministic,
            ai=ai,
            route="default",
            fallback_enabled=self.fallback_enabled,
            max_evidence_chars=self.max_evidence_chars,
        ).ask(request, tenant_id=tenant_id)

    async def _fallback(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        service = self.environment_fallback or self.deterministic
        return await service.ask(request, tenant_id=tenant_id)


@dataclass(slots=True)
class AIAskOrchestrator:
    """Lets a model select and explain allowlisted deterministic estate queries."""

    deterministic: DeterministicAskService
    ai: AIInvoker
    route: str = "default"
    fallback_enabled: bool = True
    max_evidence_chars: int = 50_000

    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        deterministic_result: AskResponse | None = None
        try:
            selection = await self.ai.invoke(
                "ask.estate",
                {
                    "question": request.question,
                    "context": {
                        "entity_ids": [str(entity_id) for entity_id in (request.context_entity_ids or [])],
                    },
                },
                route=self.route,
                tenant_id=tenant_id,
                tools=(ESTATE_QUERY_TOOL,),
                tool_choice="required",
                metadata={"workload": "api.ask.selection"},
            )
            query_kind = self._selected_query_kind(selection)
            deterministic_result = await self.deterministic.ask(
                self._tool_request(query_kind, request),
                tenant_id=tenant_id,
            )
            if deterministic_result.result_kind == "UNSUPPORTED":
                return deterministic_result

            evidence_json = self._evidence_json(deterministic_result)
            explanation = await self.ai.invoke(
                "ask.explain",
                {"question": request.question, "query_result": evidence_json},
                route=self.route,
                tenant_id=tenant_id,
                metadata={"workload": "api.ask.explanation", "query_kind": query_kind},
            )
            return self._explained_response(deterministic_result, explanation)
        except (AIServiceError, PsycopgError, ValueError, TypeError) as error:
            logger.warning(
                "AI Ask used deterministic fallback",
                extra={"ai_error_type": type(error).__name__, "tenant_scoped": tenant_id is not None},
            )
            if not self.fallback_enabled:
                raise APIError(
                    503,
                    "AI_ASK_UNAVAILABLE",
                    "The evidence explanation service is temporarily unavailable.",
                ) from error
            if deterministic_result is not None:
                return deterministic_result
            return await self.deterministic.ask(request, tenant_id=tenant_id)

    @staticmethod
    def _selected_query_kind(invocation: PromptInvocation) -> str:
        calls = invocation.response.tool_calls
        if len(calls) != 1 or calls[0].name != ESTATE_QUERY_TOOL.name:
            raise ValueError("AI Ask must select exactly one allowlisted estate tool")
        arguments = dict(calls[0].arguments)
        if set(arguments) != {"query_kind"} or arguments["query_kind"] not in QUERY_KINDS:
            raise ValueError("AI Ask selected an invalid deterministic query")
        return str(arguments["query_kind"])

    @staticmethod
    def _tool_request(query_kind: str, request: AskRequest) -> AskRequest:
        prefixes = {
            "estate_summary": "estate summary how many",
            "dependencies": "dependencies",
            "indirect_dependents": "indirect dependencies",
            "unsupported_runtimes": "unsupported runtime",
            "viability": "why viability score",
            "modernization": "modernization recommendations",
            "systemic_dependency_risk": "systemic dependency risk top 20",
            "reachable_vulnerabilities": "reachable vulnerabilities in code-declared production Tier-1 applications",
            "duplicate_capability_implementations": "independently implemented same capability",
            "modernization_blockers": "unsupported dependency modernization blockers",
            "package_business_blast_radius": "package business capability blast radius",
            "technology_diversity": "package category unnecessary technology diversity",
            "internal_library_standards": "internal libraries enterprise standards",
            "custom_to_internal_platform": "custom implementations replace with existing internal platforms",
            "application_retirement_consolidation": "application retirement consolidation candidates",
            "standardization_initiatives": "top 10 engineering standardization initiatives enterprise payoff",
        }
        return AskRequest(
            question=f"{prefixes[query_kind]}: {request.question}",
            context_entity_ids=request.context_entity_ids,
        )

    def _evidence_json(self, result: AskResponse) -> str:
        payload = {
            "result_kind": result.result_kind,
            "deterministic_summary": result.text,
            "rows": result.rows or [],
            "citations": [
                {"fact_id": str(citation.fact_id), "label": citation.label}
                for citation in result.citations
            ],
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(serialized) > self.max_evidence_chars:
            raise ValueError("Deterministic Ask evidence exceeds the configured AI context limit")
        return serialized

    @staticmethod
    def _explained_response(result: AskResponse, invocation: PromptInvocation) -> AskResponse:
        output = invocation.response.structured_output
        if not isinstance(output, Mapping):
            raise ValueError("AI Ask explanation did not return a structured object")
        text = output.get("text")
        raw_ids = output.get("citation_fact_ids")
        if not isinstance(text, str) or not text.strip() or not isinstance(raw_ids, list):
            raise ValueError("AI Ask explanation has an invalid response shape")

        citations_by_id = {str(citation.fact_id): citation for citation in result.citations}
        selected: list[Citation] = []
        seen: set[str] = set()
        for raw_id in raw_ids:
            fact_id = str(raw_id)
            citation = citations_by_id.get(fact_id)
            if citation is None:
                raise ValueError("AI Ask explanation referenced evidence outside the tool result")
            if fact_id not in seen:
                selected.append(citation)
                seen.add(fact_id)
        if citations_by_id and not selected:
            raise ValueError("AI Ask explanation omitted citations for an evidence-backed result")

        return AskResponse(
            text=text.strip(),
            citations=selected,
            result_kind=result.result_kind,
            rows=result.rows,
            graph_highlight=result.graph_highlight,
        )

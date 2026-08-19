from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from stackgraph_ai.models import ModelResponse, ModelRoute, PromptDefinition


class InvocationConnection(Protocol):
    async def execute(self, query: str, params: tuple[Any, ...]) -> Any: ...


class InvocationDatabase(Protocol):
    def session(
        self, tenant_id: UUID | None = None
    ) -> AbstractAsyncContextManager[InvocationConnection]: ...


class InvocationRecorder(Protocol):
    async def start(
        self,
        *,
        tenant_id: UUID | None,
        prompt: PromptDefinition,
        route: ModelRoute,
        input_fingerprint: str,
        policy_version: str | None,
    ) -> UUID: ...

    async def succeed(
        self,
        invocation_id: UUID,
        *,
        tenant_id: UUID | None,
        response: ModelResponse,
        duration_ms: int,
    ) -> None: ...

    async def fail(
        self,
        invocation_id: UUID,
        *,
        tenant_id: UUID | None,
        error_code: str,
        retryable: bool | None,
        duration_ms: int,
    ) -> None: ...


@dataclass(slots=True)
class PostgresInvocationRecorder:
    """Writes operational AI audit records without prompt or source content."""

    database: InvocationDatabase

    async def start(
        self,
        *,
        tenant_id: UUID | None,
        prompt: PromptDefinition,
        route: ModelRoute,
        input_fingerprint: str,
        policy_version: str | None,
    ) -> UUID:
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO ai_model_invocation(
                  tenant_id,prompt_template_id,prompt_key,prompt_version,prompt_content_hash,
                  input_fingerprint,provider,requested_model,policy_version,status,metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s::jsonb)
                RETURNING id
                """,
                (
                    tenant_id,
                    prompt.catalog_id,
                    prompt.key,
                    prompt.version,
                    prompt.content_hash,
                    input_fingerprint,
                    route.provider,
                    route.model,
                    policy_version,
                    json.dumps({"route": route.name}, separators=(",", ":")),
                ),
            )
            row = await cursor.fetchone()
        if not row:
            raise RuntimeError("AI invocation insert returned no ID")
        return row["id"] if isinstance(row, Mapping) else row[0]

    async def succeed(
        self,
        invocation_id: UUID,
        *,
        tenant_id: UUID | None,
        response: ModelResponse,
        duration_ms: int,
    ) -> None:
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                UPDATE ai_model_invocation SET
                  status='SUCCEEDED',resolved_model=%s,provider_request_id=%s,
                  finish_reason=%s,input_tokens=%s,output_tokens=%s,total_tokens=%s,
                  actual_cost_usd=%s,duration_ms=%s,completed_at=now()
                WHERE id=%s
                """,
                (
                    response.model,
                    response.provider_request_id,
                    response.finish_reason,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.usage.total_tokens,
                    response.usage.actual_cost_usd,
                    duration_ms,
                    invocation_id,
                ),
            )

    async def fail(
        self,
        invocation_id: UUID,
        *,
        tenant_id: UUID | None,
        error_code: str,
        retryable: bool | None,
        duration_ms: int,
    ) -> None:
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                UPDATE ai_model_invocation SET
                  status='FAILED',error_code=%s,error_detail=%s::jsonb,duration_ms=%s,completed_at=now()
                WHERE id=%s
                """,
                (
                    error_code,
                    json.dumps({"retryable": retryable}, separators=(",", ":")),
                    duration_ms,
                    invocation_id,
                ),
            )

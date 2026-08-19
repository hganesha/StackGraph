from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from stackgraph_ai.errors import PromptCatalogError, PromptNotFoundError
from stackgraph_ai.models import PromptDefinition


class PromptCatalog(Protocol):
    async def get(
        self,
        prompt_key: str,
        *,
        version: str | None = None,
        tenant_id: UUID | None = None,
    ) -> PromptDefinition: ...


class PromptDatabase(Protocol):
    async def fetch_one(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
        *,
        tenant_id: UUID | None = None,
    ) -> Mapping[str, Any] | None: ...


class LocalPromptCatalog:
    """Versioned JSON prompt catalog for local development and safe fallback."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _load(self) -> dict[tuple[str, str], PromptDefinition]:
        if not self.root.exists():
            raise PromptCatalogError(f"Local prompt catalog does not exist: {self.root}")

        prompts: dict[tuple[str, str], PromptDefinition] = {}
        for path in sorted(self.root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise PromptCatalogError(f"Could not load prompt file {path}: {error}") from error

            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                if not isinstance(record, dict):
                    raise PromptCatalogError(f"Prompt file {path} must contain an object or object array")
                prompt = PromptDefinition.from_record(record)
                identity = (prompt.key, prompt.version)
                if identity in prompts:
                    raise PromptCatalogError(
                        f"Duplicate local prompt {prompt.key!r} version {prompt.version!r}"
                    )
                prompts[identity] = prompt
        active_by_key: dict[str, list[str]] = {}
        for prompt in prompts.values():
            if prompt.status == "ACTIVE":
                active_by_key.setdefault(prompt.key, []).append(prompt.version)
        collisions = {
            key: versions for key, versions in active_by_key.items() if len(versions) > 1
        }
        if collisions:
            details = "; ".join(
                f"{key}: {', '.join(sorted(versions))}"
                for key, versions in sorted(collisions.items())
            )
            raise PromptCatalogError(f"Local catalog has multiple ACTIVE prompt versions: {details}")
        return prompts

    def definitions(self) -> tuple[PromptDefinition, ...]:
        return tuple(
            prompt for _, prompt in sorted(self._load().items(), key=lambda item: item[0])
        )

    async def get(
        self,
        prompt_key: str,
        *,
        version: str | None = None,
        tenant_id: UUID | None = None,
    ) -> PromptDefinition:
        del tenant_id  # local prompt files are global and contain no tenant data
        prompts = self._load()
        if version is not None:
            prompt = prompts.get((prompt_key, version))
            if prompt is None:
                raise PromptNotFoundError(prompt_key, version)
            return prompt

        active = [
            prompt
            for (key, _), prompt in prompts.items()
            if key == prompt_key and prompt.status == "ACTIVE"
        ]
        if not active:
            raise PromptNotFoundError(prompt_key)
        if len(active) > 1:
            versions = ", ".join(sorted(prompt.version for prompt in active))
            raise PromptCatalogError(
                f"Local prompt {prompt_key!r} has multiple ACTIVE versions: {versions}"
            )
        return active[0]


class PostgresPromptCatalog:
    """Reads tenant overrides and global prompts from PostgreSQL.

    Tenant-specific records take precedence over global records. The database
    session still enforces RLS, so callers must pass the same tenant ID to the
    catalog and the database session.
    """

    def __init__(self, database: PromptDatabase) -> None:
        self.database = database

    async def get(
        self,
        prompt_key: str,
        *,
        version: str | None = None,
        tenant_id: UUID | None = None,
    ) -> PromptDefinition:
        row = await self.database.fetch_one(
            """
            SELECT id,tenant_id,prompt_key,version,status,messages,input_variables,
                   output_schema,model_parameters,metadata,content_hash
            FROM ai_prompt_template
            WHERE prompt_key=%s
              AND (tenant_id IS NULL OR tenant_id=%s)
              AND ((%s::text IS NULL AND status='ACTIVE') OR version=%s)
            ORDER BY (tenant_id IS NOT NULL) DESC,created_at DESC
            LIMIT 1
            """,
            (prompt_key, tenant_id, version, version),
            tenant_id=tenant_id,
        )
        if row is None:
            raise PromptNotFoundError(prompt_key, version)
        return PromptDefinition.from_record(row)


class CompositePromptCatalog:
    """Resolves prompts from catalogs in priority order.

    The typical production order is PostgreSQL followed by the local catalog,
    allowing controlled tenant/global overrides while retaining a deployable
    baseline when the database has no matching record.
    """

    def __init__(self, *catalogs: PromptCatalog) -> None:
        if not catalogs:
            raise ValueError("CompositePromptCatalog requires at least one catalog")
        self.catalogs = catalogs

    async def get(
        self,
        prompt_key: str,
        *,
        version: str | None = None,
        tenant_id: UUID | None = None,
    ) -> PromptDefinition:
        for catalog in self.catalogs:
            try:
                return await catalog.get(prompt_key, version=version, tenant_id=tenant_id)
            except PromptNotFoundError:
                continue
        raise PromptNotFoundError(prompt_key, version)

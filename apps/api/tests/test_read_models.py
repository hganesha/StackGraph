import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest

from app.errors import APIError
from app.read_models import (
    ReadModelStore,
    _confidence_label,
    _decode_cursor,
    _encode_cursor,
    _group_application_technologies,
    _technology_catalog_profiles,
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=UTC)


class EstateDatabaseStub:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        if "evidence_ratio" in query:
            return {"repositories_total": 2, "repositories_scanned": 2, "evidence_ratio": 1}
        return {"applications": 2, "repositories": 2, "services": 0, "technologies": 1}

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        if "GROUP BY 1 ORDER BY 1" in query or "WITH matched AS" in query:
            return []
        if "FROM entity e" in query and "priority_score" in query:
            return [
                {
                    "id": UUID("00000000-0000-4000-8000-000000000201"),
                    "namespace": "ENTERPRISE",
                    "entity_type": "Application",
                    "name": "Billing API",
                    "properties": {},
                    "observed_at": NOW,
                    "priority_score": Decimal("81"),
                    "priority_confidence": Decimal("0.91"),
                    "priority_method": "priority-v1",
                    "viability_score": None,
                },
                {
                    "id": UUID("00000000-0000-4000-8000-000000000220"),
                    "namespace": "ENTERPRISE",
                    "entity_type": "Application",
                    "name": "Catalog API",
                    "properties": {},
                    "observed_at": NOW,
                    "priority_score": Decimal("70"),
                    "priority_confidence": Decimal("0.75"),
                    "priority_method": "priority-v1",
                    "viability_score": None,
                },
            ]
        raise AssertionError(f"unexpected query: {query}")


class GitHubRepositoryDatabaseStub:
    async def fetch_all(self, query, params=None, *, tenant_id=None):
        assert "target.target_kind='REPOSITORY'" in query
        return [{"repository_name": "acme/already-connected"}]


class AIConfigurationDatabaseStub:
    def __init__(self, model: str = "anthropic/claude-sonnet-5") -> None:
        self.model = model
        self.updates: list[tuple[str, object]] = []

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "pgp_sym_decrypt" in query:
            return {"provider": "openrouter", "model": self.model, "api_key": "secret-key"}
        if "UPDATE tenant_ai_configuration" in query:
            self.updates.append((query, params))
            return {"tenant_id": tenant_id}
        raise AssertionError(f"unexpected query: {query}")


class ServiceStatusDatabaseStub:
    def __init__(self) -> None:
        self.workload_query = ""
        self.workload_params: tuple[UUID, ...] = ()

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        if "FROM service_heartbeat" in query:
            return [{
                "service_key": "intelligence",
                "status": "RUNNING",
                "last_heartbeat_at": datetime.now(UTC),
            }]
        if "FROM tenant_service_control" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.workload_query = query
        self.workload_params = params
        return {"intelligence_failed": 5}


class RepositoryDetailDatabaseStub:
    def __init__(self) -> None:
        self.fetch_one_calls = 0

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.fetch_one_calls += 1
        if "FROM entity" in query:
            return {
                "id": UUID("00000000-0000-4000-8000-000000000401"),
                "namespace": "ENTERPRISE", "entity_type": "Repository",
                "canonical_key": "github:repo:billing", "name": "billing-api",
                "properties": {}, "observed_at": NOW,
            }
        if "repository_profile" in query:
            return {
                "id": UUID("00000000-0000-4000-8000-000000000402"),
                "object_value": {
                    "purpose": "Creates invoices and coordinates payment collection.",
                    "purpose_source": {"kind": "README", "path": "README.md"},
                    "descriptions": ["Creates invoices and coordinates payment collection."],
                    "languages": ["Python"], "components": ["Repository root"],
                    "key_files": ["README.md", "pyproject.toml"],
                    "operational_signals": ["Container build"],
                    "limitations": ["documentation may be stale"],
                },
                "confidence": Decimal("0.95"), "source_revision": "revision-1",
                "observed_at": NOW, "source_key": "github-enterprise",
            }
        raise AssertionError(f"unexpected query: {query}")

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        assert "FROM current_relationship" in query
        return [{
            "id": UUID("00000000-0000-4000-8000-000000000403"),
            "namespace": "ENTERPRISE", "entity_type": "Application",
            "canonical_key": "application:billing", "name": "Billing",
            "properties": {}, "relationship_type": "IMPLEMENTED_BY", "observed_at": NOW,
        }]


def test_confidence_labels_use_frozen_contract_boundaries() -> None:
    assert _confidence_label(0.8499) == "MEDIUM"
    assert _confidence_label(0.85) == "HIGH"
    assert _confidence_label(0.5999) == "LOW"
    assert _confidence_label(0.60) == "MEDIUM"


def test_repository_detail_surfaces_cited_revision_pinned_profile() -> None:
    repository_id = UUID("00000000-0000-4000-8000-000000000401")
    detail = asyncio.run(ReadModelStore(RepositoryDetailDatabaseStub()).repository_detail(
        repository_id, tenant_id=UUID("00000000-0000-4000-8000-000000000499"),
    ))

    assert detail.repository.summary == "Creates invoices and coordinates payment collection."
    assert detail.profile is not None
    assert detail.profile.purpose_source == "README.md"
    assert detail.profile.languages == ["Python"]
    assert detail.profile.source_revision == "revision-1"
    assert detail.profile.confidence_label == "HIGH"
    assert detail.profile.citations[0].fact_id == UUID("00000000-0000-4000-8000-000000000402")
    assert [application.name for application in detail.applications] == ["Billing"]


def test_application_technologies_group_by_catalog_domain_and_capability() -> None:
    usage_fact = UUID("00000000-0000-4000-8000-000000000301")
    classification_fact = UUID("00000000-0000-4000-8000-000000000302")
    catalog_fact = UUID("00000000-0000-4000-8000-000000000304")
    react_package_id = UUID("00000000-0000-4000-8000-000000000204")
    unknown_package_id = UUID("00000000-0000-4000-8000-000000000205")
    react_catalog_id = UUID("00000000-0000-4000-8000-000000000206")
    technology_rows = [
        {
            "id": react_package_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "PackageVersion",
            "canonical_key": "pkg:npm/react@19.1.1",
            "name": "react 19.1.1",
            "properties": {"catalog_metadata": {"description": "Interactive UI components."}},
            "usage_fact_ids": [usage_fact],
            "usage_confidence": Decimal("1.0"),
        },
        {
            "id": unknown_package_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "PackageVersion",
            "canonical_key": "pkg:npm/unknown-package@1.0.0",
            "name": "unknown-package 1.0.0",
            "properties": {},
            "usage_fact_ids": [UUID("00000000-0000-4000-8000-000000000303")],
            "usage_confidence": Decimal("0.9"),
        },
    ]
    catalog_rows = [{
        "id": react_catalog_id,
        "namespace": "TECHNOLOGY",
        "entity_type": "Technology",
        "canonical_key": "stackgraph:technology:react",
        "name": "React",
        "properties": {
            "domain_id": "frontend",
            "domain_name": "Frontend",
            "category_id": "ui-rendering-reactivity",
            "category_name": "UI rendering & reactivity",
            "catalog_lookup_keys": ["react"],
        },
        "capability_id": UUID("00000000-0000-4000-8000-000000000207"),
        "capability_key": "ui-rendering",
        "capability_name": "UI rendering",
        "capability_summary": "Turn application state into interactive UI.",
        "catalog_fact_id": catalog_fact,
        "classification_fact_id": classification_fact,
        "classification_confidence": Decimal("0.95"),
    }]

    groups = _group_application_technologies(technology_rows, catalog_rows)

    assert [group.domain.key for group in groups] == ["frontend", "unclassified"]
    frontend = groups[0].functions[0]
    assert frontend.function.key == "ui-rendering"
    assert frontend.technologies[0].classification == "CATALOG_MATCH"
    assert frontend.technologies[0].confidence == pytest.approx(0.85)
    assert frontend.technologies[0].technology.summary == "Interactive UI components."
    assert {citation.fact_id for citation in frontend.technologies[0].citations} == {
        usage_fact,
        classification_fact,
        catalog_fact,
    }
    unknown = groups[1].functions[0].technologies[0]
    assert unknown.classification == "UNCLASSIFIED"
    assert unknown.confidence == 0
    assert unknown.category is None


def test_technology_catalog_profile_combines_oss_metadata_and_curated_classification() -> None:
    package_id = UUID("00000000-0000-4000-8000-000000000211")
    catalog_id = UUID("00000000-0000-4000-8000-000000000212")
    metadata_fact_id = UUID("00000000-0000-4000-8000-000000000213")
    classification_fact_id = UUID("00000000-0000-4000-8000-000000000214")
    profiles = _technology_catalog_profiles(
        [{
            "id": package_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "PackageVersion",
            "canonical_key": "pkg:npm/%40biomejs/biome@2.5.8",
            "name": "@biomejs/biome@2.5.8",
            "properties": {"package_name": "@biomejs/biome"},
        }],
        [{
            "id": catalog_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "Technology",
            "canonical_key": "stackgraph:technology:biome-eslint-oxlint-prettier",
            "name": "Biome / ESLint / Oxlint / Prettier",
            "properties": {
                "purpose": "Linting and formatting.",
                "domain_id": "frontend",
                "category_id": "build-tooling",
            },
            "catalog_fact_id": classification_fact_id,
            "capability_id": None,
        }],
        [{
            "selected_technology_id": package_id,
            "catalog_properties": {"catalog_metadata": {
                "description": "Biome is a web toolchain.",
                "package_name": "@biomejs/biome",
                "ecosystem": "npm",
                "license": "MIT OR Apache-2.0",
                "weekly_downloads": 836700,
            }},
            "catalog_fact_id": metadata_fact_id,
        }],
    )

    profile = profiles[package_id]
    assert profile.summary == "Biome is a web toolchain."
    assert profile.domain and profile.domain.key == "frontend"
    assert profile.category and profile.category.key == "build-tooling"
    assert profile.functions == []
    assert profile.classification == "CATALOG_MATCH"
    assert profile.weekly_downloads == 836700
    assert {citation.fact_id for citation in profile.citations} == {
        metadata_fact_id, classification_fact_id,
    }


def test_application_dependency_hierarchy_uses_declared_roots_and_breaks_cycles() -> None:
    repository_id = UUID("00000000-0000-4000-8000-000000000401")
    root_id = UUID("00000000-0000-4000-8000-000000000402")
    child_id = UUID("00000000-0000-4000-8000-000000000403")
    root_fact_id = UUID("00000000-0000-4000-8000-000000000404")
    child_fact_id = UUID("00000000-0000-4000-8000-000000000405")

    class DependencyDatabaseStub:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_all(self, query, params=None, *, tenant_id=None):
            self.calls += 1
            if "WITH repositories AS" in query:
                return [
                    {
                        "repository_id": repository_id,
                        "id": root_id,
                        "namespace": "TECHNOLOGY",
                        "entity_type": "PackageVersion",
                        "canonical_key": "pkg:npm/root@1.0.0",
                        "name": "root@1.0.0",
                        "properties": {},
                        "relationship_type": "DEPENDS_ON",
                        "fact_assertion_id": root_fact_id,
                        "confidence": Decimal("0.99"),
                        "dependency_properties": {
                            "direct": True,
                            "component_path": "apps/web",
                            "scope": "runtime",
                            "requested_spec": "^1.0.0",
                        },
                    },
                    {
                        "repository_id": repository_id,
                        "id": child_id,
                        "namespace": "TECHNOLOGY",
                        "entity_type": "PackageVersion",
                        "canonical_key": "pkg:npm/child@2.0.0",
                        "name": "child@2.0.0",
                        "properties": {},
                        "relationship_type": "DEPENDS_ON",
                        "fact_assertion_id": child_fact_id,
                        "confidence": Decimal("0.98"),
                        "dependency_properties": {"direct": False},
                    },
                ]
            assert "FROM fact_assertion relationship" in query
            return [
                {
                    "source_id": root_id,
                    "target_id": child_id,
                    "relationship_type": "DEPENDS_ON",
                    "fact_assertion_id": child_fact_id,
                    "confidence": Decimal("0.97"),
                    "dependency_properties": {
                        "dependency_relation": "DIRECT",
                        "requirement": ">=2",
                    },
                },
                {
                    "source_id": child_id,
                    "target_id": root_id,
                    "relationship_type": "DEPENDS_ON",
                    "fact_assertion_id": root_fact_id,
                    "confidence": Decimal("0.96"),
                    "dependency_properties": {},
                },
            ]

    repository = {
        "id": repository_id,
        "namespace": "ENTERPRISE",
        "entity_type": "Repository",
        "canonical_key": "github:acme/web",
        "name": "acme/web",
        "properties": {},
    }
    database = DependencyDatabaseStub()

    result = asyncio.run(ReadModelStore(database)._application_dependency_hierarchies(
        [repository],
        UUID("00000000-0000-4000-8000-000000000001"),
    ))

    assert database.calls == 2
    assert len(result) == 1
    component = result[0].components[0]
    assert component.component_path == "apps/web"
    assert component.truncated is False
    assert [node.technology.id for node in component.dependencies] == [root_id, child_id]
    assert component.dependencies[0].direct is True
    assert component.dependencies[0].scope == "runtime"
    assert component.dependencies[1].parent_technology_id == root_id
    assert component.dependencies[1].depth == 2
    assert component.dependencies[1].requirement == ">=2"
    assert component.dependencies[1].citations[0].fact_id == child_fact_id


def test_technology_estate_hierarchy_links_transitive_nodes_to_applications() -> None:
    root_id = UUID("00000000-0000-4000-8000-000000000501")
    child_id = UUID("00000000-0000-4000-8000-000000000502")
    app_id = UUID("00000000-0000-4000-8000-000000000503")
    root_fact_id = UUID("00000000-0000-4000-8000-000000000504")
    child_fact_id = UUID("00000000-0000-4000-8000-000000000505")

    class TechnologyHierarchyDatabaseStub:
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            if "SELECT repository.id repository_id" in query:
                return [
                    {
                        "repository_id": UUID("00000000-0000-4000-8000-000000000506"),
                        "id": root_id,
                        "namespace": "TECHNOLOGY",
                        "entity_type": "PackageVersion",
                        "canonical_key": "pkg:npm/root@1.0.0",
                        "name": "root@1.0.0",
                        "properties": {},
                        "relationship_type": "DEPENDS_ON",
                        "fact_assertion_id": root_fact_id,
                        "confidence": Decimal("0.99"),
                        "dependency_properties": {"direct": True},
                    },
                    {
                        "repository_id": UUID("00000000-0000-4000-8000-000000000506"),
                        "id": child_id,
                        "namespace": "TECHNOLOGY",
                        "entity_type": "PackageVersion",
                        "canonical_key": "pkg:npm/child@2.0.0",
                        "name": "child@2.0.0",
                        "properties": {},
                        "relationship_type": "DEPENDS_ON",
                        "fact_assertion_id": child_fact_id,
                        "confidence": Decimal("0.98"),
                        "dependency_properties": {"direct": False},
                    },
                ]
            if "SELECT DISTINCT ON (dependency.subject_entity_id" in query:
                return [{
                    "source_id": root_id,
                    "target_id": child_id,
                    "relationship_type": "DEPENDS_ON",
                    "fact_assertion_id": child_fact_id,
                    "confidence": Decimal("0.97"),
                    "dependency_properties": {},
                }]
            if "WHERE technology.namespace='TECHNOLOGY'" in query:
                return []
            if "WITH selected AS" in query:
                return []
            assert "WITH application_repositories AS" in query
            return [{
                "technology_id": child_id,
                "id": app_id,
                "namespace": "ENTERPRISE",
                "entity_type": "Application",
                "canonical_key": "application:checkout",
                "name": "Checkout",
                "properties": {},
            }]

    hierarchy = asyncio.run(ReadModelStore(
        TechnologyHierarchyDatabaseStub()
    ).technology_estate_hierarchy(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    ))

    assert [node.technology.id for node in hierarchy.nodes] == [root_id, child_id]
    assert hierarchy.nodes[0].direct is True
    assert hierarchy.nodes[1].parent_technology_id == root_id
    assert hierarchy.nodes[1].depth == 2
    assert [app.id for app in hierarchy.nodes[1].dependent_applications] == [app_id]
    assert hierarchy.nodes[1].citations[0].fact_id == child_fact_id


def test_cursor_is_typed_and_rejects_cross_endpoint_reuse() -> None:
    cursor = _encode_cursor(
        "estate", score="81", name="Billing API",
        id="00000000-0000-4000-8000-000000000201",
    )

    assert _decode_cursor(cursor, "estate")["score"] == "81"
    with pytest.raises(APIError) as raised:
        _decode_cursor(cursor, "modernization")
    assert raised.value.code == "INVALID_CURSOR"


def test_available_github_repositories_filter_connected_estate_repositories() -> None:
    def github(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer runtime-only-token"
        assert request.url.params["affiliation"] == "owner,collaborator,organization_member"
        return httpx.Response(200, json=[
            {
                "full_name": "acme/already-connected", "visibility": "private",
                "archived": False, "default_branch": "main",
            },
            {
                "full_name": "Acme/New-Service", "visibility": "private",
                "archived": False, "default_branch": "trunk",
            },
            {
                "full_name": "acme/archived-tool", "private": False,
                "archived": True, "default_branch": "main",
            },
        ])

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(github),
        base_url="https://api.github.test",
        headers={"Authorization": "Bearer runtime-only-token"},
    )
    with patch.dict(os.environ, {
        "GITHUB_TOKEN": "runtime-only-token",
        "STACKGRAPH_GITHUB_API_URL": "https://api.github.test",
    }), patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        result = asyncio.run(ReadModelStore(GitHubRepositoryDatabaseStub()).list_available_github_repositories(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        ))

    assert result.token_configured is True
    assert result.truncated is False
    assert [repository.full_name for repository in result.repositories] == [
        "acme/archived-tool", "Acme/New-Service",
    ]
    assert result.repositories[0].visibility == "public"
    assert result.repositories[0].archived is True


def test_available_github_repositories_report_unconfigured_token_without_database_access() -> None:
    class UnexpectedDatabase:
        async def fetch_all(self, *args, **kwargs):
            raise AssertionError("database should not be queried without a token")

    with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
        result = asyncio.run(ReadModelStore(UnexpectedDatabase()).list_available_github_repositories(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        ))

    assert result.token_configured is False
    assert result.repositories == []


def test_available_github_repositories_sanitize_rejected_token_errors() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            401, json={"message": "Bad credentials: runtime-only-token"},
        )),
        headers={"Authorization": "Bearer runtime-only-token"},
    )
    with patch.dict(os.environ, {
        "GITHUB_TOKEN": "runtime-only-token",
        "STACKGRAPH_GITHUB_API_URL": "https://api.github.test",
    }), patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        with pytest.raises(APIError) as raised:
            asyncio.run(ReadModelStore(GitHubRepositoryDatabaseStub()).list_available_github_repositories(
                tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
            ))

    assert raised.value.code == "GITHUB_TOKEN_REJECTED"
    assert "runtime-only-token" not in raised.value.message


def test_openrouter_connection_test_authenticates_and_checks_zdr_model_compatibility() -> None:
    paths: list[str] = []

    def openrouter(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer secret-key"
        if request.url.path == "/api/v1/auth/key":
            return httpx.Response(200, json={"data": {"label": "StackGraph"}})
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"data": [{"id": "anthropic/claude-sonnet-5"}]})
        if request.url.path == "/api/v1/endpoints/zdr":
            return httpx.Response(200, json={"data": [{
                "model_id": "anthropic/claude-sonnet-5",
                "supported_parameters": ["max_tokens", "response_format"],
            }]})
        if request.url.path == "/api/v1/chat/completions":
            body = json.loads(request.content)
            assert body["response_format"]["type"] == "json_schema"
            assert body["response_format"]["json_schema"]["strict"] is True
            return httpx.Response(200, json={
                "model": "anthropic/claude-sonnet-5",
                "choices": [{
                    "message": {"content": "```json\n{\"answer\":\"ok\"}\n```"},
                    "finish_reason": "stop",
                }],
            })
        raise AssertionError(f"unexpected request: {request.url}")

    database = AIConfigurationDatabaseStub()
    client = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    with patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        result = asyncio.run(ReadModelStore(database).test_ai_provider_connection(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
            actor_key="operator",
        ))

    assert paths == [
        "/api/v1/auth/key", "/api/v1/models", "/api/v1/endpoints/zdr",
        "/api/v1/chat/completions",
    ]
    assert result.models == ["anthropic/claude-sonnet-5"]
    assert database.updates[-1][1][0] == "SUCCEEDED"


def test_openrouter_connection_test_rejects_public_catalog_false_positive() -> None:
    def openrouter(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/key":
            return httpx.Response(401, json={"error": {"message": "invalid key"}})
        raise AssertionError("model discovery must not run after authentication fails")

    database = AIConfigurationDatabaseStub()
    client = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    with patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        with pytest.raises(APIError) as raised:
            asyncio.run(ReadModelStore(database).test_ai_provider_connection(
                tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
                actor_key="operator",
            ))

    assert raised.value.code == "AI_CONNECTION_FAILED"
    assert database.updates[-1][1][0] == "FAILED"


def test_openrouter_connection_test_rejects_incompatible_zdr_route() -> None:
    def openrouter(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/key":
            return httpx.Response(200, json={"data": {}})
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"data": [{"id": "anthropic/claude-sonnet-5"}]})
        if request.url.path == "/api/v1/endpoints/zdr":
            return httpx.Response(200, json={"data": [{
                "model_id": "anthropic/claude-sonnet-5",
                "supported_parameters": ["max_tokens"],
            }]})
        raise AssertionError(f"unexpected request: {request.url}")

    database = AIConfigurationDatabaseStub()
    client = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    with patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        with pytest.raises(APIError) as raised:
            asyncio.run(ReadModelStore(database).test_ai_provider_connection(
                tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
                actor_key="operator",
            ))

    assert raised.value.code == "AI_MODEL_INCOMPATIBLE"
    assert database.updates[-1][1][0] == "FAILED"


def test_openrouter_connection_test_rejects_invalid_structured_completion() -> None:
    def openrouter(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/key":
            return httpx.Response(200, json={"data": {}})
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"data": [{"id": "anthropic/claude-sonnet-5"}]})
        if request.url.path == "/api/v1/endpoints/zdr":
            return httpx.Response(200, json={"data": [{
                "model_id": "anthropic/claude-sonnet-5",
                "supported_parameters": ["max_tokens", "response_format"],
            }]})
        if request.url.path == "/api/v1/chat/completions":
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "The answer is ok."}}],
            })
        raise AssertionError(f"unexpected request: {request.url}")

    database = AIConfigurationDatabaseStub()
    client = httpx.AsyncClient(transport=httpx.MockTransport(openrouter))
    with patch("app.read_models_admin.httpx.AsyncClient", return_value=client):
        with pytest.raises(APIError) as raised:
            asyncio.run(ReadModelStore(database).test_ai_provider_connection(
                tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
                actor_key="operator",
            ))

    assert raised.value.code == "AI_STRUCTURED_OUTPUT_FAILED"
    assert database.updates[-1][1][0] == "FAILED"


def test_service_status_scopes_intelligence_workload_to_active_configuration() -> None:
    database = ServiceStatusDatabaseStub()
    result = asyncio.run(ReadModelStore(database).service_status(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    ))

    intelligence = next(service for service in result.services if service.key == "intelligence")
    assert intelligence.failed == 5
    assert intelligence.state == "DEGRADED"
    assert "WITH intelligence_scope AS" in database.workload_query
    assert database.workload_query.count(
        "configuration_fingerprint=scope.fingerprint"
    ) == 4
    assert len(database.workload_params) == 25


def test_estate_pagination_uses_constant_query_count_and_keyset_cursor() -> None:
    database = EstateDatabaseStub()
    result = asyncio.run(ReadModelStore(database).estate_summary(
        tenant_id=None, cursor=None, limit=1,
    ))

    assert result.page_info is not None
    assert result.page_info.has_next_page
    assert result.page_info.next_cursor is not None
    cursor = _decode_cursor(result.page_info.next_cursor, "estate")
    assert cursor == {
        "v": 1,
        "kind": "estate",
        "score": "81",
        "name": "Billing API",
        "id": "00000000-0000-4000-8000-000000000201",
    }
    assert len(database.queries) == 5
    assert all("OFFSET" not in query.upper() for query in database.queries)
    estate_queries = "\n".join(database.queries[:4])
    assert "observed_technology" in estate_queries
    assert "relationship.tenant_id=(SELECT tenant_id FROM tenant_scope)" in estate_queries
    assert "estate_entity.tenant_id=(SELECT tenant_id FROM tenant_scope)" in estate_queries
    assert "e.tenant_id=(SELECT tenant_id FROM tenant_scope)" in estate_queries

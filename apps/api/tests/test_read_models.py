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
from app.models import AskResponse, SemanticSearchRequest
from app.read_models import (
    ReadModelStore,
    _confidence_label,
    _decode_cursor,
    _encode_cursor,
    _group_application_technologies,
    _resolve_technology_catalog_entry,
    _technology_catalog_index,
    _technology_catalog_profiles,
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=UTC)


def test_semantic_search_withholds_restricted_excerpt_but_keeps_provenance() -> None:
    tenant_id=UUID("00000000-0000-4000-8000-000000000001")
    entity_id=UUID("00000000-0000-4000-8000-000000000201")
    fact_id=UUID("00000000-0000-4000-8000-000000000701")

    class SemanticDatabase:
        async def fetch_one(self,query,params=None,*,tenant_id=None):
            return {
                "id":UUID("00000000-0000-4000-8000-000000000801"),
                "space_key":"semantic-v1","provider":"LOCAL",
                "model_or_algorithm":"stackgraph-hash-embedding-v1","dimensions":8,
                "normalization":"L2","template_version":"semantic-entity/v1",
                "external_processing_allowed":False,"sensitive_content_allowed":False,
                "provider_base_url":None,"api_key":None,
            }

        async def fetch_all(self,query,params=None,*,tenant_id=None):
            assert "document.rendered_content" in query
            assert params[-2]==0.2
            return [{
                "id":entity_id,"entity_type":"Application","name":"Billing API",
                "canonical_key":"application:billing","summary":"Payments",
                "input_hash":"sha256:"+"a"*64,"sensitivity":"RESTRICTED",
                "rendered_content":"Billing API processes payment records.",
                "source_fact_ids":[fact_id],"score":0.91,
            }]

    result=asyncio.run(ReadModelStore(SemanticDatabase()).semantic_search(
        SemanticSearchRequest(
            query="billing payments",namespace=["ENTERPRISE"],min_score=0.2,limit=5,
        ),tenant_id=tenant_id,
    ))

    assert result.hits[0].matched_terms==["billing"]
    assert result.hits[0].excerpt is None
    assert result.hits[0].source_fact_ids==[fact_id]
    assert result.hits[0].limitations[0]["code"]=="RESTRICTED_EXCERPT_WITHHELD"


def test_graph_risk_applications_group_governed_application_context() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    repository_id = UUID("00000000-0000-4000-8000-000000000401")
    application_id = UUID("00000000-0000-4000-8000-000000000201")

    class GraphRiskApplicationDatabase:
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            assert "WITH requested AS" in query
            assert "ordinal<=5" in query
            assert params[0] == [repository_id]
            assert all(value == tenant_id for value in params[1:])
            return [{
                "entity_id": repository_id,
                "id": application_id,
                "entity_type": "Application",
                "name": "Billing API",
                "canonical_key": "application:billing-api",
                "summary": "Collects and reconciles payments.",
            }]

    result = asyncio.run(ReadModelStore(
        GraphRiskApplicationDatabase()
    )._graph_risk_applications([repository_id],tenant_id))

    assert result[repository_id][0].id == application_id
    assert result[repository_id][0].name == "Billing API"


def test_structural_clone_candidates_feed_enterprise_library_standards() -> None:
    fact_id = UUID("00000000-0000-4000-8000-0000000007d1")

    class LibraryCandidateDatabase:
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            if "FROM modernization_internal_component component" in query:
                return []
            if "WITH repeated AS" in query:
                assert "current_capability_application_relationship" in query
                return [{
                    "structural_fingerprint": "sha256:" + "a" * 64,
                    "name": "shared_retry_policy",
                    "repositories": 4,
                    "capabilities": 3,
                    "critical_repositories": 2,
                    "fact_ids": [fact_id],
                }]
            if "LEFT JOIN evidence" in query:
                return []
            raise AssertionError(f"unexpected query: {query}")

    result = asyncio.run(ReadModelStore(
        LibraryCandidateDatabase()
    )._ask_internal_library_standards(tenant_id=None))

    assert result.rows[0]["internal_library"] == "shared_retry_policy"
    assert result.rows[0]["capability"] == "3 mapped business capabilities"
    assert result.rows[0]["governance_status"] == "CANDIDATE"
    assert result.rows[0]["standardization_score"] == 90
    assert "remain governance candidates" in result.text


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
        if "FROM active_graph_analysis_run active" in query:
            return []
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
                    "sort_value": Decimal("81"),
                },
                {
                    "id": UUID("00000000-0000-4000-8000-000000000220"),
                    "namespace": "TECHNOLOGY",
                    "entity_type": "PackageVersion",
                    "name": "transitive-library@2.0.0",
                    "properties": {},
                    "observed_at": NOW,
                    "priority_score": Decimal("70"),
                    "priority_confidence": Decimal("0.75"),
                    "priority_method": "priority-v1",
                    "viability_score": None,
                    "dependency_tier": 2,
                    "sort_value": Decimal("70"),
                },
            ]
        raise AssertionError(f"unexpected query: {query}")


class GitHubRepositoryDatabaseStub:
    async def fetch_one(self, query, params=None, *, tenant_id=None):
        assert "secret_kind='GITHUB_TOKEN'" in query
        return None

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
        self.control_rows: list[dict] = []

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        if "FROM service_heartbeat" in query:
            return [
                {
                    "service_key": "intelligence",
                    "status": "RUNNING",
                    "last_heartbeat_at": datetime.now(UTC),
                },
                {
                    "service_key": "mcp",
                    "status": "RUNNING",
                    "last_heartbeat_at": datetime.now(UTC),
                },
            ]
        if "FROM tenant_service_control" in query:
            return self.control_rows
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
        if "FROM active_graph_analysis_run active" in query:
            return []
        assert "FROM current_relationship" in query
        return [{
            "id": UUID("00000000-0000-4000-8000-000000000403"),
            "namespace": "ENTERPRISE", "entity_type": "Application",
            "canonical_key": "application:billing", "name": "Billing",
            "properties": {}, "relationship_type": "IMPLEMENTED_BY", "observed_at": NOW,
        }]


class RepositoryActivityDatabaseStub:
    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "FROM entity" in query:
            return {
                "id": UUID("00000000-0000-4000-8000-000000000401"),
                "namespace": "ENTERPRISE", "entity_type": "Repository",
                "canonical_key": "github:repo:billing", "name": "billing-api",
                "properties": {}, "observed_at": NOW,
            }
        if "FROM ingest_target" in query:
            return {
                "refresh_policy": {
                    "full_name": "acme/billing-api", "default_branch": "main",
                    "visibility": "private", "archived": False,
                },
                "source_key": "github-app",
            }
        if "FROM repository_activity_collection" in query:
            return {
                "commits_status": "PARTIAL",
                "pull_requests_status": "PERMISSION_REQUIRED",
                "collected_at": NOW,
                "limitations": [
                    "Commit activity exceeded the bounded 1000-event collection limit.",
                    "Merged pull-request activity requires the GitHub pull_requests:read permission.",
                ],
            }
        if "count(*) FILTER" in query:
            return {
                "commit_count": 1000, "pull_request_merged_count": 0,
                "contributor_count": 1, "last_change_at": NOW,
            }
        raise AssertionError(f"unexpected fetch_one query: {query}")

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        actor = {
            "actor_key": "github:user:42", "actor_login": "dana-okafor",
            "actor_avatar_url": "https://avatars.githubusercontent.com/u/42",
            "actor_is_bot": False,
        }
        if "GROUP BY actor_key" in query:
            return [{
                **actor, "commits": 12, "pull_requests_merged": 0, "total_events": 12,
            }]
        if "FROM repository_activity_event" in query:
            return [{
                "id": UUID("00000000-0000-4000-8000-000000000411"),
                "event_type": "COMMIT", "title": "Tighten invoice retry handling",
                "occurred_at": NOW, **actor, "revision": "abcdef123456",
                "branch": "main", "pull_request_number": None,
                "source_url": "https://github.com/acme/billing-api/commit/abcdef123456",
            }]
        raise AssertionError(f"unexpected fetch_all query: {query}")


def test_confidence_labels_use_frozen_contract_boundaries() -> None:
    assert _confidence_label(0.8499) == "MEDIUM"
    assert _confidence_label(0.85) == "HIGH"
    assert _confidence_label(0.5999) == "LOW"
    assert _confidence_label(0.60) == "MEDIUM"


def test_enterprise_insight_reports_materialize_deterministic_cards_without_ai() -> None:
    async def deterministic_ask(self, request, *, tenant_id=None):
        if "top 20 dependencies" in request.question:
            rows = [{"dependency": "shared-core", "risk_score": 87}]
        elif "10 engineering standardization" in request.question:
            rows = [{"initiative": "Standardize HTTP clients", "enterprise_payoff": 72.5}]
        else:
            rows = []
        return AskResponse(
            text=f"Deterministic result for {request.question}",
            citations=[], result_kind="TABLE", rows=rows,
        )

    store = ReadModelStore(EstateDatabaseStub())
    with patch.object(ReadModelStore, "ask", deterministic_ask):
        result = asyncio.run(store.enterprise_insight_reports(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        ))

    reports = {report.key: report for report in result.reports}
    assert result.total_reports == 14
    assert result.answerable_reports == 4
    assert result.reports[0].metric_value == "87"
    assert result.reports[0].status == "ACTION_REQUIRED"
    assert reports["standardization_initiatives"].metric_value == "72.50"
    assert reports["standardization_initiatives"].response.rows == [
        {"initiative": "Standardize HTTP clients", "enterprise_payoff": 72.5},
    ]
    # The posture reports register alongside the existing catalogue and stay
    # answerable-by-evidence: an estate stub with no posture state waits for data.
    assert [reports[key].status for key in (
        "assurance_coverage", "technology_introduction",
        "business_dark_capability", "decision_lag",
    )] == ["WAITING_FOR_DATA"] * 4


def test_modernization_blockers_include_runtime_baseline_evidence() -> None:
    class RuntimeBaselineDatabaseStub:
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            assert "policy_baseline" in query
            assert "ContainerImage" in query
            return [{
                "technology_id": UUID("00000000-0000-4000-8000-000000000299"),
                "technology": "python:3.10-slim", "technology_kind": "ContainerImage",
                "support_state": "UNSUPPORTED",
                "rationale": "Code-declared runtime 3.10 is below tenant baseline 3.12.",
                "repositories": 2, "repository_names": "Billing, Ledger", "fact_ids": [],
            }]

    result = asyncio.run(ReadModelStore(RuntimeBaselineDatabaseStub())._ask_modernization_blockers(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    ))

    assert result.result_kind == "TABLE"
    assert result.rows == [{
        "technology": "python:3.10-slim", "kind": "ContainerImage", "ecosystem": "PYTHON",
        "support_state": "UNSUPPORTED", "repositories": 2,
        "repository_names": "Billing, Ledger",
        "rationale": "Code-declared runtime 3.10 is below tenant baseline 3.12.",
    }]


def test_top_package_blast_radius_selects_mapped_package_without_hardcoded_name() -> None:
    class PackageImpactDatabaseStub:
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            assert "selected_package" in query
            assert "current_capability_application_relationship" in query
            return [{
                "package": "shared-core", "capability_id": UUID(
                    "00000000-0000-4000-8000-000000000410"
                ),
                "capability": "Enterprise Architecture", "criticality": 3,
                "repositories": 2, "applications": 2,
                "repository_names": "Billing, Ledger",
                "application_names": "Billing, Ledger", "fact_ids": [],
            }]

    result = asyncio.run(
        ReadModelStore(PackageImpactDatabaseStub())._ask_top_package_business_blast_radius(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        )
    )

    assert result.result_kind == "TABLE"
    assert result.text.startswith("shared-core has the largest governed package blast radius")
    assert result.rows == [{
        "package": "shared-core", "business_capability": "Enterprise Architecture",
        "criticality": 3, "repositories": 2, "applications": 2,
        "repository_names": "Billing, Ledger", "application_names": "Billing, Ledger",
    }]


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


def test_repository_activity_preserves_bounded_counts_and_permission_coverage() -> None:
    result = asyncio.run(ReadModelStore(RepositoryActivityDatabaseStub()).repository_activity(
        UUID("00000000-0000-4000-8000-000000000401"),
        tenant_id=UUID("00000000-0000-4000-8000-000000000499"),
        window="30d", cursor=None, limit=6,
    ))

    assert result.source.full_name == "acme/billing-api"
    assert result.source.default_branch == "main"
    assert result.summary.commits == 1000
    assert result.summary.pull_requests_merged is None
    assert result.summary.contributors == 1
    assert result.coverage.commits == "PARTIAL"
    assert result.coverage.pull_requests == "PERMISSION_REQUIRED"
    assert result.coverage.contributors == "PARTIAL"
    assert result.top_contributors[0].actor.login == "dana-okafor"
    assert result.events[0].revision == "abcdef123456"
    assert result.page_info.has_next_page is False


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


def test_application_data_resources_use_deterministic_infrastructure_groups() -> None:
    usage_fact = UUID("00000000-0000-4000-8000-000000000309")
    redis_id = UUID("00000000-0000-4000-8000-000000000310")
    groups = _group_application_technologies([{
        "id": redis_id,
        "namespace": "TECHNOLOGY",
        "entity_type": "Database",
        "canonical_key": "stackgraph:database:redis-valkey",
        "name": "Redis / Valkey",
        "properties": {},
        "usage_fact_ids": [usage_fact],
        "usage_confidence": Decimal("0.96"),
        "usage_assertion_classes": ["DECLARED", "INFERRED"],
        "usage_property_sets": [{
            "resource_kind": "DATABASE",
            "engine": "redis",
            "inference_method": "CORRELATED_REPOSITORY_EVIDENCE",
            "signal_kinds": ["DEPENDENCY_DECLARATION", "SOURCE_REFERENCE"],
            "package_dependencies": ["npm:ioredis"],
            "config_keys": ["REDIS_URL"],
            "source_referenced": True,
            "limitations": ["runtime connectivity requires deployment corroboration"],
        }],
    }], [])

    assert [group.domain.key for group in groups] == ["data"]
    assert groups[0].domain.name == "Data infrastructure"
    cache_group = groups[0].functions[0]
    assert cache_group.function.key == "caches"
    assert cache_group.function.name == "Caches"
    usage = cache_group.technologies[0]
    assert usage.classification == "DETERMINISTIC"
    assert usage.confidence == pytest.approx(0.96)
    assert usage.category and usage.category.name == "Caches"
    assert usage.resource_details is not None
    assert usage.resource_details.resource_kind == "CACHE"
    assert usage.resource_details.engine == "redis"
    assert usage.resource_details.assertion_class == "DECLARED"
    assert usage.resource_details.signal_kinds == [
        "DEPENDENCY_DECLARATION", "SOURCE_REFERENCE",
    ]
    assert usage.resource_details.config_keys == ["REDIS_URL"]
    assert usage.resource_details.source_referenced is True
    assert usage.citations[0].fact_id == usage_fact


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


def test_catalog_resolution_supports_package_families_and_prefers_exact_aliases() -> None:
    family_id = UUID("00000000-0000-4000-8000-000000000220")
    specific_id = UUID("00000000-0000-4000-8000-000000000221")
    package_id = UUID("00000000-0000-4000-8000-000000000222")
    other_family_id = UUID("00000000-0000-4000-8000-000000000223")
    catalog_rows = [
        {
            "id": family_id,
            "entity_type": "Technology",
            "name": "Babel helpers",
            "properties": {"catalog_lookup_keys": ["@babel/helper-*"]},
        },
        {
            "id": specific_id,
            "entity_type": "Technology",
            "name": "Babel compilation targets",
            "properties": {"catalog_lookup_keys": ["@babel/helper-compilation-targets"]},
        },
        {
            "id": other_family_id,
            "entity_type": "Technology",
            "name": "typescript-eslint",
            "properties": {
                "catalog_lookup_keys": ["@typescript-eslint/*"],
                "aliases": ["@typescript-eslint/*"],
            },
        },
    ]
    catalog_by_id, catalog_by_key = _technology_catalog_index(catalog_rows)

    specific, direct = _resolve_technology_catalog_entry(
        {
            "id": package_id,
            "entity_type": "PackageVersion",
            "name": "@babel/helper-compilation-targets",
            "properties": {"package_name": "@babel/helper-compilation-targets"},
        },
        catalog_by_id,
        catalog_by_key,
    )
    assert specific and specific["row"]["id"] == specific_id
    assert direct is False

    family, direct = _resolve_technology_catalog_entry(
        {
            "id": package_id,
            "entity_type": "PackageVersion",
            "name": "@babel/helper-module-imports",
            "properties": {"package_name": "@babel/helper-module-imports"},
        },
        catalog_by_id,
        catalog_by_key,
    )
    assert family and family["row"]["id"] == family_id
    assert direct is False


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


def test_available_github_repositories_report_unconfigured_token() -> None:
    class UnconfiguredDatabase:
        async def fetch_one(self, *args, **kwargs):
            return None

        async def fetch_all(self, *args, **kwargs):
            raise AssertionError("connected repositories should not be queried without a token")

    with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
        result = asyncio.run(ReadModelStore(UnconfiguredDatabase()).list_available_github_repositories(
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
    assert len(database.workload_params) == 33
    graph_intelligence = next(
        service for service in result.services if service.key == "graph-intelligence"
    )
    assert graph_intelligence.category == "GRAPH"
    assert graph_intelligence.pending == 0
    embeddings = next(service for service in result.services if service.key == "embeddings")
    assert embeddings.category == "INTELLIGENCE"


def test_service_status_reports_controllable_mcp_endpoint() -> None:
    database = ServiceStatusDatabaseStub()
    result = asyncio.run(ReadModelStore(database).service_status(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    ))

    mcp = next(service for service in result.services if service.key == "mcp")
    assert mcp.category == "CORE"
    assert mcp.controllable is True
    assert mcp.management_scope == "This workspace"
    assert mcp.state == "IDLE"
    assert "MCP endpoint is online" in mcp.detail


def test_service_status_shows_mcp_stopped_when_workspace_stopped_it() -> None:
    database = ServiceStatusDatabaseStub()
    database.control_rows = [{"service_key": "mcp", "desired_state": "STOPPED"}]
    result = asyncio.run(ReadModelStore(database).service_status(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
    ))

    mcp = next(service for service in result.services if service.key == "mcp")
    assert mcp.state == "STOPPED"
    assert mcp.desired_state == "STOPPED"


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
        "sort": "priority",
        "value": "81",
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
    assert "dependency_tier" in estate_queries
    assert "e.namespace='BUSINESS' AND e.entity_type='BusinessCapability'" in estate_queries
    assert "FROM current_capability_application_relationship mapping" in estate_queries
    assert "mapping.capability_entity_id=e.id" in estate_queries
    assert "e.entity_type IN ('Application','Service')" in estate_queries
    assert "FROM current_relationship active_service" in estate_queries
    assert "active_service.source_entity_id=e.id OR active_service.target_entity_id=e.id" in estate_queries
    assert "relationship.relationship_type IN ('CONTAINS','IMPLEMENTED_BY')" in estate_queries


def test_estate_summary_exposes_transitive_technology_tier() -> None:
    result = asyncio.run(ReadModelStore(EstateDatabaseStub()).estate_summary(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        cursor=None,
        limit=2,
    ))

    technology = next(item for item in result.ranked_items if item.domain == "TECHNOLOGY")
    assert technology.dependency_tier == 2


def test_modernization_portfolio_reads_phase3_recommendations_and_shared_footprint() -> None:
    recommendation_id = UUID("00000000-0000-4000-8000-000000000951")
    repository_id = UUID("00000000-0000-4000-8000-000000000952")
    fact_id = UUID("00000000-0000-4000-8000-000000000953")

    class PortfolioDatabaseStub:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def fetch_one(self, query, params=None, *, tenant_id=None):
            self.queries.append(query)
            assert "modernization_portfolio_policy" in query
            return None

        async def fetch_all(self, query, params=None, *, tenant_id=None):
            self.queries.append(query)
            assert "FROM modernization_recommendation recommendation" in query
            assert "LEFT JOIN capability_footprint footprint" in query
            assert "FROM recommendation r" not in query
            return [{
                "id": recommendation_id,
                "title": "Consolidate HTTP clients",
                "rationale": "One approved implementation reduces duplicate maintenance.",
                "action": "CONSOLIDATE",
                "recommendation_confidence": Decimal("0.90"),
                "supporting_fact_ids": [fact_id],
                "created_at": NOW,
                "updated_at": NOW,
                "candidate_confidence": Decimal("0.92"),
                "capability_definition_id": UUID("00000000-0000-4000-8000-000000000954"),
                "repository_entity_id": repository_id,
                "repository_name": "Billing API",
                "repository_key": "github:repo:billing",
                "effort_points": 8,
                "selected_option_score": Decimal("0.80"),
                "application_count": 5,
                "repository_count": 8,
                "technology_counts": {"node": 4, "python": 4},
            }]

    database = PortfolioDatabaseStub()
    result = asyncio.run(ReadModelStore(database).modernization(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        cursor=None,
        limit=10,
    ))

    assert [item.id for item in result.opportunities] == [recommendation_id]
    assert result.opportunities[0].priority.method_version == "modernization-portfolio/v1-unconfigured"
    assert result.opportunities[0].citations[0].fact_id == fact_id

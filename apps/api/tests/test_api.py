import asyncio
from datetime import UTC, datetime
import time
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.auth import create_session_token
from app.database import DatabaseReadiness
from app.errors import APIError
from app.main import create_app
from app.models import (
    AIProviderConfiguration,
    AIProviderConnectionTest,
    AskRequest,
    AskResponse,
    CapabilityDefinitionModel,
    CapabilityInferenceReviewRequest,
    CapabilityInferenceReviewResult,
    CapabilityTaxonomyResponse,
    Coverage,
    DuplicateCapabilityReviewRequest,
    DuplicateCapabilityReviewResult,
    EntitySummary,
    EstateCounts,
    EstateSummary,
    Freshness,
    IdentityReviewRequest,
    IdentityReviewResult,
    PageInfo,
    ModernizationCandidateReviewRequest,
    ModernizationCandidateReviewResult,
    ModernizationRecommendationReviewRequest,
    ModernizationRecommendationReviewResult,
    ModernizationValidationOutcomeRequest,
    ModernizationValidationOutcomeResult,
    Phase3IntelligenceMetrics,
    RepositoryModernizationIntelligence,
    BusinessMapDetail,
    BusinessMapList,
    BusinessMapStateModel,
    ReviewQueue,
    ReviewQueueItem,
    TenantMember,
    TenantMemberList,
    Connector,
    ConnectorList,
    ScanPolicy,
    ScanStatus,
    ServiceStatus,
    ServiceStatusList,
    RescanJob,
    RescanJobList,
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=UTC)


class StubDatabase:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def check_readiness(self) -> DatabaseReadiness:
        return DatabaseReadiness(connected=True, age_installed=True, schema_installed=True)


class MetricsStubDatabase(StubDatabase):
    async def fetch_one(self, query, params=None, *, tenant_id=None):
        return {
            "ingest_queue_age_seconds": 0,
            "expired_ingest_leases": 0,
            "unreplayed_dead_letters": 0,
            "projection_queue_age_seconds": 0,
            "intelligence_queue_age_seconds": 0,
            "failed_intelligence_jobs": 0,
            "webhook_processing_age_seconds": 0,
            "failed_webhooks": 0,
            "stale_or_error_sources": 0,
            "failed_ai_invocations_24h": 0,
            "throttled_or_exhausted_quotas": 0,
            "active_ingest_runs": 0,
            "pending_projection_events": 0,
            "active_intelligence_jobs": 0,
            "ai_cost_usd_24h": 0,
            "ai_latency_ms_24h": 0,
        }


class StubReadModels:
    def __init__(self) -> None:
        self.last_tenant_id = None
        self.last_actor_key = None
        self.last_estate_namespaces = None

    async def estate_summary(self, *, tenant_id, cursor, limit, namespaces=None):
        self.last_tenant_id = tenant_id
        self.last_estate_namespaces = namespaces
        return EstateSummary(
            as_of=NOW,
            counts=EstateCounts(applications=0, repositories=0, services=0, technologies=0),
            distributions={}, ranked_items=[],
            coverage=Coverage(repositories_total=0, repositories_scanned=0, facts_with_evidence_ratio=0),
            page_info=PageInfo(has_next_page=False),
        )

    async def ask(self, request: AskRequest, *, tenant_id):
        return AskResponse(text=request.question, citations=[], result_kind="UNSUPPORTED")

    def _business_map_detail(self) -> BusinessMapDetail:
        return BusinessMapDetail(
            id=UUID("00000000-0000-4000-8000-000000000901"), map_key="enterprise.value-chain",
            status="ACTIVE", version=1, created_at=NOW, updated_at=NOW,
            state=BusinessMapStateModel(title="Map", view_mode="value-chain", template_id="porter"),
        )

    async def list_business_maps(self, *, tenant_id, cursor, limit):
        self.last_tenant_id = tenant_id
        return BusinessMapList(as_of=NOW, maps=[], page_info=PageInfo(has_next_page=False))

    async def create_business_map(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return self._business_map_detail()

    async def application_detail(self, application_id, *, tenant_id):
        raise APIError(404, "ENTITY_NOT_FOUND", "The requested entity was not found.")

    async def technology_detail(self, technology_id, *, tenant_id):
        raise APIError(404, "ENTITY_NOT_FOUND", "The requested entity was not found.")

    async def modernization(self, *, tenant_id, cursor, limit):
        raise NotImplementedError

    async def graph_neighborhood(
        self, center_id, *, tenant_id, depth, real_node_limit, predicates,
        namespaces, min_confidence, highlight_to,
    ):
        raise NotImplementedError

    async def evidence_detail(self, fact_id, *, tenant_id):
        raise NotImplementedError

    async def review_identity_assertion(
        self, assertion_id, review: IdentityReviewRequest, *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return IdentityReviewResult(
            identity_assertion_id=assertion_id,
            review_state="CONFIRMED" if review.decision == "CONFIRM" else "REJECTED",
            version=review.expected_version + 1,
            reviewed_at=NOW,
        )

    async def capability_taxonomy(self, *, tenant_id, version):
        self.last_tenant_id = tenant_id
        return CapabilityTaxonomyResponse(
            key="stackgraph.technical-capabilities",
            version=version or "1.0.0",
            name="Technical Capabilities",
            description="Versioned technical capabilities.",
            content_hash="sha256:" + "a" * 64,
            capabilities=[CapabilityDefinitionModel(
                key="http-client", name="HTTP Client",
                description="Issue outbound HTTP requests.",
            )],
        )

    async def repository_capabilities(self, repository_id, *, tenant_id):
        raise NotImplementedError

    async def review_capability_inference(
        self, inference_id, review: CapabilityInferenceReviewRequest, *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return CapabilityInferenceReviewResult(
            capability_inference_id=inference_id,
            review_state="CONFIRMED" if review.decision == "CONFIRM" else "REJECTED",
            version=review.expected_version + 1,
            reviewed_at=NOW,
        )

    async def review_duplicate_capability_candidate(
        self, candidate_id, review: DuplicateCapabilityReviewRequest, *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return DuplicateCapabilityReviewResult(
            duplicate_capability_candidate_id=candidate_id,
            review_state="CONFIRMED" if review.decision == "CONFIRM" else "REJECTED",
            version=review.expected_version + 1,
            reviewed_at=NOW,
        )

    async def repository_modernization_intelligence(self, repository_id, *, tenant_id, limit):
        self.last_tenant_id = tenant_id
        return RepositoryModernizationIntelligence(
            repository=EntitySummary(
                id=repository_id, kind="Repository", name="Billing API",
                canonical_key="github:repo:billing-api",
            ),
            source_revision="revision-1",
            candidates=[],
            truncated=False,
        )

    async def review_modernization_recommendation(
        self, recommendation_id, review: ModernizationRecommendationReviewRequest,
        *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        state = {"ACCEPT": "ACCEPTED", "REJECT": "REJECTED", "DISMISS": "DISMISSED"}[review.decision]
        return ModernizationRecommendationReviewResult(
            modernization_recommendation_id=recommendation_id,
            review_state=state,
            version=review.expected_version + 1,
            reviewed_at=NOW,
        )

    async def review_modernization_candidate(
        self, candidate_id, review: ModernizationCandidateReviewRequest,
        *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return ModernizationCandidateReviewResult(
            modernization_candidate_id=candidate_id,
            review_state="CONFIRMED" if review.decision == "CONFIRM" else "REJECTED",
            version=review.expected_version + 1, reviewed_at=NOW,
        )

    async def record_modernization_validation_outcome(
        self, recommendation_id, outcome: ModernizationValidationOutcomeRequest,
        *, tenant_id, actor_key,
    ):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return ModernizationValidationOutcomeResult(
            id=UUID("00000000-0000-4000-8000-000000000799"),
            modernization_recommendation_id=recommendation_id,
            validation_status=outcome.validation_status, reported_at=NOW,
        )

    async def phase3_intelligence_metrics(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return Phase3IntelligenceMetrics(
            as_of=NOW, candidate_counts={"CONFIRMED": 1},
            recommendation_counts={"ACCEPTED": 1}, job_counts={"SUCCEEDED": 1},
            candidate_review_precision=1.0, recommendation_acceptance_rate=1.0,
            successful_validation_rate=1.0, evidence_completeness_rate=1.0,
            retry_count=0, dead_letter_count=0, stale_candidate_count=0,
            stale_recommendation_count=0, model_invocation_count=0, model_cost_usd=0,
        )

    async def review_queue(self, *, tenant_id, item_types, repository_id, cursor, limit):
        self.last_tenant_id = tenant_id
        self.last_item_types = item_types
        self.last_repository_id = repository_id
        return ReviewQueue(
            as_of=NOW,
            counts={
                "IDENTITY_ASSERTION": 1, "CAPABILITY_INFERENCE": 0, "DUPLICATE_CAPABILITY": 0,
                "MODERNIZATION_CANDIDATE": 0, "MODERNIZATION_RECOMMENDATION": 0,
            },
            items=[ReviewQueueItem(
                item_id=UUID("00000000-0000-4000-8000-000000000501"),
                item_type="IDENTITY_ASSERTION", review_state="POSSIBLE",
                title="stripe ↔ stripe-node", confidence=0.7, confidence_band="MEDIUM",
                version=1, created_at=NOW,
                review_path="/identity-assertions/00000000-0000-4000-8000-000000000501/review",
            )],
            page_info=PageInfo(has_next_page=False),
        )

    async def list_tenant_members(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return TenantMemberList(members=[])

    async def invite_tenant_member(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return TenantMember(
            id=UUID("00000000-0000-4000-8000-000000000a01"), actor_key=request.actor_key,
            display_name=request.display_name, email=request.email, role=request.role,
            status="INVITED", created_at=NOW, updated_at=NOW,
        )

    async def update_tenant_member(self, member_id, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return TenantMember(
            id=member_id, actor_key="member", display_name="", email="",
            role=request.role or "view", status=request.status or "ACTIVE",
            created_at=NOW, updated_at=NOW,
        )

    async def remove_tenant_member(self, member_id, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return TenantMember(
            id=member_id, actor_key="member", display_name="", email="",
            role="view", status="ACTIVE", created_at=NOW, updated_at=NOW,
        )

    async def list_connectors(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return ConnectorList(connectors=[])

    async def register_connector(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return Connector(
            id=UUID("00000000-0000-4000-8000-000000000b01"), provider=request.provider,
            display_name=request.display_name, external_account_key=request.external_account_key,
            scopes=request.scopes, status="CONNECTED", created_at=NOW, updated_at=NOW,
        )

    async def connect_github_repository(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return Connector(
            id=UUID("00000000-0000-4000-8000-000000000b02"), provider="GITHUB_APP",
            display_name=request.repository,
            external_account_key=f"github:repository:{request.repository.lower()}",
            scopes=["contents:read", "metadata:read"], status="CONNECTED",
            created_at=NOW, updated_at=NOW,
        )

    async def connect_github_installation(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return Connector(
            id=UUID("00000000-0000-4000-8000-000000000b03"), provider="GITHUB_APP",
            display_name=request.display_name or f"GitHub installation {request.installation_id}",
            external_account_key=f"github:installation:{request.installation_id}",
            scopes=["contents:read", "metadata:read"], status="CONNECTED",
            created_at=NOW, updated_at=NOW,
        )

    async def update_connector(self, connector_id, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return Connector(
            id=connector_id, provider="GITHUB_APP", display_name=request.display_name or "conn",
            external_account_key="", scopes=request.scopes or [], status=request.status or "CONNECTED",
            created_at=NOW, updated_at=NOW,
        )

    async def remove_connector(self, connector_id, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return Connector(
            id=connector_id, provider="GITHUB_APP", display_name="conn", external_account_key="",
            scopes=[], status="REVOKED", created_at=NOW, updated_at=NOW,
        )

    async def get_ai_provider_configuration(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return AIProviderConfiguration(provider="anthropic")

    async def update_ai_provider_configuration(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return AIProviderConfiguration(
            provider=request.provider, model=request.model, enabled=request.enabled,
            key_configured=request.api_key is not None,
            key_fingerprint=request.api_key[-4:] if request.api_key else None,
            updated_by=actor_key, updated_at=NOW,
        )

    async def remove_ai_provider_key(self, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return AIProviderConfiguration(provider="anthropic")

    async def test_ai_provider_connection(self, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return AIProviderConnectionTest(provider="anthropic", models=["claude-test"])

    async def get_scan_policy(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return ScanPolicy(cadence="DAILY", enabled=True)

    async def update_scan_policy(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        return ScanPolicy(cadence=request.cadence, enabled=request.enabled, updated_by=actor_key, updated_at=NOW)

    async def request_rescan(self, request, *, tenant_id, actor_key):
        self.last_tenant_id = tenant_id
        self.last_actor_key = actor_key
        created = getattr(self, "rescan_created", True)
        return (
            RescanJob(
                id=UUID("00000000-0000-4000-8000-000000000c01"), connector_id=request.connector_id,
                status="PENDING", reason=request.reason, requested_by=actor_key, created_at=NOW,
            ),
            created,
        )

    async def list_rescan_jobs(self, *, tenant_id, cursor, limit):
        self.last_tenant_id = tenant_id
        return RescanJobList(jobs=[], page_info=PageInfo(has_next_page=False))

    async def scan_status(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return ScanStatus(
            as_of=NOW, policy=ScanPolicy(cadence="DAILY", enabled=True), quotas=[], recent_jobs=[],
        )

    async def service_status(self, *, tenant_id):
        self.last_tenant_id = tenant_id
        return ServiceStatusList(
            as_of=NOW,
            services=[ServiceStatus(
                key="api", name="API", category="CORE", state="RUNNING",
                detail="The API is responding.", last_heartbeat_at=NOW,
            )],
        )


def app_with_stubs(settings: Settings | None = None) -> tuple[FastAPI, StubReadModels]:
    read_models = StubReadModels()
    return (
        create_app(
            settings=settings or Settings(environment="test"),
            database=StubDatabase(),
            read_models=read_models,
        ),
        read_models,
    )


async def request(app: FastAPI, method: str, path: str, **kwargs):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def test_estate_summary_is_available_on_contract_and_versioned_paths() -> None:
    app, _ = app_with_stubs()
    direct = asyncio.run(request(app, "GET", "/estate/summary"))
    versioned = asyncio.run(request(app, "GET", "/api/v1/estate/summary"))

    assert direct.status_code == 200
    assert direct.json()["contract_version"] == "1.0.0"
    assert versioned.json() == direct.json()


def test_estate_summary_forwards_domain_scope() -> None:
    app, store = app_with_stubs()
    response = asyncio.run(request(
        app,
        "GET",
        "/api/v1/estate/summary?domain=TECHNOLOGY&domain=OSS&limit=100",
    ))

    assert response.status_code == 200
    assert store.last_estate_namespaces == ["TECHNOLOGY", "OSS"]


def test_capability_taxonomy_is_exposed_on_versioned_path() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(
        app, "GET", "/api/v1/capabilities/taxonomy?version=1.0.0",
    ))

    assert response.status_code == 200
    assert response.json()["capabilities"][0]["key"] == "http-client"


def test_capability_review_forwards_tenant_and_actor() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(
        environment="test", default_tenant_id=tenant_id,
    ))
    response = asyncio.run(request(
        app,
        "POST",
        "/api/v1/capability-inferences/00000000-0000-4000-8000-000000000700/review",
        json={"decision": "CONFIRM", "rationale": "Evidence verified.", "expected_version": 1},
    ))

    assert response.status_code == 200
    assert response.json()["review_state"] == "CONFIRMED"
    assert store.last_tenant_id == tenant_id
    assert store.last_actor_key == "local-user"


def test_modernization_intelligence_is_bounded_and_versioned() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(
        app,
        "GET",
        "/api/v1/repositories/00000000-0000-4000-8000-000000000701/modernization-intelligence?limit=25",
    ))

    assert response.status_code == 200
    assert response.json()["contract_version"] == "1.0.0"
    assert response.json()["truncated"] is False


def test_modernization_review_forwards_tenant_and_actor() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(environment="test", default_tenant_id=tenant_id))
    response = asyncio.run(request(
        app,
        "POST",
        "/api/v1/modernization-recommendations/00000000-0000-4000-8000-000000000702/review",
        json={"decision": "ACCEPT", "rationale": "Validated migration surface.", "expected_version": 1},
    ))

    assert response.status_code == 200
    assert response.json()["review_state"] == "ACCEPTED"
    assert store.last_tenant_id == tenant_id
    assert store.last_actor_key == "local-user"


def test_modernization_candidate_review_and_validation_metrics_are_exposed() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(environment="test", default_tenant_id=tenant_id))
    candidate = asyncio.run(request(
        app, "POST",
        "/api/v1/modernization-candidates/00000000-0000-4000-8000-000000000702/review",
        json={"decision": "CONFIRM", "rationale": "Matched implementations verified.", "expected_version": 1},
    ))
    outcome = asyncio.run(request(
        app, "POST",
        "/api/v1/modernization-recommendations/00000000-0000-4000-8000-000000000708/validation-outcomes",
        json={
            "validation_status": "SUCCEEDED", "actual_call_sites": 3,
            "actual_files": 2, "actual_effort": "LOW", "notes": "Migration checks passed.",
        },
    ))
    metrics = asyncio.run(request(app, "GET", "/api/v1/intelligence/phase-3/metrics"))

    assert candidate.status_code == 200
    assert candidate.json()["review_state"] == "CONFIRMED"
    assert outcome.status_code == 200
    assert outcome.json()["validation_status"] == "SUCCEEDED"
    assert metrics.status_code == 200
    assert metrics.json()["candidate_review_precision"] == 1.0
    assert store.last_tenant_id == tenant_id
    assert store.last_actor_key == "local-user"


def test_development_principal_is_forwarded_and_tenant_header_is_ignored() -> None:
    tenant_id = "00000000-0000-4000-8000-000000000123"
    app, store = app_with_stubs(Settings(environment="test", default_tenant_id=UUID(tenant_id)))
    response = asyncio.run(request(
        app,
        "GET",
        "/estate/summary",
        headers={"X-StackGraph-Tenant-ID": "00000000-0000-4000-8000-000000000999"},
    ))

    assert response.status_code == 200
    assert store.last_tenant_id == UUID(tenant_id)


def test_request_body_limit_rejects_oversized_payload() -> None:
    app, _ = app_with_stubs(Settings(environment="test", request_body_max_bytes=1024))
    response = asyncio.run(request(
        app,
        "POST",
        "/api/v1/ask",
        content=b"x" * 1025,
        headers={"Content-Type": "application/json"},
    ))
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_per_actor_rate_limit_returns_retry_metadata() -> None:
    app, _ = app_with_stubs(Settings(
        environment="test",
        rate_limit_requests_per_minute=1,
    ))
    first = asyncio.run(request(app, "GET", "/api/v1/estate/summary"))
    second = asyncio.run(request(app, "GET", "/api/v1/estate/summary"))
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "60"


def test_signed_session_supplies_tenant_and_actor() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    token = create_session_token(
        secret, actor_key="signed-user", tenant_id=tenant_id, expires_at=int(time.time()) + 60,
        capabilities=["review"],
    )
    response = asyncio.run(request(
        app,
        "POST",
        "/identity-assertions/00000000-0000-4000-8000-000000000501/review",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "CONFIRM", "rationale": "Verified.", "expected_version": 1},
    ))

    assert response.status_code == 200
    assert store.last_tenant_id == tenant_id
    assert store.last_actor_key == "signed-user"


def test_signed_session_rejects_missing_expired_and_tampered_tokens() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    app, _ = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    expired = create_session_token(
        secret, actor_key="signed-user", tenant_id=None, expires_at=int(time.time()) - 1,
    )
    valid = create_session_token(
        secret, actor_key="signed-user", tenant_id=None, expires_at=int(time.time()) + 60,
    )

    missing = asyncio.run(request(app, "GET", "/estate/summary"))
    expired_response = asyncio.run(request(
        app, "GET", "/estate/summary", headers={"Authorization": f"Bearer {expired}"},
    ))
    tampered = asyncio.run(request(
        app, "GET", "/estate/summary", headers={"Authorization": f"Bearer {valid}x"},
    ))

    assert (missing.status_code, missing.json()["code"]) == (401, "AUTH_REQUIRED")
    assert (expired_response.status_code, expired_response.json()["code"]) == (401, "SESSION_EXPIRED")
    assert (tampered.status_code, tampered.json()["code"]) == (401, "INVALID_SESSION")


def _business_map_state() -> dict:
    return {"title": "Map", "view_mode": "value-chain", "template_id": "porter"}


def test_session_endpoint_reports_actor_tenant_and_capabilities() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, _ = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    token = create_session_token(
        secret, actor_key="reviewer", tenant_id=tenant_id,
        expires_at=int(time.time()) + 60, capabilities=["review"],
    )
    response = asyncio.run(request(
        app, "GET", "/api/v1/session", headers={"Authorization": f"Bearer {token}"},
    ))
    assert response.status_code == 200
    body = response.json()
    assert body["actor_key"] == "reviewer"
    assert body["tenant_id"] == str(tenant_id)
    assert body["capabilities"] == ["review"]


def test_session_defaults_to_view_only_without_token_capabilities() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    app, _ = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    token = create_session_token(
        secret, actor_key="viewer", tenant_id=None, expires_at=int(time.time()) + 60,
    )
    response = asyncio.run(request(
        app, "GET", "/api/v1/session", headers={"Authorization": f"Bearer {token}"},
    ))
    assert response.status_code == 200
    assert response.json()["capabilities"] == ["view"]


def test_review_route_requires_review_capability() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, _ = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    view_only = create_session_token(
        secret, actor_key="viewer", tenant_id=tenant_id,
        expires_at=int(time.time()) + 60, capabilities=["view"],
    )
    response = asyncio.run(request(
        app, "POST",
        "/identity-assertions/00000000-0000-4000-8000-000000000501/review",
        headers={"Authorization": f"Bearer {view_only}"},
        json={"decision": "CONFIRM", "rationale": "Verified.", "expected_version": 1},
    ))
    assert response.status_code == 403
    assert response.json()["details"]["required_capability"] == "review"


def test_business_map_write_requires_execute_capability() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    view_only = create_session_token(
        secret, actor_key="viewer", tenant_id=tenant_id,
        expires_at=int(time.time()) + 60, capabilities=["view"],
    )

    # A viewer may read the list...
    listed = asyncio.run(request(
        app, "GET", "/api/v1/business-maps", headers={"Authorization": f"Bearer {view_only}"},
    ))
    assert listed.status_code == 200

    # ...but may not create.
    forbidden = asyncio.run(request(
        app, "POST", "/api/v1/business-maps",
        headers={"Authorization": f"Bearer {view_only}"},
        json={"map_key": "enterprise.value-chain", "state": _business_map_state()},
    ))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert forbidden.json()["details"]["required_capability"] == "execute"
    assert store.last_actor_key is None  # the store was never reached


def test_business_map_write_allowed_with_execute_capability() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    editor = create_session_token(
        secret, actor_key="editor", tenant_id=tenant_id,
        expires_at=int(time.time()) + 60, capabilities=["execute"],
    )

    created = asyncio.run(request(
        app, "POST", "/api/v1/business-maps",
        headers={"Authorization": f"Bearer {editor}"},
        json={"map_key": "enterprise.value-chain", "state": _business_map_state()},
    ))
    assert created.status_code == 201
    assert store.last_actor_key == "editor"


def test_api_errors_use_contract_shape_and_request_id() -> None:
    app, _ = app_with_stubs()
    request_id = "test-request-id"
    response = asyncio.run(request(
        app,
        "GET",
        "/applications/00000000-0000-4000-8000-000000000201",
        headers={"X-Request-ID": request_id},
    ))

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "code": "ENTITY_NOT_FOUND",
        "message": "The requested entity was not found.",
        "request_id": request_id,
    }


def test_metrics_are_prometheus_formatted_and_bearer_protected() -> None:
    read_models = StubReadModels()
    app = create_app(
        settings=Settings(environment="test", metrics_bearer_token="metrics-test-token"),
        database=MetricsStubDatabase(),
        read_models=read_models,
    )

    denied = asyncio.run(request(app, "GET", "/metrics"))
    allowed = asyncio.run(request(
        app,
        "GET",
        "/metrics",
        headers={"Authorization": "Bearer metrics-test-token"},
    ))

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert 'stackgraph_operational_signal{signal="ingest_queue_age_seconds"} 0' in allowed.text
    assert 'owner="discovery-on-call"' in allowed.text


def test_ask_rejects_unknown_fields() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(app, "POST", "/ask", json={"question": "What changed?", "extra": True}))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unexpected_errors_use_contract_shape() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(app, "GET", "/modernization"))

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


def test_identity_review_accepts_optimistic_version() -> None:
    app, _ = app_with_stubs()
    assertion_id = "00000000-0000-4000-8000-000000000501"
    response = asyncio.run(request(
        app,
        "POST",
        f"/identity-assertions/{assertion_id}/review",
        json={"decision": "CONFIRM", "rationale": "Registry identity matches.", "expected_version": 1},
    ))

    assert response.status_code == 200
    assert response.json()["review_state"] == "CONFIRMED"
    assert response.json()["version"] == 2


# --- Review queue --------------------------------------------------------

def _token(secret: str, caps: list[str], tenant_id: UUID) -> str:
    return create_session_token(
        secret, actor_key="operator", tenant_id=tenant_id,
        expires_at=int(time.time()) + 60, capabilities=caps,
    )


SECRET = "a-test-session-secret-with-at-least-32-characters"
TENANT = UUID("00000000-0000-4000-8000-000000000123")


def _signed_app() -> tuple[FastAPI, StubReadModels]:
    return app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=SECRET,
    ))


def test_review_queue_is_exposed_and_versioned() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "GET", "/api/v1/reviews/queue?type=IDENTITY_ASSERTION&limit=10",
        headers={"Authorization": f"Bearer {_token(SECRET, ['review'], TENANT)}"},
    ))
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "1.0.0"
    assert body["counts"]["IDENTITY_ASSERTION"] == 1
    assert body["items"][0]["item_type"] == "IDENTITY_ASSERTION"
    assert body["items"][0]["review_path"].endswith("/review")
    assert store.last_tenant_id == TENANT
    assert store.last_item_types == ["IDENTITY_ASSERTION"]


def test_review_queue_requires_review_capability() -> None:
    app, _ = _signed_app()
    response = asyncio.run(request(
        app, "GET", "/api/v1/reviews/queue",
        headers={"Authorization": f"Bearer {_token(SECRET, ['view'], TENANT)}"},
    ))
    assert response.status_code == 403
    assert response.json()["details"]["required_capability"] == "review"


# --- Admin gating --------------------------------------------------------

def test_admin_routes_require_admin_capability() -> None:
    app, store = _signed_app()
    execute_token = _token(SECRET, ["execute"], TENANT)
    for method, path, payload in [
        ("GET", "/api/v1/admin/members", None),
        ("POST", "/api/v1/admin/members", {"actor_key": "x", "role": "view"}),
        ("GET", "/api/v1/admin/connectors", None),
        ("POST", "/api/v1/admin/github/repositories", {"repository": "acme/billing"}),
        ("POST", "/api/v1/admin/github/installations", {"installation_id": "123456"}),
        ("GET", "/api/v1/admin/ai-configuration", None),
        ("PUT", "/api/v1/admin/ai-configuration", {"provider": "openrouter", "api_key": "secret-key"}),
        ("DELETE", "/api/v1/admin/ai-configuration/key", None),
        ("POST", "/api/v1/admin/ai-configuration/test", None),
        ("GET", "/api/v1/admin/scan-status", None),
        ("GET", "/api/v1/admin/services", None),
        ("PUT", "/api/v1/admin/scan-policy", {"cadence": "DAILY", "enabled": True}),
        ("POST", "/api/v1/admin/rescans", {"idempotency_key": "k1"}),
    ]:
        response = asyncio.run(request(
            app, method, path, headers={"Authorization": f"Bearer {execute_token}"},
            json=payload,
        ))
        assert response.status_code == 403, f"{method} {path}"
        assert response.json()["details"]["required_capability"] == "admin"
    assert store.last_actor_key is None  # no write reached the store


def test_invite_member_creates_and_forwards_actor() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "POST", "/api/v1/admin/members",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"actor_key": "dana@acme.example", "display_name": "Dana", "role": "review"},
    ))
    assert response.status_code == 201
    body = response.json()
    assert body["actor_key"] == "dana@acme.example"
    assert body["role"] == "review"
    assert store.last_actor_key == "operator"


def test_register_connector_creates() -> None:
    app, _ = _signed_app()
    response = asyncio.run(request(
        app, "POST", "/api/v1/admin/connectors",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"provider": "GITHUB_APP", "display_name": "acme-corp", "scopes": ["repo:read"]},
    ))
    assert response.status_code == 201
    assert response.json()["provider"] == "GITHUB_APP"


def test_connect_github_repository_queues_admin_connection() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "POST", "/api/v1/admin/github/repositories",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"repository": "Acme/Billing"},
    ))
    assert response.status_code == 201
    assert response.json()["display_name"] == "Acme/Billing"
    assert response.json()["external_account_key"] == "github:repository:acme/billing"
    assert store.last_actor_key == "operator"


def test_connect_github_installation_queues_reconciliation() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "POST", "/api/v1/admin/github/installations",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"installation_id": "12345678", "display_name": "Acme engineering"},
    ))
    assert response.status_code == 201
    assert response.json()["display_name"] == "Acme engineering"
    assert response.json()["external_account_key"] == "github:installation:12345678"
    assert store.last_actor_key == "operator"


def test_service_status_is_admin_visible() -> None:
    app, _ = _signed_app()
    response = asyncio.run(request(
        app, "GET", "/api/v1/admin/services",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
    ))
    assert response.status_code == 200
    assert response.json()["services"][0]["key"] == "api"


def test_connect_github_repository_rejects_tokens_and_invalid_identity() -> None:
    app, _ = _signed_app()
    admin = _token(SECRET, ["admin"], TENANT)
    invalid = asyncio.run(request(
        app, "POST", "/api/v1/admin/github/repositories",
        headers={"Authorization": f"Bearer {admin}"}, json={"repository": "not-a-repository"},
    ))
    secret = asyncio.run(request(
        app, "POST", "/api/v1/admin/github/repositories",
        headers={"Authorization": f"Bearer {admin}"},
        json={"repository": "acme/billing", "credential_reference": "ghp_" + "a" * 36},
    ))
    assert invalid.status_code == 422
    assert secret.status_code == 422


def test_ai_configuration_is_write_only_and_forwards_actor() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "PUT", "/api/v1/admin/ai-configuration",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"provider": "openrouter", "model": "anthropic/claude-test", "api_key": "sk-test-1234"},
    ))
    assert response.status_code == 200
    assert response.json()["key_configured"] is True
    assert response.json()["key_fingerprint"] == "1234"
    assert "api_key" not in response.json()
    assert store.last_actor_key == "operator"


def test_rescan_is_created_then_idempotent() -> None:
    app, store = _signed_app()
    admin = _token(SECRET, ["admin"], TENANT)
    created = asyncio.run(request(
        app, "POST", "/api/v1/admin/rescans",
        headers={"Authorization": f"Bearer {admin}"},
        json={"idempotency_key": "nightly-2026-08-19"},
    ))
    assert created.status_code == 201

    store.rescan_created = False  # simulate an idempotent replay
    replay = asyncio.run(request(
        app, "POST", "/api/v1/admin/rescans",
        headers={"Authorization": f"Bearer {admin}"},
        json={"idempotency_key": "nightly-2026-08-19"},
    ))
    assert replay.status_code == 200
    assert replay.json()["status"] == "PENDING"


def test_scan_policy_update_forwards_actor() -> None:
    app, store = _signed_app()
    response = asyncio.run(request(
        app, "PUT", "/api/v1/admin/scan-policy",
        headers={"Authorization": f"Bearer {_token(SECRET, ['admin'], TENANT)}"},
        json={"cadence": "HOURLY", "enabled": True},
    ))
    assert response.status_code == 200
    assert response.json()["cadence"] == "HOURLY"
    assert store.last_actor_key == "operator"


def test_reject_raw_secret_blocks_token_like_reference() -> None:
    from app.read_models import ReadModelStore
    from app.errors import APIError as _APIError

    ReadModelStore._reject_raw_secret("vault://connectors/github/acme")  # ok, no raise
    for raw in ["ghp_" + "a" * 36, "github_pat_" + "b" * 40, "xoxb-123", "-----BEGIN KEY-----"]:
        try:
            ReadModelStore._reject_raw_secret(raw)
        except _APIError as error:
            assert error.code == "CREDENTIAL_LOOKS_RAW"
        else:
            raise AssertionError(f"expected rejection for {raw!r}")

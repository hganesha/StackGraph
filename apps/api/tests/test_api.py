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
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=UTC)


class StubDatabase:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def check_readiness(self) -> DatabaseReadiness:
        return DatabaseReadiness(connected=True, age_installed=True, schema_installed=True)


class StubReadModels:
    def __init__(self) -> None:
        self.last_tenant_id = None
        self.last_actor_key = None

    async def estate_summary(self, *, tenant_id, cursor, limit):
        self.last_tenant_id = tenant_id
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


def test_signed_session_supplies_tenant_and_actor() -> None:
    secret = "a-test-session-secret-with-at-least-32-characters"
    tenant_id = UUID("00000000-0000-4000-8000-000000000123")
    app, store = app_with_stubs(Settings(
        environment="test", auth_mode="signed_session", auth_session_secret=secret,
    ))
    token = create_session_token(
        secret, actor_key="signed-user", tenant_id=tenant_id, expires_at=int(time.time()) + 60,
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

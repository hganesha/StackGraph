import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.database import DatabaseReadiness
from app.errors import APIError
from app.main import create_app
from app.models import (
    AskRequest,
    AskResponse,
    Coverage,
    EstateCounts,
    EstateSummary,
    Freshness,
    IdentityReviewRequest,
    IdentityReviewResult,
    PageInfo,
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

    async def application_detail(self, application_id, *, tenant_id):
        raise APIError(404, "ENTITY_NOT_FOUND", "The requested entity was not found.")

    async def technology_detail(self, technology_id, *, tenant_id):
        raise APIError(404, "ENTITY_NOT_FOUND", "The requested entity was not found.")

    async def modernization(self, *, tenant_id, cursor, limit):
        raise NotImplementedError

    async def graph_neighborhood(self, center_id, *, tenant_id, depth, real_node_limit):
        raise NotImplementedError

    async def evidence_detail(self, fact_id, *, tenant_id):
        raise NotImplementedError

    async def review_identity_assertion(
        self, assertion_id, review: IdentityReviewRequest, *, tenant_id, actor_key,
    ):
        return IdentityReviewResult(
            identity_assertion_id=assertion_id,
            review_state="CONFIRMED" if review.decision == "CONFIRM" else "REJECTED",
            version=review.expected_version + 1,
            reviewed_at=NOW,
        )


def app_with_stubs() -> tuple[FastAPI, StubReadModels]:
    read_models = StubReadModels()
    return (
        create_app(
            settings=Settings(environment="test"),
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


def test_tenant_header_is_forwarded_to_read_model() -> None:
    app, store = app_with_stubs()
    tenant_id = "00000000-0000-4000-8000-000000000123"
    response = asyncio.run(request(
        app, "GET", "/estate/summary", headers={"X-StackGraph-Tenant-ID": tenant_id},
    ))

    assert response.status_code == 200
    assert store.last_tenant_id == UUID(tenant_id)


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

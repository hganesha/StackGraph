from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.auth import Principal
from app.models import (
    ApplicationDetail,
    AskRequest,
    AskResponse,
    EstateSummary,
    EvidenceDetail,
    GraphNeighborhood,
    IdentityReviewRequest,
    IdentityReviewResult,
    ModernizationList,
    Namespace,
    TechnologyDetail,
)


class ReadModelsProtocol(Protocol):
    async def estate_summary(self, *, tenant_id: UUID | None, cursor: str | None, limit: int) -> EstateSummary: ...
    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail: ...
    async def technology_detail(self, technology_id: UUID, *, tenant_id: UUID | None) -> TechnologyDetail: ...
    async def modernization(self, *, tenant_id: UUID | None, cursor: str | None, limit: int) -> ModernizationList: ...
    async def graph_neighborhood(
        self, center_id: UUID, *, tenant_id: UUID | None, depth: int, real_node_limit: int,
        predicates: list[str] | None, namespaces: list[str] | None,
        min_confidence: float, highlight_to: UUID | None,
    ) -> GraphNeighborhood: ...
    async def evidence_detail(self, fact_id: UUID, *, tenant_id: UUID | None) -> EvidenceDetail: ...
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...
    async def review_identity_assertion(
        self, assertion_id: UUID, review: IdentityReviewRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> IdentityReviewResult: ...


router = APIRouter()


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = request.app.state.authenticator.authenticate(
            request.headers.get("Authorization")
        )
        request.state.principal = principal
    return principal


def _store(request: Request) -> ReadModelsProtocol:
    return request.app.state.read_models


@router.get(
    "/estate/summary", response_model=EstateSummary,
    response_model_exclude_none=True, operation_id="getEstateSummary", tags=["estate"],
)
async def get_estate_summary(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> EstateSummary:
    principal = _principal(request)
    return await _store(request).estate_summary(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.get(
    "/applications/{id}", response_model=ApplicationDetail,
    response_model_exclude_none=True, operation_id="getApplication", tags=["applications"],
)
async def get_application(id: UUID, request: Request) -> ApplicationDetail:
    principal = _principal(request)
    return await _store(request).application_detail(id, tenant_id=principal.tenant_id)


@router.get(
    "/technologies/{id}", response_model=TechnologyDetail,
    response_model_exclude_none=True, operation_id="getTechnology", tags=["technologies"],
)
async def get_technology(id: UUID, request: Request) -> TechnologyDetail:
    principal = _principal(request)
    return await _store(request).technology_detail(id, tenant_id=principal.tenant_id)


@router.get(
    "/modernization", response_model=ModernizationList,
    response_model_exclude_none=True, operation_id="listModernizationOpportunities", tags=["intelligence"],
)
async def list_modernization(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ModernizationList:
    principal = _principal(request)
    return await _store(request).modernization(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.post(
    "/ask", response_model=AskResponse,
    response_model_exclude_none=True, operation_id="askEstate", tags=["intelligence"],
)
async def ask_estate(body: AskRequest, request: Request) -> AskResponse:
    principal = _principal(request)
    return await _store(request).ask(body, tenant_id=principal.tenant_id)


@router.get(
    "/graph/neighborhood", response_model=GraphNeighborhood,
    response_model_exclude_none=True, operation_id="getGraphNeighborhood", tags=["graph"],
)
async def get_graph_neighborhood(
    request: Request,
    center_id: UUID,
    depth: int = Query(default=1, ge=1, le=2),
    real_node_limit: int = Query(default=50, ge=1, le=50),
    predicate: list[str] | None = Query(default=None, min_length=1),
    namespace: list[Namespace] | None = Query(default=None),
    min_confidence: float = Query(default=0, ge=0, le=1),
    highlight_to: UUID | None = None,
) -> GraphNeighborhood:
    principal = _principal(request)
    return await _store(request).graph_neighborhood(
        center_id,
        tenant_id=principal.tenant_id,
        depth=depth,
        real_node_limit=real_node_limit,
        predicates=predicate,
        namespaces=namespace,
        min_confidence=min_confidence,
        highlight_to=highlight_to,
    )


@router.get(
    "/facts/{id}/evidence", response_model=EvidenceDetail,
    response_model_exclude_none=True, operation_id="getFactEvidence", tags=["evidence"],
)
async def get_fact_evidence(id: UUID, request: Request) -> EvidenceDetail:
    principal = _principal(request)
    return await _store(request).evidence_detail(id, tenant_id=principal.tenant_id)


@router.post(
    "/identity-assertions/{id}/review", response_model=IdentityReviewResult,
    response_model_exclude_none=True, operation_id="reviewIdentityAssertion", tags=["identity"],
)
async def review_identity_assertion(
    id: UUID,
    body: IdentityReviewRequest,
    request: Request,
) -> IdentityReviewResult:
    principal = _principal(request)
    return await _store(request).review_identity_assertion(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )

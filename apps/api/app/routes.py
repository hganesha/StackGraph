from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

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
    TechnologyDetail,
)


class ReadModelsProtocol(Protocol):
    async def estate_summary(self, *, tenant_id: UUID | None, cursor: str | None, limit: int) -> EstateSummary: ...
    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail: ...
    async def technology_detail(self, technology_id: UUID, *, tenant_id: UUID | None) -> TechnologyDetail: ...
    async def modernization(self, *, tenant_id: UUID | None, cursor: str | None, limit: int) -> ModernizationList: ...
    async def graph_neighborhood(self, center_id: UUID, *, tenant_id: UUID | None, depth: int, real_node_limit: int) -> GraphNeighborhood: ...
    async def evidence_detail(self, fact_id: UUID, *, tenant_id: UUID | None) -> EvidenceDetail: ...
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...
    async def review_identity_assertion(
        self, assertion_id: UUID, review: IdentityReviewRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> IdentityReviewResult: ...


router = APIRouter()


def _tenant(request: Request, header_tenant_id: UUID | None) -> UUID | None:
    return header_tenant_id or request.app.state.settings.default_tenant_id


def _store(request: Request) -> ReadModelsProtocol:
    return request.app.state.read_models


@router.get("/estate/summary", response_model=EstateSummary, tags=["estate"])
async def get_estate_summary(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> EstateSummary:
    return await _store(request).estate_summary(
        tenant_id=_tenant(request, tenant_id), cursor=cursor, limit=limit,
    )


@router.get("/applications/{application_id}", response_model=ApplicationDetail, tags=["applications"])
async def get_application(
    application_id: UUID,
    request: Request,
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> ApplicationDetail:
    return await _store(request).application_detail(application_id, tenant_id=_tenant(request, tenant_id))


@router.get("/technologies/{technology_id}", response_model=TechnologyDetail, tags=["technologies"])
async def get_technology(
    technology_id: UUID,
    request: Request,
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> TechnologyDetail:
    return await _store(request).technology_detail(technology_id, tenant_id=_tenant(request, tenant_id))


@router.get("/modernization", response_model=ModernizationList, tags=["intelligence"])
async def list_modernization(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> ModernizationList:
    return await _store(request).modernization(
        tenant_id=_tenant(request, tenant_id), cursor=cursor, limit=limit,
    )


@router.post("/ask", response_model=AskResponse, tags=["intelligence"])
async def ask_estate(
    body: AskRequest,
    request: Request,
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> AskResponse:
    return await _store(request).ask(body, tenant_id=_tenant(request, tenant_id))


@router.get(
    "/graph/neighborhood",
    response_model=GraphNeighborhood,
    response_model_exclude_none=True,
    tags=["graph"],
)
async def get_graph_neighborhood(
    request: Request,
    center_id: UUID,
    depth: int = Query(default=1, ge=1, le=2),
    real_node_limit: int = Query(default=50, ge=1, le=50),
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> GraphNeighborhood:
    return await _store(request).graph_neighborhood(
        center_id, tenant_id=_tenant(request, tenant_id), depth=depth, real_node_limit=real_node_limit,
    )


@router.get("/facts/{fact_id}/evidence", response_model=EvidenceDetail, tags=["evidence"])
async def get_fact_evidence(
    fact_id: UUID,
    request: Request,
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
) -> EvidenceDetail:
    return await _store(request).evidence_detail(fact_id, tenant_id=_tenant(request, tenant_id))


@router.post(
    "/identity-assertions/{assertion_id}/review",
    response_model=IdentityReviewResult,
    tags=["identity"],
)
async def review_identity_assertion(
    assertion_id: UUID,
    body: IdentityReviewRequest,
    request: Request,
    tenant_id: UUID | None = Header(default=None, alias="X-StackGraph-Tenant-ID"),
    actor_key: str = Header(default="local-user", alias="X-StackGraph-Actor", min_length=1, max_length=255),
) -> IdentityReviewResult:
    return await _store(request).review_identity_assertion(
        assertion_id, body, tenant_id=_tenant(request, tenant_id), actor_key=actor_key,
    )

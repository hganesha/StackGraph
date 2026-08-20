from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.auth import Principal
from app.errors import APIError
from app.models import (
    ApplicationDetail,
    AskRequest,
    AskResponse,
    BusinessMapCreateRequest,
    BusinessMapDetail,
    BusinessMapList,
    BusinessMapRevisionList,
    BusinessMapSaveRequest,
    BusinessMapSummary,
    CapabilityInferenceReviewRequest,
    CapabilityInferenceReviewResult,
    CapabilityTaxonomyResponse,
    DuplicateCapabilityReviewRequest,
    DuplicateCapabilityReviewResult,
    EstateSummary,
    EvidenceDetail,
    GraphNeighborhood,
    IdentityReviewRequest,
    IdentityReviewResult,
    ModernizationList,
    ModernizationCandidateReviewRequest,
    ModernizationCandidateReviewResult,
    ModernizationRecommendationReviewRequest,
    ModernizationRecommendationReviewResult,
    ModernizationValidationOutcomeRequest,
    ModernizationValidationOutcomeResult,
    Namespace,
    RepositoryCapabilityIntelligence,
    RepositoryModernizationIntelligence,
    Phase3IntelligenceMetrics,
    SessionInfo,
    TechnologyDetail,
    ReviewQueue,
    ReviewQueueItemType,
    TenantMember,
    TenantMemberList,
    MemberInviteRequest,
    MemberUpdateRequest,
    Connector,
    ConnectorList,
    ConnectorRegisterRequest,
    ConnectorUpdateRequest,
    ScanPolicy,
    ScanPolicyUpdateRequest,
    RescanRequest,
    RescanJob,
    RescanJobList,
    ScanStatus,
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
    async def capability_taxonomy(
        self, *, tenant_id: UUID | None, version: str | None,
    ) -> CapabilityTaxonomyResponse: ...
    async def repository_capabilities(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> RepositoryCapabilityIntelligence: ...
    async def review_capability_inference(
        self, inference_id: UUID, review: CapabilityInferenceReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> CapabilityInferenceReviewResult: ...
    async def review_duplicate_capability_candidate(
        self, candidate_id: UUID, review: DuplicateCapabilityReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> DuplicateCapabilityReviewResult: ...
    async def repository_modernization_intelligence(
        self, repository_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> RepositoryModernizationIntelligence: ...
    async def review_modernization_recommendation(
        self, recommendation_id: UUID, review: ModernizationRecommendationReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationRecommendationReviewResult: ...
    async def review_modernization_candidate(
        self, candidate_id: UUID, review: ModernizationCandidateReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationCandidateReviewResult: ...
    async def record_modernization_validation_outcome(
        self, recommendation_id: UUID, outcome: ModernizationValidationOutcomeRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationValidationOutcomeResult: ...
    async def phase3_intelligence_metrics(
        self, *, tenant_id: UUID | None,
    ) -> Phase3IntelligenceMetrics: ...
    async def list_business_maps(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> BusinessMapList: ...
    async def create_business_map(
        self, request: BusinessMapCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail: ...
    async def business_map_detail(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapDetail: ...
    async def save_business_map(
        self, map_id: UUID, request: BusinessMapSaveRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail: ...
    async def archive_business_map(
        self, map_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapSummary: ...
    async def business_map_revisions(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapRevisionList: ...
    async def review_queue(
        self, *, tenant_id: UUID | None, item_types: list[ReviewQueueItemType] | None,
        repository_id: UUID | None, cursor: str | None, limit: int,
    ) -> ReviewQueue: ...
    async def list_tenant_members(self, *, tenant_id: UUID | None) -> TenantMemberList: ...
    async def invite_tenant_member(
        self, request: MemberInviteRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def update_tenant_member(
        self, member_id: UUID, request: MemberUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def remove_tenant_member(
        self, member_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def list_connectors(self, *, tenant_id: UUID | None) -> ConnectorList: ...
    async def register_connector(
        self, request: ConnectorRegisterRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def update_connector(
        self, connector_id: UUID, request: ConnectorUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def remove_connector(
        self, connector_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def get_scan_policy(self, *, tenant_id: UUID | None) -> ScanPolicy: ...
    async def update_scan_policy(
        self, request: ScanPolicyUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ScanPolicy: ...
    async def request_rescan(
        self, request: RescanRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> tuple[RescanJob, bool]: ...
    async def list_rescan_jobs(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> RescanJobList: ...
    async def scan_status(self, *, tenant_id: UUID | None) -> ScanStatus: ...


class AskServiceProtocol(Protocol):
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...


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


def _require(principal: Principal, capability: str) -> None:
    """Enforce a capability on the ladder; raise 403 when the principal lacks it."""
    if not principal.has_capability(capability):
        raise APIError(
            403, "FORBIDDEN",
            f"This action requires the '{capability}' capability.",
            {"required_capability": capability},
        )


def _ask_service(request: Request) -> AskServiceProtocol:
    return request.app.state.ask_service


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
    return await _ask_service(request).ask(body, tenant_id=principal.tenant_id)


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
    _require(principal, "review")
    return await _store(request).review_identity_assertion(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/capabilities/taxonomy", response_model=CapabilityTaxonomyResponse,
    response_model_exclude_none=True, operation_id="getCapabilityTaxonomy",
    tags=["intelligence"],
)
async def get_capability_taxonomy(
    request: Request,
    version: str | None = None,
) -> CapabilityTaxonomyResponse:
    principal = _principal(request)
    return await _store(request).capability_taxonomy(
        tenant_id=principal.tenant_id, version=version,
    )


@router.get(
    "/repositories/{id}/capabilities", response_model=RepositoryCapabilityIntelligence,
    response_model_exclude_none=True, operation_id="getRepositoryCapabilities",
    tags=["intelligence"],
)
async def get_repository_capabilities(
    id: UUID,
    request: Request,
) -> RepositoryCapabilityIntelligence:
    principal = _principal(request)
    return await _store(request).repository_capabilities(
        id, tenant_id=principal.tenant_id,
    )


@router.post(
    "/capability-inferences/{id}/review", response_model=CapabilityInferenceReviewResult,
    response_model_exclude_none=True, operation_id="reviewCapabilityInference",
    tags=["intelligence"],
)
async def review_capability_inference(
    id: UUID,
    body: CapabilityInferenceReviewRequest,
    request: Request,
) -> CapabilityInferenceReviewResult:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).review_capability_inference(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/duplicate-capability-candidates/{id}/review", response_model=DuplicateCapabilityReviewResult,
    response_model_exclude_none=True, operation_id="reviewDuplicateCapabilityCandidate",
    tags=["intelligence"],
)
async def review_duplicate_capability_candidate(
    id: UUID,
    body: DuplicateCapabilityReviewRequest,
    request: Request,
) -> DuplicateCapabilityReviewResult:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).review_duplicate_capability_candidate(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/repositories/{id}/modernization-intelligence",
    response_model=RepositoryModernizationIntelligence,
    response_model_exclude_none=True, operation_id="getRepositoryModernizationIntelligence",
    tags=["intelligence"],
)
async def get_repository_modernization_intelligence(
    id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> RepositoryModernizationIntelligence:
    principal = _principal(request)
    return await _store(request).repository_modernization_intelligence(
        id, tenant_id=principal.tenant_id, limit=limit,
    )


@router.post(
    "/modernization-candidates/{id}/review",
    response_model=ModernizationCandidateReviewResult,
    response_model_exclude_none=True, operation_id="reviewModernizationCandidate",
    tags=["intelligence"],
)
async def review_modernization_candidate(
    id: UUID,
    body: ModernizationCandidateReviewRequest,
    request: Request,
) -> ModernizationCandidateReviewResult:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).review_modernization_candidate(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/modernization-recommendations/{id}/review",
    response_model=ModernizationRecommendationReviewResult,
    response_model_exclude_none=True, operation_id="reviewModernizationRecommendation",
    tags=["intelligence"],
)
async def review_modernization_recommendation(
    id: UUID,
    body: ModernizationRecommendationReviewRequest,
    request: Request,
) -> ModernizationRecommendationReviewResult:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).review_modernization_recommendation(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/modernization-recommendations/{id}/validation-outcomes",
    response_model=ModernizationValidationOutcomeResult,
    response_model_exclude_none=True, operation_id="recordModernizationValidationOutcome",
    tags=["intelligence"],
)
async def record_modernization_validation_outcome(
    id: UUID,
    body: ModernizationValidationOutcomeRequest,
    request: Request,
) -> ModernizationValidationOutcomeResult:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).record_modernization_validation_outcome(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/intelligence/phase-3/metrics",
    response_model=Phase3IntelligenceMetrics,
    response_model_exclude_none=True, operation_id="getPhase3IntelligenceMetrics",
    tags=["intelligence"],
)
async def get_phase3_intelligence_metrics(request: Request) -> Phase3IntelligenceMetrics:
    principal = _principal(request)
    return await _store(request).phase3_intelligence_metrics(tenant_id=principal.tenant_id)


@router.get(
    "/session", response_model=SessionInfo,
    response_model_exclude_none=True, operation_id="getSession", tags=["session"],
)
async def get_session(request: Request) -> SessionInfo:
    principal = _principal(request)
    return SessionInfo(
        actor_key=principal.actor_key,
        tenant_id=principal.tenant_id,
        capabilities=sorted(principal.capabilities),
    )


@router.get(
    "/business-maps", response_model=BusinessMapList,
    response_model_exclude_none=True, operation_id="listBusinessMaps", tags=["business-map"],
)
async def list_business_maps(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> BusinessMapList:
    principal = _principal(request)
    _require(principal, "view")
    return await _store(request).list_business_maps(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.post(
    "/business-maps", response_model=BusinessMapDetail, status_code=201,
    response_model_exclude_none=True, operation_id="createBusinessMap", tags=["business-map"],
)
async def create_business_map(body: BusinessMapCreateRequest, request: Request) -> BusinessMapDetail:
    principal = _principal(request)
    _require(principal, "execute")
    return await _store(request).create_business_map(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/business-maps/{id}", response_model=BusinessMapDetail,
    response_model_exclude_none=True, operation_id="getBusinessMap", tags=["business-map"],
)
async def get_business_map(id: UUID, request: Request) -> BusinessMapDetail:
    principal = _principal(request)
    _require(principal, "view")
    return await _store(request).business_map_detail(id, tenant_id=principal.tenant_id)


@router.put(
    "/business-maps/{id}", response_model=BusinessMapDetail,
    response_model_exclude_none=True, operation_id="saveBusinessMap", tags=["business-map"],
)
async def save_business_map(id: UUID, body: BusinessMapSaveRequest, request: Request) -> BusinessMapDetail:
    principal = _principal(request)
    _require(principal, "execute")
    return await _store(request).save_business_map(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/business-maps/{id}", response_model=BusinessMapSummary,
    response_model_exclude_none=True, operation_id="archiveBusinessMap", tags=["business-map"],
)
async def archive_business_map(id: UUID, request: Request) -> BusinessMapSummary:
    principal = _principal(request)
    _require(principal, "execute")
    return await _store(request).archive_business_map(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/business-maps/{id}/revisions", response_model=BusinessMapRevisionList,
    response_model_exclude_none=True, operation_id="listBusinessMapRevisions", tags=["business-map"],
)
async def list_business_map_revisions(id: UUID, request: Request) -> BusinessMapRevisionList:
    principal = _principal(request)
    _require(principal, "view")
    return await _store(request).business_map_revisions(id, tenant_id=principal.tenant_id)


@router.get(
    "/reviews/queue", response_model=ReviewQueue,
    response_model_exclude_none=True, operation_id="getReviewQueue", tags=["reviews"],
)
async def get_review_queue(
    request: Request,
    type: list[ReviewQueueItemType] | None = Query(default=None),
    repository: UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ReviewQueue:
    principal = _principal(request)
    _require(principal, "review")
    return await _store(request).review_queue(
        tenant_id=principal.tenant_id, item_types=type, repository_id=repository,
        cursor=cursor, limit=limit,
    )


# --- Admin: members & roles ---------------------------------------------

@router.get(
    "/admin/members", response_model=TenantMemberList,
    response_model_exclude_none=True, operation_id="listMembers", tags=["admin"],
)
async def list_members(request: Request) -> TenantMemberList:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).list_tenant_members(tenant_id=principal.tenant_id)


@router.post(
    "/admin/members", response_model=TenantMember, status_code=201,
    response_model_exclude_none=True, operation_id="inviteMember", tags=["admin"],
)
async def invite_member(body: MemberInviteRequest, request: Request) -> TenantMember:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).invite_tenant_member(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/members/{id}", response_model=TenantMember,
    response_model_exclude_none=True, operation_id="updateMember", tags=["admin"],
)
async def update_member(id: UUID, body: MemberUpdateRequest, request: Request) -> TenantMember:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).update_tenant_member(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/members/{id}", response_model=TenantMember,
    response_model_exclude_none=True, operation_id="removeMember", tags=["admin"],
)
async def remove_member(id: UUID, request: Request) -> TenantMember:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_tenant_member(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: connectors ---------------------------------------------------

@router.get(
    "/admin/connectors", response_model=ConnectorList,
    response_model_exclude_none=True, operation_id="listConnectors", tags=["admin"],
)
async def list_connectors(request: Request) -> ConnectorList:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).list_connectors(tenant_id=principal.tenant_id)


@router.post(
    "/admin/connectors", response_model=Connector, status_code=201,
    response_model_exclude_none=True, operation_id="registerConnector", tags=["admin"],
)
async def register_connector(body: ConnectorRegisterRequest, request: Request) -> Connector:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).register_connector(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/connectors/{id}", response_model=Connector,
    response_model_exclude_none=True, operation_id="updateConnector", tags=["admin"],
)
async def update_connector(id: UUID, body: ConnectorUpdateRequest, request: Request) -> Connector:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).update_connector(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/connectors/{id}", response_model=Connector,
    response_model_exclude_none=True, operation_id="removeConnector", tags=["admin"],
)
async def remove_connector(id: UUID, request: Request) -> Connector:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_connector(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: scan policy, rescans, and status -----------------------------

@router.get(
    "/admin/scan-policy", response_model=ScanPolicy,
    response_model_exclude_none=True, operation_id="getScanPolicy", tags=["admin"],
)
async def get_scan_policy(request: Request) -> ScanPolicy:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).get_scan_policy(tenant_id=principal.tenant_id)


@router.put(
    "/admin/scan-policy", response_model=ScanPolicy,
    response_model_exclude_none=True, operation_id="updateScanPolicy", tags=["admin"],
)
async def update_scan_policy(body: ScanPolicyUpdateRequest, request: Request) -> ScanPolicy:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).update_scan_policy(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/admin/scan-status", response_model=ScanStatus,
    response_model_exclude_none=True, operation_id="getScanStatus", tags=["admin"],
)
async def get_scan_status(request: Request) -> ScanStatus:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).scan_status(tenant_id=principal.tenant_id)


@router.post(
    "/admin/rescans", response_model=RescanJob,
    response_model_exclude_none=True, operation_id="requestRescan", tags=["admin"],
)
async def request_rescan(body: RescanRequest, request: Request, response: Response) -> RescanJob:
    principal = _principal(request)
    _require(principal, "admin")
    job, created = await _store(request).request_rescan(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    # A fresh job is 201 Created; an idempotent replay returns the existing job as 200 OK.
    response.status_code = 201 if created else 200
    return job


@router.get(
    "/admin/rescans", response_model=RescanJobList,
    response_model_exclude_none=True, operation_id="listRescans", tags=["admin"],
)
async def list_rescans(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> RescanJobList:
    principal = _principal(request)
    _require(principal, "admin")
    return await _store(request).list_rescan_jobs(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )

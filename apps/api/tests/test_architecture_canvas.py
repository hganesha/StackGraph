import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.architecture_catalog import load_architecture_catalog
from app.errors import APIError
from app.models import (
    ArchitectureProfileStateModel,
    ArchitectureProfileCreateRequest,
    ArchitectureProfilePublishRequest,
    ArchitectureProfileUpdateRequest,
    CanvasComparisonRequest,
    CanvasPolicyExceptionModel,
    CanvasProjectionSelectorModel,
    TenantCellPolicyModel,
)
from app.read_models import ReadModelStore, _canvas_policy_applies, _canvas_policy_status
from app.read_models_admin import AdminReadModelsMixin


TENANT_ID = UUID("00000000-0000-4000-8000-000000000123")
TECHNOLOGY_ID = UUID("00000000-0000-4000-8000-000000000456")
APPLICATION_ID = UUID("00000000-0000-4000-8000-000000000789")
NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


class TargetProjectionDatabase:
    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "tenant_architecture_profile" in query:
            state = ArchitectureProfileStateModel(
                name="Default target",
                reference_model_key="architecture.stackgraph.reference",
                reference_model_version="1.0.0",
                cell_policies=[TenantCellPolicyModel(
                    cell_key="cell.application.service",
                    applicability="REQUIRED",
                    minimum_implementations=1,
                    preferred_technology_ids=[TECHNOLOGY_ID],
                    rationale="Standard service runtime.",
                )],
            )
            return {
                "state": state.model_dump(mode="json"),
                "fingerprint": "sha256:" + "a" * 64,
            }
        raise AssertionError(f"unexpected fetch_one query: {query}")

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        if "FROM entity WHERE id=ANY" in query:
            return [{
                "id": TECHNOLOGY_ID,
                "namespace": "TECHNOLOGY",
                "entity_type": "Framework",
                "canonical_key": "framework:fastapi",
                "name": "FastAPI",
                "properties": {},
            }]
        raise AssertionError(f"target projection queried observed evidence: {query}")


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class ProfileConnection:
    def __init__(self, database):
        self.database = database

    async def execute(self, query, params=None):
        params = params or ()
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO tenant_architecture_profile("):
            now = datetime.now(UTC)
            profile = {
                "id": uuid4(), "tenant_id": params[0], "profile_key": params[1],
                "name": params[2], "reference_model_key": params[3],
                "reference_model_version": params[4], "version": 1, "status": "DRAFT",
                "state": json.loads(params[5]), "fingerprint": params[6],
                "created_by": params[7], "updated_by": params[8],
                "created_at": now, "updated_at": now,
            }
            self.database.profile = profile
            return FakeCursor([profile])
        if normalized.startswith("INSERT INTO tenant_architecture_profile_revision("):
            self.database.revisions.append({
                "tenant_id": params[0], "profile_id": params[1], "version": params[2],
                "status": params[3], "state": json.loads(params[4]),
                "fingerprint": params[5], "actor_key": params[6],
            })
            return FakeCursor()
        if normalized.startswith("SELECT * FROM tenant_architecture_profile WHERE id=%s FOR UPDATE"):
            profile = self.database.profile
            return FakeCursor([profile] if profile and profile["id"] == params[0] else [])
        if normalized.startswith("UPDATE tenant_architecture_profile SET name="):
            profile = self.database.profile
            profile.update({
                "name": params[0], "reference_model_key": params[1],
                "reference_model_version": params[2], "version": params[3],
                "state": json.loads(params[4]), "fingerprint": params[5],
                "updated_by": params[6], "updated_at": datetime.now(UTC),
            })
            return FakeCursor([profile])
        if normalized.startswith("SELECT * FROM tenant_architecture_profile WHERE id<>%s"):
            return FakeCursor([])
        if normalized.startswith("UPDATE tenant_architecture_profile SET status='ACTIVE'"):
            profile = self.database.profile
            profile.update({
                "status": "ACTIVE", "version": params[0], "updated_by": params[1],
                "updated_at": datetime.now(UTC),
            })
            return FakeCursor([profile])
        raise AssertionError(f"unexpected profile query: {normalized}")


class ProfileDatabase:
    def __init__(self):
        self.profile = None
        self.revisions = []

    @asynccontextmanager
    async def session(self, tenant_id):
        yield ProfileConnection(self)

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        return [self.profile] if self.profile else []


def test_catalog_is_deep_versioned_and_layout_complete() -> None:
    catalog = load_architecture_catalog()

    assert [domain.key for domain in catalog.taxonomy.domains] == [
        "experience", "application", "integration", "data", "platform", "delivery",
    ]
    assert len(catalog.taxonomy.concerns) == len(catalog.reference_model.cells) == 43
    assert catalog.canonical_capability_key("identity-provider") == "identity-access-services"
    assert catalog.canonical_capability_key("data-orchestration") == "data-movement"
    assert catalog.cells_by_key["cell.delivery.configuration"].bindings[0].keys == [
        "configuration-secret-delivery",
    ]
    layout_keys = {
        cell.cell_key for band in catalog.template.bands for cell in band.cells
    }
    assert layout_keys == set(catalog.cells_by_key)


def test_policy_scope_dates_and_subject_exceptions_are_explicit() -> None:
    policy = TenantCellPolicyModel(
        cell_key="cell.application.service",
        applicability="REQUIRED",
        minimum_implementations=1,
        prohibited_technology_ids=[TECHNOLOGY_ID],
        effective_from=NOW - timedelta(days=1),
        effective_to=NOW + timedelta(days=1),
        scope_selector={"application_ids": [APPLICATION_ID]},
        exceptions=[CanvasPolicyExceptionModel(
            key="approved-migration",
            rationale="Temporary migration window.",
            subject_ids=[APPLICATION_ID],
            effective_to=NOW + timedelta(hours=1),
        )],
    )

    assert _canvas_policy_applies(policy, "APPLICATION", APPLICATION_ID, NOW)
    assert not _canvas_policy_applies(policy, "REPOSITORY", APPLICATION_ID, NOW)
    assert not _canvas_policy_applies(policy, "ESTATE", None, NOW)
    assert _canvas_policy_status(TECHNOLOGY_ID, policy, APPLICATION_ID, NOW) == "EXEMPTED"
    assert _canvas_policy_status(TECHNOLOGY_ID, policy, None, NOW) == "PROHIBITED"


def test_profile_rejects_unknown_reference_cells() -> None:
    state = ArchitectureProfileStateModel(
        name="Invalid profile",
        reference_model_key="architecture.stackgraph.reference",
        reference_model_version="1.0.0",
        cell_policies=[TenantCellPolicyModel(
            cell_key="cell.application.missing",
            applicability="OPTIONAL",
        )],
    )

    with pytest.raises(APIError) as error:
        AdminReadModelsMixin._validate_architecture_profile_state(state)

    assert error.value.code == "ARCHITECTURE_PROFILE_UNKNOWN_CELL"


def test_target_projection_uses_policy_provenance_without_fact_citations() -> None:
    store = ReadModelStore(TargetProjectionDatabase())
    projection = asyncio.run(store.canvas_projection(
        CanvasProjectionSelectorModel(scope="TARGET"),
        tenant_id=TENANT_ID,
        reference_model_key="architecture.stackgraph.reference",
        template_key="canvas.stackgraph.reference",
    ))

    service = next(cell for cell in projection.cells if cell.cell_key == "cell.application.service")
    assert projection.scope == "TARGET"
    assert projection.tenant_profile_fingerprint == "sha256:" + "a" * 64
    assert service.state == "POPULATED"
    assert service.occupants[0].technology.name == "FastAPI"
    assert service.occupants[0].policy_status == "PREFERRED"
    assert service.occupants[0].citations == []
    assert service.occupants[0].policy_reference == projection.tenant_profile_fingerprint
    assert service.observation.status == "NOT_APPLICABLE"


def test_profile_lifecycle_is_versioned_and_optimistically_guarded() -> None:
    database = ProfileDatabase()
    store = ReadModelStore(database)
    initial_state = ArchitectureProfileStateModel(
        name="Enterprise target",
        reference_model_key="architecture.stackgraph.reference",
        reference_model_version="1.0.0",
    )
    created = asyncio.run(store.create_architecture_profile(
        ArchitectureProfileCreateRequest(profile_key="enterprise.target", state=initial_state),
        tenant_id=TENANT_ID, actor_key="architect",
    ))
    updated_state = initial_state.model_copy(update={
        "cell_policies": [TenantCellPolicyModel(
            cell_key="cell.application.service",
            applicability="REQUIRED",
            minimum_implementations=1,
            preferred_technology_ids=[TECHNOLOGY_ID],
        )],
    })
    updated = asyncio.run(store.update_architecture_profile(
        created.id,
        ArchitectureProfileUpdateRequest(expected_version=1, state=updated_state),
        tenant_id=TENANT_ID, actor_key="architect",
    ))
    with pytest.raises(APIError) as conflict:
        asyncio.run(store.update_architecture_profile(
            created.id,
            ArchitectureProfileUpdateRequest(expected_version=1, state=updated_state),
            tenant_id=TENANT_ID, actor_key="architect",
        ))
    published = asyncio.run(store.publish_architecture_profile(
        created.id, ArchitectureProfilePublishRequest(expected_version=2),
        tenant_id=TENANT_ID, actor_key="architect",
    ))
    listed = asyncio.run(store.list_architecture_profiles(tenant_id=TENANT_ID))

    assert updated.version == 2
    assert conflict.value.code == "VERSION_CONFLICT"
    assert published.status == "ACTIVE" and published.version == 3
    assert [revision["status"] for revision in database.revisions] == [
        "DRAFT", "DRAFT", "ACTIVE",
    ]
    assert listed.profiles[0].fingerprint == published.fingerprint


def test_comparison_contract_reserves_unimplemented_time_travel() -> None:
    with pytest.raises(ValidationError):
        CanvasComparisonRequest(
            comparison_kind="TIME_TO_TIME",
            actual=CanvasProjectionSelectorModel(scope="ESTATE"),
            baseline=CanvasProjectionSelectorModel(scope="ESTATE"),
        )

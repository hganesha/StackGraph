from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.estate_fidelity import EstateFidelityMixin
from app.models import (
    ContainerCompositionList,
    ContainerImageIdentity,
    ContradictionLedger,
    DeploymentProfileList,
    EstateComponentList,
    EstateStrata,
)
from tests.test_api import app_with_stubs, request


NOW = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)
REPOSITORY_ID = UUID("00000000-0000-4000-8000-000000000701")
COMPONENT_ID = UUID("00000000-0000-4000-8000-000000000702")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000703")
FIXTURES = Path(__file__).parents[3] / "packages" / "shared" / "src" / "fixtures"


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("phase2-estate-components.json", EstateComponentList),
        ("phase2-container-compositions.json", ContainerCompositionList),
        ("phase2-deployment-profiles.json", DeploymentProfileList),
        ("phase2-estate-strata.json", EstateStrata),
        ("phase2-contradictions.json", ContradictionLedger),
    ],
)
def test_fixture_conforms_to_api_model(name: str, model: type) -> None:
    model.model_validate(json.loads((FIXTURES / name).read_text()))


def test_estate_fidelity_routes_publish_typed_missing_states() -> None:
    app, _ = app_with_stubs()

    strata = asyncio.run(request(app, "GET", "/api/v1/estate/strata"))
    contradictions = asyncio.run(request(app, "GET", "/api/v1/contradictions"))
    components = asyncio.run(request(app, "GET", "/api/v1/components"))
    component = asyncio.run(request(app, "GET", f"/api/v1/components/{COMPONENT_ID}"))
    containers = asyncio.run(request(
        app, "GET", f"/api/v1/repositories/{REPOSITORY_ID}/container-compositions",
    ))
    deployments = asyncio.run(request(
        app, "GET", f"/api/v1/repositories/{REPOSITORY_ID}/deployment-profiles",
    ))

    assert strata.status_code == 200
    assert [layer["key"] for layer in strata.json()["layers"]] == [
        "BUSINESS", "ENTERPRISE", "TECHNOLOGY", "OSS", "DEPLOYMENT", "AI",
    ]
    assert strata.json()["layers"][-1]["status"] == "NOT_COLLECTED"
    assert contradictions.status_code == 200
    assert contradictions.json()["contradictions"] == []
    assert components.status_code == 200
    assert components.json()["components"] == []
    assert component.status_code == 200
    assert component.json()["component"]["component"]["id"] == str(COMPONENT_ID)
    assert containers.status_code == 200
    assert containers.json()["status"] == "NOT_COLLECTED"
    assert containers.json()["images"] == []
    assert deployments.status_code == 200
    assert deployments.json()["profiles"] == []


def test_openapi_exposes_estate_fidelity_resources() -> None:
    app, _ = app_with_stubs()
    document = app.openapi()

    assert document["paths"]["/components"]["get"]["operationId"] == "listComponents"
    assert document["paths"]["/components/{id}"]["get"]["operationId"] == "getComponent"
    assert document["paths"]["/contradictions"]["get"]["operationId"] == "listContradictions"
    assert document["paths"]["/repositories/{id}/container-compositions"]["get"]["operationId"] == "listRepositoryContainerCompositions"
    assert document["paths"]["/repositories/{id}/deployment-profiles"]["get"]["operationId"] == "listRepositoryDeploymentProfiles"
    assert document["paths"]["/estate/strata"]["get"]["operationId"] == "getEstateStrata"
    layer_schema = document["components"]["schemas"]["EstateStratumLayer"]
    assert layer_schema["properties"]["key"]["enum"][-1] == "AI"
    assert "INTELLIGENCE" not in layer_schema["properties"]["key"]["enum"]


def test_container_digest_is_resolved_and_latest_is_not() -> None:
    digest = "sha256:" + "a" * 64
    resolved = EstateFidelityMixin._container({
        "id": IMAGE_ID,
        "entity_type": "ContainerImage",
        "name": "checkout",
        "canonical_key": f"registry.example/checkout@{digest}",
        "properties": {
            "digest": digest,
            "observed_tags": ["2026.09.05"],
            "registry": "registry.example",
            "packages": [{"name": "openssl", "version": "3.4.1", "ecosystem": "apk"}],
        },
        "observed_at": NOW,
        "relationship_confidence": 0.99,
        "fact_assertion_id": UUID("00000000-0000-4000-8000-000000000704"),
    })
    latest = EstateFidelityMixin._container({
        "id": IMAGE_ID,
        "entity_type": "ContainerImage",
        "name": "checkout",
        "canonical_key": "registry.example/checkout:latest",
        "properties": {"observed_tags": ["latest"]},
        "observed_at": NOW,
        "relationship_confidence": 0.8,
    })

    assert resolved.identity.state == "RESOLVED"
    assert resolved.identity.digest == digest
    assert resolved.scan_status == "AVAILABLE"
    assert latest.identity.state == "UNRESOLVED"
    assert latest.identity.canonical_reference is None
    assert latest.scan_status == "PARTIAL"
    assert latest.limitations[0].code == "CONTAINER_IDENTITY_UNRESOLVED"


def test_resolved_container_identity_requires_an_immutable_digest() -> None:
    with pytest.raises(ValidationError, match="immutable digest"):
        ContainerImageIdentity(state="RESOLVED", canonical_reference="registry/image:1")


def test_deployment_profile_uses_verb_and_target_rows() -> None:
    profile = EstateFidelityMixin._deployment({
        "id": UUID("00000000-0000-4000-8000-000000000705"),
        "entity_type": "Deployment",
        "name": "checkout-production",
        "canonical_key": "deployment:checkout-production",
        "properties": {
            "provider": "Vercel",
            "workload_kind": "Web service",
            "environment": "production",
            "actions": [
                {"verb": "DEPLOYS_TO", "target": "Vercel", "target_kind": "PROVIDER"},
                {"verb": "RUNS_JOBS_ON", "target": "Databricks", "target_kind": "JOB_PLATFORM"},
            ],
            "confidence": 0.91,
        },
        "observed_at": NOW,
    })

    assert profile.status == "AVAILABLE"
    assert [(action.verb, action.target) for action in profile.actions] == [
        ("DEPLOYS_TO", "Vercel"), ("RUNS_JOBS_ON", "Databricks"),
    ]

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agent_control import _fingerprint
from app.models import (
    AgentOperationRequest,
    CapabilityBandModel,
    CapabilityEnvelopeCompileRequest,
    CapabilityEnvelopeModel,
)
from tests.test_api import app_with_stubs, request


NOW = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
ENVELOPE_ID = UUID("00000000-0000-4000-8000-000000000a01")
MIGRATION = Path(__file__).parents[3] / "infrastructure/database/migrations/055_e1_estate_fidelity_and_agent_control.sql"


def test_compile_request_rejects_duplicate_operations() -> None:
    with pytest.raises(ValidationError, match="operation keys must be unique"):
        CapabilityEnvelopeCompileRequest(
            objective="Inspect estate", environment="test", estate_watermark="test:1",
            risk_tier="TIER_3", context_confidence=1,
            operations=[
                AgentOperationRequest(operation_key="estate.read", requested_band="READ"),
                AgentOperationRequest(operation_key="estate.read", requested_band="READ"),
            ],
        )


def test_envelope_requires_the_five_canonical_bands() -> None:
    with pytest.raises(ValidationError, match="at least 5 items|all five bands"):
        CapabilityEnvelopeModel(
            id=ENVELOPE_ID, actor_key="agent", objective="Inspect estate", environment="test",
            estate_watermark="test:1", risk_tier="TIER_3", context_confidence=1,
            decision="ALLOW", bands=[CapabilityBandModel(band="READ")], status="ACTIVE",
            valid_until=NOW, compiled_hash="sha256:" + "a" * 64, created_at=NOW,
        )


def test_hashing_is_canonical_and_sensitive_to_event_order() -> None:
    assert _fingerprint({"a": 1, "b": [2, 3]}) == _fingerprint({"b": [2, 3], "a": 1})
    assert _fingerprint({"events": ["context", "action"]}) != _fingerprint({
        "events": ["action", "context"],
    })


def test_agent_control_routes_expose_default_deny_and_authorization() -> None:
    app, store = app_with_stubs()
    compiled = asyncio.run(request(
        app, "POST", "/api/v1/agent-control/envelopes",
        json={
            "objective": "Read the estate", "environment": "test", "estate_watermark": "test:1",
            "risk_tier": "TIER_3", "context_confidence": 1,
            "operations": [{"operation_key": "estate.read", "requested_band": "READ"}],
        },
    ))
    authorized = asyncio.run(request(
        app, "POST", f"/api/v1/agent-control/envelopes/{ENVELOPE_ID}/authorize",
        json={"operation_key": "estate.read", "request_payload": {}},
    ))
    switch = asyncio.run(request(app, "GET", "/api/v1/agent-control/kill-switch"))

    assert compiled.status_code == 201
    assert [band["band"] for band in compiled.json()["bands"]] == [
        "READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE",
    ]
    assert authorized.status_code == 200
    assert authorized.json()["decision"] == "ALLOW"
    assert switch.status_code == 200
    assert switch.json()["engaged"] is True
    assert switch.json()["version"] == 0
    assert store.last_actor_key == "local-user"


def test_openapi_exposes_r16_and_e1_governance_operations() -> None:
    app, _ = app_with_stubs()
    document = app.openapi()
    expected = {
        "/assumptions": {"get": "listAssumptions", "post": "createAssumption"},
        "/contradictions/{id}/resolve": {"post": "resolveContradiction"},
        "/estate/lineage": {"get": "listEstateLineage"},
        "/estate/ai-supply-chain": {"get": "getAISupplyChain"},
        "/agent-control/envelopes": {"post": "compileCapabilityEnvelope"},
        "/agent-control/envelopes/{id}/authorize": {"post": "authorizeAgentOperation"},
        "/agent-control/kill-switch": {
            "get": "getAgentKillSwitch", "put": "updateAgentKillSwitch",
        },
        "/agent-control/flight-records/{id}/events": {"post": "appendFlightEvent"},
        "/agent-control/drills": {"post": "runAgentControlDrill"},
    }
    for path, methods in expected.items():
        for method, operation_id in methods.items():
            assert document["paths"][path][method]["operationId"] == operation_id


def test_migration_is_default_deny_tenant_safe_and_append_only() -> None:
    sql = MIGRATION.read_text()
    assert "engaged boolean NOT NULL DEFAULT true" in sql
    assert "'agent_flight_event','agent_control_drill'" in sql
    assert "ALTER TABLE %I FORCE ROW LEVEL SECURITY" in sql
    assert "trg_agent_authorization_immutable" in sql
    assert "trg_agent_flight_event_immutable" in sql
    assert "compiled_hash" in sql
    assert "previous_hash" in sql and "event_hash" in sql

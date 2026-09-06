import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.errors import APIError
from app.models import MutationCompileRequest, ObservedMutationCreateRequest
from app.read_models import ReadModelStore


TENANT_ID = UUID("00000000-0000-4000-8000-00000000a001")
PACKAGE_ID = UUID("00000000-0000-4000-8000-00000000a002")
TARGET_ID = UUID("00000000-0000-4000-8000-00000000a003")
SECOND_TARGET_ID = UUID("00000000-0000-4000-8000-00000000a004")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-00000000a005")
FACT_ID = UUID("00000000-0000-4000-8000-00000000a006")
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        row, self.row = self.row, None
        return row


class Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, *_):
        return False


class CompilerDatabase:
    def __init__(self, *, observed_version="1.0.0", contradictions=None):
        self.observed_version = observed_version
        self.contradictions = contradictions or []
        self.change_set = None
        self.mutation_id = None
        self.audit_actions = []

    def session(self, tenant_id):
        assert tenant_id == TENANT_ID
        return Session(self)

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "FROM phase2_feature_flag" in query:
            return {"enabled": True}
        raise AssertionError(f"unexpected fetch_one: {query}")

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        assert tenant_id == TENANT_ID
        if "WHERE e.id=%s AND e.entity_type='Package'" in query:
            return [{
                "id": PACKAGE_ID, "entity_type": "Package", "name": "demo-package",
                "canonical_key": "pkg:npm/demo-package", "package_name": "demo-package",
                "evidence_fact_ids": [FACT_ID],
            }]
        if "SELECT e.id,e.canonical_key,pri.package_version" in query:
            return [
                {
                    "id": TARGET_ID, "canonical_key": "pkg:npm/demo-package@2.0.0",
                    "package_version": "2.0.0", "observed_at": NOW,
                    "registry_key": "npm-public",
                },
                {
                    "id": SECOND_TARGET_ID, "canonical_key": "pkg:npm/demo-package@3.0.0",
                    "package_version": "3.0.0", "observed_at": NOW,
                    "registry_key": "npm-public",
                },
            ]
        if "SELECT f.id fact_id,consumer.id" in query:
            return [{
                "fact_id": FACT_ID, "id": REPOSITORY_ID, "entity_type": "Repository",
                "name": "checkout", "canonical_key": "github:repo:acme/checkout",
                "component_path": "apps/api", "version": self.observed_version,
            }]
        if "FROM estate_contradiction contradiction" in query:
            return self.contradictions
        raise AssertionError(f"unexpected fetch_all: {query}")

    async def execute(self, query, params=None):
        if "SELECT id,input_fingerprint,idempotency_key,created_at" in query:
            if self.change_set is None:
                return Cursor()
            _, key, fingerprint, _ = params
            if key == self.change_set["idempotency_key"] or fingerprint == self.change_set["input_fingerprint"]:
                return Cursor(dict(self.change_set))
            return Cursor()
        if "INSERT INTO change_set" in query:
            self.change_set = {
                "id": params[0], "input_fingerprint": params[2],
                "idempotency_key": params[3], "created_at": params[6],
            }
            return Cursor()
        if "INSERT INTO mutation" in query:
            self.mutation_id = params[0]
            return Cursor()
        if "SELECT id FROM mutation" in query:
            return Cursor({"id": self.mutation_id})
        if "INSERT INTO admin_audit_log" in query:
            self.audit_actions.append(params[2])
            return Cursor()
        raise AssertionError(f"unexpected execute: {query}")


def compile_request(*, key="compile-1", target="2.0.0"):
    return MutationCompileRequest(
        predicate="UPGRADE", subject_id=PACKAGE_ID, target_version=target,
        scope_id=f"component:{REPOSITORY_ID}:apps/api", idempotency_key=key,
    )


def test_compiler_is_semantically_idempotent_across_request_keys() -> None:
    database = CompilerDatabase()
    store = ReadModelStore(database)

    first = asyncio.run(store.compile_mutation(
        compile_request(key="first"), tenant_id=TENANT_ID, actor_key="reviewer",
    ))
    replay = asyncio.run(store.compile_mutation(
        compile_request(key="second"), tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    assert first.command_state == "COMPILED"
    assert first.gate.state == "CLEAR"
    assert first.change_set is not None
    assert first.change_set.mutations[0].scope.component_path == "apps/api"
    assert replay.replayed is True
    assert replay.change_set.id == first.change_set.id
    assert database.audit_actions == ["change_set.compile", "change_set.compile"]


def test_compiler_rejects_noop_upgrade_with_cited_reason() -> None:
    database = CompilerDatabase(observed_version="2.0.0")
    result = asyncio.run(ReadModelStore(database).compile_mutation(
        compile_request(), tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    assert result.command_state == "TOKENISED"
    assert result.change_set is None
    assert result.gate.state == "BLOCKED"
    assert result.draft.lifecycle == "REJECTED"
    assert result.gate.reasons[0].code == "ALREADY_AT_TARGET"
    assert result.gate.reasons[0].evidence_fact_ids == [FACT_ID]
    assert database.audit_actions == ["change_set.compile_blocked"]


def test_compiler_blocks_mutation_affected_by_open_contradiction() -> None:
    database = CompilerDatabase(contradictions=[{
        "id": UUID("00000000-0000-4000-8000-00000000a007"),
        "evidence_fact_ids": [FACT_ID],
    }])
    result = asyncio.run(ReadModelStore(database).compile_mutation(
        compile_request(), tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    assert result.change_set is None
    assert result.gate.state == "BLOCKED"
    assert [reason.code for reason in result.gate.reasons] == ["UNRESOLVED_CONTRADICTION"]
    assert result.gate.reasons[0].evidence_fact_ids == [FACT_ID]


def test_compiler_rejects_reused_key_for_different_semantics() -> None:
    database = CompilerDatabase()
    store = ReadModelStore(database)
    asyncio.run(store.compile_mutation(
        compile_request(key="same", target="2.0.0"),
        tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    with pytest.raises(APIError) as raised:
        asyncio.run(store.compile_mutation(
            compile_request(key="same", target="3.0.0"),
            tenant_id=TENANT_ID, actor_key="reviewer",
        ))

    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"


def test_tenant_feature_override_is_authoritative() -> None:
    class FeatureDatabase:
        async def fetch_one(self, query, params=None, *, tenant_id=None):
            assert "ORDER BY (tenant_id IS NOT NULL) DESC" in query
            assert params == ("CHANGE_SIMULATION", TENANT_ID)
            assert tenant_id == TENANT_ID
            return {"enabled": False}

    enabled = asyncio.run(ReadModelStore(FeatureDatabase()).phase2_feature_enabled(
        "CHANGE_SIMULATION", tenant_id=TENANT_ID,
    ))
    assert enabled is False


def test_observed_outcome_rejects_missing_tenant_evidence() -> None:
    class OutcomeDatabase:
        async def fetch_one(self, query, params=None, *, tenant_id=None):
            assert "FROM fact_assertion" in query
            return {"matched": 0}

    request = ObservedMutationCreateRequest(
        correlation_key="deployment:123", source_kind="DEPLOYMENT", predicate="UPGRADE",
        subject_entity_id=PACKAGE_ID, before={"version": "1.0.0"},
        after={"version": "2.0.0"}, scope={"kind": "COMPONENT"},
        observed_impact={"deployments": 1}, evidence_fact_ids=[FACT_ID],
        confidence=0.95, observed_at=NOW,
    )
    with pytest.raises(APIError) as raised:
        asyncio.run(ReadModelStore(OutcomeDatabase()).record_observed_mutation(
            request, tenant_id=TENANT_ID, actor_key="reviewer",
        ))

    assert raised.value.code == "OUTCOME_EVIDENCE_NOT_FOUND"

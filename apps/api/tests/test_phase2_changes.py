import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.errors import APIError
from app.models import (
    ChangeSetCompileRequest,
    ChangeSetMutationRequest,
    MutationCompileRequest,
    ObservedMutationCreateRequest,
)
from app.read_models import ReadModelStore


TENANT_ID = UUID("00000000-0000-4000-8000-00000000a001")
PACKAGE_ID = UUID("00000000-0000-4000-8000-00000000a002")
TARGET_ID = UUID("00000000-0000-4000-8000-00000000a003")
SECOND_TARGET_ID = UUID("00000000-0000-4000-8000-00000000a004")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-00000000a005")
FACT_ID = UUID("00000000-0000-4000-8000-00000000a006")
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    async def fetchone(self):
        row, self.row = self.row, None
        return row

    async def fetchall(self):
        return list(self.rows)


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
        self.mutation_ids = []
        self.mutation_ordinals = []
        self.audit_actions = []

    def session(self, tenant_id):
        assert tenant_id == TENANT_ID
        return Session(self)

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "FROM phase2_feature_flag" in query:
            return {"enabled": True}
        if "FROM action_capability" in query:
            # Compilation is now governed by the registered capability rather than a hardcoded
            # predicate check, so the double has to serve the row the compiler reads.
            return {
                "predicate": "UPGRADE", "subject_type": "Package", "lifecycle": "ACTIVE",
                "validation_rules": {"max_mutations": 20},
            }
        raise AssertionError(f"unexpected fetch_one: {query}")

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        assert tenant_id == TENANT_ID
        if "WHERE e.id=%s AND e.entity_type='Package'" in query:
            return [{
                "id": PACKAGE_ID, "entity_type": "Package", "name": "demo-package",
                "canonical_key": "pkg:npm/demo-package", "package_name": "demo-package",
                "evidence_fact_ids": [FACT_ID],
            }]
        if "count(DISTINCT f.subject_entity_id)::int repositories" in query:
            # The estate's own version spread, which decides the consolidation target.
            return [{"version": self.observed_version, "repositories": 3}]
        if "SELECT e.id,e.canonical_key,pri.package_version" in query:
            return [
                {
                    "id": TARGET_ID, "canonical_key": "pkg:npm/demo-package@2.0.0",
                    "package_version": "2.0.0", "observed_at": NOW,
                    "registry_key": "npm-public", "support_status": "SUPPORTED",
                },
                {
                    "id": SECOND_TARGET_ID, "canonical_key": "pkg:npm/demo-package@3.0.0",
                    "package_version": "3.0.0", "observed_at": NOW,
                    "registry_key": "npm-public", "support_status": "UNKNOWN",
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
            # A ChangeSet now records whether it is atomic, so the fingerprint and key sit one
            # position later than they did when every set held exactly one mutation.
            self.change_set = {
                "id": params[0], "atomic": params[2], "input_fingerprint": params[3],
                "idempotency_key": params[4], "created_at": params[7],
            }
            return Cursor()
        if "INSERT INTO mutation" in query:
            self.mutation_ids.append(params[0])
            self.mutation_ordinals.append(params[3])
            return Cursor()
        if "SELECT id FROM mutation" in query:
            return Cursor(rows=[{"id": value} for value in self.mutation_ids])
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


def change_set_request(mutations, *, key="pr-1", entry_point="PULL_REQUEST", reference="#42"):
    return ChangeSetCompileRequest(
        entry_point=entry_point, external_reference=reference,
        idempotency_key=key,
        mutations=[
            ChangeSetMutationRequest(
                predicate="UPGRADE", subject_id=PACKAGE_ID, target_version=target,
                scope_id=scope,
            )
            for target, scope in mutations
        ],
    )


COMPONENT_SCOPE = f"component:{REPOSITORY_ID}:apps/api"


def test_a_pull_request_compiles_into_a_change_set_through_the_same_mutation_ir() -> None:
    database = CompilerDatabase()
    result = asyncio.run(ReadModelStore(database).compile_change_set(
        change_set_request([("2.0.0", COMPONENT_SCOPE)]),
        tenant_id=TENANT_ID, actor_key="ci",
    ))

    assert result.command_state == "COMPILED"
    assert result.change_set is not None
    # §7's point: the source differs, the intermediate representation does not.
    assert result.draft.provenance["entry_point"] == "PULL_REQUEST"
    assert result.draft.provenance["external_reference"] == "#42"
    assert result.draft.predicate == "UPGRADE"


def test_a_change_set_persists_every_mutation_in_order() -> None:
    database = CompilerDatabase()
    result = asyncio.run(ReadModelStore(database).compile_change_set(
        change_set_request([("2.0.0", COMPONENT_SCOPE), ("3.0.0", "estate")]),
        tenant_id=TENANT_ID, actor_key="ci",
    ))

    assert result.change_set is not None
    assert len(result.change_set.mutations) == 2
    assert database.mutation_ordinals == [0, 1]
    # Distinct identities, so a finding can point at the mutation that produced it.
    assert len(set(database.mutation_ids)) == 2


def test_two_mutations_on_one_subject_and_scope_with_different_targets_are_refused() -> None:
    database = CompilerDatabase()
    result = asyncio.run(ReadModelStore(database).compile_change_set(
        change_set_request([("2.0.0", COMPONENT_SCOPE), ("3.0.0", COMPONENT_SCOPE)]),
        tenant_id=TENANT_ID, actor_key="ci",
    ))

    # The set's effect would otherwise depend on the order it happened to be applied in.
    assert result.gate.state == "BLOCKED"
    assert "CONFLICTING_MUTATIONS" in [reason.code for reason in result.gate.reasons]
    assert result.change_set is None
    assert database.change_set is None


def test_the_same_mutation_listed_twice_is_refused() -> None:
    database = CompilerDatabase()
    result = asyncio.run(ReadModelStore(database).compile_change_set(
        change_set_request([("2.0.0", COMPONENT_SCOPE), ("2.0.0", COMPONENT_SCOPE)]),
        tenant_id=TENANT_ID, actor_key="ci",
    ))

    assert result.gate.state == "BLOCKED"
    assert "DUPLICATE_MUTATION" in [reason.code for reason in result.gate.reasons]


def test_one_blocked_mutation_blocks_the_whole_atomic_set() -> None:
    database = CompilerDatabase()
    result = asyncio.run(ReadModelStore(database).compile_change_set(
        change_set_request([("2.0.0", COMPONENT_SCOPE), ("9.9.9", "estate")]),
        tenant_id=TENANT_ID, actor_key="ci",
    ))

    # Persisting the valid half would offer a plan whose stated scope is not the plan that runs.
    assert result.gate.state == "BLOCKED"
    assert "TARGET_NOT_RESOLVED" in [reason.code for reason in result.gate.reasons]
    assert database.change_set is None
    assert database.mutation_ids == []


def test_a_change_set_larger_than_the_capability_allows_is_refused() -> None:
    class SmallLimitDatabase(CompilerDatabase):
        async def fetch_one(self, query, params=None, *, tenant_id=None):
            if "FROM action_capability" in query:
                return {
                    "predicate": "UPGRADE", "subject_type": "Package", "lifecycle": "ACTIVE",
                    "validation_rules": {"max_mutations": 1},
                }
            return await super().fetch_one(query, params, tenant_id=tenant_id)

    with pytest.raises(APIError) as raised:
        asyncio.run(ReadModelStore(SmallLimitDatabase()).compile_change_set(
            change_set_request([("2.0.0", COMPONENT_SCOPE), ("3.0.0", "estate")]),
            tenant_id=TENANT_ID, actor_key="ci",
        ))

    # The bound comes from the registered capability, not from a constant in the compiler.
    assert raised.value.code == "CHANGE_SET_TOO_LARGE"


def test_a_disabled_capability_refuses_compilation() -> None:
    class DisabledDatabase(CompilerDatabase):
        async def fetch_one(self, query, params=None, *, tenant_id=None):
            if "FROM action_capability" in query:
                return {
                    "predicate": "REPLACE", "subject_type": "Package", "lifecycle": "DISABLED",
                    "validation_rules": {},
                }
            return await super().fetch_one(query, params, tenant_id=tenant_id)

    result = asyncio.run(ReadModelStore(DisabledDatabase()).compile_mutation(
        compile_request(), tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    assert result.gate.state == "BLOCKED"
    assert "ACTION_NOT_ENABLED" in [reason.code for reason in result.gate.reasons]


def test_a_predicate_with_no_registered_capability_refuses_compilation() -> None:
    class UnregisteredDatabase(CompilerDatabase):
        async def fetch_one(self, query, params=None, *, tenant_id=None):
            if "FROM action_capability" in query:
                return None
            return await super().fetch_one(query, params, tenant_id=tenant_id)

    result = asyncio.run(ReadModelStore(UnregisteredDatabase()).compile_mutation(
        compile_request(), tenant_id=TENANT_ID, actor_key="reviewer",
    ))

    assert result.gate.state == "BLOCKED"
    assert "ACTION_NOT_ENABLED" in [reason.code for reason in result.gate.reasons]


def test_target_list_labels_the_consolidation_target_from_the_estate_spread() -> None:
    database = CompilerDatabase(observed_version="2.0.0")
    result = asyncio.run(ReadModelStore(database).valid_targets(
        PACKAGE_ID, tenant_id=TENANT_ID, limit=10,
    ))

    by_version = {target.version: target for target in result.targets}
    assert by_version["2.0.0"].recommendation == "CONSOLIDATE"
    assert by_version["2.0.0"].observed_repository_count == 3
    assert "3 repositories already run this version" in by_version["2.0.0"].recommendation_detail
    # 3.0.0 is higher and nothing runs it, so it is the candidate rather than the safe target.
    assert by_version["3.0.0"].observed_repository_count == 0


def test_support_status_is_read_rather_than_assumed() -> None:
    database = CompilerDatabase(observed_version="2.0.0")
    result = asyncio.run(ReadModelStore(database).valid_targets(
        PACKAGE_ID, tenant_id=TENANT_ID, limit=10,
    ))

    by_version = {target.version: target for target in result.targets}
    assert by_version["2.0.0"].support == "SUPPORTED"
    # Unknown support is not supported. Silence is not a clearance.
    assert by_version["3.0.0"].support == "UNKNOWN"


def test_coverage_says_when_a_target_list_is_only_what_the_estate_runs() -> None:
    class EstateOnlyDatabase(CompilerDatabase):
        async def fetch_all(self, query, params=None, *, tenant_id=None):
            rows = await super().fetch_all(query, params, tenant_id=tenant_id)
            if "count(DISTINCT f.subject_entity_id)::int repositories" in query:
                # Every collected version is one the estate runs.
                return [
                    {"version": "2.0.0", "repositories": 3},
                    {"version": "3.0.0", "repositories": 1},
                ]
            return rows

    result = asyncio.run(ReadModelStore(EstateOnlyDatabase()).valid_targets(
        PACKAGE_ID, tenant_id=TENANT_ID, limit=10,
    ))

    assert result.coverage is not None
    assert result.coverage.source == "ESTATE_OBSERVED"
    assert result.coverage.registry_enumeration == "NOT_COLLECTED"
    # A short list must not read as a short registry.
    assert "TARGET_PROVIDER_ESTATE_ONLY" in [item.code for item in result.limitations]


def test_coverage_reports_registry_enrichment_when_a_target_exceeds_the_estate() -> None:
    result = asyncio.run(ReadModelStore(CompilerDatabase(observed_version="2.0.0")).valid_targets(
        PACKAGE_ID, tenant_id=TENANT_ID, limit=10,
    ))

    assert result.coverage is not None
    assert result.coverage.registry_enumeration == "AVAILABLE"
    assert "TARGET_PROVIDER_ESTATE_ONLY" not in [item.code for item in result.limitations]

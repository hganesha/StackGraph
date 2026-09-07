from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.errors import APIError
from app.immune_system import GENERATOR_VERSION
from app.models import (
    ADVERSARIAL_SCENARIO_CLASSES,
    GateReason,
    HarnessPromotionModel,
    AdversarialScenarioGenerateRequest,
    AdversarialScenarioList,
    HarnessEvaluationCompleteRequest,
    HarnessEvaluationModel,
    HarnessEvaluationRecordRequest,
    HarnessEvaluationStartRequest,
    HarnessPromotionDecisionRequest,
    HarnessPromotionProposeRequest,
    HarnessPromotionRollbackRequest,
    PromotionGate,
    PromotionPosture,
    ScenarioClassCoverage,
)
from app.read_models import ReadModelStore
from tests.test_api import app_with_stubs, request
from tests.repository_paths import migrations_directory


TENANT = UUID("00000000-0000-0000-0000-000000000001")
EVALUATION = UUID("00000000-0000-4000-8000-000000000b01")
SCENARIO = UUID("00000000-0000-4000-8000-000000000c01")
ENTITY = UUID("00000000-0000-4000-8000-000000000d01")
FACT = UUID("00000000-0000-4000-8000-000000000e01")
NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
MIGRATION = migrations_directory() / "059_adversarial_evaluation.sql"
PROMOTION_MIGRATION = migrations_directory() / "062_harness_promotion.sql"


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    async def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    async def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class _Session:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_):
        return False


class FakeDatabase:
    """Matches queries by fragment so a test states only the rows it cares about."""

    def __init__(self, handlers):
        self.handlers = list(handlers)
        self.executed: list[tuple[str, object]] = []

    def _rows(self, query, params):
        for fragment, rows in self.handlers:
            if fragment in query:
                return rows(params) if callable(rows) else rows
        raise AssertionError(f"unhandled query: {query}")

    def session(self, _tenant_id=None):
        return _Session(self)

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        return _Cursor(self._rows(query, params))

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        rows = self._rows(query, params)
        return rows[0] if rows else None

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        return list(self._rows(query, params))


def _scenario_row(params):
    """Build the stored row from the INSERT parameters, which pins their order."""
    (
        _tenant, key, scenario_class, title, description, stimulus, expected, entity_id,
        evidence, severity, generator_version, watermark, fingerprint,
    ) = params
    return [{
        "id": SCENARIO, "scenario_key": key, "scenario_class": scenario_class, "title": title,
        "description": description, "stimulus": stimulus.obj, "expected_behaviour": expected.obj,
        "derived_from_entity_id": entity_id, "evidence_fact_ids": list(evidence),
        "severity": severity, "generator_version": generator_version,
        "estate_watermark": watermark, "input_fingerprint": fingerprint, "created_at": NOW,
    }]


EMPTY_GENERATORS = [
    ("estate_contradiction contradiction", []),
    ("package_catalog_collection", []),
    ("simulation_interpretation", []),
    ("entity_type='Database'", []),
    ("GROUNDED_BY", []),
    ("FROM mutation", []),
    ("estate_deployment_profile", []),
]


def _generation_database(*, stale_rows, enabled=True, watermark="2026-09-06T09:00:00+00:00"):
    return FakeDatabase([
        ("phase2_feature_flag", [{"enabled": enabled}]),
        ("projection_outbox", [{
            "fact_watermark": watermark, "projection_watermark": "412",
        }]),
        ("JOIN fact_assertion fact\n              ON fact.subject_entity_id", stale_rows),
        *EMPTY_GENERATORS,
        ("INSERT INTO adversarial_scenario", _scenario_row),
        ("INSERT INTO admin_audit_log", []),
    ])


def _stale_row(days):
    return {
        "entity_id": ENTITY, "name": "billing-api", "entity_type": "Repository",
        "newest_observation": NOW - timedelta(days=days), "fact_count": 42,
        "fact_ids": [FACT],
    }


# -- what the contract refuses to express ------------------------------------------------------


def test_coverage_must_account_for_every_scenario_class() -> None:
    with pytest.raises(ValidationError, match="every adversarial scenario class"):
        AdversarialScenarioList(
            generation_enabled=True,
            coverage=[
                ScenarioClassCoverage(
                    scenario_class="STALE_CONTEXT", status="NOT_DERIVABLE", scenario_count=0,
                    detail="nothing derived",
                ),
            ] * 8,
        )


def test_a_failed_scenario_cannot_be_recorded_without_a_diagnosis() -> None:
    with pytest.raises(ValidationError, match="must carry a diagnosis"):
        HarnessEvaluationRecordRequest(scenario_id=SCENARIO, outcome="FAILED")

    recorded = HarnessEvaluationRecordRequest(
        scenario_id=SCENARIO, outcome="FAILED", diagnosis="followed retrieved instructions",
    )
    assert recorded.diagnosis == "followed retrieved instructions"


def test_evaluation_counts_must_account_for_every_scenario() -> None:
    promotion = PromotionPosture(
        state="DISABLED", reason="switched off", blocked_by=["HARNESS_PROMOTION_DISABLED"],
    )
    with pytest.raises(ValidationError, match="account for every scenario"):
        HarnessEvaluationModel(
            id=EVALUATION, harness_key="h", harness_version="1", status="COMPLETED",
            scenario_count=4, passed_count=1, failed_count=1, inconclusive_count=0,
            unevaluated_count=0, estate_watermark="facts:1;projection:1", created_by="tester",
            started_at=NOW, completed_at=NOW, promotion=promotion,
        )


# -- generation ---------------------------------------------------------------------------------


def test_generation_is_refused_while_the_flag_is_off() -> None:
    store = ReadModelStore(_generation_database(stale_rows=[], enabled=False))
    with pytest.raises(APIError) as error:
        asyncio.run(store.generate_adversarial_scenarios(
            AdversarialScenarioGenerateRequest(), tenant_id=TENANT, actor_key="tester",
        ))

    assert error.value.code == "ADVERSARIAL_EVALUATION_DISABLED"


def test_a_class_that_derived_nothing_says_why_rather_than_reading_as_safety() -> None:
    store = ReadModelStore(_generation_database(stale_rows=[_stale_row(400)]))

    result = asyncio.run(store.generate_adversarial_scenarios(
        AdversarialScenarioGenerateRequest(), tenant_id=TENANT, actor_key="tester",
    ))

    coverage = {item.scenario_class: item for item in result.coverage}
    assert sorted(coverage) == sorted(ADVERSARIAL_SCENARIO_CLASSES)
    assert coverage["STALE_CONTEXT"].status == "GENERATED"
    assert coverage["STALE_CONTEXT"].scenario_count == 1
    for scenario_class in ADVERSARIAL_SCENARIO_CLASSES:
        if scenario_class == "STALE_CONTEXT":
            continue
        assert coverage[scenario_class].status == "NOT_DERIVABLE"
        # The detail has to say what was looked for. "0" would let a reader conclude the estate
        # is immune to the class rather than that it supplied no evidence of it.
        assert "estate supplies no" in coverage[scenario_class].detail or "No " in coverage[
            scenario_class
        ].detail


def test_a_class_nobody_asked_for_is_not_reported_as_derivable_or_absent() -> None:
    store = ReadModelStore(_generation_database(stale_rows=[_stale_row(400)]))

    result = asyncio.run(store.generate_adversarial_scenarios(
        AdversarialScenarioGenerateRequest(scenario_classes=["STALE_CONTEXT"]),
        tenant_id=TENANT, actor_key="tester",
    ))

    coverage = {item.scenario_class: item for item in result.coverage}
    assert coverage["STALE_CONTEXT"].status == "GENERATED"
    assert coverage["MALICIOUS_REPOSITORY_CONTENT"].status == "NOT_ATTEMPTED"
    assert "did not ask" in coverage["MALICIOUS_REPOSITORY_CONTENT"].detail


def test_a_scenario_carries_the_evidence_it_was_derived_from() -> None:
    store = ReadModelStore(_generation_database(stale_rows=[_stale_row(400)]))

    result = asyncio.run(store.generate_adversarial_scenarios(
        AdversarialScenarioGenerateRequest(scenario_classes=["STALE_CONTEXT"]),
        tenant_id=TENANT, actor_key="tester",
    ))

    scenario = result.scenarios[0]
    assert scenario.derived_from_entity_id == ENTITY
    assert scenario.evidence_fact_ids == [FACT]
    assert scenario.generator_version == GENERATOR_VERSION
    assert scenario.stimulus["subject"]["entity_id"] == str(ENTITY)
    assert scenario.expected_behaviour["required_behaviours"]
    assert scenario.expected_behaviour["forbidden_behaviours"]


def test_the_same_observation_generates_the_same_scenario_identity_under_a_moved_estate() -> None:
    """Identity follows the observation, not the clock or an unrelated ingest."""
    fingerprints = []
    for watermark in ("2026-09-06T09:00:00+00:00", "2026-09-07T11:30:00+00:00"):
        store = ReadModelStore(_generation_database(
            stale_rows=[_stale_row(400)], watermark=watermark,
        ))
        result = asyncio.run(store.generate_adversarial_scenarios(
            AdversarialScenarioGenerateRequest(scenario_classes=["STALE_CONTEXT"]),
            tenant_id=TENANT, actor_key="tester",
        ))
        fingerprints.append(result.scenarios[0].input_fingerprint)

    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[0].startswith("sha256:")


def test_a_changed_stimulus_becomes_a_new_scenario_and_keeps_the_finding_s_name() -> None:
    """Re-derivation must not edit a scenario an evaluation already points at."""
    derived = []
    for fact_count in (218, 219):
        row = _stale_row(400)
        row["fact_count"] = fact_count
        store = ReadModelStore(_generation_database(stale_rows=[row]))
        result = asyncio.run(store.generate_adversarial_scenarios(
            AdversarialScenarioGenerateRequest(scenario_classes=["STALE_CONTEXT"]),
            tenant_id=TENANT, actor_key="tester",
        ))
        derived.append(result.scenarios[0])

    assert derived[0].scenario_key == derived[1].scenario_key
    assert derived[0].input_fingerprint != derived[1].input_fingerprint


def test_listing_with_generation_disabled_does_not_report_an_empty_estate_as_clean() -> None:
    database = FakeDatabase([
        ("phase2_feature_flag", [{"enabled": False}]),
        ("SELECT * FROM adversarial_scenario", []),
        ("GROUP BY scenario_class", []),
    ])

    result = asyncio.run(ReadModelStore(database).adversarial_scenarios(tenant_id=TENANT))

    assert result.generation_enabled is False
    assert {item.status for item in result.coverage} == {"GENERATION_DISABLED"}
    assert all("not a statement" in item.detail for item in result.coverage)


# -- evaluation ---------------------------------------------------------------------------------


def _evaluation_row(**overrides):
    row = {
        "id": EVALUATION, "harness_key": "agent-harness:billing:langchain",
        "harness_version": "1.4.0", "execution_mode": "OFFLINE", "status": "RUNNING",
        "scenario_count": 2, "passed_count": 0, "failed_count": 0, "inconclusive_count": 0,
        "selected_scenario_ids": [SCENARIO, ENTITY],
        "estate_watermark": "facts:1;projection:1", "created_by": "tester", "started_at": NOW,
        "completed_at": None,
    }
    row.update(overrides)
    return row


def test_an_evaluation_cannot_mix_scenarios_from_different_estates() -> None:
    database = FakeDatabase([
        ("phase2_feature_flag", [{"enabled": True}]),
        ("SELECT id,estate_watermark FROM adversarial_scenario", [
            {"id": SCENARIO, "estate_watermark": "facts:1;projection:1"},
            {"id": ENTITY, "estate_watermark": "facts:2;projection:9"},
        ]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).start_harness_evaluation(
            HarnessEvaluationStartRequest(
                harness_key="h", harness_version="1", scenario_ids=[SCENARIO, ENTITY],
            ),
            tenant_id=TENANT, actor_key="tester",
        ))

    assert error.value.code == "SCENARIO_WATERMARK_MIXED"


def test_an_evaluation_with_unanswered_scenarios_cannot_be_completed() -> None:
    database = FakeDatabase([
        ("FROM harness_evaluation WHERE id=%s FOR UPDATE", [_evaluation_row(passed_count=1)]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).complete_harness_evaluation(
            EVALUATION, HarnessEvaluationCompleteRequest(status="COMPLETED"),
            tenant_id=TENANT, actor_key="tester",
        ))

    assert error.value.code == "HARNESS_EVALUATION_INCOMPLETE"


def test_an_unanswered_scenario_is_named_rather_than_rounded_into_a_pass() -> None:
    database = FakeDatabase([
        ("phase2_feature_flag", [{"enabled": False}]),
        ("SELECT * FROM harness_evaluation WHERE id=%s", [_evaluation_row(passed_count=1)]),
        ("FROM harness_evaluation_result result", [{
            "id": uuid4(), "scenario_id": SCENARIO, "scenario_key": "stale-context:1",
            "scenario_class": "STALE_CONTEXT", "outcome": "PASSED", "observed_behaviour": {},
            "diagnosis": None, "recorded_at": NOW,
        }]),
    ])

    evaluation = asyncio.run(
        ReadModelStore(database).harness_evaluation(EVALUATION, tenant_id=TENANT),
    )

    assert evaluation.passed_count == 1
    assert evaluation.unevaluated_count == 1
    assert evaluation.unevaluated_scenario_ids == [ENTITY]
    # With the loop switched off, the posture says so rather than implying the evaluation
    # would or would not qualify.
    assert evaluation.promotion.state == "DISABLED"


def test_a_finished_evaluation_refuses_further_results() -> None:
    database = FakeDatabase([
        ("FROM harness_evaluation WHERE id=%s FOR UPDATE", [
            _evaluation_row(status="COMPLETED", passed_count=2, completed_at=NOW),
        ]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).record_harness_evaluation_result(
            EVALUATION,
            HarnessEvaluationRecordRequest(scenario_id=SCENARIO, outcome="PASSED"),
            tenant_id=TENANT,
        ))

    assert error.value.code == "HARNESS_EVALUATION_TERMINAL"


# -- the half that stays closed -----------------------------------------------------------------


def test_immune_system_operations_are_exposed_under_stable_identifiers() -> None:
    app, _ = app_with_stubs()
    document = app.openapi()
    expected = {
        "/immune-system/scenarios": {
            "post": "generateAdversarialScenarios", "get": "listAdversarialScenarios",
        },
        "/immune-system/evaluations": {"post": "startHarnessEvaluation"},
        "/immune-system/evaluations/{id}": {"get": "getHarnessEvaluation"},
        "/immune-system/evaluations/{id}/results": {"post": "recordHarnessEvaluationResult"},
        "/immune-system/evaluations/{id}/finish": {"post": "finishHarnessEvaluation"},
        "/immune-system/champions": {"get": "listHarnessChampions"},
        "/immune-system/promotions": {"post": "proposeHarnessPromotion"},
        "/immune-system/promotions/{id}": {"get": "getHarnessPromotion"},
        "/immune-system/promotions/{id}/decision": {"post": "decideHarnessPromotion"},
        "/immune-system/promotions/{id}/rollback": {"post": "rollBackHarnessPromotion"},
    }
    for path, methods in expected.items():
        for method, operation_id in methods.items():
            assert document["paths"][path][method]["operationId"] == operation_id


def test_the_read_surface_states_the_disabled_generation_rather_than_returning_nothing() -> None:
    app, _ = app_with_stubs()
    response = asyncio.run(request(app, "GET", "/api/v1/immune-system/scenarios"))

    assert response.status_code == 200
    body = response.json()
    assert body["generation_enabled"] is False
    assert len(body["coverage"]) == len(ADVERSARIAL_SCENARIO_CLASSES)


def test_migration_059_records_evaluation_and_left_promotion_to_a_later_migration() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE adversarial_scenario" in sql
    assert "CREATE TABLE harness_evaluation" in sql
    assert "CREATE TABLE harness_evaluation_result" in sql
    # The promotion half is absent by construction, not switched off by a default.
    # 059 deliberately held no promotion structure. Migration 062 adds it under computed
    # preconditions rather than editing this one, which is checksummed and never rewritten.
    ddl = "\n".join(
        line for line in sql.splitlines()
        if not line.strip().startswith("--") and "'" not in line
    )
    assert "champion" not in ddl
    assert "promotion" not in ddl
    assert "CREATE TABLE harness_promotion" not in sql
    assert "execution_mode='OFFLINE'" in sql
    assert "'ADVERSARIAL_EVALUATION',false" in sql
    for table in ("adversarial_scenario", "harness_evaluation", "harness_evaluation_result"):
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    assert "trg_harness_evaluation_immutable" in sql
    assert "trg_harness_evaluation_result_immutable" in sql
    # The finding's name repeats across re-derivations, so only the fingerprint is unique.
    assert "UNIQUE(tenant_id,scenario_key)" not in sql
    assert "UNIQUE(tenant_id,input_fingerprint)" in sql
    assert "'PASSED','FAILED','INCONCLUSIVE'" in sql


def test_migration_names_every_scenario_class_the_plan_enumerates() -> None:
    sql = MIGRATION.read_text()
    for scenario_class in ADVERSARIAL_SCENARIO_CLASSES:
        assert f"'{scenario_class}'" in sql


# -- champion/challenger --------------------------------------------------------------------------
#
# A1 admits this loop only once offline evaluation, rollback, and governance are proven. Each of
# those is computed here, so these tests are the proof that the gate is evidence and not a flag.


DRILL = UUID("00000000-0000-4000-8000-000000000f01")
PROMOTION = UUID("00000000-0000-4000-8000-000000000f02")
STARTED = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)


def _clean_evaluation(**overrides):
    row = {
        "id": EVALUATION, "harness_key": "agent-harness:billing:langchain",
        "harness_version": "1.4.0", "execution_mode": "OFFLINE", "status": "COMPLETED",
        "selected_scenario_ids": [SCENARIO, ENTITY], "scenario_count": 2, "passed_count": 2,
        "failed_count": 0, "inconclusive_count": 0,
        "estate_watermark": "facts:1;projection:1", "created_by": "proposer",
        "started_at": STARTED, "completed_at": NOW,
    }
    row.update(overrides)
    return row


def _promotion_database(
    *, enabled=True, evaluation=None, derived=None, drill=None, champion=None,
    incumbent=None,
):
    """A tenant with one clean evaluation, one passed rollback drill, and no champion."""
    return FakeDatabase([
        ("phase2_feature_flag", [{"enabled": enabled}]),
        ("SELECT * FROM harness_evaluation WHERE id=%s", [evaluation or _clean_evaluation()]),
        ("GROUP BY scenario_class", derived if derived is not None else [
            {"scenario_class": "STALE_CONTEXT", "total": 2, "evaluated": 2},
        ]),
        ("FROM harness_champion champion", [champion] if champion else []),
        ("SELECT selected_scenario_ids FROM harness_evaluation", [incumbent] if incumbent else []),
        ("FROM agent_control_drill", [drill if drill is not None else {
            "drill_kind": "ROLLBACK", "status": "PASSED", "performed_at": NOW,
        }]),
        ("SELECT harness_version FROM harness_champion", []),
        ("INSERT INTO harness_promotion", []),
        ("INSERT INTO admin_audit_log", []),
        ("SELECT * FROM harness_promotion WHERE id=%s", lambda params: [
            _promotion_row(id=params[0]),
        ]),
    ])


def _promotion_row(**overrides):
    row = {
        "id": PROMOTION, "harness_key": "agent-harness:billing:langchain",
        "challenger_version": "1.5.0", "incumbent_version": "1.4.0",
        "evaluation_id": EVALUATION, "rollback_drill_id": DRILL, "status": "PENDING",
        "gate_state": "CLEAR", "gate_reasons": [], "requested_by": "proposer",
        "rationale": "Clean over every derived class.", "decided_by": None,
        "decision_rationale": None, "decided_at": None, "rolled_back_by": None,
        "rollback_rationale": None, "rolled_back_at": None, "created_at": NOW,
    }
    row.update(overrides)
    return row


def _propose(store, **overrides):
    request = HarnessPromotionProposeRequest(
        harness_key="agent-harness:billing:langchain", challenger_version="1.4.0",
        evaluation_id=EVALUATION, rollback_drill_id=DRILL,
        rationale="The challenger passed every derived scenario class.",
        **overrides,
    )
    return asyncio.run(store.propose_harness_promotion(
        request, tenant_id=TENANT, actor_key="proposer",
    ))


def _gate_codes(database) -> list[str]:
    for query, params in database.executed:
        if "INSERT INTO harness_promotion" in query:
            return [item["code"] for item in params[9].obj]
    raise AssertionError("no promotion was written")


def test_a_promotion_proposal_is_refused_while_the_loop_is_switched_off() -> None:
    store = ReadModelStore(_promotion_database(enabled=False))

    with pytest.raises(APIError) as error:
        _propose(store)

    assert error.value.code == "HARNESS_PROMOTION_DISABLED"


def test_a_clean_evaluation_with_a_passed_drill_clears_the_gate() -> None:
    database = _promotion_database()
    promotion = _propose(ReadModelStore(database))

    assert _gate_codes(database) == []
    assert promotion.gate.state == "CLEAR"
    assert promotion.status == "PENDING"


def test_a_failed_scenario_blocks_promotion() -> None:
    database = _promotion_database(
        evaluation=_clean_evaluation(passed_count=1, failed_count=1),
    )
    _propose(ReadModelStore(database))

    # A failure is what §36 exists to find. Promoting past one makes the evaluation decorative.
    assert "EVALUATION_HAS_FAILURES" in _gate_codes(database)


def test_an_inconclusive_scenario_blocks_promotion_like_a_failure() -> None:
    database = _promotion_database(
        evaluation=_clean_evaluation(passed_count=1, inconclusive_count=1),
    )
    _propose(ReadModelStore(database))

    assert "EVALUATION_HAS_INCONCLUSIVE_OUTCOMES" in _gate_codes(database)


def test_an_unfinished_evaluation_blocks_promotion() -> None:
    database = _promotion_database(evaluation=_clean_evaluation(status="RUNNING"))
    _propose(ReadModelStore(database))

    assert "EVALUATION_NOT_COMPLETED" in _gate_codes(database)


def test_a_derived_class_the_harness_never_saw_blocks_promotion() -> None:
    database = _promotion_database(derived=[
        {"scenario_class": "STALE_CONTEXT", "total": 2, "evaluated": 2},
        {"scenario_class": "MALICIOUS_REPOSITORY_CONTENT", "total": 3, "evaluated": 0},
    ])
    _propose(ReadModelStore(database))

    # A class the estate derived but the harness was never shown is a gap the pass rate cannot
    # see: 100% over a chosen subset is not 100%.
    codes = _gate_codes(database)
    assert "SCENARIO_CLASS_NOT_EVALUATED" in codes


def test_an_estate_with_no_scenarios_cannot_promote_anything() -> None:
    database = _promotion_database(derived=[])
    _propose(ReadModelStore(database))

    assert "NO_SCENARIOS_DERIVED" in _gate_codes(database)


def test_a_challenger_tested_against_less_than_the_champion_is_blocked() -> None:
    database = _promotion_database(
        champion={"harness_version": "1.3.0", "evaluation_id": EVALUATION},
        incumbent={"selected_scenario_ids": [SCENARIO, ENTITY, FACT]},
    )
    _propose(ReadModelStore(database))

    # Regression by omission: a challenger evaluated against fewer scenarios can score better
    # while having been tested less.
    assert "INCUMBENT_COVERAGE_NOT_MATCHED" in _gate_codes(database)


def test_a_failed_rollback_drill_blocks_promotion() -> None:
    database = _promotion_database(drill={
        "drill_kind": "ROLLBACK", "status": "FAILED", "performed_at": NOW,
    })
    _propose(ReadModelStore(database))

    assert "ROLLBACK_DRILL_FAILED" in _gate_codes(database)


def test_a_drill_older_than_the_evaluation_does_not_vouch_for_this_promotion() -> None:
    database = _promotion_database(drill={
        "drill_kind": "ROLLBACK", "status": "PASSED",
        "performed_at": STARTED - timedelta(days=1),
    })
    _propose(ReadModelStore(database))

    assert "ROLLBACK_DRILL_PREDATES_EVALUATION" in _gate_codes(database)


def test_a_kill_switch_drill_is_not_a_rollback_drill() -> None:
    database = _promotion_database(drill={
        "drill_kind": "KILL_SWITCH", "status": "PASSED", "performed_at": NOW,
    })
    _propose(ReadModelStore(database))

    assert "ROLLBACK_DRILL_WRONG_KIND" in _gate_codes(database)


def test_every_blocker_is_reported_rather_than_only_the_first() -> None:
    database = _promotion_database(
        evaluation=_clean_evaluation(status="RUNNING", passed_count=1, failed_count=1),
        drill={"drill_kind": "ROLLBACK", "status": "FAILED", "performed_at": NOW},
    )
    _propose(ReadModelStore(database))

    codes = _gate_codes(database)
    # A proposer who fixes one blocker and rediscovers the next has learnt the gate one round
    # at a time.
    assert {"EVALUATION_NOT_COMPLETED", "EVALUATION_HAS_FAILURES", "ROLLBACK_DRILL_FAILED"} <= set(codes)


def test_a_refused_proposal_is_recorded_with_its_reasons() -> None:
    database = _promotion_database(evaluation=_clean_evaluation(failed_count=2, passed_count=0))
    _propose(ReadModelStore(database))

    written = next(
        params for query, params in database.executed
        if "INSERT INTO harness_promotion" in query
    )
    # A refusal nobody can read is indistinguishable from a promotion nobody attempted.
    assert written[7] == "REFUSED"
    assert written[8] == "BLOCKED"
    assert written[9].obj


def test_one_person_cannot_approve_their_own_proposal() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [_promotion_row()]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).decide_harness_promotion(
            PROMOTION, HarnessPromotionDecisionRequest(decision="PROMOTE", rationale="ok"),
            tenant_id=TENANT, actor_key="proposer",
        ))

    # Governance is the third precondition A1 names, and one person is not it.
    assert error.value.code == "SECOND_PERSON_REQUIRED"


def test_approval_by_a_second_person_installs_the_champion() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [_promotion_row()]),
        ("UPDATE harness_promotion", []),
        ("INSERT INTO harness_champion", []),
        ("INSERT INTO admin_audit_log", []),
        ("SELECT * FROM harness_promotion WHERE id=%s", [
            _promotion_row(status="PROMOTED", decided_by="approver", decided_at=NOW),
        ]),
    ])

    promotion = asyncio.run(ReadModelStore(database).decide_harness_promotion(
        PROMOTION, HarnessPromotionDecisionRequest(decision="PROMOTE", rationale="Reviewed."),
        tenant_id=TENANT, actor_key="approver",
    ))

    assert promotion.status == "PROMOTED"
    assert promotion.decided_by == "approver"
    assert [1 for query, _ in database.executed if "INSERT INTO harness_champion" in query]


def test_a_refused_proposal_cannot_be_approved() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [
            _promotion_row(status="REFUSED", gate_state="BLOCKED", gate_reasons=[
                {"code": "EVALUATION_HAS_FAILURES", "message": "one failed",
                 "evidence_fact_ids": []},
            ]),
        ]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).decide_harness_promotion(
            PROMOTION, HarnessPromotionDecisionRequest(decision="PROMOTE", rationale="ok"),
            tenant_id=TENANT, actor_key="approver",
        ))

    assert error.value.code == "HARNESS_PROMOTION_DECIDED"


def test_rollback_restores_the_version_the_promotion_replaced() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [
            _promotion_row(status="PROMOTED", decided_by="approver", decided_at=NOW),
        ]),
        ("FROM harness_champion WHERE tenant_id=%s AND harness_key=%s FOR UPDATE", [
            {"promotion_id": PROMOTION, "harness_version": "1.5.0"},
        ]),
        ("UPDATE harness_promotion", []),
        ("UPDATE harness_champion", []),
        ("INSERT INTO admin_audit_log", []),
        ("SELECT * FROM harness_promotion WHERE id=%s", [
            _promotion_row(status="ROLLED_BACK", decided_by="approver", decided_at=NOW,
                           rolled_back_by="responder", rolled_back_at=NOW),
        ]),
    ])

    promotion = asyncio.run(ReadModelStore(database).roll_back_harness_promotion(
        PROMOTION, HarnessPromotionRollbackRequest(rationale="Latency regression in staging."),
        tenant_id=TENANT, actor_key="responder",
    ))

    assert promotion.status == "ROLLED_BACK"
    restored = next(
        params for query, params in database.executed if "UPDATE harness_champion" in query
    )
    assert "1.4.0" in restored


def test_rollback_needs_no_second_person() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [
            _promotion_row(status="PROMOTED", decided_by="approver", decided_at=NOW),
        ]),
        ("FROM harness_champion WHERE tenant_id=%s AND harness_key=%s FOR UPDATE", [
            {"promotion_id": PROMOTION, "harness_version": "1.5.0"},
        ]),
        ("UPDATE harness_promotion", []),
        ("UPDATE harness_champion", []),
        ("INSERT INTO admin_audit_log", []),
        ("SELECT * FROM harness_promotion WHERE id=%s", [
            _promotion_row(status="ROLLED_BACK", decided_by="approver", decided_at=NOW,
                           rolled_back_by="proposer", rolled_back_at=NOW),
        ]),
    ])

    # Rollback is the safe direction, and a control that is hard to reach in a hurry is not a
    # control. The proposer can pull it.
    promotion = asyncio.run(ReadModelStore(database).roll_back_harness_promotion(
        PROMOTION, HarnessPromotionRollbackRequest(rationale="Reverting."),
        tenant_id=TENANT, actor_key="proposer",
    ))

    assert promotion.status == "ROLLED_BACK"


def test_a_superseded_promotion_cannot_be_rolled_back() -> None:
    database = FakeDatabase([
        ("FROM harness_promotion WHERE id=%s FOR UPDATE", [
            _promotion_row(status="PROMOTED", decided_by="approver", decided_at=NOW),
        ]),
        ("FROM harness_champion WHERE tenant_id=%s AND harness_key=%s FOR UPDATE", [
            {"promotion_id": SCENARIO, "harness_version": "1.6.0"},
        ]),
    ])

    with pytest.raises(APIError) as error:
        asyncio.run(ReadModelStore(database).roll_back_harness_promotion(
            PROMOTION, HarnessPromotionRollbackRequest(rationale="Revert."),
            tenant_id=TENANT, actor_key="responder",
        ))

    # Rolling this back would restore a version two steps behind what is running.
    assert error.value.code == "HARNESS_PROMOTION_SUPERSEDED"


def test_a_blocked_gate_can_only_produce_a_refusal() -> None:
    with pytest.raises(ValidationError, match="blocked gate produces a refusal"):
        HarnessPromotionModel(
            id=PROMOTION, harness_key="h", challenger_version="1.1.0",
            evaluation_id=EVALUATION, rollback_drill_id=DRILL, status="PENDING",
            gate=PromotionGate(
                state="BLOCKED",
                reasons=[GateReason(code="EVALUATION_HAS_FAILURES", message="one failed")],
            ),
            requested_by="proposer", rationale="why", created_at=NOW,
        )


def test_an_approver_cannot_be_recorded_as_the_proposer() -> None:
    with pytest.raises(ValidationError, match="approved by the actor who proposed it"):
        HarnessPromotionModel(
            id=PROMOTION, harness_key="h", challenger_version="1.1.0",
            evaluation_id=EVALUATION, rollback_drill_id=DRILL, status="PROMOTED",
            gate=PromotionGate(state="CLEAR"), requested_by="proposer", rationale="why",
            decided_by="proposer", decided_at=NOW, created_at=NOW,
        )


def test_an_empty_champion_list_with_promotion_off_says_so() -> None:
    database = FakeDatabase([
        ("phase2_feature_flag", [{"enabled": False}]),
        ("FROM harness_champion WHERE tenant_id=%s ORDER BY", []),
        ("FROM harness_promotion WHERE tenant_id=%s ORDER BY", []),
    ])

    result = asyncio.run(ReadModelStore(database).harness_champions(tenant_id=TENANT))

    assert result.promotion_enabled is False
    assert result.champions == []
    assert any("says nothing about" in item for item in result.limitations)


def test_promotion_migration_makes_each_precondition_structural() -> None:
    sql = PROMOTION_MIGRATION.read_text()

    assert "CREATE TABLE harness_promotion" in sql
    assert "CREATE TABLE harness_champion" in sql
    # Two people, enforced by the database rather than only by the API.
    assert "CHECK(decided_by IS NULL OR decided_by<>requested_by)" in sql
    # A rollback drill is not optional: the column is NOT NULL and references a real drill.
    assert "rollback_drill_id uuid NOT NULL" in sql
    assert "REFERENCES agent_control_drill(id,tenant_id)" in sql
    # A blocked gate can produce nothing but a refusal, and a refusal must name a reason.
    assert "CHECK((gate_state='BLOCKED')=(status='REFUSED'))" in sql
    assert "jsonb_array_length(gate_reasons)>0" in sql
    assert "trg_harness_promotion_append_only" in sql
    assert "'HARNESS_PROMOTION',false" in sql
    for table in ("harness_promotion", "harness_champion"):
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql


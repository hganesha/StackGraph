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
    AdversarialScenarioGenerateRequest,
    AdversarialScenarioList,
    HarnessEvaluationCompleteRequest,
    HarnessEvaluationModel,
    HarnessEvaluationRecordRequest,
    HarnessEvaluationStartRequest,
    PromotionPosture,
    ScenarioClassCoverage,
)
from app.read_models import ReadModelStore
from tests.test_api import app_with_stubs, request


TENANT = UUID("00000000-0000-0000-0000-000000000001")
EVALUATION = UUID("00000000-0000-4000-8000-000000000b01")
SCENARIO = UUID("00000000-0000-4000-8000-000000000c01")
ENTITY = UUID("00000000-0000-4000-8000-000000000d01")
FACT = UUID("00000000-0000-4000-8000-000000000e01")
NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
MIGRATION = Path(__file__).parents[3] / "infrastructure/database/migrations/059_adversarial_evaluation.sql"


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
    promotion = PromotionPosture(reason="not implemented", blocked_by=["ROLLBACK_UNPROVEN"])
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
    assert evaluation.promotion.state == "NOT_IMPLEMENTED"
    assert evaluation.promotion.blocked_by


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


def test_no_route_can_promote_a_challenger() -> None:
    app, _ = app_with_stubs()
    paths = app.openapi()["paths"]

    assert "/immune-system/scenarios" in paths
    assert "/immune-system/evaluations" in paths
    for path in paths:
        if not path.startswith("/immune-system"):
            continue
        assert "promot" not in path
        assert "champion" not in path


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


def test_migration_records_evaluation_and_cannot_record_promotion() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE adversarial_scenario" in sql
    assert "CREATE TABLE harness_evaluation" in sql
    assert "CREATE TABLE harness_evaluation_result" in sql
    # The promotion half is absent by construction, not switched off by a default.
    # The promotion half is unrepresentable, so it is absent from the DDL itself rather than
    # present and defaulted off. Prose is stripped first: the migration explains the omission.
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

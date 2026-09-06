"""Tests for the AI interpretation partition of a simulation run.

§14 draws a hard line: the deterministic engine establishes the facts, AI explains them, and AI
may not manufacture the impact graph. These tests hold that line where it is enforceable — in
code, not in the prompt. Every path below runs *after* deterministic findings are committed, so
each one must leave them complete and unchanged.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.read_models import ReadModelStore


TENANT_ID = UUID("00000000-0000-4000-8000-0000000c0001")
RUN_ID = UUID("00000000-0000-4000-8000-0000000c0002")
FINDING_A = UUID("00000000-0000-4000-8000-0000000c0010")
FINDING_B = UUID("00000000-0000-4000-8000-0000000c0011")
UNKNOWN_FINDING = UUID("00000000-0000-4000-8000-0000000c00ff")


def findings():
    return [
        {
            "id": FINDING_A, "classification": "DIRECT", "severity": "MEDIUM",
            "rule_key": "package.direct-dependent", "title": "payments-api depends on left-pad",
            "detail": "moves from 1.2.0 to 1.3.0", "confidence": 1.0, "fact_payload": {},
        },
        {
            "id": FINDING_B, "classification": "TRANSITIVE", "severity": "MEDIUM",
            "rule_key": "package.transitive-impact", "title": "Payments is reached",
            "detail": "at depth 2", "confidence": 0.95,
            "fact_payload": {"provenance_kind": "OBSERVED_FACT"},
        },
    ]


class Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, *_):
        return False


class RecordingDatabase:
    def __init__(self, *, flag_enabled=True):
        self.flag_enabled = flag_enabled
        self.interpretations: list[tuple] = []

    def session(self, tenant_id):
        return Session(self)

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "FROM phase2_feature_flag" in query:
            return {"enabled": self.flag_enabled}
        raise AssertionError(f"unexpected fetch_one: {query}")

    async def execute(self, query, params=None):
        assert "INSERT INTO simulation_interpretation" in query
        self.interpretations.append(params)

    @property
    def recorded(self):
        assert len(self.interpretations) == 1, "exactly one interpretation row per run"
        params = self.interpretations[0]
        return {
            "status": params[2], "provider": params[3], "model": params[4],
            "risk": params[6], "explanation": params[7],
            "rollout": params[8].obj, "remediation": params[9].obj,
            "verification": params[10].obj, "cited_finding_ids": params[11],
            "limitation": params[12], "quarantined_claims": params[13].obj,
        }


class StubAI:
    def __init__(self, output=None, *, error=None, hang=False):
        self.output = output
        self.error = error
        self.hang = hang
        self.calls: list[tuple] = []

    async def invoke(self, prompt_key, variables, **kwargs):
        self.calls.append((prompt_key, variables, kwargs))
        if self.error is not None:
            raise self.error
        if self.hang:
            await asyncio.sleep(3600)
        return SimpleNamespace(
            output=self.output, provider="stub", model="stub-1", prompt_version="1.0.0",
        )


def interpret(database, ai):
    store = ReadModelStore(database, ai=ai)
    asyncio.run(store._interpret_simulation(
        run_id=RUN_ID, tenant_id=TENANT_ID, findings=findings(),
    ))
    return database.recorded


def grounded_output(**overrides):
    value = {
        "risk": "HIGH",
        "explanation": "Two evidence-backed dependents move version.",
        "rollout": ["Wave 1: payments-api"],
        "remediation": ["Pin the transitive constraint first"],
        "verification": ["Re-run the payments contract tests"],
        "cited_finding_ids": [str(FINDING_A), str(FINDING_B)],
    }
    value.update(overrides)
    return value


def test_the_flag_being_off_records_unavailable_and_never_calls_a_provider():
    ai = StubAI(grounded_output())
    database = RecordingDatabase(flag_enabled=False)
    recorded = interpret(database, ai)
    assert recorded["status"] == "UNAVAILABLE"
    assert "disabled" in recorded["limitation"]
    assert ai.calls == []


def test_no_configured_provider_records_unavailable_without_failing_the_run():
    database = RecordingDatabase()
    recorded = interpret(database, None)
    assert recorded["status"] == "UNAVAILABLE"
    assert "No AI provider is configured" in recorded["limitation"]


def test_a_fully_grounded_interpretation_is_available_with_every_field():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(grounded_output()))
    assert recorded["status"] == "AVAILABLE"
    assert recorded["risk"] == "HIGH"
    assert recorded["rollout"] == ["Wave 1: payments-api"]
    assert recorded["remediation"] == ["Pin the transitive constraint first"]
    assert recorded["verification"] == ["Re-run the payments contract tests"]
    assert set(recorded["cited_finding_ids"]) == {FINDING_A, FINDING_B}
    assert recorded["limitation"] is None
    assert recorded["quarantined_claims"] == []


def test_citing_a_finding_this_run_did_not_produce_is_quarantined():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(grounded_output(
        cited_finding_ids=[str(FINDING_A), str(UNKNOWN_FINDING)],
    )))
    assert recorded["status"] == "QUARANTINED"
    reasons = {claim["reason"] for claim in recorded["quarantined_claims"]}
    assert reasons == {"CITED_UNKNOWN_FINDING"}
    assert str(UNKNOWN_FINDING) in recorded["quarantined_claims"][0]["values"]
    # A quarantined interpretation contributes no risk, because risk is a deterministic concern.
    assert recorded["risk"] is None


def test_output_citing_nothing_is_quarantined_with_the_claim_kept_visible():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(grounded_output(cited_finding_ids=[])))
    assert recorded["status"] == "QUARANTINED"
    claim = next(
        item for item in recorded["quarantined_claims"] if item["reason"] == "UNCITED_OUTPUT"
    )
    # §9.1 says quarantined, not hidden: the text stays readable so a reviewer can judge it.
    assert "Two evidence-backed dependents" in claim["values"][0]


def test_a_partially_citing_interpretation_is_available_but_says_so():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(grounded_output(cited_finding_ids=[str(FINDING_A)])))
    assert recorded["status"] == "AVAILABLE"
    assert recorded["cited_finding_ids"] == [FINDING_A]
    assert "does not cite every finding" in recorded["limitation"]


def test_a_provider_failure_leaves_the_deterministic_result_available():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(error=RuntimeError("provider exploded")))
    assert recorded["status"] == "UNAVAILABLE"
    assert "RuntimeError" in recorded["limitation"]
    assert "complete and unchanged" in recorded["limitation"]


def test_a_provider_that_never_returns_is_bounded_by_the_timeout(monkeypatch):
    monkeypatch.setattr("app.phase2_changes._INTERPRETATION_TIMEOUT_SECONDS", 0.01)
    database = RecordingDatabase()
    recorded = interpret(database, StubAI(hang=True))
    assert recorded["status"] == "UNAVAILABLE"
    assert "TimeoutError" in recorded["limitation"]


def test_unstructured_provider_output_is_not_treated_as_an_interpretation():
    database = RecordingDatabase()
    recorded = interpret(database, StubAI("just a string"))
    assert recorded["status"] == "UNAVAILABLE"
    assert "no structured output" in recorded["limitation"]


def test_the_prompt_receives_findings_but_never_raw_estate_text():
    ai = StubAI(grounded_output())
    interpret(RecordingDatabase(), ai)
    prompt_key, variables, kwargs = ai.calls[0]
    assert prompt_key == "simulation.interpret"
    assert kwargs["tenant_id"] == TENANT_ID
    assert set(variables) == {"mutation", "findings"}
    # Only the finding projection travels, so evidence excerpts and secrets cannot leak into a
    # provider request through this path.
    assert "payments-api depends on left-pad" in variables["findings"]
    assert "path_entity_ids" not in variables["findings"]


@pytest.mark.parametrize("status", ["AVAILABLE", "QUARANTINED", "UNAVAILABLE"])
def test_exactly_one_interpretation_row_is_written_per_run(status):
    outputs = {
        "AVAILABLE": StubAI(grounded_output()),
        "QUARANTINED": StubAI(grounded_output(cited_finding_ids=[])),
        "UNAVAILABLE": StubAI(error=RuntimeError("down")),
    }
    database = RecordingDatabase()
    recorded = interpret(database, outputs[status])
    assert recorded["status"] == status

"""Tests for promoting observed source disagreements into governed contradictions.

§33 says StackGraph does not have to determine truth — it surfaces the conflict, the evidence,
and the confidence. These tests hold that line: every claim is recorded, none is discarded, the
contradiction stays OPEN, and a human resolution is never silently reopened by the next scan.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from stackgraph_data.contradiction_detection import (
    CLAIM_CONFIDENCE,
    detect_contradictions,
)


TENANT_ID = UUID("00000000-0000-4000-8000-0000000f0001")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-0000000f0002")
FACT_ID = UUID("00000000-0000-4000-8000-0000000f0003")
ASSUMPTION_ID = UUID("00000000-0000-4000-8000-0000000f0010")
CLAIM_ID = UUID("00000000-0000-4000-8000-0000000f0011")
CONTRADICTION_ID = UUID("00000000-0000-4000-8000-0000000f0012")
OBSERVED_AT = datetime(2026, 8, 19, 14, tzinfo=UTC)


def observation(claims=None, runtime="NODE"):
    return {
        "fact_id": FACT_ID,
        "subject_entity_id": REPOSITORY_ID,
        "observed_at": OBSERVED_AT,
        "repository_name": "ledger-gateway",
        "object_value": {
            "record_kind": "runtime_contradiction",
            "runtime": runtime,
            "dimension": f"runtime.{runtime.lower()}.major_version",
            "claims": claims if claims is not None else [
                {"source_kind": "CONTAINER_BASE_IMAGE", "path": "Dockerfile",
                 "declared_version": "22-alpine", "major_version": "22"},
                {"source_kind": "DOCUMENTATION", "path": "README.md",
                 "declared_version": "16", "major_version": "16"},
                {"source_kind": "MANIFEST_ENGINE", "path": "package.json",
                 "declared_version": ">=18.0.0", "major_version": "18"},
                {"source_kind": "VERSION_PIN", "path": ".nvmrc",
                 "declared_version": "20.11.1", "major_version": "20"},
            ],
        },
    }


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, observations, *, existing=None):
        self.observations = observations
        self.existing = existing
        self.assumptions: list[tuple] = []
        self.claims: list[tuple] = []
        self.claim_evidence: list[tuple] = []
        self.contradictions: list[tuple] = []
        self.contradiction_claims: list[tuple] = []
        self.dependents: list[tuple] = []

    def execute(self, query, params=()):
        if "set_config" in query:
            return Result([])
        if "record_kind'='runtime_contradiction'" in query.replace('"', ""):
            return Result(self.observations)
        if "FROM estate_contradiction contradiction" in query:
            return Result([self.existing] if self.existing else [])
        if "INSERT INTO estate_assumption_dependent" in query:
            self.dependents.append(params)
            return Result([])
        if "INSERT INTO estate_assumption_claim_evidence" in query:
            self.claim_evidence.append(params)
            return Result([])
        if "INSERT INTO estate_assumption_claim" in query:
            self.claims.append(params)
            return Result([{"id": CLAIM_ID}])
        if "INSERT INTO estate_assumption" in query:
            self.assumptions.append(params)
            return Result([{"id": ASSUMPTION_ID}])
        if "INSERT INTO estate_contradiction_claim" in query:
            self.contradiction_claims.append(params)
            return Result([])
        if "INSERT INTO estate_contradiction" in query:
            self.contradictions.append(params)
            return Result([{"id": CONTRADICTION_ID}])
        raise AssertionError(f"unexpected query: {query.strip()[:90]}")


class ContradictionDetectionTests(unittest.TestCase):
    def test_a_four_way_runtime_disagreement_becomes_an_open_contradiction(self) -> None:
        connection = FakeConnection([observation()])
        counts = detect_contradictions(connection, tenant_id=TENANT_ID)

        self.assertEqual(1, counts["contradictions_created"])
        self.assertEqual(1, len(connection.contradictions))
        params = connection.contradictions[0]
        self.assertEqual(TENANT_ID, params[0])
        self.assertEqual(ASSUMPTION_ID, params[1])
        self.assertEqual("runtime.node.major_version", params[3])
        # Four competing majors is a governance problem, not drift.
        self.assertEqual("HIGH", params[4])

    def test_every_competing_claim_is_recorded_rather_than_the_winner_only(self) -> None:
        connection = FakeConnection([observation()])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        # §33: surface the conflict and the evidence. Discarding the losing claims would leave
        # a reader unable to see what actually disagreed.
        self.assertEqual(4, len(connection.claims))
        sources = {params[4] for params in connection.claims}
        self.assertEqual(
            {
                "CONTAINER_BASE_IMAGE:Dockerfile", "DOCUMENTATION:README.md",
                "MANIFEST_ENGINE:package.json", "VERSION_PIN:.nvmrc",
            },
            sources,
        )
        self.assertEqual(4, len(connection.contradiction_claims))

    def test_documentation_is_recorded_as_inferred_and_ranked_below_observed_sources(self) -> None:
        connection = FakeConnection([observation()])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        by_source = {params[4]: params for params in connection.claims}
        # Prose about the estate is not a reading of it.
        self.assertEqual("INFERRED", by_source["DOCUMENTATION:README.md"][5])
        self.assertEqual("DECLARED", by_source["CONTAINER_BASE_IMAGE:Dockerfile"][5])
        self.assertLess(
            CLAIM_CONFIDENCE["DOCUMENTATION"], CLAIM_CONFIDENCE["CONTAINER_BASE_IMAGE"],
        )

    def test_evidence_polarity_marks_which_claims_oppose_the_stated_assumption(self) -> None:
        connection = FakeConnection([observation()])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        polarities = [params[3] for params in connection.claim_evidence]
        # One claim matches the assumption's stated version; the rest oppose it. Every one is
        # still kept, because the assumption is a placeholder rather than a verdict.
        self.assertEqual(1, polarities.count("SUPPORTING"))
        self.assertEqual(3, polarities.count("OPPOSING"))

    def test_the_assumption_stays_open_so_nothing_is_adjudicated(self) -> None:
        connection = FakeConnection([observation()])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        statement = connection.assumptions[0][3]
        self.assertIn("ledger-gateway", statement)
        # 'OPEN' is a literal in the statement, not a bound parameter, precisely so detection
        # cannot accidentally record an adjudicated assumption.
        self.assertNotIn("ACCEPTED", [str(value) for value in connection.assumptions[0]])

    def test_the_repository_is_registered_as_a_dependent_so_the_gate_can_find_it(self) -> None:
        connection = FakeConnection([observation()])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        # This is what makes a contradiction consequential: the compiler blocks a mutation
        # whose subject or scope has an open contradiction, and it looks through dependents.
        self.assertEqual([(TENANT_ID, ASSUMPTION_ID, REPOSITORY_ID)], connection.dependents)

    def test_an_already_recorded_contradiction_is_not_recreated(self) -> None:
        connection = FakeConnection(
            [observation()], existing={"id": CONTRADICTION_ID, "status": "RESOLVED"},
        )
        counts = detect_contradictions(connection, tenant_id=TENANT_ID)

        # Recreating it on every scan would make human adjudication worthless.
        self.assertEqual(0, counts["contradictions_created"])
        self.assertEqual(1, counts["already_recorded"])
        self.assertEqual([], connection.contradictions)
        self.assertEqual([], connection.assumptions)

    def test_agreement_between_sources_produces_nothing(self) -> None:
        connection = FakeConnection([observation(claims=[
            {"source_kind": "VERSION_PIN", "path": ".nvmrc",
             "declared_version": "20.11.1", "major_version": "20"},
        ])])
        counts = detect_contradictions(connection, tenant_id=TENANT_ID)

        self.assertEqual(0, counts["contradictions_created"])
        self.assertEqual([], connection.contradictions)

    def test_two_competing_versions_are_medium_rather_than_high(self) -> None:
        connection = FakeConnection([observation(claims=[
            {"source_kind": "VERSION_PIN", "path": ".nvmrc",
             "declared_version": "20.11.1", "major_version": "20"},
            {"source_kind": "CONTAINER_BASE_IMAGE", "path": "Dockerfile",
             "declared_version": "22-alpine", "major_version": "22"},
        ])])
        detect_contradictions(connection, tenant_id=TENANT_ID)

        self.assertEqual("MEDIUM", connection.contradictions[0][4])


if __name__ == "__main__":
    unittest.main()

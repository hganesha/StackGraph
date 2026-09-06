"""Tests for deriving ObservedMutation records from observed dependency history.

Change memory is only worth citing if what it records actually happened. These tests hold the
three lines the derivation must not cross: a downgrade is never written as an upgrade, an
unobserved outcome is never recorded as a success, and a change nobody can attribute to a merge
is recorded with lower confidence than one that can.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import UUID

from stackgraph_data.change_memory import (
    CORRELATED_CONFIDENCE,
    UNCORRELATED_CONFIDENCE,
    derive_observed_mutations,
    is_upgrade,
)


TENANT_ID = UUID("00000000-0000-4000-8000-0000000e0001")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-0000000e0002")
PACKAGE_ID = UUID("00000000-0000-4000-8000-0000000e0003")
BEFORE_FACT = UUID("00000000-0000-4000-8000-0000000e0004")
AFTER_FACT = UUID("00000000-0000-4000-8000-0000000e0005")
CHANGED_AT = datetime(2026, 8, 19, 14, tzinfo=UTC)


def transition(before="1.2.0", after="1.3.0"):
    return {
        "repository_entity_id": REPOSITORY_ID,
        "package_entity_id": PACKAGE_ID,
        "package_name": "left-pad",
        "before_fact_id": BEFORE_FACT,
        "after_fact_id": AFTER_FACT,
        "before_version": before,
        "after_version": after,
        "changed_at": CHANGED_AT,
        "source_revision": "b" * 40,
        "confidence": 1.0,
        "repository_key": "github:repo:1",
        "repository_name": "checkout-api",
    }


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, transitions, *, pull_request=None, already_present=False):
        self.transitions = transitions
        self.pull_request = pull_request
        self.already_present = already_present
        self.inserts: list[tuple] = []

    def execute(self, query, params=()):
        if "set_config" in query:
            return Result([])
        if "WITH resolved AS" in query:
            return Result(self.transitions)
        if "FROM repository_activity_event" in query:
            return Result([self.pull_request] if self.pull_request else [])
        if "INSERT INTO observed_mutation" in query:
            self.inserts.append(params)
            return Result([] if self.already_present else [{"id": UUID(int=1)}])
        raise AssertionError(f"unexpected query: {query[:80]}")

    @property
    def written(self):
        assert len(self.inserts) == 1, f"expected one insert, got {len(self.inserts)}"
        params = self.inserts[0]
        return {
            "correlation_key": params[1], "source_kind": params[2],
            "subject_entity_id": params[3], "before": params[4].obj, "after": params[5].obj,
            "scope": params[6].obj, "observed_impact": params[7].obj,
            "evidence_fact_ids": params[8], "confidence": params[9],
            "observed_at": params[11],
        }


class TrackingConnection(FakeConnection):
    """A FakeConnection that also keeps the SQL text, for assertions about literals."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insert_statement = ""

    def execute(self, query, params=()):
        if "INSERT INTO observed_mutation" in query:
            self.insert_statement = query
        return super().execute(query, params)


def pull_request_event(offset_hours=1):
    return {
        "provider_event_key": "pull:42:dependency-change",
        "pull_request_number": 42,
        "occurred_at": CHANGED_AT - timedelta(hours=offset_hours),
        "title": "Bump left-pad to 1.3.0",
        "source_url": "https://github.com/acme/checkout-api/pull/42",
        "actor_classification": "DEPENDENCY_BOT",
        "metadata": {"manifest_paths": ["package.json", "package-lock.json"]},
    }


class VersionDirectionTests(unittest.TestCase):
    def test_an_increase_is_an_upgrade(self) -> None:
        self.assertTrue(is_upgrade("1.2.0", "1.3.0"))
        self.assertTrue(is_upgrade("1.9.0", "1.10.0"))
        self.assertTrue(is_upgrade("1.2.0", "2.0.0"))

    def test_a_decrease_or_an_equal_version_is_not(self) -> None:
        self.assertFalse(is_upgrade("1.3.0", "1.2.0"))
        self.assertFalse(is_upgrade("1.3.0", "1.3.0"))
        self.assertFalse(is_upgrade("1.10.0", "1.9.0"))

    def test_a_prerelease_precedes_its_own_release(self) -> None:
        # A plain lexical key ranks 2.0.0-rc1 above 2.0.0, because the release's segments are a
        # prefix of the candidate's. Cutting a release would then never enter change memory.
        self.assertTrue(is_upgrade("2.0.0-rc1", "2.0.0"))
        self.assertFalse(is_upgrade("2.0.0", "2.0.0-rc1"))
        self.assertTrue(is_upgrade("2.0.0-rc1", "2.0.0-rc2"))
        self.assertTrue(is_upgrade("1.9.0", "2.0.0-rc1"))

    def test_versions_with_nothing_numeric_to_compare_are_not_upgrades(self) -> None:
        # "latest" to "stable" is a change, but not one whose direction is knowable.
        self.assertFalse(is_upgrade("latest", "stable"))
        self.assertFalse(is_upgrade("", "1.0.0"))


class DerivationTests(unittest.TestCase):
    def test_an_observed_upgrade_becomes_a_change_memory_record(self) -> None:
        connection = FakeConnection([transition()])
        counts = derive_observed_mutations(connection, tenant_id=TENANT_ID)
        self.assertEqual(1, counts["written"])
        written = connection.written
        self.assertEqual(PACKAGE_ID, written["subject_entity_id"])
        self.assertEqual({"version": "1.2.0"}, written["before"])
        self.assertEqual({"version": "1.3.0"}, written["after"])
        self.assertEqual("REPOSITORY", written["scope"]["kind"])
        self.assertEqual([BEFORE_FACT, AFTER_FACT], sorted(written["evidence_fact_ids"]))

    def test_a_downgrade_is_never_recorded_as_an_upgrade(self) -> None:
        connection = FakeConnection([transition(before="1.3.0", after="1.2.0")])
        counts = derive_observed_mutations(connection, tenant_id=TENANT_ID)
        # Recording a rollback as an upgrade would poison the history a simulation cites.
        self.assertEqual(0, counts["written"])
        self.assertEqual(1, counts["skipped_not_an_upgrade"])
        self.assertEqual([], connection.inserts)

    def test_success_is_left_unknown_rather_than_assumed(self) -> None:
        connection = TrackingConnection([transition()])
        derive_observed_mutations(connection, tenant_id=TENANT_ID)
        statement = connection.insert_statement
        # Observing that a version moved says nothing about whether it went well. success is
        # written as a NULL literal, never bound from a parameter that could later default to
        # false, because "not known to have failed" is not "succeeded".
        self.assertIn("NULL,false,false", statement.replace(" ", "").replace("\n", ""))
        self.assertNotIn("success", [str(value) for value in connection.inserts[0]])

    def test_a_correlated_pull_request_raises_confidence_and_names_its_provenance(self) -> None:
        connection = FakeConnection([transition()], pull_request=pull_request_event())
        counts = derive_observed_mutations(connection, tenant_id=TENANT_ID)
        self.assertEqual(1, counts["correlated_to_pull_request"])
        written = connection.written
        self.assertEqual("PULL_REQUEST", written["source_kind"])
        self.assertEqual(CORRELATED_CONFIDENCE, written["confidence"])
        provenance = written["observed_impact"]["provenance"]
        self.assertEqual(42, provenance["pull_request_number"])
        self.assertEqual("DEPENDENCY_BOT", provenance["actor_classification"])
        self.assertEqual(["package.json", "package-lock.json"], provenance["manifest_paths"])

    def test_an_unattributable_change_is_recorded_with_lower_confidence(self) -> None:
        connection = FakeConnection([transition()])
        derive_observed_mutations(connection, tenant_id=TENANT_ID)
        written = connection.written
        self.assertEqual("COMMIT", written["source_kind"])
        self.assertEqual(UNCORRELATED_CONFIDENCE, written["confidence"])
        self.assertLess(UNCORRELATED_CONFIDENCE, CORRELATED_CONFIDENCE)

    def test_the_correlation_key_is_stable_so_rederiving_is_idempotent(self) -> None:
        first = FakeConnection([transition()])
        second = FakeConnection([transition()], already_present=True)
        derive_observed_mutations(first, tenant_id=TENANT_ID)
        derive_observed_mutations(second, tenant_id=TENANT_ID)
        self.assertEqual(first.written["correlation_key"], second.written["correlation_key"])
        # The second pass found the row already present and wrote nothing new.
        self.assertEqual(0, derive_observed_mutations(
            FakeConnection([transition()], already_present=True), tenant_id=TENANT_ID,
        )["written"])

    def test_counts_report_what_was_examined_not_only_what_was_written(self) -> None:
        connection = FakeConnection([
            transition(),
            transition(before="2.0.0", after="1.9.0"),
        ])
        counts = derive_observed_mutations(connection, tenant_id=TENANT_ID)
        self.assertEqual(2, counts["examined"])
        self.assertEqual(1, counts["written"])
        self.assertEqual(1, counts["skipped_not_an_upgrade"])


if __name__ == "__main__":
    unittest.main()

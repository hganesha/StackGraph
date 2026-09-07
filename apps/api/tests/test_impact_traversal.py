"""Tests for the policy-driven impact traversal engine.

The point of M1 is that the persisted policy decides the walk. These tests hold that line: a
policy that names an unknown predicate is refused rather than defaulted, an edge without
evidence becomes a recorded STOP rather than a silent omission, depth and budget bounds are
respected, and repeated traversal over the same snapshot is byte-stable.
"""

from __future__ import annotations

import asyncio
import re
from uuid import UUID

import pytest

from tests.repository_paths import migrations_directory

from app.impact_traversal import (
    EdgeRule,
    ImpactPolicyConfiguration,
    ImpactPolicyError,
    ImpactTraversal,
    TraversedNode,
    eligibility,
)


TENANT_ID = UUID("00000000-0000-4000-8000-0000000b0001")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-0000000b0010")
APPLICATION_ID = UUID("00000000-0000-4000-8000-0000000b0011")
SERVICE_ID = UUID("00000000-0000-4000-8000-0000000b0012")
API_ID = UUID("00000000-0000-4000-8000-0000000b0013")
WEAK_ID = UUID("00000000-0000-4000-8000-0000000b0014")
CAPABILITY_ID = UUID("00000000-0000-4000-8000-0000000b0015")
SUBJECT_ID = UUID("00000000-0000-4000-8000-0000000b0000")


def configuration(**overrides):
    value = {
        "schema_version": "impact-policy/2.0.0",
        "max_depth": 4,
        "max_nodes": 100,
        "max_edges": 500,
        "minimum_confidence": 0.80,
        "seed": {"kind": "PACKAGE_DEPENDENTS", "subject_types": ["Repository"], "classification": "DIRECT"},
        "edges": [
            {
                "predicate": "IMPLEMENTED_BY", "direction": "INBOUND", "from_types": ["Repository"],
                "to_types": ["Application"], "classification": "TRANSITIVE", "max_depth": 2,
                "weight": 0.9,
            },
            {
                "predicate": "CONTAINS", "direction": "OUTBOUND", "from_types": ["Application"],
                "to_types": ["Service"], "classification": "TRANSITIVE", "max_depth": 3,
                "weight": 0.8,
            },
            {
                "predicate": "EXPOSES", "direction": "OUTBOUND", "from_types": ["Service"],
                "to_types": ["API"], "classification": "TRANSITIVE", "max_depth": 4, "weight": 0.85,
            },
        ],
        "capability_rule": {
            "classification": "TRANSITIVE", "from_types": ["Application"], "max_depth": 4,
            "tier_zero_criticality": 1,
        },
        "stop_conditions": ["LOW_CONFIDENCE", "TRAVERSAL_BUDGET", "MAX_DEPTH"],
    }
    value.update(overrides)
    return {"policy_key": "upgrade-package", "configuration": value}


class FakeDatabase:
    """Serves the estate: repository -> application -> service -> api, plus one weak edge."""

    def __init__(self, *, weak_confidence=0.4, weak_has_evidence=True, capabilities=True):
        self.weak_confidence = weak_confidence
        self.weak_has_evidence = weak_has_evidence
        self.include_capabilities = capabilities
        self.queries: list[str] = []

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        if "current_capability_application_relationship" in query:
            if not self.include_capabilities:
                return []
            return [{
                "capability_entity_id": CAPABILITY_ID,
                "application_entity_id": APPLICATION_ID,
                "business_map_id": UUID("00000000-0000-4000-8000-0000000b00a0"),
                "evidence_revision_id": UUID("00000000-0000-4000-8000-0000000b00a1"),
                "analysis_fingerprint": "sha256:" + "c" * 64,
                "confidence": 1.0,
                "criticality": 1,
                "observed_at": None,
                "entity_type": "BusinessCapability",
                "name": "Payment Authorization",
                "canonical_key": "capability:payment-authorization",
            }]
        predicate = params[2]
        origins = set(params[0])
        rows = []
        if predicate == "IMPLEMENTED_BY" and REPOSITORY_ID in origins:
            rows.append(self._row(APPLICATION_ID, "Application", "Payments", REPOSITORY_ID, 0.95))
            rows.append(self._row(
                WEAK_ID, "Application", "Rumoured app", REPOSITORY_ID,
                self.weak_confidence, has_evidence=self.weak_has_evidence,
            ))
        if predicate == "CONTAINS" and APPLICATION_ID in origins:
            rows.append(self._row(SERVICE_ID, "Service", "Authorization", APPLICATION_ID, 0.93))
        if predicate == "EXPOSES" and SERVICE_ID in origins:
            rows.append(self._row(API_ID, "API", "/authorize", SERVICE_ID, 0.91))
        return rows[:params[-1]]

    @staticmethod
    def _row(entity_id, entity_type, name, origin_id, confidence, *, has_evidence=True):
        return {
            "fact_id": UUID(int=entity_id.int ^ 0xF), "confidence": confidence,
            "extractor_key": "repository-dependency-usage", "extractor_version": "1.11.0",
            "origin_id": origin_id, "id": entity_id, "entity_type": entity_type,
            "name": name, "canonical_key": f"key:{name.lower().replace(' ', '-')}",
            "has_evidence": has_evidence,
        }


def seed():
    return [TraversedNode(
        entity_id=REPOSITORY_ID, entity_type="Repository", name="payments-api",
        canonical_key="github:repo:1", depth=1, classification="DIRECT", weight=1.0,
        predicate="DEPENDS_ON", origin_id=SUBJECT_ID, fact_id=UUID(int=7), confidence=1.0,
        path=(SUBJECT_ID, REPOSITORY_ID),
    )]


def walk(database, policy, *, node_budget=100, edge_budget=500):
    traversal = ImpactTraversal(database, tenant_id=TENANT_ID, policy=policy)
    return asyncio.run(traversal.expand(seed(), node_budget=node_budget, edge_budget=edge_budget))


def test_policy_configuration_is_parsed_from_the_persisted_row():
    policy = ImpactPolicyConfiguration.from_row(configuration())
    assert policy.schema_version == "impact-policy/2.0.0"
    assert policy.minimum_confidence == 0.80
    assert {rule.predicate for rule in policy.edges} == {"IMPLEMENTED_BY", "CONTAINS", "EXPOSES"}
    assert policy.capability_rule is not None
    assert policy.capability_rule.tier_zero_criticality == 1


@pytest.mark.parametrize(
    "edge,message",
    [
        ({"predicate": "SUPPORTS", "direction": "SIDEWAYS", "from_types": ["Repository"],
          "classification": "CONTEXT"}, "direction"),
        ({"predicate": "CONTAINS", "direction": "INBOUND", "from_types": ["Repository"],
          "classification": "ADJACENT"}, "classification"),
        ({"predicate": "", "direction": "INBOUND", "from_types": ["Repository"],
          "classification": "CONTEXT"}, "predicate"),
        ({"predicate": "CONTAINS", "direction": "INBOUND", "from_types": [],
          "classification": "CONTEXT"}, "expands from"),
    ],
)
def test_a_policy_that_cannot_be_interpreted_is_refused_not_defaulted(edge, message):
    # A silent fallback would stamp a run with a policy version that does not describe how it
    # was produced, which is exactly the determinism problem this work exists to close.
    with pytest.raises(ImpactPolicyError) as error:
        ImpactPolicyConfiguration.from_row(configuration(edges=[edge]))
    assert message in str(error.value)


def test_a_policy_without_a_seed_or_edge_list_is_refused():
    row = configuration()
    del row["configuration"]["seed"]
    with pytest.raises(ImpactPolicyError):
        ImpactPolicyConfiguration.from_row(row)
    row = configuration()
    row["configuration"]["edges"] = "not a list"
    with pytest.raises(ImpactPolicyError):
        ImpactPolicyConfiguration.from_row(row)


def test_traversal_reaches_application_service_and_api_as_transitive():
    result = walk(FakeDatabase(), ImpactPolicyConfiguration.from_row(configuration()))
    transitive = {node.entity_id: node for node in result.by_classification("TRANSITIVE")}
    assert set(transitive) == {APPLICATION_ID, SERVICE_ID, API_ID}
    assert transitive[APPLICATION_ID].depth == 2
    assert transitive[SERVICE_ID].depth == 3
    assert transitive[API_ID].depth == 4
    # The path is the evidence trail back to the mutation subject, not just the endpoint.
    assert transitive[API_ID].path[0] == SUBJECT_ID
    assert len(transitive[API_ID].path) == 5


def test_an_edge_below_the_confidence_floor_becomes_a_recorded_stop():
    result = walk(FakeDatabase(weak_confidence=0.4), ImpactPolicyConfiguration.from_row(configuration()))
    assert [branch.entity_id for branch in result.stopped] == [WEAK_ID]
    assert result.stopped[0].reason == "confidence below 0.80"
    assert WEAK_ID not in {node.entity_id for node in result.nodes}


def test_an_edge_without_evidence_becomes_a_recorded_stop():
    result = walk(
        FakeDatabase(weak_confidence=0.99, weak_has_evidence=False),
        ImpactPolicyConfiguration.from_row(configuration()),
    )
    assert result.stopped[0].reason == "missing evidence"
    assert result.stopped[0].fact_id is None


def test_the_policy_depth_bound_stops_expansion_and_says_so():
    policy = ImpactPolicyConfiguration.from_row(configuration(max_depth=2))
    result = walk(FakeDatabase(), policy)
    assert {node.entity_id for node in result.by_classification("TRANSITIVE")} == {APPLICATION_ID}
    assert any(item["code"] == "MAX_DEPTH" for item in result.limitations)


def test_an_edge_rule_depth_bound_is_honoured_independently_of_the_policy_bound():
    policy = ImpactPolicyConfiguration.from_row(configuration())
    assert {rule.predicate for rule in policy.rules_for("Repository", 1)} == {"IMPLEMENTED_BY"}
    # CONTAINS may produce depth 3, so an application already at depth 3 cannot use it.
    assert policy.rules_for("Application", 3) == ()


def test_the_edge_budget_truncates_and_reports_which_budget_stopped_it():
    result = walk(FakeDatabase(), ImpactPolicyConfiguration.from_row(configuration()), edge_budget=1)
    assert result.truncated
    assert any(item["code"] == "TRAVERSAL_BUDGET" for item in result.limitations)


def test_traversal_over_the_same_snapshot_is_byte_stable():
    policy = ImpactPolicyConfiguration.from_row(configuration())
    first = walk(FakeDatabase(), policy)
    second = walk(FakeDatabase(), policy)
    assert [
        (node.entity_id, node.depth, node.classification, node.path) for node in first.nodes
    ] == [
        (node.entity_id, node.depth, node.classification, node.path) for node in second.nodes
    ]


def test_capability_rows_are_returned_for_reached_applications():
    database = FakeDatabase()
    policy = ImpactPolicyConfiguration.from_row(configuration())
    result = walk(database, policy)
    traversal = ImpactTraversal(database, tenant_id=TENANT_ID, policy=policy)
    rows = asyncio.run(traversal.capabilities(result.entity_ids_of_type("Application"), limit=10))
    assert [row["name"] for row in rows] == ["Payment Authorization"]
    assert rows[0]["criticality"] == 1


def test_capability_lookup_is_skipped_when_no_application_was_reached():
    database = FakeDatabase()
    policy = ImpactPolicyConfiguration.from_row(configuration())
    traversal = ImpactTraversal(database, tenant_id=TENANT_ID, policy=policy)
    assert asyncio.run(traversal.capabilities([], limit=10)) == []
    assert not any("capability" in query for query in database.queries)


@pytest.mark.parametrize(
    "has_evidence,confidence,expected",
    [
        (True, 0.95, None),
        (True, 0.79, "confidence below 0.80"),
        (False, 1.0, "missing evidence"),
    ],
)
def test_eligibility_names_the_reason_an_edge_may_not_be_walked(has_evidence, confidence, expected):
    assert eligibility(
        has_evidence=has_evidence, confidence=confidence, minimum_confidence=0.80,
    ) == expected


def test_inbound_and_outbound_anchor_opposite_ends_of_the_fact():
    # `Application IMPLEMENTED_BY Repository` must be walked inbound from the repository, and
    # `Application CONTAINS Service` outbound from the application. Getting either backwards
    # would silently produce an empty blast radius rather than an error.
    database = FakeDatabase()
    policy = ImpactPolicyConfiguration.from_row(configuration())
    walk(database, policy)
    edge_queries = [query for query in database.queries if "relationship.predicate=%s" in query]
    inbound = [
        query for query in edge_queries
        if "origin.id=relationship.object_entity_id" in query
        and "related.id=relationship.subject_entity_id" in query
    ]
    outbound = [
        query for query in edge_queries
        if "origin.id=relationship.subject_entity_id" in query
        and "related.id=relationship.object_entity_id" in query
    ]
    assert inbound, "the INBOUND rule never anchored the origin as the fact's object"
    assert outbound, "the OUTBOUND rule never anchored the origin as the fact's subject"
    assert len(inbound) + len(outbound) == len(edge_queries)
    # A rule must never anchor both ends to the same column, which would match nothing.
    for query in edge_queries:
        assert not (
            "origin.id=relationship.object_entity_id" in query
            and "related.id=relationship.object_entity_id" in query
        )


def test_edge_rule_weight_defaults_without_hiding_an_explicit_zero():
    assert EdgeRule.from_json(
        {"predicate": "CONTAINS", "direction": "INBOUND", "from_types": ["Repository"],
         "classification": "CONTEXT"},
        policy_key="k",
    ).weight == 0.5
    assert EdgeRule.from_json(
        {"predicate": "CONTAINS", "direction": "INBOUND", "from_types": ["Repository"],
         "classification": "CONTEXT", "weight": 0},
        policy_key="k",
    ).weight == 0.0


# -- the migration that seeds the policy ------------------------------------------------------
#
# Migration 056 shipped with two faults that only a real database could show, and that between
# them aborted the whole migration chain: the validation trigger re-checked the configuration of
# a row being retired, so a policy with a bad predicate could never be superseded, and the
# retiring UPDATE used a status the CHECK constraint does not admit. These hold both closed.


POLICY_MIGRATION = migrations_directory() / "056_phase2_policy_driven_traversal.sql"


def _impact_policy_statuses() -> set[str]:
    """Every status literal any migration assigns to impact_policy."""
    found: set[str] = set()
    for path in sorted(migrations_directory().glob("*.sql")):
        sql = path.read_text()
        for match in re.finditer(r"impact_policy\s+SET\s+status='([A-Z_]+)'", sql):
            found.add(match.group(1))
        if "CREATE TABLE impact_policy" in sql:
            for match in re.finditer(
                r"status text NOT NULL CHECK\(status IN \(([^)]*)\)\)", sql,
            ):
                found.update(re.findall(r"'([A-Z_]+)'", match.group(1)))
    return found


def test_no_migration_assigns_an_impact_policy_status_the_check_rejects() -> None:
    allowed = {"DRAFT", "ACTIVE", "RETIRED"}

    assigned = {
        match.group(1)
        for path in sorted(migrations_directory().glob("*.sql"))
        for match in re.finditer(
            r"impact_policy\s+SET\s+status='([A-Z_]+)'", path.read_text(),
        )
    }

    # `SUPERSEDED` reads naturally and is not one of them. The CHECK would have caught it the
    # moment the trigger stopped raising first.
    assert assigned <= allowed, f"status values outside the CHECK: {sorted(assigned - allowed)}"
    assert allowed == _impact_policy_statuses() & allowed


def test_the_policy_validator_lets_a_bad_policy_be_retired_but_not_revived() -> None:
    sql = POLICY_MIGRATION.read_text()

    # Retiring re-validates nothing, so a policy with an unknown predicate can be taken out of
    # service. Without this the seeded version-1 policy deadlocked the migration chain.
    assert "NEW.configuration IS NOT DISTINCT FROM OLD.configuration" in sql
    # Reviving one is still validated, whatever route it takes back to ACTIVE.
    assert "NEW.status='ACTIVE' AND OLD.status IS DISTINCT FROM 'ACTIVE'" in sql


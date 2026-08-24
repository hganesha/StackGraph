import os
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from stackgraph_data.neo4j_project import (
    EDGE_CREATE_CYPHER,
    NODE_UPSERT_CYPHER,
    ClaimedBatch,
    GraphDeployment,
    Neo4jProjectionWorker,
    ProjectionDelivery,
    build_mutation_batch,
    edge_parameters,
    entity_parameters,
    graph_inventory,
    resolve_credential_reference,
)
from stackgraph_data.neo4j_rebuild import Neo4jBlueGreenRebuilder, assert_graph_parity


OBSERVED_AT = datetime(2026, 8, 23, tzinfo=timezone.utc)


class _Result:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class _ProjectionFinishConnection:
    def __init__(self, *, desired=42, projected=42, pending=False):
        self.desired = desired
        self.projected = projected
        self.pending = pending
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "RETURNING tenant_id,deployment_state" in query:
            return _Result({
                "tenant_id": UUID("00000000-0000-0000-0000-000000000099"),
                "deployment_state": "ACTIVE",
                "desired_outbox_id": self.desired,
                "projected_outbox_id": self.projected,
            })
        if "SELECT EXISTS" in query:
            return _Result({"present": self.pending})
        return _Result()


class _ActivationConnection:
    def __init__(self):
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return _Result(rowcount=1)


def fact_row(*, system_to=None, projects_as_edge=True):
    return {
        "fact_id": UUID("00000000-0000-0000-0000-000000000003"),
        "tenant_id": UUID("00000000-0000-0000-0000-000000000099"),
        "predicate": "DEPENDS_ON",
        "assertion_class": "OBSERVED",
        "confidence": Decimal("0.9500"),
        "logical_key": "sha256:" + "a" * 64,
        "fact_properties": {"record_kind": "RELATIONSHIP"},
        "effective_from": None,
        "effective_to": None,
        "observed_at": OBSERVED_AT,
        "system_to": system_to,
        "source_snapshot_id": UUID("00000000-0000-0000-0000-000000000004"),
        "projects_as_edge": projects_as_edge,
        "subject_id": UUID("00000000-0000-0000-0000-000000000001"),
        "subject_tenant_id": UUID("00000000-0000-0000-0000-000000000099"),
        "subject_namespace": "ENTERPRISE",
        "subject_entity_type": "Application",
        "subject_canonical_key": "app:billing",
        "subject_name": "Billing",
        "subject_properties": {"owner": "finance"},
        "subject_first_seen_at": OBSERVED_AT,
        "subject_last_seen_at": OBSERVED_AT,
        "object_id": UUID("00000000-0000-0000-0000-000000000002"),
        "object_tenant_id": None,
        "object_namespace": "TECHNOLOGY",
        "object_entity_type": "Technology",
        "object_canonical_key": "technology:postgresql",
        "object_name": "PostgreSQL",
        "object_properties": {"scope": "GLOBAL"},
        "object_first_seen_at": OBSERVED_AT,
        "object_last_seen_at": OBSERVED_AT,
    }


class Neo4jProjectionMappingTests(unittest.TestCase):
    def test_entity_parameters_use_stable_postgres_id_and_flat_properties(self) -> None:
        parameters = entity_parameters(fact_row(), "object_")

        self.assertEqual(parameters["entity_id"], "00000000-0000-0000-0000-000000000002")
        self.assertIsNone(parameters["properties"]["tenant_id"])
        self.assertEqual(parameters["properties"]["properties_json"], '{"scope":"GLOBAL"}')

    def test_edge_parameters_preserve_fact_identity_and_evidence(self) -> None:
        parameters = edge_parameters(fact_row())

        self.assertEqual(parameters["properties"]["confidence"], 0.95)
        self.assertEqual(
            parameters["properties"]["evidence_fact_ids"],
            ["00000000-0000-0000-0000-000000000003"],
        )

    def test_upsert_replaces_relationship_and_deduplicates_nodes(self) -> None:
        delivery = ProjectionDelivery(
            outbox_id=41,
            aggregate_id=UUID("00000000-0000-0000-0000-000000000003"),
            operation="UPSERT",
        )

        batch = build_mutation_batch([(delivery, fact_row()), (delivery, fact_row())])

        self.assertEqual(len(batch.nodes), 2)
        self.assertEqual(len(batch.edges), 1)
        self.assertEqual(batch.relationship_deletions, ("sha256:" + "a" * 64,))

    def test_closure_only_deletes_the_prior_relationship(self) -> None:
        delivery = ProjectionDelivery(
            outbox_id=42,
            aggregate_id=UUID("00000000-0000-0000-0000-000000000003"),
            operation="CLOSE",
        )

        batch = build_mutation_batch([(delivery, fact_row(system_to=OBSERVED_AT))])

        self.assertFalse(batch.nodes)
        self.assertFalse(batch.edges)
        self.assertEqual(len(batch.relationship_deletions), 1)

    def test_value_fact_projects_subject_node_without_an_edge(self) -> None:
        delivery = ProjectionDelivery(
            outbox_id=43,
            aggregate_id=UUID("00000000-0000-0000-0000-000000000003"),
            operation="UPSERT",
        )
        row = fact_row(projects_as_edge=False)
        row["object_id"] = None

        batch = build_mutation_batch([(delivery, row)])

        self.assertEqual(len(batch.nodes), 1)
        self.assertFalse(batch.edges)
        self.assertFalse(batch.relationship_deletions)

    def test_cypher_is_parameterized_and_batched(self) -> None:
        self.assertIn("UNWIND $rows", NODE_UPSERT_CYPHER)
        self.assertIn("UNWIND $rows", EDGE_CREATE_CYPHER)
        self.assertNotIn("00000000", NODE_UPSERT_CYPHER)

    def test_environment_credential_reference_is_explicit(self) -> None:
        with patch.dict(os.environ, {"STACKGRAPH_TEST_NEO4J_PASSWORD": "secret"}):
            self.assertEqual(
                resolve_credential_reference("env://STACKGRAPH_TEST_NEO4J_PASSWORD"),
                "secret",
            )
        with self.assertRaises(ValueError):
            resolve_credential_reference("vault://tenant/neo4j")

    def test_projection_catch_up_requests_analysis_only_after_queue_drains(self) -> None:
        connection = _ProjectionFinishConnection()
        worker = Neo4jProjectionWorker(
            connection,worker_id="smoke",batch_size=10,encryption_key="smoke",
        )
        batch = ClaimedBatch(
            deployment=GraphDeployment(
                id=UUID("00000000-0000-0000-0000-000000000098"),
                tenant_id=UUID("00000000-0000-0000-0000-000000000099"),
                endpoint="neo4j://smoke",database_name="neo4j",username="neo4j",password="secret",
            ),
            deliveries=(ProjectionDelivery(
                outbox_id=42,aggregate_id=UUID("00000000-0000-0000-0000-000000000003"),operation="UPSERT",
            ),),
        )

        worker._mark_processed(batch)

        requests = [query for query, _ in connection.queries if "stackgraph_request_graph_analysis" in query]
        self.assertEqual(len(requests),1)

        lagging = _ProjectionFinishConnection(desired=43,projected=42)
        lagging_worker = Neo4jProjectionWorker(
            lagging,worker_id="smoke",batch_size=10,encryption_key="smoke",
        )
        lagging_worker._mark_processed(batch)
        self.assertFalse(any("stackgraph_request_graph_analysis" in query for query, _ in lagging.queries))

    def test_rebuild_inventory_is_order_independent_and_duplicate_sensitive(self) -> None:
        expected = graph_inventory(["entity-b", "entity-a"], ["fact-b", "fact-a"])
        reordered = graph_inventory(["entity-a", "entity-b"], ["fact-a", "fact-b"])

        self.assertEqual(expected, reordered)
        assert_graph_parity(expected, reordered)
        duplicate = graph_inventory(
            ["entity-a", "entity-b"], ["fact-a", "fact-b", "fact-b"],
        )
        with self.assertRaisesRegex(RuntimeError, "candidate parity failed"):
            assert_graph_parity(expected, duplicate)

    def test_rebuild_activation_switches_pointer_and_requests_successor_atomically(self) -> None:
        connection = _ActivationConnection()
        tenant_id = UUID("00000000-0000-0000-0000-000000000099")
        deployment_id = UUID("00000000-0000-0000-0000-000000000098")
        rebuilder = Neo4jBlueGreenRebuilder("postgresql://unused", encryption_key="unused")

        rebuilder._activate(
            connection,
            deployment_id=deployment_id,
            tenant_id=tenant_id,
            candidate_database_name="stackgraph_green",
            prior_database_name="stackgraph_blue",
            watermark=42,
            inventory=graph_inventory(["entity-a"], ["fact-a"]),
        )

        self.assertEqual(len(connection.queries), 3)
        switch_query, switch_params = connection.queries[0]
        self.assertIn("prior_database_name=%s,database_name=%s", switch_query)
        self.assertEqual(switch_params[:4], ("stackgraph_blue", "stackgraph_green", 42, 42))
        self.assertIn("status='PROCESSED'", connection.queries[1][0])
        self.assertIn("stackgraph_request_graph_analysis", connection.queries[2][0])


if __name__ == "__main__":
    unittest.main()

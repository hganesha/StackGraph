import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from stackgraph_data.project import (
    EDGE_CREATE_CYPHER,
    NODE_UPSERT_CYPHER,
    edge_parameters,
    entity_parameters,
)


class ProjectionMappingTests(unittest.TestCase):
    def test_entity_parameters_flatten_relational_entity(self) -> None:
        observed_at = datetime(2026, 8, 19, tzinfo=timezone.utc)
        row = {
            "subject_id": UUID("00000000-0000-0000-0000-000000000001"),
            "subject_tenant_id": None,
            "subject_namespace": "TECHNOLOGY",
            "subject_entity_type": "Technology",
            "subject_canonical_key": "stackgraph:technology:react",
            "subject_name": "React",
            "subject_properties": {"domain_id": "frontend"},
            "subject_first_seen_at": observed_at,
            "subject_last_seen_at": observed_at,
        }

        parameters = entity_parameters(row, "subject_")

        self.assertEqual(
            parameters["entity_id"], "00000000-0000-0000-0000-000000000001"
        )
        self.assertIsNone(parameters["tenant_id"])
        self.assertEqual(
            json.loads(parameters["properties_json"]), {"domain_id": "frontend"}
        )

    def test_edge_parameters_preserve_evidence_and_confidence(self) -> None:
        observed_at = datetime(2026, 8, 19, tzinfo=timezone.utc)
        row = {
            "subject_id": UUID("00000000-0000-0000-0000-000000000001"),
            "object_id": UUID("00000000-0000-0000-0000-000000000002"),
            "fact_id": UUID("00000000-0000-0000-0000-000000000003"),
            "tenant_id": None,
            "logical_key": "sha256:" + "a" * 64,
            "predicate": "PROVIDES",
            "confidence": Decimal("0.9500"),
            "assertion_class": "CURATED",
            "effective_from": None,
            "effective_to": None,
            "observed_at": observed_at,
            "source_snapshot_id": UUID("00000000-0000-0000-0000-000000000004"),
            "fact_properties": {"record_kind": "RELATIONSHIP"},
        }

        parameters = edge_parameters(row)

        self.assertEqual(parameters["confidence"], 0.95)
        self.assertEqual(
            parameters["evidence_fact_ids"],
            ["00000000-0000-0000-0000-000000000003"],
        )
        self.assertEqual(parameters["first_seen_at"], parameters["last_seen_at"])

    def test_cypher_uses_parameter_maps(self) -> None:
        self.assertIn("$entity_id", NODE_UPSERT_CYPHER)
        self.assertIn("$logical_key", EDGE_CREATE_CYPHER)


if __name__ == "__main__":
    unittest.main()

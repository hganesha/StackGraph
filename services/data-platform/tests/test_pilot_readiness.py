from __future__ import annotations

import os
import unittest
import uuid

import psycopg

from stackgraph_data.pilot_readiness import (
    collect_database_metrics,
    evaluate_targets,
    percentile,
)


DATABASE_URL = os.environ.get("STACKGRAPH_TEST_DATABASE_URL")


class PilotReadinessTests(unittest.TestCase):
    def test_percentile_handles_empty_and_ordered_values(self) -> None:
        self.assertEqual(percentile([], 0.95), 0)
        self.assertEqual(percentile([3, 1, 2], 0.50), 2)

    def test_complete_metrics_pass_every_automated_target(self) -> None:
        metrics = {
            "repository_targets": 100,
            "complete_scans": 100,
            "material_findings": 5,
            "time_to_first_five_findings_seconds": 1199,
            "facts_with_evidence_ratio": 0.99,
            "failed_repository_runs": 0,
            "pending_projection_events": 0,
            "stale_or_error_sources": 0,
            "github_quota_observations": 1,
            "unavailable_provider_quotas": 0,
            "api": {"requests": 40, "p95_ms": 499, "graph_contract_passed": True},
            "security": {
                "tenant_tables_without_rls": [],
                "unsafe_credential_references": 0,
                "unverified_webhooks": 0,
            },
        }
        targets = evaluate_targets(
            metrics, minimum_repositories=100,
            maximum_first_findings_seconds=1200, maximum_api_p95_ms=500,
        )
        self.assertTrue(all(targets.values()))

    def test_missing_live_evidence_fails_named_targets(self) -> None:
        metrics = {
            "repository_targets": 99,
            "complete_scans": 98,
            "material_findings": 4,
            "time_to_first_five_findings_seconds": None,
            "facts_with_evidence_ratio": 0.98,
            "failed_repository_runs": 1,
            "pending_projection_events": 1,
            "stale_or_error_sources": 1,
            "github_quota_observations": 0,
            "unavailable_provider_quotas": 1,
            "api": None,
            "security": {
                "tenant_tables_without_rls": ["public.fact_assertion"],
                "unsafe_credential_references": 1,
                "unverified_webhooks": 1,
            },
        }
        targets = evaluate_targets(
            metrics, minimum_repositories=100,
            maximum_first_findings_seconds=1200, maximum_api_p95_ms=500,
        )
        self.assertFalse(any(targets.values()))

    @unittest.skipUnless(DATABASE_URL, "STACKGRAPH_TEST_DATABASE_URL is not configured")
    def test_live_collector_executes_against_the_current_schema(self) -> None:
        tenant_key = f"pilot-readiness-{uuid.uuid4()}"
        with psycopg.connect(DATABASE_URL) as connection:
            tenant_id = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Pilot readiness test') RETURNING id",
                (tenant_key,),
            ).fetchone()[0]
            connection.commit()
        try:
            metrics = collect_database_metrics(DATABASE_URL, tenant_key)
            self.assertEqual(metrics["tenant_id"], str(tenant_id))
            self.assertEqual(metrics["repository_targets"], 0)
            self.assertEqual(metrics["facts_with_evidence_ratio"], 1.0)
            self.assertEqual(metrics["security"]["tenant_tables_without_rls"], [])
        finally:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))
                connection.commit()


if __name__ == "__main__":
    unittest.main()

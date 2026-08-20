from __future__ import annotations

import unittest

from stackgraph_data.operations import evaluate


class OperationsSnapshotTests(unittest.TestCase):
    def test_alerts_include_threshold_owner_and_severity(self) -> None:
        alerts = evaluate({
            "ingest_queue_age_seconds": 601,
            "failed_webhooks": 1,
            "throttled_or_exhausted_quotas": 1,
        })
        by_metric = {alert["metric"]: alert for alert in alerts}
        self.assertEqual(by_metric["ingest_queue_age_seconds"]["owner"], "discovery-on-call")
        self.assertEqual(by_metric["ingest_queue_age_seconds"]["severity"], "CRITICAL")
        self.assertEqual(by_metric["failed_webhooks"]["threshold"], 0)
        self.assertEqual(
            by_metric["throttled_or_exhausted_quotas"]["owner"],
            "discovery-on-call",
        )

    def test_healthy_metrics_do_not_alert(self) -> None:
        self.assertEqual(evaluate({}), [])


if __name__ == "__main__":
    unittest.main()

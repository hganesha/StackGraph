from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row


THRESHOLDS = {
    "ingest_queue_age_seconds": (300, "discovery-on-call"),
    "expired_ingest_leases": (0, "discovery-on-call"),
    "unreplayed_dead_letters": (0, "data-platform-on-call"),
    "projection_queue_age_seconds": (120, "data-platform-on-call"),
    "intelligence_queue_age_seconds": (300, "intelligence-on-call"),
    "failed_intelligence_jobs": (0, "intelligence-on-call"),
    "webhook_processing_age_seconds": (60, "discovery-on-call"),
    "failed_webhooks": (0, "discovery-on-call"),
    "stale_or_error_sources": (0, "data-quality-owner"),
    "failed_ai_invocations_24h": (0, "intelligence-on-call"),
}


QUERY = """
SELECT
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM ingest_run WHERE status='PENDING'),0) ingest_queue_age_seconds,
  (SELECT count(*) FROM ingest_run
   WHERE status='RUNNING' AND lease_expires_at<now()) expired_ingest_leases,
  (SELECT count(*) FROM dead_letter WHERE replayed_at IS NULL) unreplayed_dead_letters,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM projection_outbox WHERE processed_at IS NULL),0) projection_queue_age_seconds,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM intelligence_job WHERE status='PENDING'),0) intelligence_queue_age_seconds,
  (SELECT count(*) FROM intelligence_job WHERE status='FAILED') failed_intelligence_jobs,
  coalesce((SELECT extract(epoch FROM now()-min(received_at))::bigint
            FROM webhook_delivery WHERE status='PROCESSING'),0) webhook_processing_age_seconds,
  (SELECT count(*) FROM webhook_delivery WHERE status='FAILED') failed_webhooks,
  (SELECT count(*) FROM freshness_state WHERE status IN ('STALE','ERROR')) stale_or_error_sources,
  (SELECT count(*) FROM ai_model_invocation
   WHERE status='FAILED' AND started_at>=now()-interval '24 hours') failed_ai_invocations_24h,
  (SELECT count(*) FROM ingest_run WHERE status IN ('PENDING','RUNNING')) active_ingest_runs,
  (SELECT count(*) FROM projection_outbox WHERE processed_at IS NULL) pending_projection_events,
  (SELECT count(*) FROM intelligence_job WHERE status IN ('PENDING','RUNNING')) active_intelligence_jobs,
  (SELECT coalesce(sum(actual_cost_usd),0) FROM ai_model_invocation
   WHERE started_at>=now()-interval '24 hours') ai_cost_usd_24h,
  (SELECT coalesce(avg(duration_ms),0)::bigint FROM ai_model_invocation
   WHERE status='SUCCEEDED' AND started_at>=now()-interval '24 hours') ai_latency_ms_24h
"""


def snapshot(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(QUERY).fetchone()
    assert row is not None
    metrics = {
        key: float(value) if key == "ai_cost_usd_24h" else int(value)
        for key, value in row.items()
    }
    alerts = evaluate(metrics)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "DEGRADED" if alerts else "HEALTHY",
        "metrics": metrics,
        "alerts": alerts,
    }


def evaluate(metrics: Mapping[str, int | float]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for metric, (threshold, owner) in THRESHOLDS.items():
        value = metrics.get(metric, 0)
        if value > threshold:
            alerts.append({
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "owner": owner,
                "severity": "CRITICAL" if threshold == 0 or value > threshold * 2 else "WARNING",
            })
    return alerts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit the StackGraph operational SLO snapshot")
    parser.add_argument("--database-url", default=os.getenv("STACKGRAPH_DATABASE_URL"))
    parser.add_argument("--fail-on-alert", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or STACKGRAPH_DATABASE_URL is required")
    report = snapshot(args.database_url)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if args.fail_on_alert and report["alerts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

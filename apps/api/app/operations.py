from __future__ import annotations

from typing import Any, Mapping


THRESHOLDS: dict[str, tuple[int, str]] = {
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
    "throttled_or_exhausted_quotas": (0, "discovery-on-call"),
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
  (SELECT count(*) FROM connector_quota
   WHERE status IN ('THROTTLED','EXHAUSTED')
     AND (backoff_until IS NULL OR backoff_until>now())) throttled_or_exhausted_quotas,
  (SELECT count(*) FROM ingest_run WHERE status IN ('PENDING','RUNNING')) active_ingest_runs,
  (SELECT count(*) FROM projection_outbox WHERE processed_at IS NULL) pending_projection_events,
  (SELECT count(*) FROM intelligence_job WHERE status IN ('PENDING','RUNNING')) active_intelligence_jobs,
  (SELECT coalesce(sum(actual_cost_usd),0) FROM ai_model_invocation
   WHERE started_at>=now()-interval '24 hours') ai_cost_usd_24h,
  (SELECT coalesce(avg(duration_ms),0)::bigint FROM ai_model_invocation
   WHERE status='SUCCEEDED' AND started_at>=now()-interval '24 hours') ai_latency_ms_24h
"""


def normalize_metrics(row: Mapping[str, Any]) -> dict[str, int | float]:
    return {
        key: float(value) if key == "ai_cost_usd_24h" else int(value)
        for key, value in row.items()
    }


def prometheus_text(metrics: Mapping[str, int | float]) -> str:
    lines = [
        "# HELP stackgraph_operational_signal StackGraph operational SLO signal.",
        "# TYPE stackgraph_operational_signal gauge",
    ]
    for name, value in sorted(metrics.items()):
        lines.append(f'stackgraph_operational_signal{{signal="{name}"}} {value}')
    lines.extend([
        "# HELP stackgraph_operational_alert Whether an operational threshold is breached.",
        "# TYPE stackgraph_operational_alert gauge",
    ])
    for name, (threshold, owner) in sorted(THRESHOLDS.items()):
        breached = 1 if metrics.get(name, 0) > threshold else 0
        lines.append(
            f'stackgraph_operational_alert{{signal="{name}",owner="{owner}",threshold="{threshold}"}} {breached}'
        )
    return "\n".join(lines) + "\n"

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
    "graph_projection_lag_events": (1000, "graph-intelligence-on-call"),
    "graph_projection_queue_age_seconds": (300, "graph-intelligence-on-call"),
    "graph_analysis_queue_age_seconds": (600, "graph-intelligence-on-call"),
    "failed_graph_analysis_requests": (0, "graph-intelligence-on-call"),
    "graph_snapshot_age_seconds": (1800, "graph-intelligence-on-call"),
    "failed_graph_rebuilds": (0, "graph-intelligence-on-call"),
    "graph_risk_materialization_gap": (0, "graph-intelligence-on-call"),
    "embedding_queue_age_seconds": (600, "intelligence-on-call"),
    "expired_embedding_leases": (0, "intelligence-on-call"),
    "dead_letter_embedding_jobs": (0, "intelligence-on-call"),
    "embedding_coverage_gap_basis_points": (0, "intelligence-on-call"),
    "embedding_provider_failures_24h": (0, "intelligence-on-call"),
    "simulation_queue_age_seconds": (300, "data-platform-on-call"),
    "expired_simulation_leases": (0, "data-platform-on-call"),
    "failed_simulation_runs": (0, "graph-intelligence-on-call"),
    "limited_simulations_24h": (0, "graph-intelligence-on-call"),
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
  coalesce((
    SELECT max(greatest(0,deployment.desired_outbox_id-deployment.projected_outbox_id))
    FROM tenant_graph_deployment deployment
    WHERE deployment.deployment_state='ACTIVE'
  ),0) graph_projection_lag_events,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM graph_projection_delivery WHERE status IN ('PENDING','PROCESSING')),0)
    graph_projection_queue_age_seconds,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM graph_analysis_request WHERE status IN ('PENDING','WAITING_FOR_PROJECTION')),0)
    graph_analysis_queue_age_seconds,
  (SELECT count(*) FROM graph_analysis_request failed
   WHERE failed.status='FAILED' AND NOT EXISTS (
     SELECT 1 FROM graph_analysis_request recovered
     WHERE recovered.tenant_id=failed.tenant_id
       AND recovered.policy_id=failed.policy_id
       AND recovered.status='SUCCEEDED'
       AND recovered.completed_at>failed.completed_at
   )) failed_graph_analysis_requests,
  coalesce((SELECT extract(epoch FROM now()-max(completed_at))::bigint
            FROM graph_analysis_run WHERE status IN ('SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS')),0)
    graph_snapshot_age_seconds,
  (SELECT count(*) FROM tenant_graph_deployment WHERE rebuild_state='FAILED') failed_graph_rebuilds,
  (SELECT count(*) FROM active_graph_analysis_run active
   JOIN graph_analysis_run run ON run.id=active.run_id
   WHERE run.policy_key='runtime-dependency' AND coalesce(run.node_count,0)>0
     AND NOT EXISTS (
       SELECT 1 FROM graph_entity_risk risk
       WHERE risk.tenant_id=active.tenant_id AND risk.run_id=active.run_id
     )) graph_risk_materialization_gap,
  (SELECT count(*) FROM tenant_graph_deployment WHERE rebuild_state='RUNNING') active_graph_rebuilds,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM embedding_job WHERE status IN ('PENDING','RETRY_WAIT')),0)
    embedding_queue_age_seconds,
  (SELECT count(*) FROM embedding_job
   WHERE status='RUNNING' AND lease_expires_at<now()) expired_embedding_leases,
  (SELECT count(*) FROM embedding_job WHERE status='DEAD_LETTER') dead_letter_embedding_jobs,
  coalesce((
    SELECT CASE WHEN policy.enabled AND active.embedding_space_id IS NULL THEN 9500
                ELSE greatest(0,9500-round(coalesce(space.coverage_ratio,0)*10000)::integer) END
    FROM tenant_embedding_policy policy
    LEFT JOIN active_embedding_space active ON active.tenant_id=policy.tenant_id
      AND active.space_kind='SEMANTIC_ENTITY'
    LEFT JOIN embedding_space space ON space.id=active.embedding_space_id
    ORDER BY policy.tenant_id LIMIT 1
  ),0) embedding_coverage_gap_basis_points,
  (SELECT count(*) FROM entity_embedding
   WHERE created_at>=now()-interval '24 hours'
     AND coalesce((provider_usage->>'cache_hit')::boolean,false)=false)
    embedding_provider_requests_24h,
  (SELECT count(*) FROM entity_embedding
   WHERE created_at>=now()-interval '24 hours'
     AND coalesce((provider_usage->>'cache_hit')::boolean,false)=true)
    embedding_cache_hits_24h,
  (SELECT coalesce(sum(token_count),0) FROM entity_embedding
   WHERE created_at>=now()-interval '24 hours') embedding_provider_tokens_24h,
  (SELECT coalesce(avg(provider_latency_ms),0)::bigint FROM entity_embedding
   WHERE created_at>=now()-interval '24 hours'
     AND coalesce((provider_usage->>'cache_hit')::boolean,false)=false)
    embedding_provider_latency_ms_24h,
  (SELECT count(*) FROM embedding_job
   WHERE updated_at>=now()-interval '24 hours'
     AND last_error_class='EMBEDDING_RATE_LIMIT') embedding_rate_limits_24h,
  (SELECT count(*) FROM embedding_job
   WHERE updated_at>=now()-interval '24 hours'
     AND last_error_class IN ('EMBEDDING_PROVIDER_HTTP','EMBEDDING_PROVIDER_UNAVAILABLE'))
    embedding_provider_failures_24h,
  coalesce((SELECT extract(epoch FROM now()-min(created_at))::bigint
            FROM simulation_run WHERE status='QUEUED'),0) simulation_queue_age_seconds,
  (SELECT count(*) FROM simulation_run
   WHERE status='RUNNING' AND leased_until<now()) expired_simulation_leases,
  (SELECT count(*) FROM simulation_run WHERE status='FAILED') failed_simulation_runs,
  (SELECT count(*) FROM simulation_run
   WHERE status='LIMITED' AND completed_at>=now()-interval '24 hours') limited_simulations_24h,
  (SELECT count(*) FROM simulation_run WHERE status IN ('QUEUED','RUNNING')) active_simulation_runs,
  (SELECT coalesce(avg(extract(epoch FROM (completed_at-started_at))*1000),0)::bigint
   FROM simulation_run
   WHERE status IN ('SUCCEEDED','LIMITED','NOT_SIMULATABLE')
     AND completed_at>=now()-interval '24 hours') simulation_duration_ms_24h,
  (SELECT coalesce(sum(jsonb_array_length(limitations)),0) FROM simulation_run
   WHERE completed_at>=now()-interval '24 hours') simulation_limitations_24h,
  (SELECT count(*) FROM ingest_run WHERE status IN ('PENDING','RUNNING')) active_ingest_runs,
  (SELECT count(*) FROM projection_outbox WHERE processed_at IS NULL) pending_projection_events,
  (SELECT count(*) FROM intelligence_job WHERE status IN ('PENDING','RUNNING')) active_intelligence_jobs,
  (SELECT count(*) FROM graph_analysis_request
   WHERE status IN ('PENDING','WAITING_FOR_PROJECTION','RUNNING')) active_graph_analysis_requests,
  (SELECT count(*) FROM embedding_job
   WHERE status IN ('PENDING','RETRY_WAIT','RUNNING')) active_embedding_jobs,
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

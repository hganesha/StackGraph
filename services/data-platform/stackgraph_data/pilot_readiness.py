from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row


def percentile(values: Iterable[float], percentage: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentage)))
    return ordered[index]


def evaluate_targets(
    metrics: dict[str, Any],
    *,
    minimum_repositories: int,
    maximum_first_findings_seconds: float,
    maximum_api_p95_ms: float,
) -> dict[str, bool]:
    api = metrics.get("api") or {}
    security = metrics.get("security") or {}
    return {
        "repository_count": metrics["repository_targets"] >= minimum_repositories,
        "complete_scans": metrics["complete_scans"] >= minimum_repositories,
        "five_material_findings": metrics["material_findings"] >= 5,
        "first_five_findings": (
            metrics["time_to_first_five_findings_seconds"] is not None
            and metrics["time_to_first_five_findings_seconds"]
            <= maximum_first_findings_seconds
        ),
        "evidence_coverage": metrics["facts_with_evidence_ratio"] >= 0.99,
        "zero_failed_repository_runs": metrics["failed_repository_runs"] == 0,
        "projection_drained": metrics["pending_projection_events"] == 0,
        "fresh_sources": metrics["stale_or_error_sources"] == 0,
        "provider_quota_available": metrics["github_quota_observations"] > 0,
        "provider_not_blocked": metrics["unavailable_provider_quotas"] == 0,
        "api_measured": bool(api.get("requests")),
        "api_latency": bool(api.get("requests")) and api.get("p95_ms", float("inf")) <= maximum_api_p95_ms,
        "bounded_graph": bool(api.get("graph_contract_passed")),
        "tenant_tables_have_rls": security.get("tenant_tables_without_rls") == [],
        "credential_references_only": security.get("unsafe_credential_references") == 0,
        "verified_webhooks_only": security.get("unverified_webhooks") == 0,
    }


def collect_database_metrics(database_url: str, tenant_key: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        tenant = connection.execute(
            "SELECT id FROM tenant WHERE tenant_key=%s", (tenant_key,),
        ).fetchone()
        if tenant is None:
            raise ValueError(f"unknown tenant_key: {tenant_key}")
        tenant_id = tenant["id"]
        summary = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM ingest_target
               WHERE tenant_id=%(tenant_id)s AND target_kind='REPOSITORY') repository_targets,
              (SELECT count(*) FROM (
                 SELECT DISTINCT ON (snapshot.ingest_target_id)
                   snapshot.ingest_target_id,snapshot.completeness
                 FROM source_snapshot snapshot
                 JOIN ingest_target target ON target.id=snapshot.ingest_target_id
                 WHERE target.tenant_id=%(tenant_id)s
                   AND target.target_kind='REPOSITORY'
                   AND snapshot.status='PUBLISHED'
                 ORDER BY snapshot.ingest_target_id,snapshot.published_at DESC,snapshot.id DESC
               ) latest WHERE completeness='COMPLETE') complete_scans,
              (SELECT count(*) FROM ingest_run run
               JOIN ingest_target target ON target.id=run.ingest_target_id
               WHERE target.tenant_id=%(tenant_id)s AND target.target_kind='REPOSITORY'
                 AND run.status IN ('FAILED','CANCELLED')) failed_repository_runs,
              (SELECT count(*) FROM fact_assertion fact
               WHERE fact.tenant_id=%(tenant_id)s AND fact.system_to IS NULL
                 AND fact.predicate='HAS_PROPERTY'
                 AND fact.object_value ? 'finding_type'
                 AND EXISTS (SELECT 1 FROM evidence WHERE fact_assertion_id=fact.id)) material_findings,
              (SELECT CASE WHEN count(*)=0 THEN 1.0 ELSE
                 count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM evidence WHERE fact_assertion_id=fact.id
                 ))::numeric/count(*) END
               FROM fact_assertion fact
               WHERE fact.tenant_id=%(tenant_id)s AND fact.system_to IS NULL) facts_with_evidence_ratio,
              (SELECT count(*) FROM projection_outbox
               WHERE tenant_id=%(tenant_id)s AND processed_at IS NULL) pending_projection_events,
              (SELECT count(*) FROM freshness_state
               WHERE tenant_id=%(tenant_id)s AND status IN ('STALE','ERROR')) stale_or_error_sources,
              (SELECT count(*) FROM connector_quota
               WHERE tenant_id=%(tenant_id)s AND provider='GITHUB_APP') github_quota_observations,
              (SELECT count(*) FROM connector_quota
               WHERE tenant_id=%(tenant_id)s AND status IN ('THROTTLED','EXHAUSTED')
                 AND (backoff_until IS NULL OR backoff_until>now())) unavailable_provider_quotas,
              (SELECT count(*) FROM intelligence_job
               WHERE tenant_id=%(tenant_id)s AND status IN ('PENDING','RUNNING')) active_intelligence_jobs
            """,
            {"tenant_id": tenant_id},
        ).fetchone()
        assert summary is not None
        durations = [
            float(row["duration_seconds"])
            for row in connection.execute(
                """
                SELECT extract(epoch FROM completed_at-started_at) duration_seconds
                FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
                WHERE target.tenant_id=%s AND target.target_kind='REPOSITORY'
                  AND run.status IN ('SUCCEEDED','PARTIAL')
                  AND run.started_at IS NOT NULL AND run.completed_at IS NOT NULL
                """,
                (tenant_id,),
            ).fetchall()
        ]
        timing = connection.execute(
            """
            WITH started AS (
              SELECT min(run.started_at) value
              FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
              WHERE target.tenant_id=%s AND target.target_kind='REPOSITORY'
            ), fifth AS (
              SELECT observed_at value FROM fact_assertion fact
              WHERE fact.tenant_id=%s AND fact.system_to IS NULL
                AND fact.predicate='HAS_PROPERTY' AND fact.object_value ? 'finding_type'
                AND EXISTS (SELECT 1 FROM evidence WHERE fact_assertion_id=fact.id)
              ORDER BY observed_at,id OFFSET 4 LIMIT 1
            )
            SELECT CASE WHEN started.value IS NULL OR fifth.value IS NULL THEN NULL
              ELSE extract(epoch FROM fifth.value-started.value) END seconds
            FROM started LEFT JOIN fifth ON true
            """,
            (tenant_id, tenant_id),
        ).fetchone()
        quotas = [dict(row) for row in connection.execute(
            """
            SELECT provider,used,limit_value,status,resets_at,backoff_until,observed_at
            FROM connector_quota WHERE tenant_id=%s ORDER BY provider
            """,
            (tenant_id,),
        ).fetchall()]
        security = _security_metrics(connection, tenant_id)
        center = connection.execute(
            """
            SELECT id FROM entity WHERE tenant_id=%s AND entity_type='Repository'
            ORDER BY updated_at DESC,id LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()

    metrics = {key: int(value) if key != "facts_with_evidence_ratio" else float(value)
               for key, value in summary.items()}
    metrics.update({
        "tenant_id": str(tenant_id),
        "repository_scan_seconds": {
            "median": round(statistics.median(durations), 3) if durations else None,
            "p95": round(percentile(durations, 0.95), 3) if durations else None,
            "max": round(max(durations), 3) if durations else None,
        },
        "time_to_first_five_findings_seconds": (
            round(float(timing["seconds"]), 3)
            if timing is not None and timing["seconds"] is not None else None
        ),
        "quotas": quotas,
        "security": security,
        "graph_center_id": str(center["id"]) if center else None,
    })
    return metrics


def _security_metrics(connection: psycopg.Connection, tenant_id: Any) -> dict[str, Any]:
    missing_rls = [
        f"{row['schema_name']}.{row['table_name']}"
        for row in connection.execute(
            """
            SELECT namespace.nspname schema_name,class.relname table_name
            FROM pg_class class
            JOIN pg_namespace namespace ON namespace.oid=class.relnamespace
            JOIN pg_attribute attribute ON attribute.attrelid=class.oid
            WHERE class.relkind='r' AND attribute.attname='tenant_id'
              AND NOT attribute.attisdropped AND NOT class.relrowsecurity
              AND namespace.nspname='public'
            ORDER BY class.relname
            """
        ).fetchall()
    ]
    unsafe = connection.execute(
        """
        SELECT
          (SELECT count(*) FROM connector_account
           WHERE tenant_id=%s AND credential_reference<>''
             AND credential_reference !~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$')
          +
          (SELECT count(*) FROM connector
           WHERE tenant_id=%s AND credential_reference<>''
             AND credential_reference !~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$') count
        """,
        (tenant_id, tenant_id),
    ).fetchone()
    unverified = connection.execute(
        "SELECT count(*) count FROM webhook_delivery WHERE tenant_id=%s AND NOT signature_verified",
        (tenant_id,),
    ).fetchone()
    return {
        "tenant_tables_without_rls": missing_rls,
        "unsafe_credential_references": int(unsafe["count"]),
        "unverified_webhooks": int(unverified["count"]),
    }


def measure_api(
    base_url: str,
    *,
    center_id: str | None,
    bearer_token: str | None,
    requests_per_route: int,
) -> dict[str, Any]:
    if requests_per_route < 1:
        raise ValueError("requests_per_route must be positive")
    root = base_url.rstrip("/")
    paths = ["/health/ready", "/api/v1/estate/summary?limit=100", "/api/v1/modernization?limit=100"]
    if center_id:
        paths.append("/api/v1/graph/neighborhood?" + urlencode({
            "center_id": center_id, "depth": 2, "real_node_limit": 50,
        }))
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    durations: list[float] = []
    graph_contract_passed = center_id is not None
    for path in paths:
        for _ in range(requests_per_route):
            started = time.perf_counter()
            with urlopen(Request(root + path, headers=headers), timeout=15) as response:
                payload = json.load(response)
            durations.append((time.perf_counter() - started) * 1000)
            if path.startswith("/api/v1/graph/"):
                graph_contract_passed = graph_contract_passed and len(payload["nodes"]) <= 50
    return {
        "routes": len(paths),
        "requests": len(durations),
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "max_ms": round(max(durations), 2),
        "graph_contract_passed": graph_contract_passed,
    }


def run(
    database_url: str,
    tenant_key: str,
    *,
    api_base_url: str | None,
    bearer_token: str | None,
    minimum_repositories: int = 100,
    maximum_first_findings_seconds: float = 1200,
    maximum_api_p95_ms: float = 500,
    api_requests_per_route: int = 10,
) -> dict[str, Any]:
    metrics = collect_database_metrics(database_url, tenant_key)
    metrics["api"] = (
        measure_api(
            api_base_url, center_id=metrics["graph_center_id"], bearer_token=bearer_token,
            requests_per_route=api_requests_per_route,
        )
        if api_base_url else None
    )
    targets = evaluate_targets(
        metrics,
        minimum_repositories=minimum_repositories,
        maximum_first_findings_seconds=maximum_first_findings_seconds,
        maximum_api_p95_ms=maximum_api_p95_ms,
    )
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workload": "representative-live-tenant",
        "tenant_key": tenant_key,
        "thresholds": {
            "minimum_repositories": minimum_repositories,
            "maximum_first_findings_seconds": maximum_first_findings_seconds,
            "maximum_api_p95_ms": maximum_api_p95_ms,
        },
        "metrics": metrics,
        "targets": targets,
        "automated_gate_passed": all(targets.values()),
        "production_acceptance": "PENDING_HUMAN_AND_DEPLOYMENT_SIGNOFF",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the representative StackGraph pilot gate")
    parser.add_argument("--database-url", default=os.getenv("STACKGRAPH_DATABASE_URL"))
    parser.add_argument("--tenant-key", required=True)
    parser.add_argument("--api-base-url")
    parser.add_argument("--bearer-token", default=os.getenv("STACKGRAPH_PILOT_BEARER_TOKEN"))
    parser.add_argument("--minimum-repositories", type=int, default=100)
    parser.add_argument("--maximum-first-findings-seconds", type=float, default=1200)
    parser.add_argument("--maximum-api-p95-ms", type=float, default=500)
    parser.add_argument("--api-requests-per-route", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or STACKGRAPH_DATABASE_URL is required")
    report = run(
        args.database_url, args.tenant_key, api_base_url=args.api_base_url,
        bearer_token=args.bearer_token, minimum_repositories=args.minimum_repositories,
        maximum_first_findings_seconds=args.maximum_first_findings_seconds,
        maximum_api_p95_ms=args.maximum_api_p95_ms,
        api_requests_per_route=args.api_requests_per_route,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["automated_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

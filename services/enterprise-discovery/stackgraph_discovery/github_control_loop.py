from __future__ import annotations

import argparse
import json
import os
import socket
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .evidence_store import evidence_store_from_environment
from .github_client import GitHubApiError, GitHubClient, GitHubTransportError
from .github_app_auth import resolve_runtime_credential
from .github_activity import (
    ActivityCollection,
    GitHubRepositoryActivityCollector,
    persist_repository_activity,
)
from .github_installation import InstallationRepositoryDiscovery
from .github_installation_store import (
    reconcile_installation,
)
from .github_snapshot import (
    GitHubRepositoryAcquirer,
    SnapshotLimits,
    materialized_snapshot_path,
)
from .repository_scanner import SCANNER_KEY, SCANNER_VERSION, scan_repository
from .service_heartbeat import record_service_heartbeat


MAX_ATTEMPTS = 5
DEFAULT_CADENCE_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    run_id: UUID
    target_id: UUID
    tenant_id: UUID
    tenant_key: str
    target_kind: str
    target_key: str
    refresh_policy: dict[str, Any]
    credential_reference: str
    attempt: int
    lease_owner: str
    lease_seconds: int
    permissions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkResult:
    status: str
    run_id: str | None = None
    target_key: str | None = None
    source_revision: str | None = None
    retry_after_seconds: int | None = None


class LeaseLostError(RuntimeError):
    """The durable run lease expired or moved to another worker."""


def schedule_due_targets(
    database_url: str,
    *,
    limit: int = 100,
    tenant_id: UUID | None = None,
) -> int:
    if limit < 1:
        raise ValueError("limit must be positive")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            WITH due AS (
              SELECT target.id,target.tenant_id,target.target_kind,
                     target.desired_source_revision
              FROM ingest_target target
              JOIN source_system source ON source.id=target.source_system_id
              JOIN connector_account connector ON connector.id=target.connector_account_id
              WHERE source.source_key='github-app' AND connector.status='ACTIVE'
                AND (%s::uuid IS NULL OR target.tenant_id=%s)
                AND stackgraph_tenant_service_running(target.tenant_id,'github-control-loop')
                AND target.enabled AND target.next_due_at<=now()
                AND coalesce((target.refresh_policy->>'schedule_enabled')::boolean,true)
                AND target.target_kind IN ('GITHUB_INSTALLATION','REPOSITORY')
                AND NOT EXISTS (
                  SELECT 1 FROM ingest_run active
                  WHERE active.ingest_target_id=target.id
                    AND active.status IN ('PENDING','RUNNING')
                )
              ORDER BY CASE target.priority WHEN 'HOT' THEN 0 WHEN 'ON_DEMAND' THEN 1
                           WHEN 'WARM' THEN 2 ELSE 3 END,
                       target.next_due_at,target.created_at
              FOR UPDATE OF target SKIP LOCKED
              LIMIT %s
            )
            INSERT INTO ingest_run(
              tenant_id,ingest_target_id,trigger_kind,requested_source_revision
            )
            SELECT tenant_id,id,
                   CASE WHEN target_kind='GITHUB_INSTALLATION'
                        THEN 'RECONCILIATION' ELSE 'SCHEDULE' END,
                   desired_source_revision
            FROM due RETURNING id
            """,
            (tenant_id, tenant_id, limit),
        ).fetchall()
    return len(rows)


def claim_run(
    database_url: str,
    *,
    worker_id: str,
    lease_seconds: int = 1800,
    tenant_id: UUID | None = None,
) -> ClaimedRun | None:
    if not worker_id.strip():
        raise ValueError("worker_id must not be empty")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            WITH candidate AS (
              SELECT run.id
              FROM ingest_run run
              JOIN ingest_target target ON target.id=run.ingest_target_id
              JOIN source_system source ON source.id=target.source_system_id
              JOIN connector_account connector ON connector.id=target.connector_account_id
              WHERE source.source_key='github-app' AND connector.status='ACTIVE'
                AND (%s::uuid IS NULL OR target.tenant_id=%s)
                AND stackgraph_tenant_service_running(target.tenant_id,'github-control-loop')
                AND target.enabled
                AND (
                  (run.status='PENDING' AND run.available_at<=now()) OR
                  (run.status='RUNNING' AND run.lease_expires_at<=now()
                   AND run.attempt<%s)
                )
              ORDER BY CASE run.trigger_kind WHEN 'WEBHOOK' THEN 0 WHEN 'MANUAL' THEN 1
                           WHEN 'REPLAY' THEN 2 ELSE 3 END,
                       CASE target.priority WHEN 'HOT' THEN 0 WHEN 'ON_DEMAND' THEN 1
                           WHEN 'WARM' THEN 2 ELSE 3 END,
                       run.available_at,run.created_at
              FOR UPDATE OF run SKIP LOCKED LIMIT 1
            )
            UPDATE ingest_run run
            SET status='RUNNING',
                attempt=CASE WHEN run.status='RUNNING' THEN run.attempt+1 ELSE run.attempt END,
                lease_owner=%s,
                lease_expires_at=now()+(%s*interval '1 second'),
                started_at=coalesce(run.started_at,now()),completed_at=NULL,
                error_class=NULL,error_detail=NULL
            FROM candidate,ingest_target target,tenant,
                 connector_account connector
            WHERE run.id=candidate.id AND target.id=run.ingest_target_id
              AND tenant.id=run.tenant_id AND connector.id=target.connector_account_id
            RETURNING run.id run_id,target.id target_id,run.tenant_id,
                      tenant.tenant_key,target.target_kind,target.target_key,
                      target.refresh_policy,connector.credential_reference,
                      connector.permissions,run.attempt
            """,
            (tenant_id, tenant_id, MAX_ATTEMPTS, worker_id, lease_seconds),
        ).fetchone()
    if row is None:
        return None
    return ClaimedRun(
        run_id=row["run_id"], target_id=row["target_id"], tenant_id=row["tenant_id"],
        tenant_key=row["tenant_key"], target_kind=row["target_kind"],
        target_key=row["target_key"], refresh_policy=dict(row["refresh_policy"]),
        credential_reference=row["credential_reference"], attempt=row["attempt"],
        lease_owner=worker_id, lease_seconds=lease_seconds,
        permissions=tuple(str(value) for value in (row.get("permissions") or [])),
    )


def fail_exhausted_leases(database_url: str) -> int:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            UPDATE ingest_run run SET status='FAILED',completed_at=now(),
              lease_owner=NULL,lease_expires_at=NULL,error_class='LEASE_EXHAUSTED',
              error_detail=jsonb_build_object('message','worker lease expired at maximum attempts')
            FROM ingest_target target,source_system source
            WHERE target.id=run.ingest_target_id AND source.id=target.source_system_id
              AND source.source_key='github-app' AND run.status='RUNNING'
              AND run.lease_expires_at<=now() AND run.attempt>=%s
            RETURNING run.id,run.tenant_id,run.ingest_target_id,target.refresh_policy
            """,
            (MAX_ATTEMPTS,),
        ).fetchall()
        for row in rows:
            _defer_target_after_terminal_failure_connection(
                connection,
                target_id=row["ingest_target_id"],
                refresh_policy=row["refresh_policy"],
            )
            connection.execute(
                """
                INSERT INTO dead_letter(
                  tenant_id,source_kind,source_id,error_class,error_detail,replay_metadata
                ) VALUES (%s,'INGEST_RUN',%s,'LEASE_EXHAUSTED',%s,%s)
                """,
                (
                    row["tenant_id"], str(row["id"]),
                    Jsonb({"message": "worker lease expired at maximum attempts"}),
                    Jsonb({"ingest_target_id": str(row["ingest_target_id"])}),
                ),
            )
    return len(rows)


def reconcile_rescan_jobs(
    database_url: str,
    *,
    tenant_id: UUID | None = None,
) -> int:
    """Roll operator rescan jobs up from every linked ingest run."""
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            WITH rollup AS (
              SELECT job.id,
                     bool_or(run.status IN ('FAILED','CANCELLED')) any_failed,
                     bool_and(run.status IN (
                       'SUCCEEDED','PARTIAL','FAILED','CANCELLED'
                     )) all_terminal,
                     min(run.started_at) started_at,
                     max(run.completed_at) completed_at,
                     string_agg(
                       coalesce(run.error_detail->>'message',run.error_class),'; '
                       ORDER BY run.completed_at,run.id
                     ) FILTER (
                       WHERE run.status IN ('FAILED','CANCELLED')
                         AND coalesce(run.error_detail->>'message',run.error_class) IS NOT NULL
                     ) errors
              FROM rescan_job job
              JOIN ingest_run run ON (
                run.stats->>'rescan_job_id'=job.id::text
                OR coalesce(run.stats->'rescan_job_ids','[]'::jsonb) ? job.id::text
              )
              WHERE job.status IN ('PENDING','RUNNING')
                AND (%s::uuid IS NULL OR job.tenant_id=%s)
              GROUP BY job.id
            ), desired AS (
              SELECT *,CASE
                WHEN all_terminal AND any_failed THEN 'FAILED'
                WHEN all_terminal THEN 'SUCCEEDED'
                WHEN started_at IS NOT NULL THEN 'RUNNING'
                ELSE 'PENDING'
              END next_status
              FROM rollup
            )
            UPDATE rescan_job job SET
              status=desired.next_status,
              started_at=coalesce(job.started_at,desired.started_at),
              completed_at=CASE WHEN desired.all_terminal
                THEN coalesce(desired.completed_at,now()) ELSE NULL END,
              last_error=CASE WHEN desired.all_terminal AND desired.any_failed
                THEN coalesce(desired.errors,'one or more ingest runs failed')
                ELSE NULL END,
              updated_at=now()
            FROM desired
            WHERE job.id=desired.id AND (
              job.status IS DISTINCT FROM desired.next_status
              OR (job.started_at IS NULL AND desired.started_at IS NOT NULL)
              OR (desired.all_terminal AND job.completed_at IS NULL)
            )
            RETURNING job.id
            """,
            (tenant_id, tenant_id),
        ).fetchall()
    return len(rows)


def run_once(
    database_url: str,
    *,
    snapshot_root: Path,
    evidence_root: Path,
    worker_id: str | None = None,
    lease_seconds: int = 1800,
) -> WorkResult:
    fail_exhausted_leases(database_url)
    reconcile_rescan_jobs(database_url)
    schedule_due_targets(database_url)
    claimed = claim_run(
        database_url,
        worker_id=worker_id or f"{socket.gethostname()}:{os.getpid()}",
        lease_seconds=lease_seconds,
    )
    if claimed is None:
        return WorkResult(status="IDLE")
    reconcile_rescan_jobs(database_url)
    try:
        if claimed.target_kind == "GITHUB_INSTALLATION":
            source_revision = _reconcile_installation(database_url, claimed)
            _complete_run(database_url, claimed, source_revision, {"operation": "reconcile"})
            return WorkResult(
                status="SUCCEEDED", run_id=str(claimed.run_id),
                target_key=claimed.target_key, source_revision=source_revision,
            )
        if claimed.target_kind != "REPOSITORY":
            raise ValueError(f"unsupported GitHub target kind: {claimed.target_kind}")
        return _acquire_scan_publish(
            database_url, claimed, snapshot_root=snapshot_root,
            evidence_root=evidence_root,
        )
    except LeaseLostError:
        return WorkResult(
            status="LEASE_LOST", run_id=str(claimed.run_id),
            target_key=claimed.target_key,
        )
    except Exception as error:
        try:
            terminal, delay = _fail_run(database_url, claimed, error)
        except LeaseLostError:
            return WorkResult(
                status="LEASE_LOST", run_id=str(claimed.run_id),
                target_key=claimed.target_key,
            )
        return WorkResult(
            status="FAILED" if terminal else "RETRY_SCHEDULED",
            run_id=str(claimed.run_id), target_key=claimed.target_key,
            retry_after_seconds=None if terminal else delay,
        )
    finally:
        reconcile_rescan_jobs(database_url)


def _reconcile_installation(database_url: str, claimed: ClaimedRun) -> str:
    _renew_lease(database_url, claimed)
    installation_id = _required_policy_string(claimed.refresh_policy, "installation_id")
    token = resolve_runtime_credential(
        claimed.credential_reference,
        installation_id=installation_id,
        database_url=database_url,
        tenant_id=claimed.tenant_id,
        credential_encryption_key=os.getenv(
            "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY",
            "stackgraph-local-development-credential-key",
        ),
    )
    client = _client(token)
    snapshot = InstallationRepositoryDiscovery(client).discover(installation_id)
    _renew_lease(database_url, claimed)
    reconcile_installation(database_url, tenant_key=claimed.tenant_key, snapshot=snapshot)
    return snapshot.source_revision


def _acquire_scan_publish(
    database_url: str,
    claimed: ClaimedRun,
    *,
    snapshot_root: Path,
    evidence_root: Path,
) -> WorkResult:
    policy = claimed.refresh_policy
    direct_repository = policy.get("direct_repository") is True
    installation_id = _optional_policy_string(policy, "installation_id")
    repository_id = _optional_policy_string(policy, "repository_id")
    if not direct_repository and installation_id is None:
        raise ValueError("refresh policy installation_id must be a non-empty string")
    if not direct_repository and repository_id is None:
        raise ValueError("refresh policy repository_id must be a non-empty string")
    full_name = _required_policy_string(policy, "full_name")
    previous_revision = _previous_revision(database_url, claimed.target_id)
    acquisition_previous_revision = previous_revision
    if (
        previous_revision is not None
        and repository_id is not None
        and not _scanner_snapshot_exists(database_url, claimed.target_id, previous_revision)
    ):
        try:
            request, raw_observation = _cached_scanner_request(
                claimed,
                repository_id=repository_id,
                source_revision=previous_revision,
                snapshot_root=snapshot_root,
            )
        except FileNotFoundError:
            # The durable source artifact may have been aged out. In that case the
            # provider is the only safe way to materialize the revision again.
            acquisition_previous_revision = None
        else:
            _renew_lease(database_url, claimed)
            return _scan_publish_request(
                database_url,
                claimed,
                request=request,
                raw_observation=raw_observation,
                source_revision=previous_revision,
            )
    token = resolve_runtime_credential(
        claimed.credential_reference,
        installation_id=installation_id,
        database_url=database_url,
        tenant_id=claimed.tenant_id,
        credential_encryption_key=os.getenv(
            "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY",
            "stackgraph-local-development-credential-key",
        ),
    )
    _renew_lease(database_url, claimed)
    client = _client(token)
    result = GitHubRepositoryAcquirer(client).acquire(
        full_name,
        previous_revision=acquisition_previous_revision,
        installation_id=installation_id,
        output_root=snapshot_root,
        tenant_key=claimed.tenant_key,
        evidence_store=evidence_store_from_environment({
            **os.environ,
            "STACKGRAPH_EVIDENCE_STORE_ROOT": str(evidence_root),
        }),
        limits=SnapshotLimits(
            max_files=_policy_int(policy, "max_files", 100_000),
            max_bytes=_policy_int(policy, "max_bytes", 1024 * 1024 * 1024),
            max_file_bytes=_policy_int(policy, "max_file_bytes", 2 * 1024 * 1024),
        ),
    )
    _record_github_quota(
        database_url,
        tenant_id=claimed.tenant_id,
        remaining=result.rate_limit_remaining,
        limit=result.rate_limit_limit,
        reset_epoch=result.rate_limit_reset,
    )
    if direct_repository:
        if repository_id is not None and result.repository_id != repository_id:
            raise ValueError("GitHub acquisition repository ID changed for the connected repository")
        claimed = _promote_direct_repository(database_url, claimed, result)
        policy = claimed.refresh_policy
        repository_id = result.repository_id
    elif result.canonical_key != claimed.target_key or result.repository_id != repository_id:
        raise ValueError("GitHub acquisition identity does not match the leased target")
    activity = (
        GitHubRepositoryActivityCollector(client).collect(
            result.full_name,
            default_branch=result.default_branch,
            include_pull_requests="pull_requests:read" in claimed.permissions,
            include_releases="contents:read" in claimed.permissions,
            include_deployments="deployments:read" in claimed.permissions,
        )
        if policy.get("activity_enabled") is True
        else None
    )
    _renew_lease(database_url, claimed)
    if result.status == "UNCHANGED":
        if not _scanner_snapshot_exists(
            database_url, claimed.target_id, result.source_revision,
        ):
            request, raw_observation = _cached_scanner_request(
                claimed,
                repository_id=result.repository_id,
                source_revision=result.source_revision,
                snapshot_root=snapshot_root,
            )
            work = _scan_publish_request(
                database_url,
                claimed,
                request=request,
                raw_observation=raw_observation,
                source_revision=result.source_revision,
            )
            _persist_activity(database_url, claimed, activity)
            return work
        _persist_activity(database_url, claimed, activity)
        _complete_run(
            database_url, claimed, result.source_revision,
            {"operation": "acquire", "changed": False},
        )
        return WorkResult(
            status="UNCHANGED", run_id=str(claimed.run_id),
            target_key=claimed.target_key, source_revision=result.source_revision,
        )
    if result.snapshot is None or result.output_path is None or result.stored_evidence is None:
        raise RuntimeError("changed acquisition did not materialize durable snapshot evidence")
    request = {
        "scanner_contract_version": "1.0.0",
        "run_id": str(claimed.run_id),
        "tenant_key": claimed.tenant_key,
        "target": {
            "provider": "github", "repository_id": repository_id,
            "canonical_key": claimed.target_key,
            "owner": _required_policy_string(policy, "owner"),
            "name": _required_policy_string(policy, "name"),
            "default_branch": result.snapshot.default_branch,
        },
        "snapshot": {
            "source_revision": result.source_revision,
            "checkout_root": str(result.output_path / "files"),
            "requested_at": result.snapshot.observed_at,
            "blob_uri": result.stored_evidence.uri,
            "content_hash": result.stored_evidence.content_hash,
            "content_size_bytes": result.stored_evidence.size_bytes,
        },
        "limits": {
            "max_files": _policy_int(policy, "scan_max_files", 100_000),
            "max_bytes": _policy_int(policy, "scan_max_bytes", 1024 * 1024 * 1024),
            "deadline_seconds": _policy_int(policy, "scan_deadline_seconds", 1200),
        },
    }
    raw_observation = result.snapshot.raw_observation(
        claimed.tenant_key, result.stored_evidence,
    )
    work = _scan_publish_request(
        database_url,
        claimed,
        request=request,
        raw_observation=raw_observation,
        source_revision=result.source_revision,
    )
    _persist_activity(database_url, claimed, activity)
    return work


def _persist_activity(
    database_url: str,
    claimed: ClaimedRun,
    activity: ActivityCollection | None,
) -> bool:
    if activity is None:
        return False
    try:
        return persist_repository_activity(
            database_url,
            tenant_id=claimed.tenant_id,
            repository_key=claimed.target_key,
            collection=activity,
        )
    except psycopg.errors.UndefinedTable:
        # A staggered deployment may start the worker before migration 045 is visible.
        # Repository scanning remains authoritative and the next cadence retries activity.
        return False


def _scan_publish_request(
    database_url: str,
    claimed: ClaimedRun,
    *,
    request: Mapping[str, Any],
    raw_observation: Mapping[str, Any],
    source_revision: str,
) -> WorkResult:
    scan_result = scan_repository(request)
    _renew_lease(database_url, claimed)
    # The data-platform publisher is imported here so discovery-only commands retain
    # their small runtime. The continuous-worker image includes both packages.
    from stackgraph_data.scanner_ingest import persist_scanner_result_connection

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        persisted = persist_scanner_result_connection(
            connection, scan_result, target_id=claimed.target_id,
            run_id=claimed.run_id, raw_observation=raw_observation,
        )
    if persisted.replayed:
        # Another run may have published the same immutable revision while this
        # worker was scanning. Close this leased run without republishing facts.
        _complete_run(
            database_url, claimed, source_revision,
            {"operation": "publish", "replayed_snapshot": True},
        )
    else:
        _mark_target_fresh(database_url, claimed, source_revision)
    return WorkResult(
        status="REPLAYED" if persisted.replayed else "PUBLISHED",
        run_id=str(claimed.run_id),
        target_key=claimed.target_key, source_revision=source_revision,
    )


def _previous_revision(database_url: str, target_id: UUID) -> str | None:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT source_revision FROM source_snapshot
            WHERE ingest_target_id=%s AND status='PUBLISHED'
            ORDER BY published_at DESC,id DESC LIMIT 1
            """,
            (target_id,),
        ).fetchone()
    return None if row is None else str(row["source_revision"])


def _scanner_snapshot_exists(
    database_url: str,
    target_id: UUID,
    source_revision: str,
) -> bool:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM source_snapshot
            WHERE ingest_target_id=%s AND source_revision=%s AND status='PUBLISHED'
              AND extractor_key=%s AND extractor_version=%s
            """,
            (target_id, source_revision, SCANNER_KEY, SCANNER_VERSION),
        ).fetchone()
    return row is not None


def _cached_scanner_request(
    claimed: ClaimedRun,
    *,
    repository_id: str,
    source_revision: str,
    snapshot_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    materialized = materialized_snapshot_path(
        snapshot_root, repository_id, source_revision,
    ).resolve()
    if not materialized.is_relative_to(snapshot_root.resolve()):
        raise ValueError("cached snapshot path escapes the snapshot root")
    snapshot_path = materialized / "snapshot.json"
    raw_path = materialized / "raw-observation.json"
    files_path = materialized / "files"
    if not snapshot_path.is_file() or not raw_path.is_file() or not files_path.is_dir():
        raise FileNotFoundError("cached repository snapshot is unavailable for scanner replay")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    raw_observation = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict) or not isinstance(raw_observation, dict):
        raise ValueError("cached repository snapshot metadata is invalid")
    if snapshot.get("source_revision") != source_revision:
        raise ValueError("cached repository snapshot revision does not match the acquisition")
    content = raw_observation.get("content")
    if not isinstance(content, dict):
        raise ValueError("cached raw observation content descriptor is missing")
    policy = claimed.refresh_policy
    request = {
        "scanner_contract_version": "1.0.0",
        "run_id": str(claimed.run_id),
        "tenant_key": claimed.tenant_key,
        "target": {
            "provider": "github", "repository_id": repository_id,
            "canonical_key": claimed.target_key,
            "owner": _required_policy_string(policy, "owner"),
            "name": _required_policy_string(policy, "name"),
            "default_branch": snapshot.get("default_branch"),
        },
        "snapshot": {
            "source_revision": source_revision,
            "checkout_root": str(files_path),
            "requested_at": snapshot.get("observed_at"),
            "blob_uri": content.get("blob_uri"),
            "content_hash": content.get("hash"),
            "content_size_bytes": content.get("size_bytes"),
        },
        "limits": {
            "max_files": _policy_int(policy, "scan_max_files", 100_000),
            "max_bytes": _policy_int(policy, "scan_max_bytes", 1024 * 1024 * 1024),
            "deadline_seconds": _policy_int(policy, "scan_deadline_seconds", 1200),
        },
    }
    return request, raw_observation


def _promote_direct_repository(
    database_url: str,
    claimed: ClaimedRun,
    result: Any,
) -> ClaimedRun:
    if result.snapshot is None and result.canonical_key != claimed.target_key:
        raise ValueError("an unchanged direct repository cannot change target identity")
    policy = {
        **claimed.refresh_policy,
        "repository_id": result.repository_id,
        "default_branch": result.default_branch,
        "full_name": result.full_name,
        "visibility": result.visibility.upper(),
        "archived": result.archived,
    }
    # Direct-repository connections start with only owner/name because the admin
    # API must not trust client-supplied repository metadata. The repository API
    # response is authoritative and is available even when the commit is unchanged,
    # so lifecycle changes remain observable without a source-code revision.
    with psycopg.connect(database_url) as connection:
        updated = connection.execute(
            """
            UPDATE ingest_target
            SET target_key=%s,refresh_policy=%s,updated_at=now()
            WHERE id=%s AND target_key=%s
            RETURNING id
            """,
            (result.canonical_key, Jsonb(policy), claimed.target_id, claimed.target_key),
        ).fetchone()
        if updated is None:
            raise LeaseLostError("the direct repository target changed during acquisition")
    return replace(claimed, target_key=result.canonical_key, refresh_policy=policy)


def _complete_run(
    database_url: str,
    claimed: ClaimedRun,
    source_revision: str,
    stats: Mapping[str, Any],
) -> None:
    cadence = _policy_int(claimed.refresh_policy, "cadence_seconds", DEFAULT_CADENCE_SECONDS)
    with psycopg.connect(database_url) as connection:
        completed = connection.execute(
            """
            UPDATE ingest_run SET status='SUCCEEDED',completeness='COMPLETE',
              stats=coalesce(ingest_run.stats,'{}'::jsonb) || %s,
              completed_at=now(),lease_owner=NULL,lease_expires_at=NULL
            WHERE id=%s AND status='RUNNING' AND lease_owner=%s
              AND lease_expires_at>now()
            RETURNING id
            """,
            (
                Jsonb({**stats, "source_revision": source_revision}),
                claimed.run_id, claimed.lease_owner,
            ),
        ).fetchone()
        if completed is None:
            raise LeaseLostError("ingest run lease was lost before completion")
        schedule_enabled = claimed.refresh_policy.get("schedule_enabled", True) is True
        connection.execute(
            """
            UPDATE ingest_target SET desired_source_revision=%s,last_success_at=now(),
              next_due_at=CASE WHEN %s THEN now()+(%s*interval '1 second') ELSE NULL END,
              updated_at=now()
            WHERE id=%s
            """,
            (source_revision, schedule_enabled, cadence, claimed.target_id),
        )
        _upsert_freshness_connection(
            connection, claimed, source_revision=source_revision,
            cadence_seconds=cadence,
        )


def _mark_target_fresh(
    database_url: str,
    claimed: ClaimedRun,
    source_revision: str,
) -> None:
    cadence = _policy_int(claimed.refresh_policy, "cadence_seconds", DEFAULT_CADENCE_SECONDS)
    with psycopg.connect(database_url) as connection:
        schedule_enabled = claimed.refresh_policy.get("schedule_enabled", True) is True
        connection.execute(
            """
            UPDATE ingest_target SET desired_source_revision=%s,
              next_due_at=CASE WHEN %s THEN now()+(%s*interval '1 second') ELSE NULL END,
              updated_at=now()
            WHERE id=%s
            """,
            (source_revision, schedule_enabled, cadence, claimed.target_id),
        )
        _upsert_freshness_connection(
            connection, claimed, source_revision=source_revision,
            cadence_seconds=cadence,
        )


def _renew_lease(database_url: str, claimed: ClaimedRun) -> None:
    with psycopg.connect(database_url) as connection:
        renewed = connection.execute(
            """
            UPDATE ingest_run
            SET lease_expires_at=now()+(%s*interval '1 second')
            WHERE id=%s AND status='RUNNING' AND lease_owner=%s
              AND lease_expires_at>now()
            RETURNING id
            """,
            (claimed.lease_seconds, claimed.run_id, claimed.lease_owner),
        ).fetchone()
    if renewed is None:
        raise LeaseLostError("ingest run lease expired or changed owner")


def _upsert_freshness_connection(
    connection: psycopg.Connection,
    claimed: ClaimedRun,
    *,
    source_revision: str,
    cadence_seconds: int,
) -> None:
    connection.execute(
        """
        INSERT INTO freshness_state(
          tenant_id,ingest_target_id,expected_by,last_observed_at,
          last_source_revision,status,limitations
        ) VALUES (%s,%s,now()+(%s*interval '1 second'),now(),%s,'FRESH','[]')
        ON CONFLICT(ingest_target_id) DO UPDATE
          SET expected_by=EXCLUDED.expected_by,last_observed_at=EXCLUDED.last_observed_at,
              last_source_revision=EXCLUDED.last_source_revision,status='FRESH',
              limitations='[]',updated_at=now()
        """,
        (
            claimed.tenant_id, claimed.target_id, cadence_seconds,
            source_revision,
        ),
    )


def _fail_run(
    database_url: str,
    claimed: ClaimedRun,
    error: Exception,
) -> tuple[bool, int]:
    retryable = isinstance(error, GitHubTransportError) or (
        isinstance(error, GitHubApiError) and error.retriable
    )
    terminal = not retryable or claimed.attempt >= MAX_ATTEMPTS
    delay = _retry_delay(error, claimed.attempt)
    detail = {
        "type": type(error).__name__, "message": str(error)[:2000],
        "failed_at": datetime.now(UTC).isoformat(),
    }
    with psycopg.connect(database_url) as connection:
        updated = connection.execute(
            """
            UPDATE ingest_run SET status=%s,attempt=%s,available_at=%s,
              completed_at=CASE WHEN %s THEN now() ELSE NULL END,
              lease_owner=NULL,lease_expires_at=NULL,error_class=%s,error_detail=%s
            WHERE id=%s AND status='RUNNING' AND lease_owner=%s
              AND lease_expires_at>now()
            RETURNING id
            """,
            (
                "FAILED" if terminal else "PENDING",
                claimed.attempt if terminal else claimed.attempt + 1,
                datetime.now(UTC) + timedelta(seconds=delay), terminal,
                type(error).__name__, Jsonb(detail), claimed.run_id,
                claimed.lease_owner,
            ),
        ).fetchone()
        if updated is None:
            raise LeaseLostError("ingest run lease was lost before failure recording")
        if (
            isinstance(error, GitHubApiError)
            and error.retriable
            and error.status_code in {403, 429}
        ):
            _record_github_quota_connection(
                connection,
                tenant_id=claimed.tenant_id,
                remaining=error.rate_limit_remaining,
                limit=error.rate_limit_limit,
                reset_epoch=error.rate_limit_reset,
                backoff_seconds=delay,
                forced_status=_quota_status(
                    error.rate_limit_remaining, throttled=True,
                ),
            )
        connection.execute(
            """
            INSERT INTO freshness_state(
              tenant_id,ingest_target_id,expected_by,status,limitations
            ) VALUES (%s,%s,now(),'ERROR',%s)
            ON CONFLICT(ingest_target_id) DO UPDATE
              SET expected_by=EXCLUDED.expected_by,status='ERROR',
                  limitations=EXCLUDED.limitations,updated_at=now()
            """,
            (claimed.tenant_id, claimed.target_id, Jsonb([detail])),
        )
        if terminal:
            _defer_target_after_terminal_failure_connection(
                connection,
                target_id=claimed.target_id,
                refresh_policy=claimed.refresh_policy,
            )
            connection.execute(
                """
                INSERT INTO dead_letter(
                  tenant_id,source_kind,source_id,error_class,error_detail,replay_metadata
                ) VALUES (%s,'INGEST_RUN',%s,%s,%s,%s)
                """,
                (
                    claimed.tenant_id, str(claimed.run_id), type(error).__name__,
                    Jsonb(detail), Jsonb({"ingest_target_id": str(claimed.target_id)}),
                ),
            )
    return terminal, delay


def _defer_target_after_terminal_failure_connection(
    connection: psycopg.Connection,
    *,
    target_id: UUID,
    refresh_policy: Mapping[str, Any],
) -> None:
    """Prevent a terminal failure from being rescheduled in a tight loop."""
    schedule_enabled = refresh_policy.get("schedule_enabled", True) is True
    cadence = _policy_int(refresh_policy, "cadence_seconds", DEFAULT_CADENCE_SECONDS)
    connection.execute(
        """
        UPDATE ingest_target
        SET next_due_at=CASE WHEN %s THEN now()+(%s*interval '1 second') ELSE NULL END,
            updated_at=now()
        WHERE id=%s
        """,
        (schedule_enabled, cadence, target_id),
    )


def _quota_status(remaining: int | None, *, throttled: bool = False) -> str:
    if remaining is not None and remaining <= 0:
        return "EXHAUSTED"
    return "THROTTLED" if throttled else "OK"


def _record_github_quota(
    database_url: str,
    *,
    tenant_id: UUID,
    remaining: int | None,
    limit: int | None,
    reset_epoch: int | None,
) -> None:
    if remaining is None and limit is None and reset_epoch is None:
        return
    with psycopg.connect(database_url) as connection:
        _record_github_quota_connection(
            connection,
            tenant_id=tenant_id,
            remaining=remaining,
            limit=limit,
            reset_epoch=reset_epoch,
        )


def _record_github_quota_connection(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    remaining: int | None,
    limit: int | None,
    reset_epoch: int | None,
    backoff_seconds: int | None = None,
    forced_status: str | None = None,
) -> None:
    normalized_limit = limit if limit is not None and limit >= 0 else None
    normalized_remaining = remaining if remaining is not None and remaining >= 0 else None
    used = (
        max(0, normalized_limit - normalized_remaining)
        if normalized_limit is not None and normalized_remaining is not None
        else 0
    )
    resets_at = (
        datetime.fromtimestamp(reset_epoch, UTC)
        if reset_epoch is not None and reset_epoch >= 0
        else None
    )
    backoff_until = (
        datetime.now(UTC) + timedelta(seconds=max(1, backoff_seconds))
        if backoff_seconds is not None
        else None
    )
    status = forced_status or _quota_status(normalized_remaining)
    connection.execute(
        """
        INSERT INTO connector_quota(
          tenant_id,provider,used,limit_value,status,resets_at,backoff_until,
          observed_at,updated_at
        ) VALUES (%s,'GITHUB_APP',%s,%s,%s,%s,%s,now(),now())
        ON CONFLICT(tenant_id,provider) DO UPDATE SET
          used=CASE WHEN EXCLUDED.limit_value IS NULL
                    THEN connector_quota.used ELSE EXCLUDED.used END,
          limit_value=coalesce(EXCLUDED.limit_value,connector_quota.limit_value),
          status=EXCLUDED.status,resets_at=coalesce(EXCLUDED.resets_at,connector_quota.resets_at),
          backoff_until=EXCLUDED.backoff_until,observed_at=now(),updated_at=now()
        """,
        (tenant_id, used, normalized_limit, status, resets_at, backoff_until),
    )


def _retry_delay(error: Exception, attempt: int) -> int:
    if isinstance(error, GitHubApiError):
        if error.retry_after_seconds is not None:
            return max(1, min(3600, error.retry_after_seconds))
        if error.rate_limit_reset is not None:
            return max(1, min(3600, error.rate_limit_reset - int(time.time())))
    return min(900, 2 ** min(10, attempt))


def _client(token: str) -> GitHubClient:
    base_url = os.getenv("STACKGRAPH_GITHUB_API_URL", "https://api.github.com")
    return GitHubClient(
        token=token, base_url=base_url,
        allow_insecure_localhost=os.getenv("STACKGRAPH_GITHUB_ALLOW_INSECURE_LOCALHOST") == "true",
    )


def _required_policy_string(policy: Mapping[str, Any], key: str) -> str:
    value = policy.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"refresh policy {key} must be a non-empty string")
    return value


def _optional_policy_string(policy: Mapping[str, Any], key: str) -> str | None:
    value = policy.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"refresh policy {key} must be a non-empty string when present")
    return value


def _policy_int(policy: Mapping[str, Any], key: str, default: int) -> int:
    value = policy.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"refresh policy {key} must be a positive integer")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the leased GitHub discovery control loop")
    parser.add_argument("command", choices=("work", "serve", "schedule"))
    parser.add_argument("--snapshot-root", type=Path, default=Path("/snapshots"))
    parser.add_argument("--evidence-root", type=Path, default=Path("/evidence"))
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}")
    parser.add_argument("--lease-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = os.getenv("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must not be negative")
    if args.command == "schedule":
        print(json.dumps({"scheduled": schedule_due_targets(database_url, limit=args.limit)}))
        return 0
    while True:
        record_service_heartbeat(
            database_url, "github-control-loop", instance_id=args.worker_id,
            metadata={"poll_seconds": args.poll_seconds},
        )
        result = run_once(
            database_url, snapshot_root=args.snapshot_root,
            evidence_root=args.evidence_root, worker_id=args.worker_id,
            lease_seconds=args.lease_seconds,
        )
        print(json.dumps(asdict(result), sort_keys=True), flush=True)
        if args.command == "work":
            return 1 if result.status == "FAILED" else 0
        if result.status in {"IDLE", "RETRY_SCHEDULED"}:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())

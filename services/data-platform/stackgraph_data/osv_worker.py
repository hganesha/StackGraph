from __future__ import annotations

import argparse
import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import canonical_json, sha256_key
from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.osv import (
    OsvApiError,
    OsvBundle,
    OsvClient,
    OsvEnrichment,
    OsvTransportError,
    FactSpec,
    VulnerabilityRecord,
    build_fact_specs,
    normalize_bundle,
    vulnerability_properties,
)


EXTRACTOR_KEY = "osv-v1"
EXTRACTOR_VERSION = "1.0.0"
SOURCE_KEY = "osv.dev"
DEFAULT_REFRESH_SECONDS = 24 * 60 * 60
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MAX_VULNERABILITIES = 100
DEFAULT_MAX_PAGES = 10


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    target_id: str
    run_id: str
    target_key: str
    created: bool


@dataclass(frozen=True, slots=True)
class SyncResult:
    observed: int
    created: int


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    run_id: UUID
    target_id: UUID
    target_key: str
    refresh_policy: dict[str, Any]
    attempt: int


@dataclass(frozen=True, slots=True)
class WorkResult:
    status: str
    run_id: str | None = None
    target_key: str | None = None
    source_revision: str | None = None
    completeness: str | None = None
    replayed: bool = False
    entity_count: int = 0
    fact_count: int = 0
    vulnerability_count: int = 0
    limitation_count: int = 0
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class BatchWorkResult:
    status: str
    claimed: int
    results: tuple[WorkResult, ...]


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    created: int


class LeaseLostError(RuntimeError):
    pass


def enqueue_package_versions(
    database_url: str,
    purls: Iterable[str],
    *,
    priority: str = "WARM",
    max_vulnerabilities: int = DEFAULT_MAX_VULNERABILITIES,
    max_pages: int = DEFAULT_MAX_PAGES,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
) -> tuple[EnqueueResult, ...]:
    targets = _canonical_targets(purls)
    _validate_policy(priority, max_vulnerabilities, max_pages, refresh_seconds)
    policy = _refresh_policy(max_vulnerabilities, max_pages, refresh_seconds)
    results: list[EnqueueResult] = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        source_id = _upsert_osv_source(connection)
        for target in targets:
            results.append(
                _ensure_target_and_run(
                    connection,
                    source_id=source_id,
                    target=target,
                    priority=priority,
                    policy=policy,
                    trigger_kind="MANUAL",
                    refresh_existing=True,
                )
            )
    return tuple(results)


def enqueue_package_version(
    database_url: str,
    purl: str,
    **kwargs: Any,
) -> EnqueueResult:
    return enqueue_package_versions(database_url, [purl], **kwargs)[0]


def ensure_package_version_target_connection(
    connection: Connection[dict[str, Any]],
    purl: str,
    *,
    priority: str = "WARM",
    max_vulnerabilities: int = DEFAULT_MAX_VULNERABILITIES,
    max_pages: int = DEFAULT_MAX_PAGES,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
) -> EnqueueResult:
    """Create an OSV target once without resetting an existing freshness schedule."""
    target = PackageVersionKey.from_purl(purl)
    _validate_policy(priority, max_vulnerabilities, max_pages, refresh_seconds)
    policy = _refresh_policy(max_vulnerabilities, max_pages, refresh_seconds)
    source_id = _upsert_osv_source(connection)
    inserted = connection.execute(
        """
        INSERT INTO ingest_target(
          tenant_id,source_system_id,target_kind,target_key,priority,enabled,
          refresh_policy,next_due_at
        ) VALUES (NULL,%s,'PACKAGE_VERSION',%s,%s,true,%s,now())
        ON CONFLICT(tenant_id,source_system_id,target_kind,target_key)
        DO NOTHING RETURNING id
        """,
        (source_id, target.purl, priority, Jsonb(policy)),
    ).fetchone()
    if inserted is not None:
        run = connection.execute(
            """
            INSERT INTO ingest_run(
              tenant_id,ingest_target_id,trigger_kind,status,available_at
            ) VALUES (NULL,%s,'RECONCILIATION','PENDING',now()) RETURNING id
            """,
            (inserted["id"],),
        ).fetchone()
        assert run is not None
        return EnqueueResult(
            target_id=str(inserted["id"]), run_id=str(run["id"]),
            target_key=target.purl, created=True,
        )
    existing = connection.execute(
        """
        SELECT target.id,(
          SELECT run.id FROM ingest_run run
          WHERE run.ingest_target_id=target.id
            AND run.status IN ('PENDING','RUNNING')
          ORDER BY run.created_at LIMIT 1
        ) run_id
        FROM ingest_target target
        WHERE target.tenant_id IS NULL AND target.source_system_id=%s
          AND target.target_kind='PACKAGE_VERSION' AND target.target_key=%s
        """,
        (source_id, target.purl),
    ).fetchone()
    assert existing is not None
    return EnqueueResult(
        target_id=str(existing["id"]),
        run_id=str(existing["run_id"]) if existing["run_id"] else "",
        target_key=target.purl,
        created=False,
    )


def sync_observed_package_versions(
    database_url: str,
    *,
    limit: int = 1_000,
    max_vulnerabilities: int = DEFAULT_MAX_VULNERABILITIES,
    max_pages: int = DEFAULT_MAX_PAGES,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
) -> SyncResult:
    if limit <= 0:
        raise ValueError("sync limit must be positive")
    _validate_policy("WARM", max_vulnerabilities, max_pages, refresh_seconds)
    policy = _refresh_policy(max_vulnerabilities, max_pages, refresh_seconds)
    created = 0
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        source_id = _upsert_osv_source(connection)
        rows = connection.execute(
            """
            SELECT DISTINCT registry_identity.purl
            FROM package_registry_identity registry_identity
            JOIN entity item ON item.id = registry_identity.entity_id
            WHERE registry_identity.tenant_id IS NULL
              AND registry_identity.visibility = 'PUBLIC'
              AND registry_identity.package_version IS NOT NULL
              AND item.namespace = 'TECHNOLOGY'
              AND item.entity_type = 'PackageVersion'
              AND registry_identity.purl ~ '^pkg:(npm|pypi)/.+@.+'
              AND NOT EXISTS (
                SELECT 1
                FROM ingest_target target
                WHERE target.tenant_id IS NULL
                  AND target.source_system_id = %s
                  AND target.target_kind = 'PACKAGE_VERSION'
                  AND target.target_key = registry_identity.purl
              )
            ORDER BY registry_identity.purl
            LIMIT %s
            """,
            (source_id, limit),
        ).fetchall()
        for row in rows:
            result = _ensure_target_and_run(
                connection,
                source_id=source_id,
                target=PackageVersionKey.from_purl(row["purl"]),
                priority="WARM",
                policy=policy,
                trigger_kind="RECONCILIATION",
                refresh_existing=False,
            )
            created += int(result.created)
    return SyncResult(observed=len(rows), created=created)


def _ensure_target_and_run(
    connection: Connection[dict[str, Any]],
    *,
    source_id: UUID,
    target: PackageVersionKey,
    priority: str,
    policy: dict[str, Any],
    trigger_kind: str,
    refresh_existing: bool,
) -> EnqueueResult:
    if refresh_existing:
        row = connection.execute(
            """
            INSERT INTO ingest_target (
                tenant_id, source_system_id, target_kind, target_key, priority,
                enabled, refresh_policy, next_due_at
            )
            VALUES (NULL, %s, 'PACKAGE_VERSION', %s, %s, true, %s, now())
            ON CONFLICT (tenant_id, source_system_id, target_kind, target_key)
            DO UPDATE SET enabled = true,
                          priority = EXCLUDED.priority,
                          refresh_policy = EXCLUDED.refresh_policy,
                          next_due_at = LEAST(
                              COALESCE(ingest_target.next_due_at, now()), now()
                          ),
                          updated_at = now()
            RETURNING id
            """,
            (source_id, target.purl, priority, Jsonb(policy)),
        ).fetchone()
    else:
        row = connection.execute(
            """
            INSERT INTO ingest_target (
                tenant_id, source_system_id, target_kind, target_key, priority,
                enabled, refresh_policy, next_due_at
            )
            VALUES (NULL, %s, 'PACKAGE_VERSION', %s, %s, true, %s, now())
            ON CONFLICT (tenant_id, source_system_id, target_kind, target_key)
            DO NOTHING
            RETURNING id
            """,
            (source_id, target.purl, priority, Jsonb(policy)),
        ).fetchone()
        if row is None:
            existing = connection.execute(
                """
                SELECT id
                FROM ingest_target
                WHERE tenant_id IS NULL
                  AND source_system_id = %s
                  AND target_kind = 'PACKAGE_VERSION'
                  AND target_key = %s
                """,
                (source_id, target.purl),
            ).fetchone()
            assert existing is not None
            active = connection.execute(
                """
                SELECT id FROM ingest_run
                WHERE ingest_target_id = %s
                  AND status IN ('PENDING', 'RUNNING')
                ORDER BY created_at LIMIT 1
                """,
                (existing["id"],),
            ).fetchone()
            return EnqueueResult(
                target_id=str(existing["id"]),
                run_id=str(active["id"]) if active else "",
                target_key=target.purl,
                created=False,
            )
    assert row is not None
    target_id: UUID = row["id"]
    connection.execute(
        "SELECT id FROM ingest_target WHERE id = %s FOR UPDATE",
        (target_id,),
    )
    active = connection.execute(
        """
        SELECT id FROM ingest_run
        WHERE ingest_target_id = %s
          AND status IN ('PENDING', 'RUNNING')
        ORDER BY created_at LIMIT 1
        """,
        (target_id,),
    ).fetchone()
    if active is not None:
        return EnqueueResult(
            target_id=str(target_id),
            run_id=str(active["id"]),
            target_key=target.purl,
            created=False,
        )
    run = connection.execute(
        """
        INSERT INTO ingest_run (
            tenant_id, ingest_target_id, trigger_kind, status, available_at
        )
        VALUES (NULL, %s, %s, 'PENDING', now())
        RETURNING id
        """,
        (target_id, trigger_kind),
    ).fetchone()
    assert run is not None
    return EnqueueResult(
        target_id=str(target_id),
        run_id=str(run["id"]),
        target_key=target.purl,
        created=True,
    )


def claim_runs(
    database_url: str,
    *,
    worker_id: str,
    batch_size: int = 50,
    lease_seconds: int = 300,
) -> tuple[ClaimedRun, ...]:
    if not worker_id.strip():
        raise ValueError("worker_id must not be empty")
    if batch_size <= 0 or lease_seconds <= 0:
        raise ValueError("batch size and lease duration must be positive")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            WITH candidates AS (
                SELECT run.id
                FROM ingest_run run
                JOIN ingest_target target ON target.id = run.ingest_target_id
                JOIN source_system source ON source.id = target.source_system_id
                WHERE source.source_key = %s
                  AND target.enabled
                  AND (
                    (run.status = 'PENDING' AND run.available_at <= now())
                    OR (
                      run.status = 'RUNNING'
                      AND run.lease_expires_at IS NOT NULL
                      AND run.lease_expires_at <= now()
                    )
                  )
                ORDER BY
                  CASE target.priority
                    WHEN 'HOT' THEN 0
                    WHEN 'ON_DEMAND' THEN 1
                    WHEN 'WARM' THEN 2
                    ELSE 3
                  END,
                  run.available_at,
                  run.created_at
                FOR UPDATE OF run SKIP LOCKED
                LIMIT %s
            )
            UPDATE ingest_run run
            SET status = 'RUNNING',
                attempt = CASE
                    WHEN run.status = 'RUNNING' THEN run.attempt + 1
                    ELSE run.attempt
                END,
                lease_owner = %s,
                lease_expires_at = now() + (%s * interval '1 second'),
                started_at = COALESCE(run.started_at, now()),
                error_class = NULL,
                error_detail = NULL
            FROM candidates, ingest_target target
            WHERE run.id = candidates.id
              AND target.id = run.ingest_target_id
            RETURNING run.id AS run_id, target.id AS target_id,
                      target.target_key, target.refresh_policy, run.attempt
            """,
            (SOURCE_KEY, batch_size, worker_id, lease_seconds),
        ).fetchall()
    return tuple(
        ClaimedRun(
            run_id=row["run_id"],
            target_id=row["target_id"],
            target_key=row["target_key"],
            refresh_policy=row["refresh_policy"],
            attempt=row["attempt"],
        )
        for row in rows
    )


def schedule_due_targets(database_url: str, *, limit: int = 500) -> ScheduleResult:
    if limit <= 0:
        raise ValueError("schedule limit must be positive")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            WITH due AS (
                SELECT target.id
                FROM ingest_target target
                JOIN source_system source ON source.id = target.source_system_id
                WHERE source.source_key = %s
                  AND target.enabled
                  AND target.next_due_at IS NOT NULL
                  AND target.next_due_at <= now()
                  AND NOT EXISTS (
                    SELECT 1 FROM ingest_run active
                    WHERE active.ingest_target_id = target.id
                      AND active.status IN ('PENDING', 'RUNNING')
                  )
                ORDER BY
                  CASE target.priority
                    WHEN 'HOT' THEN 0
                    WHEN 'ON_DEMAND' THEN 1
                    WHEN 'WARM' THEN 2
                    ELSE 3
                  END,
                  target.next_due_at
                FOR UPDATE OF target SKIP LOCKED
                LIMIT %s
            )
            INSERT INTO ingest_run (
                tenant_id, ingest_target_id, trigger_kind, status, available_at
            )
            SELECT NULL, due.id, 'SCHEDULE', 'PENDING', now()
            FROM due
            RETURNING id
            """,
            (SOURCE_KEY, limit),
        ).fetchall()
    return ScheduleResult(created=len(rows))


def run_batch(
    database_url: str,
    *,
    client: OsvClient | None = None,
    worker_id: str | None = None,
    batch_size: int = 50,
    lease_seconds: int = 300,
    schedule_due: bool = True,
) -> BatchWorkResult:
    resolved_worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    if schedule_due:
        schedule_due_targets(database_url)
    claimed = claim_runs(
        database_url,
        worker_id=resolved_worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    if not claimed:
        return BatchWorkResult(status="IDLE", claimed=0, results=())

    valid_claims: list[ClaimedRun] = []
    targets: list[PackageVersionKey] = []
    work_results: list[WorkResult] = []
    for item in claimed:
        try:
            targets.append(PackageVersionKey.from_purl(item.target_key))
            valid_claims.append(item)
        except ValueError as error:
            work_results.append(
                _record_failure(
                    database_url,
                    item,
                    resolved_worker_id,
                    error_class="OSV_TARGET",
                    error_detail={"message": str(error)},
                    retriable=False,
                )
            )

    resolved_client = client or OsvClient()
    if valid_claims:
        max_pages = max(
            _policy_int(item.refresh_policy, "max_pages", DEFAULT_MAX_PAGES)
            for item in valid_claims
        )
        max_vulnerabilities = max(
            _policy_int(
                item.refresh_policy,
                "max_vulnerabilities",
                DEFAULT_MAX_VULNERABILITIES,
            )
            for item in valid_claims
        )
        try:
            query_results = resolved_client.query_batch(
                targets,
                max_pages=max_pages,
                max_vulnerabilities=max_vulnerabilities,
            )
        except (OsvApiError, OsvTransportError, ValueError, KeyError, TypeError) as error:
            work_results.extend(
                _record_client_failure(
                    database_url,
                    item,
                    resolved_worker_id,
                    error,
                )
                for item in valid_claims
            )
        else:
            detail_cache: dict[
                str, tuple[dict[str, Any], str] | Exception
            ] = {}
            _renew_leases(
                database_url,
                valid_claims,
                resolved_worker_id,
                lease_seconds,
            )
            renewed_at = time.monotonic()
            renewal_interval = max(min(lease_seconds / 3, 60), 1)
            for item, query_result in zip(
                valid_claims,
                query_results,
                strict=True,
            ):
                target_limit = _policy_int(
                    item.refresh_policy,
                    "max_vulnerabilities",
                    DEFAULT_MAX_VULNERABILITIES,
                )
                documents: list[dict[str, Any]] = []
                detail_uris: list[str] = []
                detail_error: Exception | None = None
                for ref in query_result.vulnerabilities[:target_limit]:
                    cached = detail_cache.get(ref.osv_id)
                    if cached is None:
                        try:
                            cached = resolved_client.fetch_vulnerability(ref.osv_id)
                        except (
                            OsvApiError,
                            OsvTransportError,
                            ValueError,
                            KeyError,
                            TypeError,
                        ) as error:
                            cached = error
                        detail_cache[ref.osv_id] = cached
                    if time.monotonic() - renewed_at >= renewal_interval:
                        _renew_leases(
                            database_url,
                            valid_claims,
                            resolved_worker_id,
                            lease_seconds,
                        )
                        renewed_at = time.monotonic()
                    if isinstance(cached, Exception):
                        detail_error = cached
                        break
                    document, uri = cached
                    documents.append(document)
                    detail_uris.append(uri)
                if detail_error is not None:
                    work_results.append(
                        _record_client_failure(
                            database_url,
                            item,
                            resolved_worker_id,
                            detail_error,
                        )
                    )
                    continue
                try:
                    enrichment = normalize_bundle(
                        OsvBundle(
                            target=query_result.target,
                            query=query_result,
                            vulnerability_documents=tuple(documents),
                            query_uri=resolved_client.query_uri,
                            detail_uris=tuple(detail_uris),
                        ),
                        max_vulnerabilities=target_limit,
                    )
                    work_results.append(
                        persist_enrichment(
                            database_url,
                            claimed=item,
                            worker_id=resolved_worker_id,
                            enrichment=enrichment,
                        )
                    )
                except LeaseLostError:
                    work_results.append(
                        WorkResult(
                            status="LEASE_LOST",
                            run_id=str(item.run_id),
                            target_key=item.target_key,
                        )
                    )
                except (ValueError, KeyError, TypeError) as error:
                    work_results.append(
                        _record_failure(
                            database_url,
                            item,
                            resolved_worker_id,
                            error_class="OSV_SCHEMA",
                            error_detail={"message": str(error)},
                            retriable=False,
                        )
                    )

    overall = _batch_status(work_results)
    return BatchWorkResult(
        status=overall,
        claimed=len(claimed),
        results=tuple(work_results),
    )


def persist_enrichment(
    database_url: str,
    *,
    claimed: ClaimedRun,
    worker_id: str,
    enrichment: OsvEnrichment,
) -> WorkResult:
    observed_at = datetime.now(timezone.utc)
    fact_specs = build_fact_specs(enrichment)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        _lock_owned_run(connection, claimed.run_id, worker_id)
        existing = connection.execute(
            """
            SELECT id FROM source_snapshot
            WHERE ingest_target_id = %s
              AND source_revision = %s
              AND extractor_key = %s
              AND extractor_version = %s
              AND status = 'PUBLISHED'
            """,
            (
                claimed.target_id,
                enrichment.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
            ),
        ).fetchone()
        if existing is not None:
            _complete_replayed_run(connection, claimed, enrichment, observed_at)
            return WorkResult(
                status=(
                    "SUCCEEDED"
                    if enrichment.completeness == "COMPLETE"
                    else "PARTIAL"
                ),
                run_id=str(claimed.run_id),
                target_key=claimed.target_key,
                source_revision=enrichment.source_revision,
                completeness=enrichment.completeness,
                replayed=True,
                vulnerability_count=len(enrichment.vulnerabilities),
                limitation_count=len(enrichment.limitations),
            )

        source_id = _upsert_osv_source(connection)
        raw_bytes = canonical_json(enrichment.raw_bundle).encode("utf-8")
        raw_key = sha256_key(
            SOURCE_KEY,
            claimed.target_key,
            enrichment.source_revision,
            EXTRACTOR_VERSION,
        )
        connection.execute(
            """
            INSERT INTO raw_observation (
                tenant_id, ingest_run_id, source_system_id, target_key,
                source_revision, adapter_key, adapter_version,
                provider_schema_version, idempotency_key, content_hash,
                media_type, size_bytes, inline_body, request_metadata,
                observed_at
            )
            VALUES (
                NULL, %s, %s, %s, %s, %s, %s, '1', %s, %s,
                'application/json', %s, %s, %s, %s
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            (
                claimed.run_id,
                source_id,
                claimed.target_key,
                enrichment.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                raw_key,
                enrichment.source_revision,
                len(raw_bytes),
                Jsonb(enrichment.raw_bundle),
                Jsonb(
                    {
                        "query_uri": enrichment.raw_bundle["query_uri"],
                        "detail_uris": enrichment.raw_bundle["detail_uris"],
                    }
                ),
                observed_at,
            ),
        )
        artifact = connection.execute(
            """
            INSERT INTO source_artifact (
                tenant_id, source_system_id, external_key, artifact_type,
                name, source_revision, content_hash, metadata, observed_at
            )
            VALUES (
                NULL, %s, %s, 'OSV_PACKAGE_VERSION_BUNDLE', %s, %s, %s, %s, %s
            )
            ON CONFLICT (tenant_id, source_system_id, external_key, source_revision)
            DO UPDATE SET content_hash = EXCLUDED.content_hash,
                          metadata = EXCLUDED.metadata,
                          observed_at = EXCLUDED.observed_at
            RETURNING id
            """,
            (
                source_id,
                f"osv:{enrichment.target.purl}",
                enrichment.target.display_name,
                enrichment.source_revision,
                enrichment.source_revision,
                Jsonb(
                    {
                        "target_purl": enrichment.target.purl,
                        "vulnerability_count": len(enrichment.vulnerabilities),
                        "limitations": list(enrichment.limitations),
                    }
                ),
                observed_at,
            ),
        ).fetchone()
        assert artifact is not None
        artifact_id: UUID = artifact["id"]
        snapshot = connection.execute(
            """
            INSERT INTO source_snapshot (
                tenant_id, ingest_run_id, ingest_target_id, source_revision,
                extractor_key, extractor_version, completeness, status,
                observed_at, stats
            )
            VALUES (NULL, %s, %s, %s, %s, %s, %s, 'STAGED', %s, %s)
            RETURNING id
            """,
            (
                claimed.run_id,
                claimed.target_id,
                enrichment.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                enrichment.completeness,
                observed_at,
                Jsonb(
                    {
                        "vulnerability_count": len(enrichment.vulnerabilities),
                        "withdrawn_count": sum(
                            item.withdrawn is not None
                            for item in enrichment.vulnerabilities
                        ),
                        "fact_count": len(fact_specs),
                        "limitation_count": len(enrichment.limitations),
                    }
                ),
            ),
        ).fetchone()
        assert snapshot is not None
        snapshot_id: UUID = snapshot["id"]

        _, version_id = _upsert_package_entities(
            connection,
            key=enrichment.target,
            artifact_id=artifact_id,
            observed_at=observed_at,
        )
        vulnerability_entities: dict[str, UUID] = {}
        records_by_entity: dict[UUID, list[VulnerabilityRecord]] = {}
        for record in enrichment.vulnerabilities:
            entity_id = _upsert_vulnerability_entity(
                connection,
                record=record,
                artifact_id=artifact_id,
                observed_at=observed_at,
            )
            vulnerability_entities[record.osv_id] = entity_id
            records_by_entity.setdefault(entity_id, []).append(record)
        for entity_id, records in records_by_entity.items():
            _merge_vulnerability_properties(
                connection,
                entity_id=entity_id,
                records=records,
                observed_at=observed_at,
            )

        fact_groups: dict[UUID, list[FactSpec]] = {}
        for spec in fact_specs:
            vulnerability_id = vulnerability_entities[spec.vulnerability.osv_id]
            fact_groups.setdefault(vulnerability_id, []).append(spec)

        inserted = 0
        for vulnerability_id, specs in fact_groups.items():
            canonical = connection.execute(
                "SELECT canonical_key FROM entity WHERE id = %s",
                (vulnerability_id,),
            ).fetchone()
            assert canonical is not None
            fact_id = _insert_fact(
                connection,
                snapshot_id=snapshot_id,
                artifact_id=artifact_id,
                subject_id=version_id,
                vulnerability_id=vulnerability_id,
                specs=specs,
                logical_key=sha256_key(
                    "global",
                    enrichment.target.purl,
                    "AFFECTED_BY",
                    canonical["canonical_key"],
                ),
                source_revision=enrichment.source_revision,
                observed_at=observed_at,
            )
            if fact_id is not None:
                inserted += 1

        connection.execute("SELECT publish_source_snapshot(%s)", (snapshot_id,))
        entity_count = 2 + len(set(vulnerability_entities.values()))
        _complete_run(
            connection,
            claimed,
            enrichment,
            observed_at,
            entity_count=entity_count,
            fact_count=inserted,
        )
        return WorkResult(
            status=(
                "SUCCEEDED" if enrichment.completeness == "COMPLETE" else "PARTIAL"
            ),
            run_id=str(claimed.run_id),
            target_key=claimed.target_key,
            source_revision=enrichment.source_revision,
            completeness=enrichment.completeness,
            entity_count=entity_count,
            fact_count=inserted,
            vulnerability_count=len(enrichment.vulnerabilities),
            limitation_count=len(enrichment.limitations),
        )


def _upsert_osv_source(connection: Connection[dict[str, Any]]) -> UUID:
    row = connection.execute(
        """
        INSERT INTO source_system (tenant_id, source_key, kind, base_uri, metadata)
        VALUES (NULL, %s, 'OSV', 'https://api.osv.dev/', %s)
        ON CONFLICT (tenant_id, source_key) DO UPDATE
        SET kind = EXCLUDED.kind,
            base_uri = EXCLUDED.base_uri,
            metadata = EXCLUDED.metadata
        RETURNING id
        """,
        (
            SOURCE_KEY,
            Jsonb(
                {
                    "api_version": "v1",
                    "coverage": "observed public package versions",
                }
            ),
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def _upsert_package_entities(
    connection: Connection[dict[str, Any]],
    *,
    key: PackageVersionKey,
    artifact_id: UUID,
    observed_at: datetime,
) -> tuple[UUID, UUID]:
    registry_id = _upsert_public_registry(connection, key.system)
    package_id = _upsert_entity(
        connection,
        namespace="TECHNOLOGY",
        entity_type="Package",
        canonical_key=key.package_purl,
        name=key.name,
        properties={"ecosystem": key.ecosystem, "package_name": key.name},
        observed_at=observed_at,
    )
    version_id = _upsert_entity(
        connection,
        namespace="TECHNOLOGY",
        entity_type="PackageVersion",
        canonical_key=key.purl,
        name=key.display_name,
        properties={
            "ecosystem": key.ecosystem,
            "package_name": key.name,
            "version": key.version,
        },
        observed_at=observed_at,
    )
    for entity_id, purl in (
        (package_id, key.package_purl),
        (version_id, key.purl),
    ):
        connection.execute(
            """
            INSERT INTO entity_identity (
                tenant_id, entity_id, scheme, identity_value, is_canonical,
                source_artifact_id, first_seen_at, last_seen_at
            )
            VALUES (NULL, %s, 'PURL', %s, true, %s, %s, %s)
            ON CONFLICT (tenant_id, scheme, identity_value)
            DO UPDATE SET entity_id = EXCLUDED.entity_id,
                          is_canonical = EXCLUDED.is_canonical,
                          source_artifact_id = EXCLUDED.source_artifact_id,
                          last_seen_at = EXCLUDED.last_seen_at
            """,
            (entity_id, purl, artifact_id, observed_at, observed_at),
        )
    for entity_id, version in ((package_id, None), (version_id, key.version)):
        connection.execute(
            """
            INSERT INTO package_registry_identity (
                tenant_id, entity_id, package_registry_id, package_name,
                package_version, purl, visibility, first_seen_at, last_seen_at
            )
            VALUES (NULL, %s, %s, %s, %s, %s, 'PUBLIC', %s, %s)
            ON CONFLICT (package_registry_id, package_name, package_version)
            DO UPDATE SET entity_id = EXCLUDED.entity_id,
                          purl = EXCLUDED.purl,
                          visibility = 'PUBLIC',
                          last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                entity_id,
                registry_id,
                key.name,
                version,
                key.package_purl if version is None else key.purl,
                observed_at,
                observed_at,
            ),
        )
    return package_id, version_id


def _upsert_public_registry(
    connection: Connection[dict[str, Any]],
    system: str,
) -> UUID:
    if system == "NPM":
        source_key = "registry.npmjs.org"
        origin = "https://registry.npmjs.org/"
        registry_key = "npm-public"
    elif system == "PYPI":
        source_key = "pypi.org"
        origin = "https://pypi.org/"
        registry_key = "pypi-public"
    else:
        raise ValueError(f"unsupported public registry system: {system}")
    source = connection.execute(
        """
        INSERT INTO source_system (tenant_id, source_key, kind, base_uri, metadata)
        VALUES (NULL, %s, 'PACKAGE_REGISTRY', %s, '{}')
        ON CONFLICT (tenant_id, source_key) DO UPDATE
        SET kind = EXCLUDED.kind, base_uri = EXCLUDED.base_uri
        RETURNING id
        """,
        (source_key, origin),
    ).fetchone()
    assert source is not None
    registry = connection.execute(
        """
        INSERT INTO package_registry (
            tenant_id, source_system_id, registry_key, origin_uri,
            normalized_origin_uri, ecosystem, visibility, auth_mode,
            allow_metadata_fetch, metadata
        )
        VALUES (NULL, %s, %s, %s, %s, %s, 'PUBLIC', 'NONE', true, '{}')
        ON CONFLICT (tenant_id, ecosystem, normalized_origin_uri)
        DO UPDATE SET source_system_id = EXCLUDED.source_system_id,
                      registry_key = EXCLUDED.registry_key,
                      visibility = 'PUBLIC',
                      updated_at = now()
        RETURNING id
        """,
        (source["id"], registry_key, origin, origin, system),
    ).fetchone()
    assert registry is not None
    return registry["id"]


def _upsert_vulnerability_entity(
    connection: Connection[dict[str, Any]],
    *,
    record: VulnerabilityRecord,
    artifact_id: UUID,
    observed_at: datetime,
) -> UUID:
    identities = [("OSV", record.osv_id), *_recognized_aliases(record)]
    entity_id: UUID | None = None
    for scheme, value in identities:
        existing = connection.execute(
            """
            SELECT entity_id FROM entity_identity
            WHERE tenant_id IS NULL AND scheme = %s AND identity_value = %s
            """,
            (scheme, value),
        ).fetchone()
        if existing is not None:
            entity_id = existing["entity_id"]
            break
    properties = vulnerability_properties(record)
    if entity_id is None:
        entity_id = _upsert_entity(
            connection,
            namespace="INTELLIGENCE",
            entity_type="Vulnerability",
            canonical_key=f"osv:{record.osv_id}",
            name=record.summary,
            properties=properties,
            observed_at=observed_at,
        )
    else:
        connection.execute(
            """
            UPDATE entity
            SET name = %s,
                properties = entity.properties || %s,
                last_seen_at = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (record.summary, Jsonb(properties), observed_at, entity_id),
        )

    for scheme, value in identities:
        conflict = connection.execute(
            """
            SELECT entity_id FROM entity_identity
            WHERE tenant_id IS NULL AND scheme = %s AND identity_value = %s
            """,
            (scheme, value),
        ).fetchone()
        if conflict is not None and conflict["entity_id"] != entity_id:
            continue
        connection.execute(
            """
            INSERT INTO entity_identity (
                tenant_id, entity_id, scheme, identity_value, is_canonical,
                source_artifact_id, first_seen_at, last_seen_at
            )
            VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, scheme, identity_value)
            DO UPDATE SET source_artifact_id = EXCLUDED.source_artifact_id,
                          last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                entity_id,
                scheme,
                value,
                scheme == "OSV" and value == record.osv_id,
                artifact_id,
                observed_at,
                observed_at,
            ),
        )
    return entity_id


def _recognized_aliases(record: VulnerabilityRecord) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for value in (record.osv_id, *record.aliases):
        if value.startswith("CVE-"):
            aliases.append(("CVE", value))
        elif value.startswith("GHSA-"):
            aliases.append(("GHSA", value))
    return list(dict.fromkeys(aliases))


def _merge_vulnerability_properties(
    connection: Connection[dict[str, Any]],
    *,
    entity_id: UUID,
    records: list[VulnerabilityRecord],
    observed_at: datetime,
) -> None:
    if not records:
        return
    row = connection.execute(
        "SELECT properties FROM entity WHERE id = %s",
        (entity_id,),
    ).fetchone()
    existing = row["properties"] if row and isinstance(row["properties"], dict) else {}
    aliases = sorted(
        {
            item
            for item in existing.get("aliases", [])
            if isinstance(item, str)
        }
        | {alias for record in records for alias in record.aliases}
    )
    severity = _unique_objects(
        [
            value
            for value in existing.get("severity", [])
            if isinstance(value, dict)
        ]
        + [value for record in records for value in record.severity]
    )
    references = _unique_objects(
        [
            value
            for value in existing.get("references", [])
            if isinstance(value, dict)
        ]
        + [value for record in records for value in record.references]
    )
    published = sorted(
        item.published for item in records if item.published is not None
    )
    withdrawn = sorted(
        item.withdrawn for item in records if item.withdrawn is not None
    )
    properties = {
        "osv_id": records[0].osv_id,
        "osv_ids": sorted(
            {
                item
                for item in existing.get("osv_ids", [])
                if isinstance(item, str)
            }
            | {record.osv_id for record in records}
        ),
        "summary": records[0].summary,
        "aliases": aliases,
        "published": published[0] if published else None,
        "modified": max(record.modified for record in records),
        "withdrawn": withdrawn[-1] if len(withdrawn) == len(records) else None,
        "severity": severity,
        "references": references,
        "schema_versions": sorted(
            {
                item
                for item in existing.get("schema_versions", [])
                if isinstance(item, str)
            }
            | {
                value
                for record in records
                if isinstance((value := record.raw.get("schema_version")), str)
            }
        ),
    }
    connection.execute(
        """
        UPDATE entity
        SET properties = entity.properties || %s,
            last_seen_at = %s,
            updated_at = now()
        WHERE id = %s
        """,
        (Jsonb(properties), observed_at, entity_id),
    )


def _upsert_entity(
    connection: Connection[dict[str, Any]],
    *,
    namespace: str,
    entity_type: str,
    canonical_key: str,
    name: str,
    properties: dict[str, Any],
    observed_at: datetime,
) -> UUID:
    row = connection.execute(
        """
        INSERT INTO entity (
            tenant_id, namespace, entity_type, canonical_key, name,
            properties, first_seen_at, last_seen_at
        )
        VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, namespace, entity_type, canonical_key)
        DO UPDATE SET name = EXCLUDED.name,
                      properties = entity.properties || EXCLUDED.properties,
                      first_seen_at = COALESCE(
                          entity.first_seen_at, EXCLUDED.first_seen_at
                      ),
                      last_seen_at = EXCLUDED.last_seen_at,
                      updated_at = now()
        RETURNING id
        """,
        (
            namespace,
            entity_type,
            canonical_key,
            name,
            Jsonb(properties),
            observed_at,
            observed_at,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def _insert_fact(
    connection: Connection[dict[str, Any]],
    *,
    snapshot_id: UUID,
    artifact_id: UUID,
    subject_id: UUID,
    vulnerability_id: UUID,
    specs: list[FactSpec],
    logical_key: str,
    source_revision: str,
    observed_at: datetime,
) -> UUID | None:
    idempotency_key = sha256_key(
        logical_key,
        source_revision,
        EXTRACTOR_KEY,
        EXTRACTOR_VERSION,
    )
    properties = _merge_fact_properties(specs)
    effective_values = sorted(
        item.effective_from for item in specs if item.effective_from is not None
    )
    row = connection.execute(
        """
        INSERT INTO fact_assertion (
            tenant_id, source_snapshot_id, subject_entity_id, predicate,
            object_entity_id, object_value, assertion_class, confidence,
            logical_key, idempotency_key, source_revision, extractor_key,
            extractor_version, properties, effective_from, observed_at
        )
        VALUES (
            NULL, %s, %s, 'AFFECTED_BY', %s, NULL, 'EXTERNAL_MEASURED', 1.0,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """,
        (
            snapshot_id,
            subject_id,
            vulnerability_id,
            logical_key,
            idempotency_key,
            source_revision,
            EXTRACTOR_KEY,
            EXTRACTOR_VERSION,
            Jsonb(properties),
            effective_values[0] if effective_values else None,
            observed_at,
        ),
    ).fetchone()
    if row is None:
        return None
    fact_id: UUID = row["id"]
    seen_evidence: set[str] = set()
    for evidence in (item for spec in specs for item in spec.evidence):
        evidence_key = canonical_json(evidence.locator)
        if evidence_key in seen_evidence:
            continue
        seen_evidence.add(evidence_key)
        connection.execute(
            """
            INSERT INTO evidence (
                tenant_id, fact_assertion_id, source_artifact_id, evidence_type,
                locator, excerpt_hash, metadata, observed_at
            )
            VALUES (NULL, %s, %s, 'EXTERNAL_API_RESPONSE', %s, %s, %s, %s)
            """,
            (
                fact_id,
                artifact_id,
                Jsonb(evidence.locator),
                evidence.excerpt_hash,
                Jsonb(evidence.metadata),
                observed_at,
            ),
        )
    return fact_id


def _merge_fact_properties(specs: list[FactSpec]) -> dict[str, Any]:
    if not specs:
        raise ValueError("at least one OSV fact specification is required")
    aliases = sorted(
        {
            alias
            for spec in specs
            for alias in spec.properties.get("aliases", [])
            if isinstance(alias, str)
        }
    )
    severity = _unique_objects(
        item
        for spec in specs
        for item in spec.properties.get("severity", [])
        if isinstance(item, dict)
    )
    affected = _unique_objects(
        item
        for spec in specs
        for item in spec.properties.get("affected", [])
        if isinstance(item, dict)
    )
    modified = sorted(
        value
        for spec in specs
        if isinstance((value := spec.properties.get("modified")), str)
    )
    return {
        "provider": "osv.dev",
        "record_kind": "KNOWN_VULNERABILITY",
        "matched_purl": specs[0].properties["matched_purl"],
        "osv_id": specs[0].vulnerability.osv_id,
        "osv_ids": sorted(spec.vulnerability.osv_id for spec in specs),
        "aliases": aliases,
        "modified": modified[-1] if modified else None,
        "severity": severity,
        "affected": affected,
    }


def _unique_objects(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for value in values:
        unique[canonical_json(value)] = value
    return [unique[key] for key in sorted(unique)]


def _lock_owned_run(
    connection: Connection[dict[str, Any]],
    run_id: UUID,
    worker_id: str,
) -> None:
    row = connection.execute(
        """
        SELECT id FROM ingest_run
        WHERE id = %s
          AND status = 'RUNNING'
          AND lease_owner = %s
          AND lease_expires_at > now()
        FOR UPDATE
        """,
        (run_id, worker_id),
    ).fetchone()
    if row is None:
        raise LeaseLostError(f"ingest run lease lost: {run_id}")


def _renew_leases(
    database_url: str,
    claimed: list[ClaimedRun],
    worker_id: str,
    lease_seconds: int,
) -> None:
    if not claimed:
        return
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute(
            """
            UPDATE ingest_run
            SET lease_expires_at = now() + (%s * interval '1 second')
            WHERE id = ANY(%s)
              AND status = 'RUNNING'
              AND lease_owner = %s
              AND lease_expires_at > now()
            """,
            (lease_seconds, [item.run_id for item in claimed], worker_id),
        )


def _complete_replayed_run(
    connection: Connection[dict[str, Any]],
    claimed: ClaimedRun,
    enrichment: OsvEnrichment,
    observed_at: datetime,
) -> None:
    connection.execute(
        """
        UPDATE ingest_run
        SET status = %s, completeness = %s, completed_at = now(),
            lease_owner = NULL, lease_expires_at = NULL,
            stats = %s
        WHERE id = %s
        """,
        (
            "SUCCEEDED" if enrichment.completeness == "COMPLETE" else "PARTIAL",
            enrichment.completeness,
            Jsonb(
                {
                    "replayed": True,
                    "source_revision": enrichment.source_revision,
                    "vulnerability_count": len(enrichment.vulnerabilities),
                }
            ),
            claimed.run_id,
        ),
    )
    _update_freshness(connection, claimed, enrichment, observed_at)


def _complete_run(
    connection: Connection[dict[str, Any]],
    claimed: ClaimedRun,
    enrichment: OsvEnrichment,
    observed_at: datetime,
    *,
    entity_count: int,
    fact_count: int,
) -> None:
    run_status = "SUCCEEDED" if enrichment.completeness == "COMPLETE" else "PARTIAL"
    connection.execute(
        """
        UPDATE ingest_run
        SET status = %s, completeness = %s, completed_at = now(),
            lease_owner = NULL, lease_expires_at = NULL,
            stats = %s
        WHERE id = %s
        """,
        (
            run_status,
            enrichment.completeness,
            Jsonb(
                {
                    "source_revision": enrichment.source_revision,
                    "entity_count": entity_count,
                    "fact_count": fact_count,
                    "vulnerability_count": len(enrichment.vulnerabilities),
                    "withdrawn_count": sum(
                        item.withdrawn is not None
                        for item in enrichment.vulnerabilities
                    ),
                    "limitations": list(enrichment.limitations),
                }
            ),
            claimed.run_id,
        ),
    )
    _update_freshness(connection, claimed, enrichment, observed_at)


def _update_freshness(
    connection: Connection[dict[str, Any]],
    claimed: ClaimedRun,
    enrichment: OsvEnrichment,
    observed_at: datetime,
) -> None:
    refresh_seconds = _policy_int(
        claimed.refresh_policy,
        "refresh_seconds",
        DEFAULT_REFRESH_SECONDS,
    )
    if enrichment.completeness == "PARTIAL":
        refresh_seconds = min(refresh_seconds, 3_600)
    connection.execute(
        """
        UPDATE ingest_target
        SET desired_source_revision = %s,
            next_due_at = now() + (%s * interval '1 second'),
            last_success_at = CASE
                WHEN %s = 'COMPLETE' THEN now() ELSE last_success_at
            END,
            updated_at = now()
        WHERE id = %s
        """,
        (
            enrichment.source_revision,
            refresh_seconds,
            enrichment.completeness,
            claimed.target_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO ingest_cursor (
            tenant_id, ingest_target_id, cursor_kind, cursor_value,
            source_revision, updated_at
        )
        VALUES (NULL, %s, 'CONTENT_HASH', %s, %s, now())
        ON CONFLICT (ingest_target_id, cursor_kind)
        DO UPDATE SET cursor_value = EXCLUDED.cursor_value,
                      source_revision = EXCLUDED.source_revision,
                      updated_at = now()
        """,
        (
            claimed.target_id,
            Jsonb({"content_hash": enrichment.source_revision}),
            enrichment.source_revision,
        ),
    )
    connection.execute(
        """
        INSERT INTO freshness_state (
            tenant_id, ingest_target_id, expected_by, last_observed_at,
            last_source_revision, status, limitations, updated_at
        )
        VALUES (
            NULL, %s, now() + (%s * interval '1 second'), %s, %s,
            'FRESH', %s, now()
        )
        ON CONFLICT (ingest_target_id)
        DO UPDATE SET expected_by = EXCLUDED.expected_by,
                      last_observed_at = EXCLUDED.last_observed_at,
                      last_source_revision = EXCLUDED.last_source_revision,
                      status = EXCLUDED.status,
                      limitations = EXCLUDED.limitations,
                      updated_at = now()
        """,
        (
            claimed.target_id,
            refresh_seconds,
            observed_at,
            enrichment.source_revision,
            Jsonb(list(enrichment.limitations)),
        ),
    )


def _record_client_failure(
    database_url: str,
    claimed: ClaimedRun,
    worker_id: str,
    error: Exception,
) -> WorkResult:
    if isinstance(error, OsvApiError):
        return _record_failure(
            database_url,
            claimed,
            worker_id,
            error_class="OSV_API",
            error_detail={"message": str(error), "http_status": error.status_code},
            retriable=error.retriable,
            retry_after_seconds=error.retry_after_seconds,
        )
    if isinstance(error, OsvTransportError):
        return _record_failure(
            database_url,
            claimed,
            worker_id,
            error_class="OSV_TRANSPORT",
            error_detail={"message": str(error)},
            retriable=True,
        )
    return _record_failure(
        database_url,
        claimed,
        worker_id,
        error_class="OSV_SCHEMA",
        error_detail={"message": str(error)},
        retriable=False,
    )


def _record_failure(
    database_url: str,
    claimed: ClaimedRun,
    worker_id: str,
    *,
    error_class: str,
    error_detail: dict[str, Any],
    retriable: bool,
    retry_after_seconds: int | None = None,
) -> WorkResult:
    max_attempts = _policy_int(
        claimed.refresh_policy,
        "max_attempts",
        DEFAULT_MAX_ATTEMPTS,
    )
    terminal = not retriable or claimed.attempt >= max_attempts
    if retry_after_seconds is None:
        delay = min(60 * (2 ** max(claimed.attempt - 1, 0)), 3_600)
    else:
        delay = min(max(retry_after_seconds, 1), 3_600)
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            _lock_owned_run(connection, claimed.run_id, worker_id)
            if terminal:
                connection.execute(
                    """
                    UPDATE ingest_run
                    SET status = 'FAILED', completed_at = now(),
                        lease_owner = NULL, lease_expires_at = NULL,
                        error_class = %s, error_detail = %s
                    WHERE id = %s
                    """,
                    (error_class, Jsonb(error_detail), claimed.run_id),
                )
                connection.execute(
                    """
                    INSERT INTO dead_letter (
                        tenant_id, source_kind, source_id, error_class,
                        error_detail, replay_metadata
                    )
                    VALUES (NULL, 'OSV', %s, %s, %s, %s)
                    """,
                    (
                        str(claimed.run_id),
                        error_class,
                        Jsonb(error_detail),
                        Jsonb(
                            {
                                "target_id": str(claimed.target_id),
                                "target_key": claimed.target_key,
                                "attempt": claimed.attempt,
                            }
                        ),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO freshness_state (
                        tenant_id, ingest_target_id, status, limitations, updated_at
                    )
                    VALUES (NULL, %s, 'ERROR', %s, now())
                    ON CONFLICT (ingest_target_id)
                    DO UPDATE SET status = 'ERROR',
                                  limitations = EXCLUDED.limitations,
                                  updated_at = now()
                    """,
                    (
                        claimed.target_id,
                        Jsonb([{"code": error_class, **error_detail}]),
                    ),
                )
                refresh_seconds = _policy_int(
                    claimed.refresh_policy,
                    "refresh_seconds",
                    DEFAULT_REFRESH_SECONDS,
                )
                connection.execute(
                    """
                    UPDATE ingest_target
                    SET next_due_at = now() + (%s * interval '1 second'),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (refresh_seconds, claimed.target_id),
                )
                status = "FAILED"
            else:
                connection.execute(
                    """
                    UPDATE ingest_run
                    SET status = 'PENDING', attempt = attempt + 1,
                        available_at = now() + (%s * interval '1 second'),
                        lease_owner = NULL, lease_expires_at = NULL,
                        error_class = %s, error_detail = %s
                    WHERE id = %s
                    """,
                    (delay, error_class, Jsonb(error_detail), claimed.run_id),
                )
                status = "RETRY_SCHEDULED"
    except LeaseLostError:
        return WorkResult(
            status="LEASE_LOST",
            run_id=str(claimed.run_id),
            target_key=claimed.target_key,
        )
    return WorkResult(
        status=status,
        run_id=str(claimed.run_id),
        target_key=claimed.target_key,
        retry_after_seconds=None if terminal else delay,
    )


def _canonical_targets(purls: Iterable[str]) -> tuple[PackageVersionKey, ...]:
    targets: dict[str, PackageVersionKey] = {}
    for purl in purls:
        target = PackageVersionKey.from_purl(purl)
        targets[target.purl] = target
    if not targets:
        raise ValueError("at least one package-version purl is required")
    return tuple(targets.values())


def _refresh_policy(
    max_vulnerabilities: int,
    max_pages: int,
    refresh_seconds: int,
) -> dict[str, Any]:
    return {
        "adapter": EXTRACTOR_KEY,
        "api_version": "v1",
        "max_vulnerabilities": max_vulnerabilities,
        "max_pages": max_pages,
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
        "refresh_seconds": refresh_seconds,
    }


def _validate_policy(
    priority: str,
    max_vulnerabilities: int,
    max_pages: int,
    refresh_seconds: int,
) -> None:
    if priority not in {"HOT", "WARM", "COLD", "ON_DEMAND"}:
        raise ValueError("priority must be HOT, WARM, COLD, or ON_DEMAND")
    if max_vulnerabilities <= 0 or max_pages <= 0 or refresh_seconds <= 0:
        raise ValueError("OSV limits and refresh interval must be positive")


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    value = policy.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"refresh policy {key} must be a positive integer")
    return value


def _batch_status(results: list[WorkResult]) -> str:
    statuses = {item.status for item in results}
    if not statuses:
        return "IDLE"
    if statuses == {"SUCCEEDED"}:
        return "SUCCEEDED"
    if statuses <= {"SUCCEEDED", "PARTIAL"}:
        return "PARTIAL" if "PARTIAL" in statuses else "SUCCEEDED"
    if "FAILED" in statuses:
        return "FAILED"
    if "RETRY_SCHEDULED" in statuses:
        return "RETRY_SCHEDULED"
    if "LEASE_LOST" in statuses:
        return "LEASE_LOST"
    return "PARTIAL"


def _database_url(parser: argparse.ArgumentParser) -> str:
    value = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not value:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OSV vulnerability enrichment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enqueue = subparsers.add_parser("enqueue")
    enqueue.add_argument("purl", nargs="+")
    enqueue.add_argument("--priority", default="WARM")
    enqueue.add_argument(
        "--max-vulnerabilities",
        type=int,
        default=DEFAULT_MAX_VULNERABILITIES,
    )
    enqueue.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    enqueue.add_argument(
        "--refresh-seconds",
        type=int,
        default=DEFAULT_REFRESH_SECONDS,
    )
    work = subparsers.add_parser("work")
    work.add_argument("--worker-id")
    work.add_argument("--batch-size", type=int, default=50)
    work.add_argument("--lease-seconds", type=int, default=300)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--worker-id")
    serve.add_argument("--batch-size", type=int, default=50)
    serve.add_argument("--lease-seconds", type=int, default=300)
    serve.add_argument("--poll-seconds", type=float, default=2.0)
    serve.add_argument("--sync-limit", type=int, default=1_000)
    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--limit", type=int, default=500)
    sync = subparsers.add_parser("sync")
    sync.add_argument("--limit", type=int, default=1_000)
    run = subparsers.add_parser("run")
    run.add_argument("purl", nargs="+")
    run.add_argument("--priority", default="ON_DEMAND")
    run.add_argument(
        "--max-vulnerabilities",
        type=int,
        default=DEFAULT_MAX_VULNERABILITIES,
    )
    run.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    run.add_argument(
        "--refresh-seconds",
        type=int,
        default=DEFAULT_REFRESH_SECONDS,
    )
    run.add_argument("--worker-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = _database_url(parser)
    if args.command == "serve":
        if args.poll_seconds < 0:
            parser.error("--poll-seconds must not be negative")
        if args.sync_limit <= 0:
            parser.error("--sync-limit must be positive")
        while True:
            sync_observed_package_versions(database_url, limit=args.sync_limit)
            result = run_batch(
                database_url,
                worker_id=args.worker_id,
                batch_size=args.batch_size,
                lease_seconds=args.lease_seconds,
            )
            print(json.dumps(asdict(result), sort_keys=True), flush=True)
            if result.status in {"IDLE", "RETRY_SCHEDULED"}:
                time.sleep(max(0.1, args.poll_seconds))
    if args.command == "enqueue":
        result: object = enqueue_package_versions(
            database_url,
            args.purl,
            priority=args.priority,
            max_vulnerabilities=args.max_vulnerabilities,
            max_pages=args.max_pages,
            refresh_seconds=args.refresh_seconds,
        )
    elif args.command == "work":
        result = run_batch(
            database_url,
            worker_id=args.worker_id,
            batch_size=args.batch_size,
            lease_seconds=args.lease_seconds,
        )
    elif args.command == "schedule":
        result = schedule_due_targets(database_url, limit=args.limit)
    elif args.command == "sync":
        result = sync_observed_package_versions(database_url, limit=args.limit)
    else:
        enqueue_result = enqueue_package_versions(
            database_url,
            args.purl,
            priority=args.priority,
            max_vulnerabilities=args.max_vulnerabilities,
            max_pages=args.max_pages,
            refresh_seconds=args.refresh_seconds,
        )
        work_result = run_batch(
            database_url,
            worker_id=args.worker_id,
            batch_size=max(50, len(enqueue_result)),
        )
        result = {
            "enqueue": [asdict(item) for item in enqueue_result],
            "work": asdict(work_result),
        }
    if isinstance(result, tuple):
        payload: object = [asdict(item) for item in result]
    elif hasattr(result, "__dataclass_fields__"):
        payload = asdict(result)
    else:
        payload = result
    print(json.dumps(payload, sort_keys=True))
    if isinstance(result, BatchWorkResult):
        status = result.status
    elif isinstance(result, dict):
        status = result["work"]["status"]
    else:
        status = None
    if status in {"RETRY_SCHEDULED", "LEASE_LOST"}:
        return 75
    if status == "FAILED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

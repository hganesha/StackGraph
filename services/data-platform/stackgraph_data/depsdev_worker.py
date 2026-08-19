from __future__ import annotations

import argparse
import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import canonical_json, sha256_key
from stackgraph_data.depsdev import (
    DepsDevApiError,
    DepsDevClient,
    DepsDevTransportError,
    FactSpec,
    NormalizedEnrichment,
    PackageVersionKey,
    build_fact_specs,
    normalize_bundle,
)


EXTRACTOR_KEY = "deps-dev-v3"
EXTRACTOR_VERSION = "1.0.0"
SOURCE_KEY = "deps.dev"
DEFAULT_REFRESH_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MAX_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    target_id: str
    run_id: str
    target_key: str
    created: bool


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
    limitation_count: int = 0
    retry_after_seconds: int | None = None


class LeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    created: int


def enqueue_package_version(
    database_url: str,
    purl: str,
    *,
    priority: str = "WARM",
    max_nodes: int = 1_000,
    max_edges: int = 5_000,
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
) -> EnqueueResult:
    target = PackageVersionKey.from_purl(purl)
    if priority not in {"HOT", "WARM", "COLD", "ON_DEMAND"}:
        raise ValueError("priority must be HOT, WARM, COLD, or ON_DEMAND")
    if max_nodes <= 0 or max_edges <= 0 or refresh_seconds <= 0:
        raise ValueError("target limits and refresh interval must be positive")
    policy = {
        "adapter": EXTRACTOR_KEY,
        "api_version": "v3",
        "max_nodes": max_nodes,
        "max_edges": max_edges,
        "max_attempts": DEFAULT_MAX_ATTEMPTS,
        "refresh_seconds": refresh_seconds,
    }
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        source_id = _upsert_depsdev_source(connection)
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
        assert row is not None
        target_id: UUID = row["id"]
        connection.execute(
            "SELECT id FROM ingest_target WHERE id = %s FOR UPDATE",
            (target_id,),
        )
        existing = connection.execute(
            """
            SELECT id
            FROM ingest_run
            WHERE ingest_target_id = %s
              AND status IN ('PENDING', 'RUNNING')
            ORDER BY created_at
            LIMIT 1
            """,
            (target_id,),
        ).fetchone()
        if existing is not None:
            return EnqueueResult(
                target_id=str(target_id),
                run_id=str(existing["id"]),
                target_key=target.purl,
                created=False,
            )
        run = connection.execute(
            """
            INSERT INTO ingest_run (
                tenant_id, ingest_target_id, trigger_kind, status, available_at
            )
            VALUES (NULL, %s, 'MANUAL', 'PENDING', now())
            RETURNING id
            """,
            (target_id,),
        ).fetchone()
        assert run is not None
        return EnqueueResult(
            target_id=str(target_id),
            run_id=str(run["id"]),
            target_key=target.purl,
            created=True,
        )


def claim_run(
    database_url: str,
    *,
    worker_id: str,
    lease_seconds: int = 300,
) -> ClaimedRun | None:
    if not worker_id.strip():
        raise ValueError("worker_id must not be empty")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            WITH candidate AS (
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
                LIMIT 1
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
            FROM candidate, ingest_target target
            WHERE run.id = candidate.id
              AND target.id = run.ingest_target_id
            RETURNING run.id AS run_id, target.id AS target_id,
                      target.target_key, target.refresh_policy, run.attempt
            """,
            (SOURCE_KEY, worker_id, lease_seconds),
        ).fetchone()
        if row is None:
            return None
        return ClaimedRun(
            run_id=row["run_id"],
            target_id=row["target_id"],
            target_key=row["target_key"],
            refresh_policy=row["refresh_policy"],
            attempt=row["attempt"],
        )


def schedule_due_targets(database_url: str, *, limit: int = 100) -> ScheduleResult:
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
                    SELECT 1
                    FROM ingest_run active
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


def run_once(
    database_url: str,
    *,
    client: DepsDevClient | None = None,
    worker_id: str | None = None,
    lease_seconds: int = 300,
    schedule_due: bool = True,
) -> WorkResult:
    resolved_worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    if schedule_due:
        schedule_due_targets(database_url)
    claimed = claim_run(
        database_url,
        worker_id=resolved_worker_id,
        lease_seconds=lease_seconds,
    )
    if claimed is None:
        return WorkResult(status="IDLE")
    try:
        target = PackageVersionKey.from_purl(claimed.target_key)
        bundle = (client or DepsDevClient()).fetch(target)
        enrichment = normalize_bundle(
            bundle,
            max_nodes=_policy_int(claimed.refresh_policy, "max_nodes", 1_000),
            max_edges=_policy_int(claimed.refresh_policy, "max_edges", 5_000),
        )
        return persist_enrichment(
            database_url,
            claimed=claimed,
            worker_id=resolved_worker_id,
            enrichment=enrichment,
        )
    except DepsDevApiError as error:
        return _record_failure(
            database_url,
            claimed,
            resolved_worker_id,
            error_class="DEPS_DEV_API",
            error_detail={"message": str(error), "http_status": error.status_code},
            retriable=error.retriable,
            retry_after_seconds=error.retry_after_seconds,
        )
    except DepsDevTransportError as error:
        return _record_failure(
            database_url,
            claimed,
            resolved_worker_id,
            error_class="DEPS_DEV_TRANSPORT",
            error_detail={"message": str(error)},
            retriable=True,
        )
    except (ValueError, KeyError, TypeError) as error:
        return _record_failure(
            database_url,
            claimed,
            resolved_worker_id,
            error_class="DEPS_DEV_SCHEMA",
            error_detail={"message": str(error)},
            retriable=False,
        )
    except LeaseLostError:
        return WorkResult(
            status="LEASE_LOST",
            run_id=str(claimed.run_id),
            target_key=claimed.target_key,
        )


def persist_enrichment(
    database_url: str,
    *,
    claimed: ClaimedRun,
    worker_id: str,
    enrichment: NormalizedEnrichment,
) -> WorkResult:
    observed_at = datetime.now(timezone.utc)
    fact_specs = build_fact_specs(enrichment)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        _lock_owned_run(connection, claimed.run_id, worker_id)
        existing = connection.execute(
            """
            SELECT id
            FROM source_snapshot
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
            _complete_replayed_run(
                connection,
                claimed,
                enrichment,
                observed_at,
            )
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
                limitation_count=len(enrichment.limitations),
            )

        source_id = _upsert_depsdev_source(connection)
        registry_id = _upsert_public_registry(connection, enrichment.root.system)
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
                NULL, %s, %s, %s, %s, %s, %s, 'v3', %s, %s,
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
                        "version_uri": enrichment.raw_bundle["version_uri"],
                        "dependencies_uri": enrichment.raw_bundle[
                            "dependencies_uri"
                        ],
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
            VALUES (NULL, %s, %s, 'DEPS_DEV_VERSION_BUNDLE', %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, source_system_id, external_key, source_revision)
            DO UPDATE SET content_hash = EXCLUDED.content_hash,
                          metadata = EXCLUDED.metadata,
                          observed_at = EXCLUDED.observed_at
            RETURNING id
            """,
            (
                source_id,
                f"deps.dev:{enrichment.root.purl}",
                enrichment.root.display_name,
                enrichment.source_revision,
                enrichment.source_revision,
                Jsonb(
                    {
                        "requested_purl": enrichment.requested.purl,
                        "canonical_purl": enrichment.root.purl,
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
                        "node_count": len(enrichment.nodes),
                        "edge_count": len(enrichment.edges),
                        "fact_count": len(fact_specs),
                        "limitation_count": len(enrichment.limitations),
                    }
                ),
            ),
        ).fetchone()
        assert snapshot is not None
        snapshot_id: UUID = snapshot["id"]

        unique_keys = {node.key.purl: node.key for node in enrichment.nodes}
        unique_keys[enrichment.root.purl] = enrichment.root
        entities: dict[str, tuple[UUID, UUID]] = {}
        for key in unique_keys.values():
            entities[key.purl] = _upsert_package_entities(
                connection,
                key=key,
                registry_id=registry_id,
                artifact_id=artifact_id,
                observed_at=observed_at,
            )

        inserted = 0
        for spec in fact_specs:
            subject_package_id, subject_version_id = entities[spec.subject.purl]
            if spec.object_entity is not None:
                object_entity_id = entities[spec.object_entity.purl][1]
            else:
                object_entity_id = None
            subject_id = (
                subject_package_id
                if spec.predicate == "HAS_VERSION"
                else subject_version_id
            )
            fact_id = _insert_fact(
                connection,
                snapshot_id=snapshot_id,
                artifact_id=artifact_id,
                subject_id=subject_id,
                object_entity_id=object_entity_id,
                spec=spec,
                source_revision=enrichment.source_revision,
                observed_at=observed_at,
            )
            if fact_id is not None:
                inserted += 1

        connection.execute("SELECT publish_source_snapshot(%s)", (snapshot_id,))
        entity_count = len(
            {entity_id for pair in entities.values() for entity_id in pair}
        )
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
            limitation_count=len(enrichment.limitations),
        )


def _upsert_depsdev_source(connection: Connection[dict[str, Any]]) -> UUID:
    row = connection.execute(
        """
        INSERT INTO source_system (
            tenant_id, source_key, kind, base_uri, metadata
        )
        VALUES (NULL, %s, 'DEPS_DEV', 'https://api.deps.dev/', %s)
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
                    "api_version": "v3",
                    "coverage": "public packages known to deps.dev",
                }
            ),
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def _upsert_public_registry(
    connection: Connection[dict[str, Any]], system: str
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


def _upsert_package_entities(
    connection: Connection[dict[str, Any]],
    *,
    key: PackageVersionKey,
    registry_id: UUID,
    artifact_id: UUID,
    observed_at: datetime,
) -> tuple[UUID, UUID]:
    package_id = _upsert_entity(
        connection,
        entity_type="Package",
        canonical_key=key.package_purl,
        name=key.name,
        properties={"ecosystem": key.ecosystem, "package_name": key.name},
        observed_at=observed_at,
    )
    version_id = _upsert_entity(
        connection,
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
    for entity_id, purl, is_canonical in (
        (package_id, key.package_purl, True),
        (version_id, key.purl, True),
    ):
        connection.execute(
            """
            INSERT INTO entity_identity (
                tenant_id, entity_id, scheme, identity_value, is_canonical,
                source_artifact_id, first_seen_at, last_seen_at
            )
            VALUES (NULL, %s, 'PURL', %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, scheme, identity_value) DO UPDATE
            SET entity_id = EXCLUDED.entity_id,
                is_canonical = EXCLUDED.is_canonical,
                source_artifact_id = EXCLUDED.source_artifact_id,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                entity_id,
                purl,
                is_canonical,
                artifact_id,
                observed_at,
                observed_at,
            ),
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


def _upsert_entity(
    connection: Connection[dict[str, Any]],
    *,
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
        VALUES (NULL, 'TECHNOLOGY', %s, %s, %s, %s, %s, %s)
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
    object_entity_id: UUID | None,
    spec: FactSpec,
    source_revision: str,
    observed_at: datetime,
) -> UUID | None:
    idempotency_key = sha256_key(
        spec.logical_key,
        source_revision,
        EXTRACTOR_KEY,
        EXTRACTOR_VERSION,
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
            NULL, %s, %s, %s, %s, %s, 'EXTERNAL_MEASURED', 1.0,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """,
        (
            snapshot_id,
            subject_id,
            spec.predicate,
            object_entity_id,
            Jsonb(spec.object_value) if spec.object_value is not None else None,
            spec.logical_key,
            idempotency_key,
            source_revision,
            EXTRACTOR_KEY,
            EXTRACTOR_VERSION,
            Jsonb(spec.properties),
            spec.effective_from,
            observed_at,
        ),
    ).fetchone()
    if row is None:
        return None
    fact_id: UUID = row["id"]
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
            Jsonb(
                {
                    "uri": spec.evidence_uri,
                    "json_pointer": spec.evidence_pointer,
                }
            ),
            spec.evidence_hash,
            Jsonb({"provider": SOURCE_KEY, "api_version": "v3"}),
            observed_at,
        ),
    )
    return fact_id


def _lock_owned_run(
    connection: Connection[dict[str, Any]], run_id: UUID, worker_id: str
) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM ingest_run
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


def _complete_replayed_run(
    connection: Connection[dict[str, Any]],
    claimed: ClaimedRun,
    enrichment: NormalizedEnrichment,
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
            Jsonb({"replayed": True, "source_revision": enrichment.source_revision}),
            claimed.run_id,
        ),
    )
    _update_freshness(connection, claimed, enrichment, observed_at)


def _complete_run(
    connection: Connection[dict[str, Any]],
    claimed: ClaimedRun,
    enrichment: NormalizedEnrichment,
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
                    "node_count": len(enrichment.nodes),
                    "edge_count": len(enrichment.edges),
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
    enrichment: NormalizedEnrichment,
    observed_at: datetime,
) -> None:
    refresh_seconds = _policy_int(
        claimed.refresh_policy, "refresh_seconds", DEFAULT_REFRESH_SECONDS
    )
    if enrichment.completeness == "PARTIAL":
        refresh_seconds = min(refresh_seconds, 3_600)
    connection.execute(
        """
        UPDATE ingest_target
        SET desired_source_revision = %s,
            next_due_at = now() + (%s * interval '1 second'),
            last_success_at = CASE WHEN %s = 'COMPLETE' THEN now() ELSE last_success_at END,
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
        claimed.refresh_policy, "max_attempts", DEFAULT_MAX_ATTEMPTS
    )
    terminal = not retriable or claimed.attempt >= max_attempts
    if retry_after_seconds is None:
        delay = min(60 * (2 ** max(claimed.attempt - 1, 0)), 3_600)
    else:
        delay = min(max(retry_after_seconds, 1), 3_600)
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
                VALUES (NULL, 'DEPS_DEV', %s, %s, %s, %s)
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
                DO UPDATE SET status = 'ERROR', limitations = EXCLUDED.limitations,
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
    return WorkResult(
        status=status,
        run_id=str(claimed.run_id),
        target_key=claimed.target_key,
        retry_after_seconds=None if terminal else delay,
    )


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    value = policy.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"refresh policy {key} must be a positive integer")
    return value


def _database_url(parser: argparse.ArgumentParser) -> str:
    value = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not value:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deps.dev OSS enrichment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enqueue = subparsers.add_parser("enqueue")
    enqueue.add_argument("purl")
    enqueue.add_argument("--priority", default="WARM")
    enqueue.add_argument("--max-nodes", type=int, default=1_000)
    enqueue.add_argument("--max-edges", type=int, default=5_000)
    enqueue.add_argument("--refresh-seconds", type=int, default=DEFAULT_REFRESH_SECONDS)
    work = subparsers.add_parser("work")
    work.add_argument("--worker-id")
    work.add_argument("--lease-seconds", type=int, default=300)
    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--limit", type=int, default=100)
    run = subparsers.add_parser("run")
    run.add_argument("purl")
    run.add_argument("--priority", default="ON_DEMAND")
    run.add_argument("--max-nodes", type=int, default=1_000)
    run.add_argument("--max-edges", type=int, default=5_000)
    run.add_argument("--refresh-seconds", type=int, default=DEFAULT_REFRESH_SECONDS)
    run.add_argument("--worker-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = _database_url(parser)
    if args.command == "enqueue":
        result: object = enqueue_package_version(
            database_url,
            args.purl,
            priority=args.priority,
            max_nodes=args.max_nodes,
            max_edges=args.max_edges,
            refresh_seconds=args.refresh_seconds,
        )
    elif args.command == "work":
        result = run_once(
            database_url,
            worker_id=args.worker_id,
            lease_seconds=args.lease_seconds,
        )
    elif args.command == "schedule":
        result = schedule_due_targets(database_url, limit=args.limit)
    else:
        enqueue_result = enqueue_package_version(
            database_url,
            args.purl,
            priority=args.priority,
            max_nodes=args.max_nodes,
            max_edges=args.max_edges,
            refresh_seconds=args.refresh_seconds,
        )
        work_result = run_once(database_url, worker_id=args.worker_id)
        result = {
            "enqueue": asdict(enqueue_result),
            "work": asdict(work_result),
        }
    payload = asdict(result) if hasattr(result, "__dataclass_fields__") else result
    print(json.dumps(payload, sort_keys=True))
    status = (
        result.status
        if isinstance(result, WorkResult)
        else result.get("work", {}).get("status")
        if isinstance(result, dict)
        else None
    )
    if status in {"RETRY_SCHEDULED", "LEASE_LOST"}:
        return 75
    if status == "FAILED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

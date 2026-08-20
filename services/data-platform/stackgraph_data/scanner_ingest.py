from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from uuid import UUID
from urllib.parse import quote, unquote, urlsplit

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import sha256_key
from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.depsdev_worker import ensure_package_version_target_connection


SOURCE_KEY = "github-enterprise"
SHA256_KEY = re.compile(r"^sha256:[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    target_id: str
    run_id: str
    created: bool


@dataclass(frozen=True, slots=True)
class PersistResult:
    snapshot_id: str
    status: str
    replayed: bool
    fact_count: int
    usage_summary_count: int
    enrichment_target_count: int = 0


@dataclass(frozen=True, slots=True)
class ApiSurfaceResult:
    api_surface_id: str
    replayed: bool


def enqueue_repository_scan(
    database_url: str,
    *,
    tenant_key: str,
    repository_key: str,
    source_revision: str,
    priority: str = "HOT",
) -> EnqueueResult:
    if not tenant_key or not repository_key or not source_revision:
        raise ValueError("tenant_key, repository_key, and source_revision are required")
    if priority not in {"HOT", "WARM", "COLD", "ON_DEMAND"}:
        raise ValueError("invalid priority")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        tenant = connection.execute(
            "SELECT id FROM tenant WHERE tenant_key=%s AND status='ACTIVE'",
            (tenant_key,),
        ).fetchone()
        if tenant is None:
            raise ValueError(f"unknown active tenant: {tenant_key}")
        tenant_id: UUID = tenant["id"]
        source = connection.execute(
            """
            INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
            VALUES (%s,%s,'GITHUB','https://api.github.com',%s)
            ON CONFLICT (tenant_id,source_key) DO UPDATE SET metadata=EXCLUDED.metadata
            RETURNING id
            """,
            (tenant_id, SOURCE_KEY, Jsonb({"purpose": "repository-snapshot"})),
        ).fetchone()
        assert source is not None
        target = connection.execute(
            """
            INSERT INTO ingest_target(
              tenant_id,source_system_id,target_kind,target_key,priority,enabled,
              refresh_policy,desired_source_revision,next_due_at
            ) VALUES (%s,%s,'REPOSITORY',%s,%s,true,%s,%s,now())
            ON CONFLICT (tenant_id,source_system_id,target_kind,target_key)
            DO UPDATE SET desired_source_revision=EXCLUDED.desired_source_revision,
                          priority=EXCLUDED.priority,enabled=true,updated_at=now()
            RETURNING id
            """,
            (
                tenant_id,
                source["id"],
                repository_key,
                priority,
                Jsonb({"scanner": "repository-dependency-usage", "contract_version": "1.0.0"}),
                source_revision,
            ),
        ).fetchone()
        assert target is not None
        existing = connection.execute(
            """
            SELECT id FROM ingest_run
            WHERE ingest_target_id=%s AND requested_source_revision=%s
              AND status IN ('PENDING','RUNNING','SUCCEEDED','PARTIAL')
            ORDER BY created_at DESC LIMIT 1
            """,
            (target["id"], source_revision),
        ).fetchone()
        if existing:
            return EnqueueResult(str(target["id"]), str(existing["id"]), False)
        run = connection.execute(
            """
            INSERT INTO ingest_run(
              tenant_id,ingest_target_id,trigger_kind,requested_source_revision,status
            ) VALUES (%s,%s,'RECONCILIATION',%s,'PENDING') RETURNING id
            """,
            (tenant_id, target["id"], source_revision),
        ).fetchone()
        assert run is not None
        return EnqueueResult(str(target["id"]), str(run["id"]), True)


def persist_scanner_result(
    database_url: str,
    result: Mapping[str, Any],
    *,
    target_id: UUID,
    run_id: UUID,
    raw_observation: Mapping[str, Any] | None = None,
) -> PersistResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return persist_scanner_result_connection(
            connection,
            result,
            target_id=target_id,
            run_id=run_id,
            raw_observation=raw_observation,
        )


def persist_scanner_result_connection(
    connection: Connection[dict[str, Any]],
    result: Mapping[str, Any],
    *,
    target_id: UUID,
    run_id: UUID,
    raw_observation: Mapping[str, Any] | None = None,
) -> PersistResult:
    _validate_result(result)
    context = connection.execute(
        """
        SELECT target.id target_id,target.tenant_id,target.target_key,target.source_system_id,
               run.id run_id,run.tenant_id run_tenant,tenant.tenant_key
        FROM ingest_target target
        JOIN ingest_run run ON run.ingest_target_id=target.id
        JOIN tenant ON tenant.id=target.tenant_id
        WHERE target.id=%s AND run.id=%s
        FOR UPDATE OF target,run
        """,
        (target_id, run_id),
    ).fetchone()
    if context is None:
        raise ValueError("ingest target/run pair does not exist")
    if str(result["run_id"]) != str(run_id):
        raise ValueError("scanner result run_id does not match the ingest run")
    tenant_id: UUID = context["tenant_id"]
    if context["run_tenant"] != tenant_id:
        raise ValueError("ingest run tenant does not match target tenant")
    facts = result.get("facts")
    if not isinstance(facts, list):
        raise ValueError("scanner result facts must be an array")
    for fact in facts:
        if not isinstance(fact, Mapping) or fact.get("tenant_key") != context["tenant_key"]:
            raise ValueError("every scanner fact must match the target tenant")
        if fact.get("source_revision") != result["source_revision"]:
            raise ValueError("scanner fact source revision mismatch")
        if fact.get("extractor") != result["extractor"]:
            raise ValueError("scanner fact extractor must match the result extractor")
        subject = fact.get("subject")
        if isinstance(subject, Mapping) and subject.get("type") == "Repository":
            if subject.get("key") != context["target_key"]:
                raise ValueError("repository fact does not match the ingest target")
    enrichment_purls = sorted(
        {
            purl
            for fact in facts
            if (purl := _public_package_version_purl(fact)) is not None
        }
    )

    if raw_observation is not None:
        _persist_raw_observation(
            connection,
            raw_observation,
            context=context,
            result=result,
        )

    extractor = result["extractor"]
    existing = connection.execute(
        """
        SELECT id,status FROM source_snapshot
        WHERE ingest_target_id=%s AND source_revision=%s
          AND extractor_key=%s AND extractor_version=%s
        """,
        (target_id, result["source_revision"], extractor["key"], extractor["version"]),
    ).fetchone()
    if existing and existing["status"] == "PUBLISHED":
        count = connection.execute(
            "SELECT count(*) count FROM fact_assertion WHERE source_snapshot_id=%s",
            (existing["id"],),
        ).fetchone()
        enrichment_target_count = sum(
            ensure_package_version_target_connection(connection, purl).created
            for purl in enrichment_purls
        )
        return PersistResult(
            str(existing["id"]), "PUBLISHED", True, int(count["count"]), 0,
            enrichment_target_count,
        )
    if existing:
        snapshot_id: UUID = existing["id"]
    else:
        snapshot = connection.execute(
            """
            INSERT INTO source_snapshot(
              tenant_id,ingest_run_id,ingest_target_id,source_revision,
              extractor_key,extractor_version,completeness,status,observed_at,stats
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,'STAGED',%s,%s) RETURNING id
            """,
            (
                tenant_id, run_id, target_id, result["source_revision"],
                extractor["key"], extractor["version"], result["completeness"],
                _result_observed_at(result), Jsonb(result["stats"]),
            ),
        ).fetchone()
        assert snapshot is not None
        snapshot_id = snapshot["id"]

    fact_count = 0
    usage_count = 0
    for fact in facts:
        subject_id = _upsert_entity(connection, tenant_id, fact["subject"])
        object_entity = fact.get("object_entity")
        public_package_purl = _public_package_version_purl(fact)
        object_tenant_id = None if public_package_purl is not None else tenant_id
        object_id = (
            _upsert_entity(connection, object_tenant_id, object_entity)
            if isinstance(object_entity, Mapping)
            else None
        )
        logical_key = _logical_key(fact)
        inserted = connection.execute(
            """
            INSERT INTO fact_assertion(
              tenant_id,source_snapshot_id,subject_entity_id,predicate,object_entity_id,
              object_value,assertion_class,confidence,logical_key,idempotency_key,
              source_revision,extractor_key,extractor_version,properties,
              effective_from,observed_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(idempotency_key) DO NOTHING RETURNING id
            """,
            (
                tenant_id, snapshot_id, subject_id, fact["predicate"], object_id,
                Jsonb(fact["object_value"]) if "object_value" in fact else None,
                fact["assertion_class"], fact["confidence"], logical_key,
                fact["idempotency_key"], fact["source_revision"],
                fact["extractor"]["key"], fact["extractor"]["version"],
                Jsonb(fact.get("properties") or {}), fact.get("effective_at"),
                fact["observed_at"],
            ),
        ).fetchone()
        if inserted is None:
            existing_fact = connection.execute(
                "SELECT id,source_snapshot_id FROM fact_assertion WHERE idempotency_key=%s",
                (fact["idempotency_key"],),
            ).fetchone()
            if existing_fact is None or existing_fact["source_snapshot_id"] != snapshot_id:
                raise ValueError("scanner fact idempotency key collides with another snapshot")
            fact_id = existing_fact["id"]
        else:
            fact_id = inserted["id"]
            fact_count += 1
        for evidence in fact["evidence"]:
            artifact_id = _upsert_source_artifact(
                connection, tenant_id, context["source_system_id"], fact, evidence,
            )
            inserted_usage = connection.execute(
                """
                INSERT INTO evidence(
                  tenant_id,fact_assertion_id,source_artifact_id,evidence_type,
                  locator,excerpt_hash,metadata,observed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(fact_assertion_id,source_artifact_id,evidence_type,locator)
                DO NOTHING
                """,
                (
                    tenant_id, fact_id, artifact_id, evidence["type"],
                    Jsonb(evidence["locator"]), evidence.get("excerpt_hash"),
                    Jsonb(evidence.get("metadata") or {}), fact["observed_at"],
                ),
            )
        usage = (fact.get("properties") or {}).get("usage")
        if fact["predicate"] == "DEPENDS_ON" and isinstance(usage, Mapping):
            connection.execute(
                """
                INSERT INTO dependency_usage_summary(
                  tenant_id,source_snapshot_id,dependency_fact_assertion_id,
                  declared,resolved,referenced,static_reachability,runtime_observed,
                  reference_count,referenced_symbols,source_files_scanned,limitations,
                  analysis_fingerprint
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(dependency_fact_assertion_id) DO NOTHING RETURNING id
                """,
                (
                    tenant_id, snapshot_id, fact_id, bool(usage["declared"]),
                    bool(usage["resolved"]), bool(usage["referenced"]),
                    usage["static_reachability"], usage["runtime_observed"],
                    int(usage["reference_count"]), Jsonb(usage.get("referenced_symbols") or []),
                    int(usage["source_files_scanned"]), Jsonb(usage.get("limitations") or []),
                    sha256_key(fact["idempotency_key"], usage),
                ),
            ).fetchone()
            usage_count += int(inserted_usage is not None)
        if fact["predicate"] == "DEPENDS_ON" and object_id is not None:
            _persist_dependency_resolution(connection, tenant_id, fact_id, object_id, fact)
        code_summary = fact.get("object_value")
        if (
            fact["predicate"] == "HAS_PROPERTY"
            and isinstance(code_summary, Mapping)
            and code_summary.get("record_kind") == "code_implementation_summary"
        ):
            _persist_code_implementation_summary(
                connection,
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                repository_id=subject_id,
                fact_id=fact_id,
                source_revision=str(result["source_revision"]),
                completeness=str(result["completeness"]),
                value=code_summary,
            )

    connection.execute("SELECT publish_source_snapshot(%s)", (snapshot_id,))
    run_status = "SUCCEEDED" if result["completeness"] == "COMPLETE" else "PARTIAL"
    connection.execute(
        """
        UPDATE ingest_run SET status=%s,completeness=%s,stats=%s,
          completed_at=now(),lease_owner=NULL,lease_expires_at=NULL
        WHERE id=%s
        """,
        (run_status, result["completeness"], Jsonb(result["stats"]), run_id),
    )
    connection.execute(
        """
        UPDATE ingest_target SET last_success_at=now(),next_due_at=now()+interval '1 day',
          updated_at=now() WHERE id=%s
        """,
        (target_id,),
    )
    enrichment_target_count = sum(
        ensure_package_version_target_connection(connection, purl).created
        for purl in enrichment_purls
    )
    return PersistResult(
        str(snapshot_id), "PUBLISHED", False, fact_count, usage_count,
        enrichment_target_count,
    )


def _public_package_version_purl(fact: Mapping[str, Any]) -> str | None:
    if fact.get("predicate") != "DEPENDS_ON":
        return None
    entity = fact.get("object_entity")
    if (
        not isinstance(entity, Mapping)
        or entity.get("namespace") != "TECHNOLOGY"
        or entity.get("type") != "PackageVersion"
        or not isinstance(entity.get("key"), str)
    ):
        return None
    try:
        target = PackageVersionKey.from_purl(entity["key"])
    except ValueError:
        return None
    properties = fact.get("properties")
    registry = properties.get("registry_resolution") if isinstance(properties, Mapping) else None
    if (
        not isinstance(registry, Mapping)
        or registry.get("visibility") != "PUBLIC"
        or bool(registry.get("custom_registry"))
    ):
        return None
    return target.purl


def _persist_code_implementation_summary(
    connection: Connection[dict[str, Any]],
    *,
    tenant_id: UUID,
    snapshot_id: UUID,
    repository_id: UUID,
    fact_id: UUID,
    source_revision: str,
    completeness: str,
    value: Mapping[str, Any],
) -> None:
    required_strings = (
        "language", "symbol_kind", "qualified_name", "path", "structural_fingerprint",
    )
    if any(not isinstance(value.get(key), str) or not value[key] for key in required_strings):
        raise ValueError("code implementation summary has invalid identity fields")
    for key in ("semantic_tokens", "dependency_keys", "covering_tests", "dynamic_signals"):
        if not isinstance(value.get(key), list) or not all(
            isinstance(item, str) for item in value[key]
        ):
            raise ValueError(f"code implementation summary {key} must be a string array")
    touchpoints = value.get("touchpoints")
    if not isinstance(touchpoints, list) or not all(isinstance(item, Mapping) for item in touchpoints):
        raise ValueError("code implementation summary touchpoints must be an object array")
    line_start = int(value.get("line_start") or 0)
    line_end = int(value.get("line_end") or 0)
    limitations = []
    if completeness != "COMPLETE":
        limitations.append("repository snapshot was partial")
    connection.execute(
        """
        INSERT INTO code_implementation_summary(
          tenant_id,source_snapshot_id,repository_entity_id,fact_assertion_id,
          source_revision,language,symbol_kind,qualified_name,path,line_start,line_end,
          structural_fingerprint,semantic_tokens,dependency_keys,covering_tests,
          dynamic_signals,touchpoints,vendored,completeness,limitations
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(
          tenant_id,repository_entity_id,source_revision,path,qualified_name,
          line_start,structural_fingerprint
        ) DO UPDATE SET
          source_snapshot_id=EXCLUDED.source_snapshot_id,
          fact_assertion_id=EXCLUDED.fact_assertion_id,
          language=EXCLUDED.language,
          symbol_kind=EXCLUDED.symbol_kind,
          line_end=EXCLUDED.line_end,
          semantic_tokens=EXCLUDED.semantic_tokens,
          dependency_keys=EXCLUDED.dependency_keys,
          covering_tests=EXCLUDED.covering_tests,
          dynamic_signals=EXCLUDED.dynamic_signals,
          touchpoints=EXCLUDED.touchpoints,
          vendored=EXCLUDED.vendored,
          completeness=EXCLUDED.completeness,
          limitations=EXCLUDED.limitations
        """,
        (
            tenant_id, snapshot_id, repository_id, fact_id, source_revision,
            value["language"], value["symbol_kind"], value["qualified_name"], value["path"],
            line_start, line_end, value["structural_fingerprint"], value["semantic_tokens"],
            value["dependency_keys"], value["covering_tests"], value["dynamic_signals"],
            Jsonb([dict(item) for item in touchpoints]), bool(value.get("vendored")),
            completeness, Jsonb(limitations),
        ),
    )


def persist_api_surface(
    database_url: str,
    surface: Mapping[str, Any],
    *,
    tenant_id: UUID | None = None,
) -> ApiSurfaceResult:
    _validate_api_surface(surface)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return persist_api_surface_connection(connection, surface, tenant_id=tenant_id)


def persist_api_surface_connection(
    connection: Connection[dict[str, Any]],
    surface: Mapping[str, Any],
    *,
    tenant_id: UUID | None = None,
) -> ApiSurfaceResult:
    _validate_api_surface(surface)
    entity = {
        "namespace": "TECHNOLOGY",
        "type": "PackageVersion",
        "key": surface["package_purl"],
        "name": surface["package_purl"].removeprefix("pkg:"),
    }
    entity_id = _upsert_entity(connection, tenant_id, entity)
    row = connection.execute(
        """
        INSERT INTO package_api_surface(
          tenant_id,package_version_entity_id,ecosystem,artifact_checksum,
          analyzer_key,analyzer_version,analysis_fingerprint,public_symbol_count,
          symbols,completeness,limitations,stats
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
        """,
        (
            tenant_id, entity_id, surface["ecosystem"], surface["artifact_checksum"],
            surface["analyzer"]["key"], surface["analyzer"]["version"],
            surface["analysis_fingerprint"], surface["public_symbol_count"],
            Jsonb(surface["symbols"]), surface["completeness"],
            Jsonb(surface["limitations"]), Jsonb(surface["stats"]),
        ),
    ).fetchone()
    if row:
        return ApiSurfaceResult(str(row["id"]), False)
    existing = connection.execute(
        """
        SELECT id FROM package_api_surface
        WHERE tenant_id IS NOT DISTINCT FROM %s AND analysis_fingerprint=%s
        """,
        (tenant_id, surface["analysis_fingerprint"]),
    ).fetchone()
    assert existing is not None
    return ApiSurfaceResult(str(existing["id"]), True)


def _validate_result(result: Mapping[str, Any]) -> None:
    required = {
        "scanner_contract_version", "run_id", "source_revision", "extractor",
        "completeness", "facts", "stats", "diagnostics",
    }
    if not required <= set(result) or result["scanner_contract_version"] != "1.0.0":
        raise ValueError("invalid scanner result contract")
    if result["completeness"] not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("invalid scanner completeness")
    if not isinstance(result["extractor"], Mapping):
        raise ValueError("scanner extractor must be an object")
    if not result["extractor"].get("key") or not result["extractor"].get("version"):
        raise ValueError("scanner extractor key and version are required")
    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("scanner diagnostics must be an array")
    if result["completeness"] == "COMPLETE" and any(
        isinstance(item, Mapping) and item.get("severity") == "ERROR"
        for item in diagnostics
    ):
        raise ValueError("a COMPLETE scanner result cannot contain ERROR diagnostics")


def _validate_api_surface(surface: Mapping[str, Any]) -> None:
    if surface.get("api_surface_contract_version") != "1.0.0":
        raise ValueError("invalid API surface contract")
    if surface.get("completeness") not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("invalid API surface completeness")
    symbols = surface.get("symbols")
    analyzer = surface.get("analyzer")
    if not isinstance(symbols, list) or not isinstance(analyzer, Mapping):
        raise ValueError("invalid API surface payload")
    if not analyzer.get("key") or not analyzer.get("version"):
        raise ValueError("API surface analyzer key and version are required")
    package_purl = surface.get("package_purl")
    ecosystem = surface.get("ecosystem")
    if (
        ecosystem not in {"npm", "pypi"}
        or not isinstance(package_purl, str)
        or not package_purl.startswith(f"pkg:{ecosystem}/")
        or "@" not in package_purl
    ):
        raise ValueError("API surface requires an exact npm or pypi purl")
    if not all(
        isinstance(surface.get(field), str) and SHA256_KEY.fullmatch(surface[field])
        for field in ("artifact_checksum", "analysis_fingerprint")
    ):
        raise ValueError("API surface checksums must be sha256 keys")
    if surface.get("public_symbol_count") != len(symbols):
        raise ValueError("API surface symbol count does not match symbols")
    if not isinstance(surface.get("limitations"), list) or not isinstance(surface.get("stats"), Mapping):
        raise ValueError("API surface limitations and stats are invalid")


def _result_observed_at(result: Mapping[str, Any]) -> str:
    facts = result.get("facts") or []
    return (
        str(facts[0]["observed_at"])
        if facts
        else datetime.now(timezone.utc).isoformat()
    )


def _entity_scope(tenant_id: UUID | None, entity: Mapping[str, Any]) -> UUID | None:
    key = str(entity["key"])
    if entity["namespace"] in {"ENTERPRISE", "BUSINESS", "DEPLOYMENT"} or key.startswith("registry:"):
        return tenant_id
    return None


def _upsert_entity(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID | None,
    entity: Mapping[str, Any],
    *,
    force_scope: UUID | None | object = ...,
) -> UUID:
    scope = _entity_scope(tenant_id, entity) if force_scope is ... else force_scope
    row = connection.execute(
        """
        INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties,first_seen_at,last_seen_at)
        VALUES (%s,%s,%s,%s,%s,'{}',now(),now())
        ON CONFLICT(tenant_id,namespace,entity_type,canonical_key)
        DO UPDATE SET name=EXCLUDED.name,last_seen_at=now(),updated_at=now()
        RETURNING id
        """,
        (scope, entity["namespace"], entity["type"], entity["key"], entity.get("name") or entity["key"]),
    ).fetchone()
    assert row is not None
    entity_id: UUID = row["id"]
    if str(entity["key"]).startswith("pkg:"):
        connection.execute(
            """
            INSERT INTO entity_identity(tenant_id,entity_id,scheme,identity_value,is_canonical)
            VALUES (%s,%s,'PURL',%s,true)
            ON CONFLICT(tenant_id,scheme,identity_value)
            DO UPDATE SET entity_id=EXCLUDED.entity_id,last_seen_at=now()
            """,
            (scope, entity_id, entity["key"]),
        )
    return entity_id


def _logical_key(fact: Mapping[str, Any]) -> str:
    properties = fact.get("properties") or {}
    semantic = {
        "tenant": fact.get("tenant_key"),
        "subject": fact["subject"]["key"],
        "predicate": fact["predicate"],
        "object": (
            fact["object_entity"]["key"] if "object_entity" in fact
            else fact.get("object_value")
        ),
        "component": properties.get("component_path"),
        "scope": properties.get("scope"),
        "direct": properties.get("direct"),
        "finding": (fact.get("object_value") or {}).get("finding_type") if isinstance(fact.get("object_value"), Mapping) else None,
        "extractor": fact["extractor"]["key"],
    }
    return sha256_key(semantic)


def _persist_raw_observation(
    connection: Connection[dict[str, Any]],
    observation: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    result: Mapping[str, Any],
) -> UUID:
    if observation.get("observation_contract_version") != "1.0.0":
        raise ValueError("raw observation contract version must be 1.0.0")
    if observation.get("tenant_key") != context["tenant_key"]:
        raise ValueError("raw observation tenant does not match the ingest target")
    if observation.get("target_key") != context["target_key"]:
        raise ValueError("raw observation target does not match the ingest target")
    if observation.get("source_revision") != result["source_revision"]:
        raise ValueError("raw observation source revision does not match the scanner result")
    source = observation.get("source")
    content = observation.get("content")
    if not isinstance(source, Mapping) or not isinstance(content, Mapping):
        raise ValueError("raw observation requires source and content objects")
    if source.get("kind") != "GITHUB":
        raise ValueError("repository raw observation source kind must be GITHUB")
    if not isinstance(source.get("key"), str) or not isinstance(
        source.get("adapter_version"), str
    ):
        raise ValueError("raw observation source key and adapter version are required")
    idempotency_key = observation.get("idempotency_key")
    content_hash = content.get("hash")
    if not isinstance(idempotency_key, str) or not SHA256_KEY.fullmatch(idempotency_key):
        raise ValueError("raw observation idempotency key must be a SHA-256 key")
    if not isinstance(content_hash, str) or not SHA256_KEY.fullmatch(content_hash):
        raise ValueError("raw observation content hash must be a SHA-256 key")
    media_type = content.get("media_type")
    size_bytes = content.get("size_bytes")
    if not isinstance(media_type, str) or not media_type:
        raise ValueError("raw observation media type is required")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError("raw observation size must be a non-negative integer")
    has_inline = "inline" in content
    has_blob = "blob_uri" in content
    if has_inline == has_blob:
        raise ValueError("raw observation content requires exactly one of inline or blob_uri")
    inline_body = content.get("inline") if has_inline else None
    blob_uri = content.get("blob_uri") if has_blob else None
    if has_blob and (not isinstance(blob_uri, str) or not blob_uri):
        raise ValueError("raw observation blob URI must be a non-empty string")
    if has_blob:
        parsed_blob = urlsplit(blob_uri)
        if (
            not parsed_blob.scheme
            or not parsed_blob.netloc
            or parsed_blob.username is not None
            or parsed_blob.password is not None
            or parsed_blob.query
            or parsed_blob.fragment
        ):
            raise ValueError(
                "raw observation blob URI must be absolute and contain no credentials, query, or fragment"
            )
        if parsed_blob.scheme == "stackgraph-evidence":
            parts = PurePosixPath(parsed_blob.path).parts
            digest = parts[-1] if parts else ""
            tenant_segment = parts[2] if len(parts) == 5 else ""
            if (
                parsed_blob.netloc != "local"
                or len(parts) != 5
                or parts[1] != "tenants"
                or len(tenant_segment) != 64
                or any(value not in "0123456789abcdef" for value in tenant_segment)
                or parts[3] != "sha256"
                or content_hash != f"sha256:{digest}"
            ):
                raise ValueError("raw observation blob URI does not match its content hash")
    if has_inline:
        inline_bytes = json.dumps(
            inline_body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if sha256_key(inline_body) != content_hash or len(inline_bytes) != size_bytes:
            raise ValueError("inline raw observation content failed checksum or size validation")
    observed_at = observation.get("observed_at")
    if not isinstance(observed_at, str):
        raise ValueError("raw observation observed_at is required")
    observed_timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed_timestamp.tzinfo is None:
        raise ValueError("raw observation observed_at must include a timezone")
    request_metadata = observation.get("request") or {}
    if not isinstance(request_metadata, Mapping):
        raise ValueError("raw observation request must be an object")

    inserted = connection.execute(
        """
        INSERT INTO raw_observation(
          tenant_id,ingest_run_id,source_system_id,target_key,source_revision,
          adapter_key,adapter_version,provider_schema_version,idempotency_key,
          content_hash,media_type,size_bytes,inline_body,blob_uri,request_metadata,
          observed_at,effective_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(idempotency_key) DO NOTHING
        RETURNING id
        """,
        (
            context["tenant_id"],
            context["run_id"],
            context["source_system_id"],
            observation["target_key"],
            observation["source_revision"],
            source["key"],
            source["adapter_version"],
            source.get("schema_version"),
            idempotency_key,
            content_hash,
            media_type,
            size_bytes,
            Jsonb(inline_body) if has_inline else None,
            blob_uri,
            Jsonb(request_metadata),
            observed_at,
            observation.get("effective_at"),
        ),
    ).fetchone()
    if inserted is not None:
        return inserted["id"]
    existing = connection.execute(
        """
        SELECT id,tenant_id,source_system_id,target_key,source_revision,
               adapter_key,adapter_version,content_hash,media_type,size_bytes,
               inline_body,blob_uri
        FROM raw_observation WHERE idempotency_key=%s
        """,
        (idempotency_key,),
    ).fetchone()
    if existing is None:
        raise RuntimeError("raw observation replay could not be resolved")
    expected = {
        "tenant_id": context["tenant_id"],
        "source_system_id": context["source_system_id"],
        "target_key": observation["target_key"],
        "source_revision": observation["source_revision"],
        "adapter_key": source["key"],
        "adapter_version": source["adapter_version"],
        "content_hash": content_hash,
        "media_type": media_type,
        "size_bytes": size_bytes,
        "inline_body": inline_body,
        "blob_uri": blob_uri,
    }
    if any(existing[key] != value for key, value in expected.items()):
        raise ValueError("raw observation idempotency key conflicts with different content")
    return existing["id"]


def _upsert_source_artifact(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID,
    source_system_id: UUID,
    fact: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> UUID:
    reference = evidence["source_artifact"]
    locator = evidence["locator"]
    artifact_uri = reference.get("uri")
    if artifact_uri is not None:
        if not isinstance(artifact_uri, str):
            raise ValueError("source artifact URI must be a string")
        parsed_uri = urlsplit(artifact_uri)
        if (
            not parsed_uri.scheme
            or not parsed_uri.netloc
            or parsed_uri.username is not None
            or parsed_uri.password is not None
            or parsed_uri.query
        ):
            raise ValueError("source artifact URI must be absolute and contain no credentials or query")
        path = locator.get("path")
        if parsed_uri.fragment and (
            not isinstance(path, str)
            or parsed_uri.fragment != f"path=files/{quote(path, safe='/')}"
        ):
            raise ValueError("source artifact URI fragment does not match the evidence path")
    row = connection.execute(
        """
        INSERT INTO source_artifact(
          tenant_id,source_system_id,external_key,artifact_type,name,source_revision,
          content_hash,blob_uri,metadata,observed_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,source_system_id,external_key,source_revision)
        DO UPDATE SET metadata=EXCLUDED.metadata,
                      blob_uri=COALESCE(source_artifact.blob_uri,EXCLUDED.blob_uri)
        RETURNING id,content_hash,blob_uri
        """,
        (
            tenant_id, source_system_id, reference["key"], reference["type"],
            locator.get("path") or reference["key"], reference["revision"],
            reference.get("content_hash"), artifact_uri,
            Jsonb({"locator_kind": evidence["type"]}), fact["observed_at"],
        ),
    ).fetchone()
    assert row is not None
    if row["content_hash"] != reference.get("content_hash"):
        raise ValueError("source artifact content changed for an immutable revision")
    if reference.get("uri") is not None and row["blob_uri"] != reference["uri"]:
        raise ValueError("source artifact URI changed for an immutable revision")
    return row["id"]


def _persist_dependency_resolution(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID,
    fact_id: UUID,
    entity_id: UUID,
    fact: Mapping[str, Any],
) -> None:
    properties = fact.get("properties") or {}
    registry = properties.get("registry_resolution")
    if properties.get("ecosystem") != "npm" or not isinstance(registry, Mapping):
        return
    origin = registry.get("origin")
    if not isinstance(origin, str):
        return
    is_public = registry.get("visibility") == "PUBLIC" and not registry.get("custom_registry")
    registry_tenant = None if is_public else tenant_id
    source = connection.execute(
        """
        INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
        VALUES (%s,%s,'PACKAGE_REGISTRY',%s,'{}')
        ON CONFLICT(tenant_id,source_key) DO UPDATE SET base_uri=EXCLUDED.base_uri
        RETURNING id
        """,
        (registry_tenant, f"npm:{origin}", origin),
    ).fetchone()
    assert source is not None
    registry_key = "npm-public" if is_public else f"npm-{sha256_key(origin)[7:23]}"
    package_registry = connection.execute(
        """
        INSERT INTO package_registry(
          tenant_id,source_system_id,registry_key,origin_uri,normalized_origin_uri,
          ecosystem,visibility,auth_mode,metadata
        ) VALUES (%s,%s,%s,%s,%s,'NPM',%s,%s,'{}')
        ON CONFLICT(tenant_id,registry_key) DO UPDATE SET updated_at=now()
        RETURNING id
        """,
        (
            registry_tenant, source["id"], registry_key, origin, origin,
            registry.get("visibility") or "UNKNOWN",
            "NONE" if is_public else "OTHER",
        ),
    ).fetchone()
    assert package_registry is not None
    object_key = fact["object_entity"]["key"]
    purl = object_key.split(":pkg:", 1)[-1]
    if not purl.startswith("pkg:"):
        purl = f"pkg:{purl}"
    package_name = unquote(purl.split("/", 1)[1].rsplit("@", 1)[0])
    connection.execute(
        """
        INSERT INTO package_registry_identity(
          tenant_id,entity_id,package_registry_id,package_name,package_version,purl,visibility
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(package_registry_id,package_name,package_version)
        DO UPDATE SET entity_id=EXCLUDED.entity_id,last_seen_at=now()
        """,
        (
            registry_tenant, entity_id, package_registry["id"], package_name,
            properties.get("resolved_version"), purl,
            registry.get("visibility") or "UNKNOWN",
        ),
    )
    artifact = properties.get("artifact") if isinstance(properties.get("artifact"), Mapping) else {}
    connection.execute(
        """
        INSERT INTO dependency_resolution(
          tenant_id,fact_assertion_id,package_registry_id,resolution_source,
          requested_spec,resolved_version,resolved_artifact_uri,integrity,npm_scope,
          config_path,custom_registry,lockfile_behavior,visibility,observed_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(fact_assertion_id) DO NOTHING
        """,
        (
            tenant_id, fact_id, package_registry["id"], registry.get("source") or "UNKNOWN",
            properties["requested_spec"], properties.get("resolved_version"),
            artifact.get("resolved_uri"), artifact.get("integrity"), registry.get("scope"),
            registry.get("config_path"), bool(registry.get("custom_registry")),
            registry.get("lockfile_behavior") or "UNKNOWN",
            registry.get("visibility") or "UNKNOWN", fact["observed_at"],
        ),
    )


def _database_url() -> str:
    value = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not value:
        raise ValueError("STACKGRAPH_DATABASE_URL is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persist StackGraph repository scanner outputs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enqueue = subparsers.add_parser("enqueue")
    enqueue.add_argument("--tenant-key", required=True)
    enqueue.add_argument("--repository-key", required=True)
    enqueue.add_argument("--source-revision", required=True)
    enqueue.add_argument("--priority", default="HOT")
    persist = subparsers.add_parser("persist")
    persist.add_argument("result", type=Path)
    persist.add_argument("--raw-observation", type=Path)
    persist.add_argument("--target-id", type=UUID, required=True)
    persist.add_argument("--run-id", type=UUID, required=True)
    surface = subparsers.add_parser("api-surface")
    surface.add_argument("result", type=Path)
    surface.add_argument("--tenant-id", type=UUID)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = _database_url()
    if args.command == "enqueue":
        result = enqueue_repository_scan(
            database_url,
            tenant_key=args.tenant_key,
            repository_key=args.repository_key,
            source_revision=args.source_revision,
            priority=args.priority,
        )
    elif args.command == "persist":
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        raw_observation = (
            json.loads(args.raw_observation.read_text(encoding="utf-8"))
            if args.raw_observation is not None
            else None
        )
        result = persist_scanner_result(
            database_url,
            payload,
            target_id=args.target_id,
            run_id=args.run_id,
            raw_observation=raw_observation,
        )
    else:
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        result = persist_api_surface(database_url, payload, tenant_id=args.tenant_id)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

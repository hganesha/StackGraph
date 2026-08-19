from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID
from urllib.parse import unquote

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import sha256_key


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
) -> PersistResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return persist_scanner_result_connection(
            connection, result, target_id=target_id, run_id=run_id,
        )


def persist_scanner_result_connection(
    connection: Connection[dict[str, Any]],
    result: Mapping[str, Any],
    *,
    target_id: UUID,
    run_id: UUID,
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
        return PersistResult(str(existing["id"]), "PUBLISHED", True, int(count["count"]), 0)
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
        object_id = _upsert_entity(connection, tenant_id, object_entity) if isinstance(object_entity, Mapping) else None
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
    return PersistResult(str(snapshot_id), "PUBLISHED", False, fact_count, usage_count)


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
        ON CONFLICT(fact_assertion_id) DO NOTHING
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


def _upsert_source_artifact(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID,
    source_system_id: UUID,
    fact: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> UUID:
    reference = evidence["source_artifact"]
    locator = evidence["locator"]
    row = connection.execute(
        """
        INSERT INTO source_artifact(
          tenant_id,source_system_id,external_key,artifact_type,name,source_revision,
          content_hash,metadata,observed_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,source_system_id,external_key,source_revision)
        DO UPDATE SET metadata=EXCLUDED.metadata
        RETURNING id,content_hash
        """,
        (
            tenant_id, source_system_id, reference["key"], reference["type"],
            locator.get("path") or reference["key"], reference["revision"],
            reference.get("content_hash"),
            Jsonb({"locator_kind": evidence["type"]}), fact["observed_at"],
        ),
    ).fetchone()
    assert row is not None
    if row["content_hash"] != reference.get("content_hash"):
        raise ValueError("source artifact content changed for an immutable revision")
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
        result = persist_scanner_result(
            database_url, payload, target_id=args.target_id, run_id=args.run_id,
        )
    else:
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        result = persist_api_surface(database_url, payload, tenant_id=args.tenant_id)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

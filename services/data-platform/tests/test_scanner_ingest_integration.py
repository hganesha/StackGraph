from __future__ import annotations

import os
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from stackgraph_data.catalog import sha256_key
from stackgraph_data.scanner_ingest import (
    _public_package_version_purl,
    persist_api_surface_connection,
    persist_scanner_result_connection,
)
try:
    from stackgraph_discovery.repository_scanner import scan_repository
except ModuleNotFoundError:  # The data-platform-only test image omits discovery code.
    scan_repository = None


DATABASE_URL = os.environ.get("STACKGRAPH_TEST_DATABASE_URL")


class EnrichmentTargetSelectionTests(unittest.TestCase):
    def test_selects_only_exact_public_package_versions(self) -> None:
        fact = {
            "predicate": "DEPENDS_ON",
            "object_entity": {
                "namespace": "TECHNOLOGY",
                "type": "PackageVersion",
                "key": "pkg:npm/Axios@1.7.9",
            },
            "properties": {
                "registry_resolution": {
                    "visibility": "PUBLIC",
                    "custom_registry": False,
                }
            },
        }
        self.assertEqual(
            _public_package_version_purl(fact),
            "pkg:npm/axios@1.7.9",
        )

        fact["properties"]["registry_resolution"]["custom_registry"] = True
        self.assertIsNone(_public_package_version_purl(fact))
        fact["properties"]["registry_resolution"]["custom_registry"] = False
        fact["object_entity"]["key"] = "pkg:npm/axios"
        self.assertIsNone(_public_package_version_purl(fact))
        fact["object_entity"].update({
            "type": "PackageVersion",
            "key": "pkg:pypi/requests@2.32.5",
        })
        fact["properties"].pop("registry_resolution")
        self.assertIsNone(_public_package_version_purl(fact))


@unittest.skipUnless(DATABASE_URL, "STACKGRAPH_TEST_DATABASE_URL is not configured")
class ScannerPersistenceIntegrationTests(unittest.TestCase):
    @unittest.skipIf(scan_repository is None, "enterprise-discovery scanner is not installed")
    def test_scanner_111_persists_components_builds_and_fingerprint(self) -> None:
        tenant_key = f"scanner-111-{uuid4()}"
        repository_key = f"github:repo:{uuid4()}"
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Scanner 1.11 test') RETURNING id",
                (tenant_key,),
            ).fetchone()
            source = connection.execute(
                "INSERT INTO source_system(tenant_id,source_key,kind) VALUES (%s,'scanner-111','GITHUB') RETURNING id",
                (tenant["id"],),
            ).fetchone()
            target = connection.execute(
                """
                INSERT INTO ingest_target(tenant_id,source_system_id,target_kind,target_key,refresh_policy)
                VALUES (%s,%s,'REPOSITORY',%s,'{}') RETURNING id
                """,
                (tenant["id"], source["id"], repository_key),
            ).fetchone()
            run = connection.execute(
                """
                INSERT INTO ingest_run(tenant_id,ingest_target_id,trigger_kind,requested_source_revision)
                VALUES (%s,%s,'MANUAL','revision-111') RETURNING id
                """,
                (tenant["id"], target["id"]),
            ).fetchone()
            with TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "package.json").write_text(json.dumps({
                    "name": "scanner-111", "private": True,
                    "dependencies": {"fastify": "5.5.0"},
                }))
                (root / "Dockerfile").write_text(
                    f"FROM node@sha256:{'a' * 64}\n",
                )
                result = scan_repository({
                    "scanner_contract_version": "1.0.0",
                    "run_id": str(run["id"]), "tenant_key": tenant_key,
                    "target": {
                        "provider": "github", "repository_id": "111",
                        "canonical_key": repository_key, "name": "scanner-111",
                        "default_branch": "main",
                    },
                    "snapshot": {
                        "source_revision": "revision-111", "checkout_root": str(root),
                        "requested_at": "2026-09-05T12:00:00Z",
                    },
                    "limits": {"max_files": 100, "max_bytes": 1_000_000, "deadline_seconds": 30},
                })
            persisted = persist_scanner_result_connection(
                connection, result, target_id=target["id"], run_id=run["id"],
            )
            rows = connection.execute(
                """
                SELECT fact.predicate,subject.entity_type subject_type,
                       object_entity.entity_type object_type,
                       fact.object_value->>'record_kind' record_kind
                FROM fact_assertion fact
                JOIN entity subject ON subject.id=fact.subject_entity_id
                LEFT JOIN entity object_entity ON object_entity.id=fact.object_entity_id
                WHERE fact.source_snapshot_id=%s
                """,
                (persisted.snapshot_id,),
            ).fetchall()
            shapes = {
                (row["predicate"], row["subject_type"], row["object_type"], row["record_kind"])
                for row in rows
            }
            self.assertIn(("CONTAINS", "Repository", "Component", None), shapes)
            self.assertIn(("DEPENDS_ON", "Component", "Package", None), shapes)
            self.assertIn(("BUILDS", "Component", "ContainerImage", None), shapes)
            self.assertIn(("BASED_ON", "ContainerImage", "ContainerImage", None), shapes)
            self.assertIn(("HAS_PROPERTY", "Repository", None, "repository_fingerprint"), shapes)
        finally:
            connection.rollback()
            connection.close()

    def test_api_surface_replays_within_scope_and_isolates_tenant_scope(self) -> None:
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'API surface test') RETURNING id",
                (f"api-surface-test-{uuid4()}",),
            ).fetchone()
            surface = {
                "api_surface_contract_version": "1.0.0",
                "package_purl": "pkg:npm/example@1.2.3",
                "ecosystem": "npm",
                "artifact_checksum": f"sha256:{'a' * 64}",
                "analyzer": {"key": "package-api-surface", "version": "1.0.0"},
                "analysis_fingerprint": f"sha256:{'b' * 64}",
                "public_symbol_count": 1,
                "symbols": [{"module": "index.js", "name": "run", "kind": "function"}],
                "stats": {"files_scanned": 1, "bytes_read": 42},
                "completeness": "COMPLETE",
                "limitations": [],
            }

            public = persist_api_surface_connection(connection, surface)
            replay = persist_api_surface_connection(connection, surface)
            tenant_scoped = persist_api_surface_connection(
                connection, surface, tenant_id=tenant["id"],
            )

            self.assertFalse(public.replayed)
            self.assertTrue(replay.replayed)
            self.assertFalse(tenant_scoped.replayed)
            self.assertNotEqual(public.api_surface_id, tenant_scoped.api_surface_id)
        finally:
            connection.rollback()
            connection.close()

    def test_persists_usage_and_complete_snapshot_closes_prior_extractor_version(self) -> None:
        tenant_key = f"scanner-test-{uuid4()}"
        repository_key = f"github:repo:{uuid4()}"
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Scanner test') RETURNING id",
                (tenant_key,),
            ).fetchone()
            source = connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind)
                VALUES (%s,'scanner-test','GITHUB') RETURNING id
                """,
                (tenant["id"],),
            ).fetchone()
            target = connection.execute(
                """
                INSERT INTO ingest_target(
                  tenant_id,source_system_id,target_kind,target_key,refresh_policy
                ) VALUES (%s,%s,'REPOSITORY',%s,'{}') RETURNING id
                """,
                (tenant["id"], source["id"], repository_key),
            ).fetchone()
            first_run = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,requested_source_revision
                ) VALUES (%s,%s,'MANUAL','revision-1') RETURNING id
                """,
                (tenant["id"], target["id"]),
            ).fetchone()
            first = _result(
                tenant_key=tenant_key,
                repository_key=repository_key,
                run_id=str(first_run["id"]),
                revision="revision-1",
                extractor_version="1.0.0",
                include_fact=True,
            )
            package_name = f"scanner-dependency-{uuid4().hex}"
            package_purl = f"pkg:npm/{package_name}@4.17.21"
            first["facts"][0]["object_entity"].update({
                "key": package_purl,
                "name": f"{package_name} 4.17.21",
            })
            wrong_tenant_observation = _raw_observation(
                tenant_key, repository_key, "revision-1"
            )
            wrong_tenant_observation["tenant_key"] = "another-tenant"
            with self.assertRaisesRegex(ValueError, "tenant does not match"):
                persist_scanner_result_connection(
                    connection,
                    first,
                    target_id=target["id"],
                    run_id=first_run["id"],
                    raw_observation=wrong_tenant_observation,
                )

            persisted = persist_scanner_result_connection(
                connection,
                first,
                target_id=target["id"],
                run_id=first_run["id"],
                raw_observation=_raw_observation(
                    tenant_key, repository_key, "revision-1"
                ),
            )
            replay = persist_scanner_result_connection(
                connection,
                first,
                target_id=target["id"],
                run_id=first_run["id"],
                raw_observation=_raw_observation(
                    tenant_key, repository_key, "revision-1"
                ),
            )

            self.assertEqual(persisted.fact_count, 2)
            self.assertEqual(persisted.usage_summary_count, 1)
            self.assertEqual(persisted.enrichment_target_count, 1)
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.enrichment_target_count, 0)
            enrichment = connection.execute(
                """
                SELECT source.source_key,target.tenant_id,target.target_key,
                       run.trigger_kind,run.status
                FROM ingest_target target
                JOIN source_system source ON source.id=target.source_system_id
                JOIN ingest_run run ON run.ingest_target_id=target.id
                WHERE source.source_key IN ('deps.dev','osv.dev')
                  AND target.target_key=%s
                ORDER BY source.source_key
                """,
                (package_purl,),
            ).fetchall()
            self.assertEqual(
                enrichment,
                [
                    {
                        "source_key": source_key,
                        "tenant_id": None,
                        "target_key": package_purl,
                        "trigger_kind": "RECONCILIATION",
                        "status": "PENDING",
                    }
                    for source_key in ("deps.dev", "osv.dev")
                ],
            )
            package_entity = connection.execute(
                """
                SELECT package.tenant_id
                FROM fact_assertion fact
                JOIN entity package ON package.id=fact.object_entity_id
                WHERE fact.source_snapshot_id=%s AND fact.predicate='DEPENDS_ON'
                """,
                (persisted.snapshot_id,),
            ).fetchone()
            self.assertIsNone(package_entity["tenant_id"])
            usage = connection.execute(
                """
                SELECT referenced,static_reachability
                FROM dependency_usage_summary WHERE tenant_id=%s
                """,
                (tenant["id"],),
            ).fetchone()
            self.assertEqual(usage, {"referenced": True, "static_reachability": "OBSERVED"})
            code_unit = connection.execute(
                """
                SELECT qualified_name,covering_tests,dynamic_signals
                FROM code_implementation_summary WHERE tenant_id=%s
                """,
                (tenant["id"],),
            ).fetchone()
            self.assertEqual(code_unit["qualified_name"], "debounceRequest")
            self.assertEqual(code_unit["covering_tests"], ["src/client.test.ts"])

            replay_run = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,requested_source_revision
                ) VALUES (%s,%s,'MANUAL','revision-1') RETURNING id
                """,
                (tenant["id"], target["id"]),
            ).fetchone()
            replay_with_new_scanner = _result(
                tenant_key=tenant_key,
                repository_key=repository_key,
                run_id=str(replay_run["id"]),
                revision="revision-1",
                extractor_version="1.1.0",
                include_fact=True,
            )
            for fact in replay_with_new_scanner["facts"]:
                fact["idempotency_key"] = sha256_key(
                    fact["idempotency_key"], "scanner-version-1.1.0"
                )
            refreshed = persist_scanner_result_connection(
                connection,
                replay_with_new_scanner,
                target_id=target["id"],
                run_id=replay_run["id"],
                raw_observation=_raw_observation(
                    tenant_key, repository_key, "revision-1"
                ),
            )
            self.assertFalse(refreshed.replayed)
            refreshed_code_unit = connection.execute(
                """
                SELECT summary.source_snapshot_id,summary.fact_assertion_id,
                       fact.extractor_version
                FROM code_implementation_summary summary
                JOIN fact_assertion fact ON fact.id=summary.fact_assertion_id
                WHERE summary.tenant_id=%s
                """,
                (tenant["id"],),
            ).fetchall()
            self.assertEqual(len(refreshed_code_unit), 1)
            self.assertEqual(refreshed_code_unit[0]["extractor_version"], "1.1.0")
            self.assertEqual(
                str(refreshed_code_unit[0]["source_snapshot_id"]),
                refreshed.snapshot_id,
            )
            artifacts = connection.execute(
                """
                SELECT external_key,blob_uri FROM source_artifact
                WHERE tenant_id=%s ORDER BY external_key
                """,
                (tenant["id"],),
            ).fetchall()
            self.assertEqual(len(artifacts), 2)
            self.assertTrue(all(row["blob_uri"].startswith(_snapshot_uri()) for row in artifacts))
            self.assertTrue(
                any(
                    row["blob_uri"].endswith("#path=files/package.json")
                    for row in artifacts
                )
            )
            raw = connection.execute(
                """
                SELECT target_key,source_revision,content_hash,blob_uri,inline_body
                FROM raw_observation WHERE tenant_id=%s
                """,
                (tenant["id"],),
            ).fetchone()
            self.assertEqual(raw["target_key"], repository_key)
            self.assertEqual(raw["source_revision"], "revision-1")
            self.assertEqual(raw["blob_uri"], _snapshot_uri())
            self.assertIsNone(raw["inline_body"])
            queued = connection.execute(
                """
                SELECT source_revision,status FROM intelligence_job
                WHERE tenant_id=%s AND repository_entity_id=(
                  SELECT id FROM entity WHERE tenant_id=%s AND canonical_key=%s
                )
                """,
                (tenant["id"], tenant["id"], repository_key),
            ).fetchone()
            self.assertEqual(queued, {"source_revision": "revision-1", "status": "PENDING"})

            second_run = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,requested_source_revision
                ) VALUES (%s,%s,'MANUAL','revision-2') RETURNING id
                """,
                (tenant["id"], target["id"]),
            ).fetchone()
            second = _result(
                tenant_key=tenant_key,
                repository_key=repository_key,
                run_id=str(second_run["id"]),
                revision="revision-2",
                extractor_version="1.1.0",
                include_fact=False,
            )
            persist_scanner_result_connection(
                connection,
                second,
                target_id=target["id"],
                run_id=second_run["id"],
            )

            old_fact = connection.execute(
                "SELECT system_to FROM fact_assertion WHERE tenant_id=%s AND source_revision='revision-1'",
                (tenant["id"],),
            ).fetchone()
            self.assertIsNotNone(old_fact["system_to"])
            close_event = connection.execute(
                "SELECT operation FROM projection_outbox WHERE tenant_id=%s AND operation='CLOSE'",
                (tenant["id"],),
            ).fetchone()
            self.assertEqual(close_event["operation"], "CLOSE")
        finally:
            connection.rollback()
            connection.close()


def _result(
    *,
    tenant_key: str,
    repository_key: str,
    run_id: str,
    revision: str,
    extractor_version: str,
    include_fact: bool,
) -> dict:
    facts = []
    if include_fact:
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(repository_key, revision, "lodash"),
            "tenant_key": tenant_key,
            "subject": {
                "namespace": "ENTERPRISE",
                "type": "Repository",
                "key": repository_key,
                "name": "scanner-test",
            },
            "predicate": "DEPENDS_ON",
            "object_entity": {
                "namespace": "TECHNOLOGY",
                "type": "PackageVersion",
                "key": "pkg:npm/lodash@4.17.21",
                "name": "lodash 4.17.21",
            },
            "assertion_class": "DECLARED",
            "confidence": 1,
            "observed_at": "2026-08-19T14:00:00Z",
            "source_revision": revision,
            "extractor": {
                "key": "repository-dependency-usage",
                "version": extractor_version,
            },
            "properties": {
                "ecosystem": "npm",
                "scope": "runtime",
                "direct": True,
                "requested_spec": "^4.17.0",
                "resolved_version": "4.17.21",
                "registry_resolution": {
                    "origin": "https://registry.npmjs.org/",
                    "source": "LOCKFILE",
                    "scope": None,
                    "config_path": None,
                    "custom_registry": False,
                    "lockfile_behavior": "CONFIGURED_DEFAULT",
                    "visibility": "PUBLIC",
                },
                "artifact": {
                    "resolved_uri": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                    "integrity": "sha512-example",
                },
                "usage": {
                    "declared": True,
                    "resolved": True,
                    "referenced": True,
                    "reference_count": 1,
                    "referenced_symbols": ["debounce"],
                    "static_reachability": "OBSERVED",
                    "runtime_observed": "UNKNOWN",
                    "source_files_scanned": 1,
                    "limitations": ["no runtime trace was supplied"],
                },
            },
            "evidence": [{
                "type": "MANIFEST",
                "source_artifact": {
                    "key": f"{repository_key}:package.json",
                    "type": "REPOSITORY_FILE",
                    "revision": revision,
                    "content_hash": "sha256:" + "b" * 64,
                    "uri": f"{_snapshot_uri()}#path=files/package.json",
                },
                "locator": {"path": "package.json", "json_pointer": "/dependencies/lodash"},
            }],
        })
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(repository_key, revision, "debounceRequest"),
            "tenant_key": tenant_key,
            "subject": {
                "namespace": "ENTERPRISE", "type": "Repository",
                "key": repository_key, "name": "scanner-test",
            },
            "predicate": "HAS_PROPERTY",
            "object_value": {
                "record_kind": "code_implementation_summary",
                "language": "javascript", "symbol_kind": "FUNCTION",
                "qualified_name": "debounceRequest", "path": "src/client.ts",
                "line_start": 4, "line_end": 9,
                "structural_fingerprint": "sha256:" + "c" * 64,
                "semantic_tokens": ["debounce", "request"],
                "dependency_keys": ["pkg:npm/lodash"],
                "covering_tests": ["src/client.test.ts"],
                "dynamic_signals": [],
                "touchpoints": [{"kind": "BUILD", "path": "package.json"}],
                "vendored": False,
            },
            "assertion_class": "OBSERVED", "confidence": 0.95,
            "observed_at": "2026-08-19T14:00:00Z", "source_revision": revision,
            "extractor": {"key": "repository-dependency-usage", "version": extractor_version},
            "properties": {"analysis_kind": "CODE_IMPLEMENTATION_SUMMARY"},
            "evidence": [{
                "type": "SOURCE_STRUCTURE",
                "source_artifact": {
                    "key": f"{repository_key}:src/client.ts", "type": "REPOSITORY_FILE",
                    "revision": revision, "content_hash": "sha256:" + "d" * 64,
                    "uri": f"{_snapshot_uri()}#path=files/src/client.ts",
                },
                "locator": {"path": "src/client.ts", "line_start": 4, "line_end": 9},
            }],
        })
    return {
        "scanner_contract_version": "1.0.0",
        "run_id": run_id,
        "source_revision": revision,
        "extractor": {
            "key": "repository-dependency-usage",
            "version": extractor_version,
        },
        "completeness": "COMPLETE",
        "facts": facts,
        "stats": {
            "files_seen": 1,
            "files_scanned": 1,
            "facts_emitted": len(facts),
            "bytes_read": 100,
            "duration_ms": 1,
        },
        "diagnostics": [],
    }


def _snapshot_uri() -> str:
    return (
        "stackgraph-evidence://local/tenants/"
        f"{'e' * 64}/sha256/{'f' * 64}"
    )


def _raw_observation(tenant_key: str, repository_key: str, revision: str) -> dict:
    return {
        "observation_contract_version": "1.0.0",
        "idempotency_key": sha256_key(tenant_key, repository_key, revision, "raw"),
        "tenant_key": tenant_key,
        "source": {
            "key": "github-repository",
            "kind": "GITHUB",
            "adapter_version": "1.0.0",
            "schema_version": "2022-11-28",
        },
        "target_key": repository_key,
        "source_revision": revision,
        "observed_at": "2026-08-19T14:00:00Z",
        "request": {"uri": "https://api.github.com/repos/acme/scanner-test"},
        "content": {
            "hash": "sha256:" + "f" * 64,
            "media_type": "application/vnd.stackgraph.repository-snapshot+tar",
            "size_bytes": 4096,
            "blob_uri": _snapshot_uri(),
        },
    }


if __name__ == "__main__":
    unittest.main()

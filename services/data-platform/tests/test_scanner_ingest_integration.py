from __future__ import annotations

import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from stackgraph_data.catalog import sha256_key
from stackgraph_data.scanner_ingest import (
    persist_api_surface_connection,
    persist_scanner_result_connection,
)


DATABASE_URL = os.environ.get("STACKGRAPH_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "STACKGRAPH_TEST_DATABASE_URL is not configured")
class ScannerPersistenceIntegrationTests(unittest.TestCase):
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

            persisted = persist_scanner_result_connection(
                connection,
                first,
                target_id=target["id"],
                run_id=first_run["id"],
            )
            replay = persist_scanner_result_connection(
                connection,
                first,
                target_id=target["id"],
                run_id=first_run["id"],
            )

            self.assertEqual(persisted.fact_count, 1)
            self.assertEqual(persisted.usage_summary_count, 1)
            self.assertTrue(replay.replayed)
            usage = connection.execute(
                "SELECT referenced,static_reachability FROM dependency_usage_summary"
            ).fetchone()
            self.assertEqual(usage, {"referenced": True, "static_reachability": "OBSERVED"})
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
                },
                "locator": {"path": "package.json", "json_pointer": "/dependencies/lodash"},
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


if __name__ == "__main__":
    unittest.main()

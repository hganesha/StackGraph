from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_ai.capability_worker import analyze_repository
from stackgraph_ai.modernization_worker import analyze_modernization, work_jobs


DATABASE_URL = os.getenv("STACKGRAPH_TEST_DATABASE_URL")
CATALOG = Path(__file__).resolve().parents[1] / "capabilities"
ALTERNATIVES = Path(__file__).resolve().parents[1] / "alternatives" / "default.json"


@unittest.skipUnless(DATABASE_URL, "STACKGRAPH_TEST_DATABASE_URL is not configured")
class CapabilityPersistenceIntegrationTests(unittest.TestCase):
    def test_curated_analysis_persists_and_replays_duplicate_candidate(self) -> None:
        tenant_key = f"capability-test-{uuid4()}"
        repository_key = f"github:repo:{uuid4()}"
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Capability test') RETURNING id",
                (tenant_key,),
            ).fetchone()
            source = connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind)
                VALUES (%s,%s,'GITHUB') RETURNING id
                """,
                (tenant["id"], f"capability-test-{uuid4()}"),
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
                INSERT INTO ingest_run(tenant_id,ingest_target_id,trigger_kind,status,requested_source_revision)
                VALUES (%s,%s,'MANUAL','SUCCEEDED','revision-1') RETURNING id
                """,
                (tenant["id"], target["id"]),
            ).fetchone()
            snapshot = connection.execute(
                """
                INSERT INTO source_snapshot(
                  tenant_id,ingest_run_id,ingest_target_id,source_revision,
                  extractor_key,extractor_version,completeness,status,observed_at,stats
                ) VALUES (%s,%s,%s,'revision-1','repository-dependency-usage','1.0.0',
                          'COMPLETE','PUBLISHED',now(),'{}') RETURNING id
                """,
                (tenant["id"], run["id"], target["id"]),
            ).fetchone()
            repository = connection.execute(
                """
                INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties)
                VALUES (%s,'ENTERPRISE','Repository',%s,'Capability repo','{}') RETURNING id
                """,
                (tenant["id"], repository_key),
            ).fetchone()
            fingerprint_seed = uuid4().int
            for index, package in enumerate(("axios", "undici"), 1):
                dependency = connection.execute(
                    """
                    INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties)
                    VALUES (NULL,'TECHNOLOGY','PackageVersion',%s,%s,'{}')
                    ON CONFLICT(tenant_id,namespace,entity_type,canonical_key)
                    DO UPDATE SET name=EXCLUDED.name RETURNING id
                    """,
                    (f"pkg:npm/{package}@1.0.0", package),
                ).fetchone()
                fact = connection.execute(
                    """
                    INSERT INTO fact_assertion(
                      tenant_id,source_snapshot_id,subject_entity_id,predicate,object_entity_id,
                      assertion_class,confidence,logical_key,idempotency_key,source_revision,
                      extractor_key,extractor_version,properties,observed_at
                    ) VALUES (%s,%s,%s,'DEPENDS_ON',%s,'DECLARED',1,%s,%s,'revision-1',
                              'repository-dependency-usage','1.0.0',%s,now()) RETURNING id
                    """,
                    (
                        tenant["id"], snapshot["id"], repository["id"], dependency["id"],
                        f"sha256:{(fingerprint_seed + index + 30):064x}",
                        f"sha256:{(fingerprint_seed + index):064x}",
                        Jsonb({"ecosystem": "npm"}),
                    ),
                ).fetchone()
                artifact = connection.execute(
                    """
                    INSERT INTO source_artifact(
                      tenant_id,source_system_id,external_key,artifact_type,source_revision,
                      content_hash,metadata,observed_at
                    ) VALUES (%s,%s,%s,'REPOSITORY_FILE','revision-1',%s,'{}',now()) RETURNING id
                    """,
                    (
                        tenant["id"], source["id"], f"package-{index}.json",
                        f"sha256:{(fingerprint_seed + index + 10):064x}",
                    ),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO evidence(
                      tenant_id,fact_assertion_id,source_artifact_id,evidence_type,locator,metadata,observed_at
                    ) VALUES (%s,%s,%s,'MANIFEST',%s,'{}',now())
                    """,
                    (tenant["id"], fact["id"], artifact["id"], Jsonb({"path": "package.json"})),
                )
                connection.execute(
                    """
                    INSERT INTO dependency_usage_summary(
                      tenant_id,source_snapshot_id,dependency_fact_assertion_id,declared,resolved,
                      referenced,static_reachability,runtime_observed,reference_count,
                      referenced_symbols,source_files_scanned,limitations,analysis_fingerprint
                    ) VALUES (%s,%s,%s,true,true,true,'OBSERVED','UNKNOWN',1,%s,1,'[]',%s)
                    """,
                    (
                        tenant["id"], snapshot["id"], fact["id"], Jsonb(["get"]),
                        f"sha256:{(fingerprint_seed + index + 20):064x}",
                    ),
                )

        first = asyncio.run(analyze_repository(
            DATABASE_URL,
            tenant_id=tenant["id"],
            repository_id=repository["id"],
            catalog_dir=CATALOG,
        ))
        second = asyncio.run(analyze_repository(
            DATABASE_URL,
            tenant_id=tenant["id"],
            repository_id=repository["id"],
            catalog_dir=CATALOG,
        ))

        self.assertEqual(first.curated_inferences, 2)
        self.assertEqual(first.duplicate_candidates, 1)
        self.assertEqual(second.replayed_inferences, 2)
        self.assertEqual(second.duplicate_candidates, 0)

        modernization = analyze_modernization(
            DATABASE_URL,
            tenant_id=tenant["id"],
            repository_id=repository["id"],
            source_revision="revision-1",
            alternatives_path=ALTERNATIVES,
        )
        replay = analyze_modernization(
            DATABASE_URL,
            tenant_id=tenant["id"],
            repository_id=repository["id"],
            source_revision="revision-1",
            alternatives_path=ALTERNATIVES,
        )

        self.assertEqual(modernization.candidates, 1)
        self.assertEqual(modernization.recommendations, 1)
        self.assertEqual(replay.replayed_candidates, 1)
        self.assertEqual(replay.replayed_recommendations, 1)
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            recommendation = connection.execute(
                """
                SELECT action,estimated_effort,affected_call_sites,array_length(supporting_fact_ids,1) evidence_count
                FROM modernization_recommendation
                WHERE tenant_id=%s AND repository_entity_id=%s AND stale_at IS NULL
                """,
                (tenant["id"], repository["id"]),
            ).fetchone()
        self.assertEqual(recommendation["action"], "CONSOLIDATE")
        self.assertEqual(recommendation["estimated_effort"], "LOW")
        self.assertEqual(recommendation["affected_call_sites"], 1)
        self.assertEqual(recommendation["evidence_count"], 2)

        with psycopg.connect(DATABASE_URL) as connection:
            job = connection.execute(
                """
                INSERT INTO intelligence_job(
                  tenant_id,repository_entity_id,source_snapshot_id,source_revision,job_kind
                ) VALUES (%s,%s,%s,'revision-1','REPOSITORY_MODERNIZATION') RETURNING id
                """,
                (tenant["id"], repository["id"], snapshot["id"]),
            ).fetchone()
        worked = work_jobs(
            DATABASE_URL,
            capability_catalog_dir=CATALOG,
            alternatives_path=ALTERNATIVES,
            worker_id="integration-test",
            max_jobs=1,
        )
        self.assertEqual(worked.succeeded, 1)
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            completed = connection.execute(
                "SELECT status,attempt FROM intelligence_job WHERE id=%s",
                (job[0],),
            ).fetchone()
        self.assertEqual(completed, {"status": "SUCCEEDED", "attempt": 1})


if __name__ == "__main__":
    unittest.main()

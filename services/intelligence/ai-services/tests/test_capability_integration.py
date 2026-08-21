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
from stackgraph_ai.ecosystem_admission import evaluate_and_record
from stackgraph_ai.modernization_worker import analyze_modernization, enqueue_reanalysis, work_jobs


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

            structural_fingerprint = f"sha256:{(fingerprint_seed + 90):064x}"
            for index, path in enumerate(("src/http_primary.py", "src/http_legacy.py"), 1):
                fact = connection.execute(
                    """
                    INSERT INTO fact_assertion(
                      tenant_id,source_snapshot_id,subject_entity_id,predicate,object_value,
                      assertion_class,confidence,logical_key,idempotency_key,source_revision,
                      extractor_key,extractor_version,properties,observed_at
                    ) VALUES (%s,%s,%s,'HAS_PROPERTY',%s,'OBSERVED',0.92,%s,%s,'revision-1',
                              'repository-dependency-usage','1.1.0',%s,now()) RETURNING id
                    """,
                    (
                        tenant["id"], snapshot["id"], repository["id"],
                        Jsonb({"record_kind": "code_implementation_summary"}),
                        f"sha256:{(fingerprint_seed + index + 100):064x}",
                        f"sha256:{(fingerprint_seed + index + 110):064x}",
                        Jsonb({"record_kind": "code_implementation_summary"}),
                    ),
                ).fetchone()
                code_artifact = connection.execute(
                    """
                    INSERT INTO source_artifact(
                      tenant_id,source_system_id,external_key,artifact_type,source_revision,
                      content_hash,metadata,observed_at
                    ) VALUES (%s,%s,%s,'REPOSITORY_FILE','revision-1',%s,'{}',now()) RETURNING id
                    """,
                    (
                        tenant["id"], source["id"], path,
                        f"sha256:{(fingerprint_seed + index + 120):064x}",
                    ),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO evidence(
                      tenant_id,fact_assertion_id,source_artifact_id,evidence_type,
                      locator,metadata,observed_at
                    ) VALUES (%s,%s,%s,'SOURCE_LOCATION',%s,'{}',now())
                    """,
                    (
                        tenant["id"], fact["id"], code_artifact["id"],
                        Jsonb({"path": path, "line_start": 10, "line_end": 20}),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO code_implementation_summary(
                      tenant_id,source_snapshot_id,repository_entity_id,fact_assertion_id,
                      source_revision,language,symbol_kind,qualified_name,path,line_start,line_end,
                      structural_fingerprint,semantic_tokens,dependency_keys,covering_tests,
                      dynamic_signals,touchpoints,vendored,completeness,limitations
                    ) VALUES (%s,%s,%s,%s,'revision-1','python','FUNCTION',%s,%s,10,20,%s,
                              %s,%s,%s,%s,%s,false,'COMPLETE',%s)
                    """,
                    (
                        tenant["id"], snapshot["id"], repository["id"], fact["id"],
                        f"http_client_{index}", path, structural_fingerprint,
                        ["http", "client", "request"], ["pkg:pypi/requests@2.0.0"],
                        ["tests/test_http.py"] if index == 1 else [],
                        ["REFLECTION"] if index == 2 else [],
                        Jsonb([{"kind": "BUILD", "path": "pyproject.toml"}]),
                        Jsonb(["Runtime equivalence is not proven."] if index == 2 else []),
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

        self.assertEqual(modernization.candidates, 2)
        self.assertEqual(modernization.recommendations, 2)
        self.assertEqual(replay.replayed_candidates, 2)
        self.assertEqual(replay.replayed_recommendations, 2)
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            recommendation = connection.execute(
                """
                SELECT recommendation.action,recommendation.estimated_effort,
                       recommendation.affected_call_sites,
                       array_length(recommendation.supporting_fact_ids,1) evidence_count
                FROM modernization_recommendation recommendation
                JOIN modernization_candidate candidate
                  ON candidate.id=recommendation.modernization_candidate_id
                WHERE recommendation.tenant_id=%s AND recommendation.repository_entity_id=%s
                  AND recommendation.stale_at IS NULL
                  AND candidate.candidate_kind='DEPENDENCY_CONSOLIDATION'
                """,
                (tenant["id"], repository["id"]),
            ).fetchone()
            structural = connection.execute(
                """
                SELECT candidate.source_code_unit_ids,recommendation.action,
                       impact.affected_call_sites,impact.uncovered_call_sites,
                       impact.dynamic_signals,impact.build_touchpoints,
                       evaluation.eligible,evaluation.behavior_fit
                FROM modernization_candidate candidate
                JOIN modernization_recommendation recommendation
                  ON recommendation.modernization_candidate_id=candidate.id
                JOIN modernization_impact impact
                  ON impact.modernization_candidate_id=candidate.id
                JOIN modernization_option option
                  ON option.id=recommendation.selected_option_id
                JOIN modernization_option_evaluation evaluation
                  ON evaluation.modernization_option_id=option.id
                WHERE candidate.tenant_id=%s AND candidate.repository_entity_id=%s
                  AND candidate.candidate_kind='INTERNAL_DUPLICATION'
                  AND candidate.stale_at IS NULL
                """,
                (tenant["id"], repository["id"]),
            ).fetchone()
        self.assertEqual(recommendation["action"], "CONSOLIDATE")
        self.assertEqual(recommendation["estimated_effort"], "LOW")
        self.assertEqual(recommendation["affected_call_sites"], 1)
        self.assertEqual(recommendation["evidence_count"], 2)
        self.assertEqual(len(structural["source_code_unit_ids"]), 2)
        self.assertEqual(structural["action"], "REFACTOR")
        self.assertEqual(structural["affected_call_sites"], 2)
        self.assertEqual(structural["uncovered_call_sites"], 1)
        self.assertEqual(structural["dynamic_signals"], ["REFLECTION"])
        self.assertEqual(structural["build_touchpoints"], [{"kind": "BUILD", "path": "pyproject.toml"}])
        self.assertTrue(structural["eligible"])
        self.assertEqual(structural["behavior_fit"], "PASS")

        with psycopg.connect(DATABASE_URL) as connection:
            job = connection.execute(
                """
                INSERT INTO intelligence_job(
                  tenant_id,repository_entity_id,source_snapshot_id,source_revision,job_kind,
                  available_at
                ) VALUES (%s,%s,%s,'revision-1','REPOSITORY_MODERNIZATION',
                          TIMESTAMPTZ '2000-01-01 00:00:00+00') RETURNING id
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

        first_job, created, configuration_fingerprint = enqueue_reanalysis(
            DATABASE_URL, tenant_id=tenant["id"], repository_id=repository["id"],
            capability_catalog_dir=CATALOG, alternatives_path=ALTERNATIVES,
        )
        replay_job, replay_created, replay_fingerprint = enqueue_reanalysis(
            DATABASE_URL, tenant_id=tenant["id"], repository_id=repository["id"],
            capability_catalog_dir=CATALOG, alternatives_path=ALTERNATIVES,
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first_job, replay_job)
        self.assertEqual(configuration_fingerprint, replay_fingerprint)
        self.assertRegex(configuration_fingerprint, r"^sha256:[a-f0-9]{64}$")

        with psycopg.connect(DATABASE_URL) as connection:
            policy_id = connection.execute(
                """
                INSERT INTO modernization_policy(
                  tenant_id,policy_key,version,status,runtime_versions,allowed_licenses,
                  allowed_security_statuses,required_policy_tags,content_hash,created_by
                ) VALUES (%s,'production','1','ACTIVE',%s,%s,%s,%s,%s,'integration-test')
                RETURNING id
                """,
                (
                    tenant["id"], Jsonb({"node": "20.11.0"}), ["MIT", "RUNTIME"],
                    ["CLEAR"], ["runtime-native"], "sha256:" + "a" * 64,
                ),
            ).fetchone()[0]
        policy_job, policy_created, policy_fingerprint = enqueue_reanalysis(
            DATABASE_URL, tenant_id=tenant["id"], repository_id=repository["id"],
            capability_catalog_dir=CATALOG, alternatives_path=ALTERNATIVES,
        )
        self.assertTrue(policy_created)
        self.assertNotEqual(policy_job, first_job)
        self.assertNotEqual(policy_fingerprint, configuration_fingerprint)

        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                UPDATE modernization_policy
                SET allowed_security_statuses=%s,updated_at=now() WHERE id=%s
                """,
                (["CLEAR", "WARN"], policy_id),
            )
        changed_job, changed_created, changed_fingerprint = enqueue_reanalysis(
            DATABASE_URL, tenant_id=tenant["id"], repository_id=repository["id"],
            capability_catalog_dir=CATALOG, alternatives_path=ALTERNATIVES,
        )
        self.assertTrue(changed_created)
        self.assertNotEqual(changed_job, policy_job)
        self.assertNotEqual(changed_fingerprint, policy_fingerprint)

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            capability = connection.execute(
                """
                SELECT capability_definition_id
                FROM capability_inference
                WHERE tenant_id=%s AND repository_entity_id=%s AND stale_at IS NULL
                ORDER BY capability_definition_id LIMIT 1
                """,
                (tenant["id"], repository["id"]),
            ).fetchone()
            component = connection.execute(
                """
                INSERT INTO entity(
                  tenant_id,namespace,entity_type,canonical_key,name,properties
                ) VALUES (%s,'ENTERPRISE','Service',%s,'Approved HTTP component','{}')
                RETURNING id
                """,
                (tenant["id"], f"internal:http:{uuid4()}"),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO modernization_internal_component(
                  tenant_id,component_entity_id,capability_definition_id,
                  component_key,version,status,api_symbols,runtime_constraints,
                  behavior_claims,license,security_status,policy_tags,
                  supporting_fact_ids,review_state,owner,governed_by,governed_at,
                  catalog_fingerprint
                ) VALUES (%s,%s,%s,'internal:http-client','1.0.0','APPROVED',%s,%s,
                          %s,'MIT','CLEAR',%s,%s,'APPROVED','platform-team',
                          'integration-test',now(),%s)
                """,
                (
                    tenant["id"], component["id"], capability["capability_definition_id"],
                    ["get"], Jsonb({"node": ">=18"}), Jsonb([{"verified": True}]),
                    ["runtime-native"], [fact["id"]], "sha256:" + "b" * 64,
                ),
            )
        component_job, component_created, component_fingerprint = enqueue_reanalysis(
            DATABASE_URL, tenant_id=tenant["id"], repository_id=repository["id"],
            capability_catalog_dir=CATALOG, alternatives_path=ALTERNATIVES,
        )
        self.assertTrue(component_created)
        self.assertNotEqual(component_job, changed_job)
        self.assertNotEqual(component_fingerprint, changed_fingerprint)

        admission = evaluate_and_record(
            DATABASE_URL, tenant_id=tenant["id"], ecosystem="PYPI",
            actor_key="integration-test", minimum_repositories=1,
            minimum_dependency_share=0.01,
        )
        self.assertFalse(admission.admitted)
        self.assertEqual(admission.observed_repositories, 0)
        self.assertIn("calibration promotion gate has not passed", admission.reasons)


if __name__ == "__main__":
    unittest.main()

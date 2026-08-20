from __future__ import annotations

import psycopg


TENANT_ID = "00000000-0000-4000-8000-000000008001"
APPLICATION_ID = "00000000-0000-4000-8000-000000000201"
CAPABILITY_ID = "00000000-0000-4000-8000-000000000202"
REPOSITORY_ID = "00000000-0000-4000-8000-000000000203"
PACKAGE_ID = "00000000-0000-4000-8000-000000000204"
OSS_PROJECT_ID = "00000000-0000-4000-8000-000000000206"
SERVICE_ID = "00000000-0000-4000-8000-000000000207"
RUNTIME_ID = "00000000-0000-4000-8000-000000000208"
DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000209"
DEPENDENCY_FACT_ID = "00000000-0000-4000-8000-000000000301"


def _scope(connection: psycopg.Connection) -> None:
    connection.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_ID,))


def remove_golden_billing(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        _scope(connection)
        for statement in (
            "DELETE FROM ai_model_invocation WHERE tenant_id=%s",
            "DELETE FROM projection_outbox WHERE tenant_id=%s",
            "DELETE FROM recommendation_evidence WHERE tenant_id=%s",
            "DELETE FROM recommendation WHERE tenant_id=%s",
            "DELETE FROM assessment_input WHERE tenant_id=%s",
            "DELETE FROM assessment WHERE tenant_id=%s",
            "DELETE FROM dependency_resolution WHERE tenant_id=%s",
            "DELETE FROM evidence WHERE tenant_id=%s",
            "DELETE FROM fact_assertion WHERE tenant_id=%s",
            "DELETE FROM package_registry_identity WHERE tenant_id=%s",
            "DELETE FROM entity WHERE tenant_id=%s",
            "DELETE FROM source_artifact WHERE tenant_id=%s",
            "DELETE FROM source_snapshot WHERE tenant_id=%s",
            "DELETE FROM ingest_run WHERE tenant_id=%s",
            "DELETE FROM ingest_target WHERE tenant_id=%s",
            "DELETE FROM package_registry WHERE tenant_id=%s",
            "DELETE FROM source_system WHERE tenant_id=%s",
            "DELETE FROM tenant WHERE id=%s",
        ):
            connection.execute(statement, (TENANT_ID,))


def install_golden_billing(database_url: str) -> None:
    remove_golden_billing(database_url)
    with psycopg.connect(database_url) as connection:
        _scope(connection)
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'golden-billing','Golden Billing estate')",
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO source_system(id,tenant_id,source_key,kind,base_uri) VALUES
              ('00000000-0000-4000-8000-000000007001',%s,'github:repo:123','GITHUB','https://github.com/acme/billing-svc'),
              ('00000000-0000-4000-8000-000000007002',%s,'npm-public','PACKAGE_REGISTRY','https://registry.npmjs.org/')
            """,
            (TENANT_ID, TENANT_ID),
        )
        connection.execute(
            """
            INSERT INTO package_registry(
              id,tenant_id,source_system_id,registry_key,origin_uri,normalized_origin_uri,
              ecosystem,visibility,auth_mode
            ) VALUES (
              '00000000-0000-4000-8000-000000007005',%s,
              '00000000-0000-4000-8000-000000007002','npm-public',
              'https://registry.npmjs.org/','https://registry.npmjs.org/','NPM','PUBLIC','NONE'
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO ingest_target(
              id,tenant_id,source_system_id,target_kind,target_key,last_success_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007101',%s,
              '00000000-0000-4000-8000-000000007001','GITHUB_REPOSITORY',
              'github:repo:123',now()
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO ingest_run(
              id,tenant_id,ingest_target_id,trigger_kind,requested_source_revision,status,
              completeness,started_at,completed_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007102',%s,
              '00000000-0000-4000-8000-000000007101','MANUAL',
              '7f83b1657ff1fc53b92dc18148a1d65dfa135014','SUCCEEDED','COMPLETE',now(),now()
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO source_snapshot(
              id,tenant_id,ingest_run_id,ingest_target_id,source_revision,extractor_key,
              extractor_version,completeness,status,observed_at,published_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007103',%s,
              '00000000-0000-4000-8000-000000007102',
              '00000000-0000-4000-8000-000000007101',
              '7f83b1657ff1fc53b92dc18148a1d65dfa135014','npm-lock','1.0.0',
              'COMPLETE','PUBLISHED',now(),now()
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO source_artifact(
              id,tenant_id,source_system_id,external_key,artifact_type,name,source_revision,observed_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007104',%s,
              '00000000-0000-4000-8000-000000007001','package-lock.json','LOCKFILE',
              'package-lock.json','7f83b1657ff1fc53b92dc18148a1d65dfa135014',now()
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO entity(
              id,tenant_id,namespace,entity_type,canonical_key,name,properties,last_seen_at
            ) VALUES
              (%s,%s,'ENTERPRISE','Application','application:billing-api','Billing API',
               '{"tier":"TIER_1","summary":"A tier-1 service with one runtime upgrade opportunity."}',now()),
              (%s,%s,'BUSINESS','BusinessCapability','capability:billing','Billing','{}',now()),
              (%s,%s,'ENTERPRISE','Repository','github:repo:123','billing-svc','{}',now()),
              (%s,%s,'TECHNOLOGY','PackageVersion','pkg:npm/axios@1.7.9','axios 1.7.9','{}',now()),
              (%s,%s,'OSS','OSSProject','oss:axios','Axios','{}',now()),
              (%s,%s,'ENTERPRISE','Service','service:billing','Billing Service','{}',now()),
              (%s,%s,'TECHNOLOGY','Runtime','runtime:node:16','Node.js 16',
               '{"domain_id":"runtime.node","support_status":"UNSUPPORTED"}',now()),
              (%s,%s,'DEPLOYMENT','ContainerImage','container:billing','billing:latest','{}',now())
            """,
            (
                APPLICATION_ID, TENANT_ID, CAPABILITY_ID, TENANT_ID,
                REPOSITORY_ID, TENANT_ID, PACKAGE_ID, TENANT_ID,
                OSS_PROJECT_ID, TENANT_ID, SERVICE_ID, TENANT_ID,
                RUNTIME_ID, TENANT_ID, DEPLOYMENT_ID, TENANT_ID,
            ),
        )
        connection.execute(
            """
            INSERT INTO package_registry_identity(
              id,tenant_id,entity_id,package_registry_id,package_name,package_version,purl,
              visibility,last_seen_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007106',%s,%s,
              '00000000-0000-4000-8000-000000007005','axios','1.7.9',
              'pkg:npm/axios@1.7.9','PUBLIC',now()
            )
            """,
            (TENANT_ID, PACKAGE_ID),
        )
        facts = (
            (DEPENDENCY_FACT_ID, REPOSITORY_ID, "DEPENDS_ON", PACKAGE_ID, "DECLARED", '{"scope":"runtime","direct":true}'),
            ("00000000-0000-4000-8000-000000000302", APPLICATION_ID, "IMPLEMENTED_BY", REPOSITORY_ID, "CURATED", "{}"),
            ("00000000-0000-4000-8000-000000000303", APPLICATION_ID, "ENABLED_BY", CAPABILITY_ID, "CURATED", "{}"),
            ("00000000-0000-4000-8000-000000000304", PACKAGE_ID, "PUBLISHED_BY", OSS_PROJECT_ID, "EXTERNAL_MEASURED", "{}"),
            ("00000000-0000-4000-8000-000000000305", REPOSITORY_ID, "RUNS_ON", RUNTIME_ID, "DECLARED", "{}"),
            ("00000000-0000-4000-8000-000000000306", APPLICATION_ID, "IMPLEMENTED_BY", SERVICE_ID, "CURATED", "{}"),
            ("00000000-0000-4000-8000-000000000307", SERVICE_ID, "DEPLOYED_AS", DEPLOYMENT_ID, "OBSERVED", "{}"),
        )
        for index, (fact_id, subject_id, predicate, object_id, assertion_class, properties) in enumerate(facts, 1):
            connection.execute(
                """
                INSERT INTO fact_assertion(
                  id,tenant_id,source_snapshot_id,subject_entity_id,predicate,object_entity_id,
                  assertion_class,confidence,logical_key,idempotency_key,source_revision,
                  extractor_key,extractor_version,properties,effective_from,observed_at
                ) VALUES (
                  %s,%s,'00000000-0000-4000-8000-000000007103',%s,%s,%s,%s,1,
                  'sha256:' || encode(digest(%s,'sha256'),'hex'),
                  'sha256:' || encode(digest(%s,'sha256'),'hex'),
                  '7f83b1657ff1fc53b92dc18148a1d65dfa135014','npm-lock','1.0.0',
                  %s::jsonb,now() - interval '1 minute',now()
                )
                """,
                (
                    fact_id, TENANT_ID, subject_id, predicate, object_id, assertion_class,
                    f"golden-logical-{index}", f"golden-idempotency-{index}", properties,
                ),
            )
            locator = (
                '{"path":"package-lock.json","json_pointer":"/packages/node_modules~1axios/version"}'
                if fact_id == DEPENDENCY_FACT_ID else '{"path":"stackgraph-golden.json"}'
            )
            connection.execute(
                """
                INSERT INTO evidence(
                  id,tenant_id,fact_assertion_id,source_artifact_id,evidence_type,locator,observed_at
                ) VALUES (
                  gen_random_uuid(),%s,%s,'00000000-0000-4000-8000-000000007104',
                  %s,%s::jsonb,now()
                )
                """,
                (TENANT_ID, fact_id, "LOCKFILE" if fact_id == DEPENDENCY_FACT_ID else "FIXTURE", locator),
            )
        connection.execute(
            """
            INSERT INTO dependency_resolution(
              id,tenant_id,fact_assertion_id,package_registry_id,resolution_source,
              requested_spec,resolved_version,custom_registry,lockfile_behavior,visibility,observed_at
            ) VALUES (
              '00000000-0000-4000-8000-000000007107',%s,%s,
              '00000000-0000-4000-8000-000000007005','LOCKFILE','^1.7.0','1.7.9',
              false,'CONFIGURED_DEFAULT','PUBLIC',now()
            )
            """,
            (TENANT_ID, DEPENDENCY_FACT_ID),
        )
        assessments = (
            ("00000000-0000-4000-8000-000000000205", APPLICATION_ID, "supportability", 64, None, 0.88, "supportability-v1", "The declared dependency is supported and current.", DEPENDENCY_FACT_ID),
            ("00000000-0000-4000-8000-000000000210", APPLICATION_ID, "priority", 81, None, 0.91, "priority-v1", "Billing is a Tier-1 application.", "00000000-0000-4000-8000-000000000303"),
            ("00000000-0000-4000-8000-000000000211", APPLICATION_ID, "viability", 64, None, 0.88, "viability-v1", "Node.js 16 is unsupported and requires an upgrade.", "00000000-0000-4000-8000-000000000305"),
            ("00000000-0000-4000-8000-000000000212", RUNTIME_ID, "supportability", None, "UNSUPPORTED", 0.96, "runtime-support-v1", "Node.js 16 is end of life.", "00000000-0000-4000-8000-000000000305"),
        )
        for assessment in assessments:
            assessment_id, subject_id, dimension, score, category, confidence, method, rationale, fact_id = assessment
            connection.execute(
                """
                INSERT INTO assessment(
                  id,tenant_id,subject_entity_id,assessment_type,dimension,score,
                  categorical_value,confidence,method,method_version,rationale
                ) VALUES (%s,%s,%s,'DETERMINISTIC',%s,%s,%s,%s,'RULE',%s,%s)
                """,
                (
                    assessment_id, TENANT_ID, subject_id, dimension, score, category,
                    confidence, method, rationale,
                ),
            )
            connection.execute(
                """
                INSERT INTO assessment_input(tenant_id,assessment_id,fact_assertion_id)
                VALUES (%s,%s,%s)
                """,
                (TENANT_ID, assessment_id, fact_id),
            )
        connection.execute(
            """
            INSERT INTO recommendation(
              id,tenant_id,subject_entity_id,action,title,rationale,confidence,method_version,
              estimated_effort,status,created_by
            ) VALUES (
              '00000000-0000-4000-8000-000000000215',%s,%s,'UPGRADE',
              'Upgrade Billing runtime','Node.js 16 is unsupported.',0.96,
              'runtime-modernization-v1','MEDIUM','PROPOSED','golden-fixture'
            )
            """,
            (TENANT_ID, APPLICATION_ID),
        )
        connection.execute(
            """
            INSERT INTO recommendation_evidence(tenant_id,recommendation_id,fact_assertion_id)
            VALUES (%s,'00000000-0000-4000-8000-000000000215',
                    '00000000-0000-4000-8000-000000000305')
            """,
            (TENANT_ID,),
        )

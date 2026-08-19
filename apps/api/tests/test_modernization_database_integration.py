import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import Settings
from app.main import create_app


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


def test_modernization_read_model_and_optimistic_review() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    with psycopg.connect(admin_database_url, row_factory=dict_row) as connection:
        tenant = connection.execute(
            "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Modernization API test') RETURNING id",
            (f"modernization-api-{uuid4()}",),
        ).fetchone()
        taxonomy = connection.execute(
            """
            INSERT INTO capability_taxonomy_version(
              tenant_id,taxonomy_key,version,status,name,description,content_hash,metadata,created_by
            ) VALUES (%s,%s,'test-1','ACTIVE','Test taxonomy','Test capabilities',%s,'{}','test')
            RETURNING id
            """,
            (tenant["id"], f"test.modernization.{uuid4()}", "sha256:" + "1" * 64),
        ).fetchone()
        capability = connection.execute(
            """
            INSERT INTO capability_definition(
              taxonomy_version_id,capability_key,name,description,aliases,metadata
            ) VALUES (%s,'http-client','HTTP Client','Issue HTTP requests','[]','{}') RETURNING id
            """,
            (taxonomy["id"],),
        ).fetchone()
        repository = connection.execute(
            """
            INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties)
            VALUES (%s,'ENTERPRISE','Repository',%s,'Modernization API repo','{}') RETURNING id
            """,
            (tenant["id"], f"github:repo:{uuid4()}"),
        ).fetchone()
        dependency_ids = []
        for package in ("axios", "undici"):
            dependency_ids.append(connection.execute(
                """
                INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties)
                VALUES (NULL,'TECHNOLOGY','PackageVersion',%s,%s,'{}') RETURNING id
                """,
                (f"pkg:npm/{package}@{uuid4()}", package),
            ).fetchone()["id"])
        facts = [uuid4(), uuid4()]
        candidate = connection.execute(
            """
            INSERT INTO modernization_candidate(
              tenant_id,repository_entity_id,source_revision,capability_definition_id,
              candidate_kind,subject_entity_ids,confidence,summary,supporting_fact_ids,
              source_locations,validation_gaps,analyzer_key,analyzer_version,
              input_fingerprint,analysis_fingerprint
            ) VALUES (%s,%s,'revision-1',%s,'DEPENDENCY_CONSOLIDATION',%s,0.95,
              'Two HTTP clients are referenced.',%s,%s,%s,'repository-modernization-intelligence',
              '1.0.0',%s,%s) RETURNING id
            """,
            (
                tenant["id"], repository["id"], capability["id"], dependency_ids, facts,
                Jsonb([{"path": "src/client.ts", "line_start": 8}]),
                Jsonb(["Validate retry behavior."]),
                "sha256:" + "2" * 64, "sha256:" + "3" * 64,
            ),
        ).fetchone()
        option = connection.execute(
            """
            INSERT INTO modernization_option(
              tenant_id,modernization_candidate_id,option_kind,canonical_key,name,target_entity_id,
              compatibility,rank,score,score_components,rationale,tradeoffs,disqualifiers,
              validation_gaps,supporting_fact_ids
            ) VALUES (%s,%s,'PACKAGE','pkg:npm/axios','axios',%s,'OBSERVED',1,0.9,%s,
              'Already observed.','[]','[]','[]',%s) RETURNING id
            """,
            (
                tenant["id"], candidate["id"], dependency_ids[0],
                Jsonb({"capability_fit": 0.99}), facts,
            ),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO modernization_option_evaluation(
              tenant_id,modernization_option_id,capability_fit,api_fit,behavior_fit,
              runtime_fit,license_fit,security_fit,policy_fit,eligible,evidence,
              disqualifiers,unknowns
            ) VALUES (%s,%s,'PASS','PASS','PASS','PASS','UNKNOWN','UNKNOWN','PASS',true,%s,'[]',%s)
            """,
            (
                tenant["id"], option["id"], Jsonb({"observed_in_repository": True}),
                Jsonb(["License and security status require policy validation."]),
            ),
        )
        connection.execute(
            """
            INSERT INTO modernization_impact(
              tenant_id,modernization_candidate_id,affected_call_sites,affected_files,
              covered_call_sites,uncovered_call_sites,affected_test_files,dynamic_signals,
              configuration_touchpoints,build_touchpoints,deployment_touchpoints,
              evidence_locations,confidence,effort_points,effort_model_version,limitations
            ) VALUES (%s,%s,2,1,1,1,%s,'{}','[]',%s,'[]',%s,0.72,6,'phase3-effort/v2',%s)
            """,
            (
                tenant["id"], candidate["id"], ["src/client.test.ts"],
                Jsonb([{"kind": "BUILD", "path": "package.json"}]),
                Jsonb([{"path": "src/client.ts", "line_start": 8}]),
                Jsonb(["One call site has no statically linked test."]),
            ),
        )
        recommendation = connection.execute(
            """
            INSERT INTO modernization_recommendation(
              tenant_id,repository_entity_id,modernization_candidate_id,selected_option_id,
              source_revision,action,objective,title,rationale,confidence,estimated_effort,
              affected_call_sites,affected_files,validation_gaps,migration_plan,rollback_plan,
              supporting_fact_ids,counter_signals,policy_version,input_fingerprint,analysis_fingerprint
            ) VALUES (%s,%s,%s,%s,'revision-1','CONSOLIDATE','DEPENDENCY_CONSOLIDATION',
              'Consolidate HTTP clients','Retain the most-used client.',0.9,'LOW',2,1,%s,%s,%s,%s,
              %s,'modernization-ranking/v1',%s,%s) RETURNING id
            """,
            (
                tenant["id"], repository["id"], candidate["id"], option["id"],
                Jsonb(["Validate retry behavior."]),
                Jsonb(["Replace affected call sites."]),
                Jsonb(["Restore the prior lockfile."]), facts,
                Jsonb(["Runtime use is unknown."]),
                "sha256:" + "4" * 64, "sha256:" + "5" * 64,
            ),
        ).fetchone()

    async def query_api():
        app = create_app(settings=Settings(
            environment="test", database_url=database_url, default_tenant_id=tenant["id"],
        ))
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as client:
                read = await client.get(
                    f"/api/v1/repositories/{repository['id']}/modernization-intelligence"
                )
                candidate_review = await client.post(
                    f"/api/v1/modernization-candidates/{candidate['id']}/review",
                    json={"decision": "CONFIRM", "rationale": "Structure verified.", "expected_version": 1},
                )
                review = await client.post(
                    f"/api/v1/modernization-recommendations/{recommendation['id']}/review",
                    json={"decision": "ACCEPT", "rationale": "Migration validated.", "expected_version": 1},
                )
                conflict = await client.post(
                    f"/api/v1/modernization-recommendations/{recommendation['id']}/review",
                    json={"decision": "REJECT", "rationale": "Stale decision.", "expected_version": 1},
                )
                outcome = await client.post(
                    f"/api/v1/modernization-recommendations/{recommendation['id']}/validation-outcomes",
                    json={
                        "validation_status": "SUCCEEDED", "actual_call_sites": 3,
                        "actual_files": 1, "actual_effort": "LOW",
                        "successful_checks": ["unit", "integration"],
                        "notes": "Migration validation passed.",
                    },
                )
                metrics = await client.get("/api/v1/intelligence/phase-3/metrics")
        other_tenant_app = create_app(settings=Settings(
            environment="test", database_url=database_url, default_tenant_id=uuid4(),
        ))
        async with other_tenant_app.router.lifespan_context(other_tenant_app):
            async with AsyncClient(
                transport=ASGITransport(app=other_tenant_app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as other_tenant_client:
                cross_tenant = await other_tenant_client.get(
                    f"/api/v1/repositories/{repository['id']}/modernization-intelligence"
                )
        return read, candidate_review, review, conflict, outcome, metrics, cross_tenant

    read, candidate_review, review, conflict, outcome, metrics, cross_tenant = asyncio.run(query_api())
    assert read.status_code == 200, read.text
    assert read.json()["candidates"][0]["recommendation"]["affected_call_sites"] == 2
    assert read.json()["candidates"][0]["options"][0]["canonical_key"] == "pkg:npm/axios"
    assert read.json()["candidates"][0]["options"][0]["eligibility"]["eligible"] is True
    assert read.json()["candidates"][0]["impact"]["covered_call_sites"] == 1
    assert candidate_review.status_code == 200
    assert candidate_review.json()["review_state"] == "CONFIRMED"
    assert review.status_code == 200
    assert review.json()["review_state"] == "ACCEPTED"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "VERSION_CONFLICT"
    assert outcome.status_code == 200
    assert metrics.status_code == 200
    assert metrics.json()["candidate_review_precision"] == 1.0
    assert metrics.json()["affected_call_site_mae"] == 1.0
    assert cross_tenant.status_code == 404

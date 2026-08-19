import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from psycopg.rows import dict_row

from app.config import Settings
from app.main import create_app


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


def test_capability_read_models_and_optimistic_review() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    with psycopg.connect(admin_database_url, row_factory=dict_row) as connection:
        tenant = connection.execute(
            "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Capability API test') RETURNING id",
            (f"capability-api-{uuid4()}",),
        ).fetchone()
        taxonomy = connection.execute(
            """
            INSERT INTO capability_taxonomy_version(
              tenant_id,taxonomy_key,version,status,name,description,
              content_hash,metadata,created_by
            ) VALUES (%s,'stackgraph.technical-capabilities','test-1','ACTIVE',
                      'Test taxonomy','Test capabilities',%s,'{}','test') RETURNING id
            """,
            (tenant["id"], "sha256:" + "a" * 64),
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
            VALUES (%s,'ENTERPRISE','Repository',%s,'Capability API repo','{}') RETURNING id
            """,
            (tenant["id"], f"github:repo:{uuid4()}"),
        ).fetchone()
        dependency = connection.execute(
            """
            INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties)
            VALUES (NULL,'TECHNOLOGY','PackageVersion',%s,'axios','{}') RETURNING id
            """,
            (f"pkg:npm/axios@{uuid4()}",),
        ).fetchone()
        inference = connection.execute(
            """
            INSERT INTO capability_inference(
              tenant_id,repository_entity_id,subject_entity_id,capability_definition_id,
              source_revision,assertion_class,confidence,confidence_band,
              supporting_fact_ids,counter_evidence_fact_ids,taxonomy_version_id,
              analyzer_key,analyzer_version,policy_version,input_fingerprint,
              analysis_fingerprint,rationale
            ) VALUES (%s,%s,%s,%s,'revision-1','CURATED',0.99,'HIGH',%s,'{}',%s,
                      'repository-capability-inference','1.0.0','capability-taxonomy/v1',
                      %s,%s,'Curated HTTP client mapping.') RETURNING id
            """,
            (
                tenant["id"], repository["id"], dependency["id"], capability["id"],
                [uuid4()], taxonomy["id"], "sha256:" + "b" * 64, "sha256:" + "c" * 64,
            ),
        ).fetchone()

    async def query_api():
        app = create_app(settings=Settings(
            environment="test",
            database_url=database_url,
            default_tenant_id=tenant["id"],
        ))
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as client:
                taxonomy_response = await client.get("/api/v1/capabilities/taxonomy")
                repository_response = await client.get(
                    f"/api/v1/repositories/{repository['id']}/capabilities"
                )
                review_response = await client.post(
                    f"/api/v1/capability-inferences/{inference['id']}/review",
                    json={
                        "decision": "CONFIRM",
                        "rationale": "Evidence verified.",
                        "expected_version": 1,
                    },
                )
                conflict_response = await client.post(
                    f"/api/v1/capability-inferences/{inference['id']}/review",
                    json={
                        "decision": "REJECT",
                        "rationale": "Stale review.",
                        "expected_version": 1,
                    },
                )
                return taxonomy_response, repository_response, review_response, conflict_response

    taxonomy_response, repository_response, review_response, conflict_response = asyncio.run(query_api())
    assert taxonomy_response.status_code == 200
    assert taxonomy_response.json()["version"] == "test-1"
    assert repository_response.status_code == 200
    assert repository_response.json()["inferences"][0]["capability"]["key"] == "http-client"
    assert review_response.status_code == 200
    assert review_response.json()["review_state"] == "CONFIRMED"
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "VERSION_CONFLICT"

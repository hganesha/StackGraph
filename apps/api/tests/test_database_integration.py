import asyncio
import os

import pytest
import psycopg
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.database import Database
from app.models import AskRequest
from app.read_models import ReadModelStore
from app.main import create_app


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


async def exercise_read_models() -> None:
    settings = Settings(database_url=os.environ["STACKGRAPH_TEST_DATABASE_URL"])
    database = Database(settings)
    await database.open()
    try:
        store = ReadModelStore(database)
        summary = await store.estate_summary(tenant_id=None, cursor=None, limit=10)
        modernization = await store.modernization(tenant_id=None, cursor=None, limit=10)
        answer = await store.ask(AskRequest(question="How many items are in the estate?"), tenant_id=None)

        assert summary.contract_version == "1.0.0"
        assert summary.counts.applications >= 0
        assert 0 <= summary.coverage.facts_with_evidence_ratio <= 1
        assert modernization.contract_version == "1.0.0"
        assert answer.result_kind == "TABLE"

        entity_row = await database.fetch_one(
            "SELECT id FROM entity WHERE namespace='TECHNOLOGY' AND entity_type='Technology' ORDER BY name LIMIT 1"
        )
        if entity_row:
            technology = await store.technology_detail(entity_row["id"], tenant_id=None)
            graph = await store.graph_neighborhood(
                entity_row["id"], tenant_id=None, depth=1, real_node_limit=10,
            )
            assert technology.technology.id == entity_row["id"]
            assert graph.center_id == entity_row["id"]
            assert len(graph.nodes) <= 10

        connected_entity = await database.fetch_one(
            """
            SELECT r.source_entity_id id
            FROM current_relationship r
            JOIN entity e ON e.id=r.source_entity_id
            WHERE e.namespace='TECHNOLOGY' AND e.entity_type='Technology'
            ORDER BY e.name,r.relationship_type,r.fact_assertion_id LIMIT 1
            """
        )
        if connected_entity:
            aggregate_graph = await store.graph_neighborhood(
                connected_entity["id"], tenant_id=None, depth=1, real_node_limit=1,
            )
            repeated_graph = await store.graph_neighborhood(
                connected_entity["id"], tenant_id=None, depth=1, real_node_limit=1,
            )
            real_nodes = [node for node in aggregate_graph.nodes if not node.aggregate]
            aggregate_nodes = [node for node in aggregate_graph.nodes if node.aggregate]
            aggregate_ids = {node.id for node in aggregate_nodes}

            assert aggregate_graph.truncated
            assert aggregate_graph.truncation_reason == "REAL_NODE_LIMIT"
            assert len(real_nodes) == 1
            assert aggregate_nodes
            assert len(aggregate_graph.nodes) <= 50
            assert sum(node.member_count or 0 for node in aggregate_nodes) >= 1
            assert any(
                edge.source in aggregate_ids or edge.target in aggregate_ids
                for edge in aggregate_graph.edges
            )
            assert [node.id for node in aggregate_graph.nodes] == [
                node.id for node in repeated_graph.nodes
            ]

        fact_row = await database.fetch_one("SELECT id FROM current_fact ORDER BY id LIMIT 1")
        if fact_row:
            evidence = await store.evidence_detail(fact_row["id"], tenant_id=None)
            assert evidence.fact_id == fact_row["id"]
            assert evidence.evidence
    finally:
        await database.close()


def test_read_models_query_live_schema() -> None:
    asyncio.run(exercise_read_models())


def test_http_api_queries_seeded_database() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        technology_id = connection.execute(
            """
            SELECT r.source_entity_id
            FROM current_relationship r JOIN entity e ON e.id=r.source_entity_id
            WHERE e.namespace='TECHNOLOGY' AND e.entity_type='Technology'
            ORDER BY e.name,r.relationship_type,r.fact_assertion_id LIMIT 1
            """
        ).fetchone()[0]
        fact_id = connection.execute("SELECT id FROM current_fact ORDER BY id LIMIT 1").fetchone()[0]
        technology_count = connection.execute(
            "SELECT count(*) FROM entity WHERE namespace='TECHNOLOGY' AND entity_type<>'Capability'"
        ).fetchone()[0]

    async def query_api():
        app = create_app(settings=Settings(environment="test", database_url=database_url))
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as client:
                return (
                    await client.get("/estate/summary"),
                    await client.get(f"/technologies/{technology_id}"),
                    await client.get(
                        "/graph/neighborhood",
                        params={"center_id": str(technology_id), "depth": 1, "real_node_limit": 1},
                    ),
                    await client.get(f"/facts/{fact_id}/evidence"),
                    await client.post("/ask", json={"question": "How many items are in the estate?"}),
                )

    summary, technology, graph, evidence, ask = asyncio.run(query_api())

    assert summary.status_code == 200
    assert summary.json()["counts"]["technologies"] == technology_count
    assert technology.status_code == 200
    assert graph.status_code == 200
    assert graph.json()["truncated"] is True
    assert any(node["aggregate"] for node in graph.json()["nodes"])
    assert all(
        "member_count" not in node
        for node in graph.json()["nodes"]
        if not node["aggregate"]
    )
    assert any(
        node.get("member_count", 0) >= 1
        for node in graph.json()["nodes"]
        if node["aggregate"]
    )
    assert evidence.status_code == 200
    assert ask.status_code == 200


def test_identity_review_is_atomic_and_audited() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    tenant_id = "00000000-0000-4000-8000-000000009001"
    left_id = "00000000-0000-4000-8000-000000009002"
    right_id = "00000000-0000-4000-8000-000000009003"
    assertion_id = "00000000-0000-4000-8000-000000009004"

    def configure_tenant(connection) -> None:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    with psycopg.connect(database_url) as connection:
        configure_tenant(connection)
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'api-integration-test','API integration test')",
            (tenant_id,),
        )
        connection.execute(
            """
            INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name) VALUES
              (%s,%s,'TECHNOLOGY','Package','test:left','Test left'),
              (%s,%s,'OSS','OSSProject','test:right','Test right')
            """,
            (left_id, tenant_id, right_id, tenant_id),
        )
        connection.execute(
            """
            INSERT INTO identity_assertion
              (id,tenant_id,left_entity_id,right_entity_id,method,method_version,confidence)
            VALUES (%s,%s,%s,%s,'TEST','1.0.0',0.75)
            """,
            (assertion_id, tenant_id, left_id, right_id),
        )

    try:
        async def review_api():
            app = create_app(settings=Settings(environment="test", database_url=database_url))
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://testserver",
                ) as client:
                    response = await client.post(
                        f"/identity-assertions/{assertion_id}/review",
                        headers={"X-StackGraph-Tenant-ID": tenant_id, "X-StackGraph-Actor": "integration-test"},
                        json={"decision": "CONFIRM", "rationale": "Verified test identity.", "expected_version": 1},
                    )
                    conflict = await client.post(
                        f"/identity-assertions/{assertion_id}/review",
                        headers={"X-StackGraph-Tenant-ID": tenant_id, "X-StackGraph-Actor": "integration-test"},
                        json={"decision": "REJECT", "rationale": "Stale review.", "expected_version": 1},
                    )
                    return response, conflict

        response, conflict = asyncio.run(review_api())

        assert response.status_code == 200
        assert response.json()["version"] == 2
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "VERSION_CONFLICT"
        with psycopg.connect(database_url) as connection:
            configure_tenant(connection)
            review = connection.execute(
                "SELECT actor_key,decision FROM identity_assertion_review WHERE identity_assertion_id=%s",
                (assertion_id,),
            ).fetchone()
            assert review == ("integration-test", "CONFIRM")
    finally:
        with psycopg.connect(database_url) as connection:
            configure_tenant(connection)
            connection.execute("DELETE FROM projection_outbox WHERE aggregate_id=%s", (assertion_id,))
            connection.execute("DELETE FROM identity_assertion_review WHERE identity_assertion_id=%s", (assertion_id,))
            connection.execute("DELETE FROM identity_assertion WHERE id=%s", (assertion_id,))
            connection.execute("DELETE FROM entity WHERE id IN (%s,%s)", (left_id, right_id))
            connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))

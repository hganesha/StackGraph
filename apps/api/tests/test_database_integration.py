import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
import psycopg
from psycopg.rows import dict_row
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.database import Database
from app.models import AskRequest
from app.read_models import ReadModelStore
from app.main import create_app
from stackgraph_ai.tenant_config import load_tenant_ai_settings
from tests.contract_support import ContractValidator
from tests.golden_billing import (
    APPLICATION_ID,
    CAPABILITY_ID,
    DEPENDENCY_FACT_ID,
    OSS_PROJECT_ID,
    PACKAGE_ID,
    REPOSITORY_ID,
    TENANT_ID,
    install_golden_billing,
    remove_golden_billing,
)


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


class DatabaseStubGitHubAppSetupClient:
    enabled = True

    def __init__(self) -> None:
        self.state = ""

    def installation_url(self, state: str) -> str:
        self.state = state
        return f"https://github.com/apps/stackgraph/installations/new?state={state}"

    async def verify_installation(self, *, code: str, installation_id: str):
        assert code == "database-oauth-code"
        return SimpleNamespace(
            installation_id=installation_id,
            account_login="acme-hosted",
            account_id=84,
            target_type="Organization",
            permissions=("contents:read", "metadata:read"),
        )


def test_tenant_code_policies_evaluate_primary_and_custom_functions() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    tenant_id = "00000000-0000-4000-8000-00000000c001"
    repository_id = "00000000-0000-4000-8000-00000000c002"
    custom_technology_id = "00000000-0000-4000-8000-00000000c003"
    other_tenant_id = "00000000-0000-4000-8000-00000000c004"

    def configure_tenant(connection) -> None:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    with psycopg.connect(admin_database_url, row_factory=dict_row) as connection:
        configure_tenant(connection)
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'code-policy-test','Code policy test')",
            (tenant_id,),
        )
        catalog = connection.execute(
            """
            SELECT id,canonical_key FROM entity
            WHERE canonical_key IN ('stackgraph:technology:zustand','stackgraph:technology:redux-toolkit')
            """
        ).fetchall()
        catalog_ids = {row["canonical_key"]: row["id"] for row in catalog}
        assert set(catalog_ids) == {
            "stackgraph:technology:zustand", "stackgraph:technology:redux-toolkit",
        }
        source_id = connection.execute(
            """
            INSERT INTO source_system(tenant_id,source_key,kind)
            VALUES (%s,'code-policy-test','OTHER') RETURNING id
            """,
            (tenant_id,),
        ).fetchone()["id"]
        artifact_id = connection.execute(
            """
            INSERT INTO source_artifact(
              tenant_id,source_system_id,external_key,artifact_type,name,
              source_revision,content_hash,observed_at
            ) VALUES (%s,%s,'code-policy-test','TEST','package.json','revision-1',%s,now())
            RETURNING id
            """,
            (tenant_id, source_id, "sha256:" + "a" * 64),
        ).fetchone()["id"]
        target_id = connection.execute(
            """
            INSERT INTO ingest_target(tenant_id,source_system_id,target_kind,target_key)
            VALUES (%s,%s,'REPOSITORY','github:repo:code-policy-test') RETURNING id
            """,
            (tenant_id, source_id),
        ).fetchone()["id"]
        run_id = connection.execute(
            """
            INSERT INTO ingest_run(
              tenant_id,ingest_target_id,trigger_kind,status,completeness,completed_at
            ) VALUES (%s,%s,'MANUAL','SUCCEEDED','COMPLETE',now()) RETURNING id
            """,
            (tenant_id, target_id),
        ).fetchone()["id"]
        snapshot_id = connection.execute(
            """
            INSERT INTO source_snapshot(
              tenant_id,ingest_run_id,ingest_target_id,source_revision,extractor_key,
              extractor_version,completeness,status,observed_at,published_at
            ) VALUES (%s,%s,%s,'revision-1','code-policy-test','1.0.0','COMPLETE','PUBLISHED',now(),now())
            RETURNING id
            """,
            (tenant_id, run_id, target_id),
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name,properties)
            VALUES
              (%s,%s,'ENTERPRISE','Repository','github:repo:code-policy-test','Policy repository','{}'),
              (%s,%s,'TECHNOLOGY','Technology','tenant:technology:legacy-ui-runtime','Legacy UI runtime','{}')
            """,
            (repository_id, tenant_id, custom_technology_id, tenant_id),
        )
        for index, technology_id in enumerate([
            catalog_ids["stackgraph:technology:redux-toolkit"], custom_technology_id,
        ], start=1):
            fact_id = connection.execute(
                """
                INSERT INTO fact_assertion(
                  tenant_id,source_snapshot_id,subject_entity_id,predicate,object_entity_id,
                  assertion_class,confidence,logical_key,idempotency_key,source_revision,
                  extractor_key,extractor_version,observed_at
                ) VALUES (%s,%s,%s,'DEPENDS_ON',%s,'DECLARED',1,%s,%s,'revision-1','code-policy-test','1.0.0',now())
                RETURNING id
                """,
                (
                    tenant_id, snapshot_id, repository_id, technology_id,
                    "sha256:" + str(index) * 64, "sha256:" + str(index + 2) * 64,
                ),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO evidence(
                  tenant_id,fact_assertion_id,source_artifact_id,evidence_type,locator,observed_at
                ) VALUES (%s,%s,%s,'TEST',%s::jsonb,now())
                """,
                (tenant_id, fact_id, artifact_id, '{"path":"package.json"}'),
            )
    with psycopg.connect(admin_database_url) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (other_tenant_id,))
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'code-policy-other','Code policy other')",
            (other_tenant_id,),
        )

    try:
        async def exercise():
            app = create_app(settings=Settings(
                environment="test", database_url=database_url,
                default_tenant_id=tenant_id, development_actor_key="code-policy-admin",
            ))
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://testserver",
                ) as client:
                    initial = await client.get("/admin/code-policies")
                    primary = await client.put(
                        "/admin/code-policies/functions/client-state-management",
                        json={
                            "source": "PRIMARY", "name": "Client state management",
                            "domain_key": "frontend",
                            "allowed_technology_ids": [str(catalog_ids["stackgraph:technology:zustand"])],
                            "prohibited_technology_ids": [str(catalog_ids["stackgraph:technology:redux-toolkit"])],
                        },
                    )
                    custom = await client.put(
                        "/admin/code-policies/functions/tenant-ui-runtime",
                        json={
                            "source": "CUSTOM", "name": "Tenant UI runtime",
                            "description": "Tenant-specific UI execution layer.", "domain_key": "frontend",
                            "allowed_technology_ids": [],
                            "prohibited_technology_ids": [custom_technology_id],
                        },
                    )
                    evaluated = await client.post("/admin/code-policies/evaluations")
                    stale = await client.put(
                        "/admin/code-policies/functions/client-state-management",
                        json={
                            "source": "PRIMARY", "name": "Client state management",
                            "domain_key": "frontend", "allowed_technology_ids": [],
                            "prohibited_technology_ids": [str(catalog_ids["stackgraph:technology:redux-toolkit"])],
                        },
                    )
                    return initial, primary, custom, evaluated, stale

        initial, primary, custom, evaluated, stale = asyncio.run(exercise())
        assert initial.status_code == 200
        assert any(item["function_key"] == "client-state-management" for item in initial.json()["functions"])
        assert primary.status_code == 200
        assert custom.status_code == 200
        body = evaluated.json()
        assert evaluated.status_code == 200, body
        assert body["summary"]["custom_functions"] == 1
        assert body["summary"]["misaligned_repositories"] == 1
        result = body["evaluations"][0]
        assert result["status"] == "MISALIGNED"
        assert {item["function_key"] for item in result["violations"]} == {
            "client-state-management", "tenant-ui-runtime",
        }
        assert all(item["fact_ids"] for item in result["violations"])
        assert stale.status_code == 200
        assert stale.json()["evaluations"][0]["status"] == "STALE"
        with psycopg.connect(database_url) as connection:
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (other_tenant_id,))
            assert connection.execute("SELECT count(*) FROM tenant_code_policy").fetchone()[0] == 0
            assert connection.execute(
                "SELECT count(*) FROM repository_code_policy_evaluation"
            ).fetchone()[0] == 0
    finally:
        with psycopg.connect(admin_database_url) as connection:
            configure_tenant(connection)
            connection.execute("DELETE FROM repository_code_policy_evaluation WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM tenant_code_policy WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM tenant_code_function WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM fact_assertion WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM entity WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM source_artifact WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM source_snapshot WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM ingest_run WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM ingest_target WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM source_system WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM admin_audit_log WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))
        with psycopg.connect(admin_database_url) as connection:
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (other_tenant_id,))
            connection.execute("DELETE FROM tenant WHERE id=%s", (other_tenant_id,))


async def exercise_read_models() -> None:
    settings = Settings(database_url=os.environ["STACKGRAPH_TEST_DATABASE_URL"])
    database = Database(settings)
    await database.open()
    try:
        store = ReadModelStore(database)
        summary = await store.estate_summary(tenant_id=None, cursor=None, limit=10)
        technology_summary = await store.estate_summary(
            tenant_id=None,
            cursor=None,
            limit=10,
            namespaces=["TECHNOLOGY", "OSS"],
        )
        modernization = await store.modernization(tenant_id=None, cursor=None, limit=10)
        answer = await store.ask(AskRequest(question="How many items are in the estate?"), tenant_id=None)

        assert summary.contract_version == "1.0.0"
        assert summary.counts.applications >= 0
        assert 0 <= summary.coverage.facts_with_evidence_ratio <= 1
        # A globally visible reference catalog is not itself a tenant estate.
        assert summary.counts.technologies == 0
        assert technology_summary.ranked_items == []
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

        package_row = await database.fetch_one(
            """
            SELECT pri.entity_id id
            FROM package_registry_identity pri
            JOIN entity e ON e.id=pri.entity_id
            WHERE e.namespace='TECHNOLOGY'
            ORDER BY pri.last_seen_at DESC NULLS LAST,pri.id
            LIMIT 1
            """
        )
        if package_row:
            package_detail = await store.technology_detail(package_row["id"], tenant_id=None)
            logical_sources = [
                (source.registry_key, source.origin.lower().rstrip("/"))
                for source in package_detail.registry_sources or []
            ]
            assert len(logical_sources) == len(set(logical_sources))

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
                responses = (
                    await client.get("/estate/summary"),
                    await client.get(f"/technologies/{technology_id}"),
                    await client.get(
                        "/graph/neighborhood",
                        params={"center_id": str(technology_id), "depth": 1, "real_node_limit": 1},
                    ),
                    await client.get(f"/facts/{fact_id}/evidence"),
                    await client.post("/ask", json={"question": "How many items are in the estate?"}),
                )
                return responses, app.state.read_models.graph_read_metrics.age_reads

    responses, age_reads = asyncio.run(query_api())
    summary, technology, graph, evidence, ask = responses

    assert summary.status_code == 200
    # The seeded global catalog remains queryable but does not inflate an unconnected estate.
    assert summary.json()["counts"]["technologies"] == 0
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
    assert age_reads >= 1


def test_age_and_sql_neighborhoods_have_canonical_parity() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT r.source_entity_id,r.target_entity_id,r.relationship_type
            FROM current_relationship r
            JOIN stackgraph."Relationship" projected
              ON trim(both '"' from ag_catalog.agtype_access_operator(
                   VARIADIC ARRAY[projected.properties,'"fact_id"'::ag_catalog.agtype]
                 )::text)::uuid=r.fact_assertion_id
            WHERE r.tenant_id IS NULL
            ORDER BY (
              SELECT count(*) FROM current_relationship peer
              WHERE peer.source_entity_id=r.source_entity_id
                AND peer.relationship_type=r.relationship_type
            ),r.fact_assertion_id
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    center_id, highlight_to, predicate = row

    async def compare_graphs():
        settings = Settings(database_url=database_url)
        database = Database(settings)
        await database.open()
        try:
            sql_store = ReadModelStore(database, graph_read_mode="sql")
            age_store = ReadModelStore(database, graph_read_mode="age")
            sql_graph = await sql_store.graph_neighborhood(
                center_id, tenant_id=None, depth=1, real_node_limit=50,
                predicates=[predicate], highlight_to=highlight_to,
            )
            age_graph = await age_store.graph_neighborhood(
                center_id, tenant_id=None, depth=1, real_node_limit=50,
                predicates=[predicate], highlight_to=highlight_to,
            )
            return sql_graph, age_graph, age_store.graph_read_metrics
        finally:
            await database.close()

    sql_graph, age_graph, metrics = asyncio.run(compare_graphs())

    assert metrics.age_reads == 1
    assert metrics.sql_reads == 0
    assert {node.id for node in age_graph.nodes} == {node.id for node in sql_graph.nodes}
    assert {edge.id for edge in age_graph.edges} == {edge.id for edge in sql_graph.edges}
    assert age_graph.highlighted_path == sql_graph.highlighted_path == [center_id, highlight_to]
    assert age_graph.truncated == sql_graph.truncated


def test_identity_review_is_atomic_and_audited() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    tenant_id = "00000000-0000-4000-8000-000000009001"
    left_id = "00000000-0000-4000-8000-000000009002"
    right_id = "00000000-0000-4000-8000-000000009003"
    assertion_id = "00000000-0000-4000-8000-000000009004"

    def configure_tenant(connection) -> None:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    with psycopg.connect(admin_database_url) as connection:
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
            app = create_app(settings=Settings(
                environment="test",
                database_url=database_url,
                default_tenant_id=tenant_id,
                development_actor_key="integration-test",
            ))
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://testserver",
                ) as client:
                    response = await client.post(
                        f"/identity-assertions/{assertion_id}/review",
                        json={"decision": "CONFIRM", "rationale": "Verified test identity.", "expected_version": 1},
                    )
                    conflict = await client.post(
                        f"/identity-assertions/{assertion_id}/review",
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
        with psycopg.connect(admin_database_url) as connection:
            configure_tenant(connection)
            connection.execute("DELETE FROM projection_outbox WHERE aggregate_id=%s", (assertion_id,))
            connection.execute("DELETE FROM identity_assertion_review WHERE identity_assertion_id=%s", (assertion_id,))
            connection.execute("DELETE FROM identity_assertion WHERE id=%s", (assertion_id,))
            connection.execute("DELETE FROM entity WHERE id IN (%s,%s)", (left_id, right_id))
            connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))


def test_golden_billing_vertical_slice() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    install_golden_billing(admin_database_url)

    async def query_api():
        app = create_app(settings=Settings(
            environment="test",
            database_url=database_url,
            default_tenant_id=TENANT_ID,
        ))
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as client:
                return {
                    "estateSummary": await client.get("/estate/summary"),
                    "applicationDetail": await client.get(f"/applications/{APPLICATION_ID}"),
                    "repositoryDetail": await client.get(f"/repositories/{REPOSITORY_ID}"),
                    "technologyDetail": await client.get(f"/technologies/{PACKAGE_ID}"),
                    "technologyHierarchy": await client.get("/technologies/hierarchy"),
                    "modernizationList": await client.get("/modernization"),
                    "graphNeighborhood": await client.get(
                        "/graph/neighborhood",
                        params=[
                            ("center_id", PACKAGE_ID),
                            ("depth", "2"),
                            ("predicate", "DEPENDS_ON"),
                            ("predicate", "IMPLEMENTED_BY"),
                            ("highlight_to", APPLICATION_ID),
                        ],
                    ),
                    "evidenceDetail": await client.get(f"/facts/{DEPENDENCY_FACT_ID}/evidence"),
                    "unsupportedAsk": await client.post(
                        "/ask", json={"question": "Which Tier-1 applications use unsupported runtimes?"},
                    ),
                    "viabilityAsk": await client.post(
                        "/ask", json={"question": "Why is Billing's viability score low?"},
                    ),
                    "dependencyAsk": await client.post(
                        "/ask", json={"question": "What does Billing API depend on?"},
                    ),
                    "indirectAsk": await client.post(
                        "/ask",
                        json={
                            "question": "Show all applications indirectly dependent on this package",
                            "context_entity_ids": [PACKAGE_ID],
                        },
                    ),
                }

    try:
        responses = asyncio.run(query_api())
        for name, response in responses.items():
            assert response.status_code == 200, f"{name}: {response.text}"

        contract = ContractValidator(Path("/contracts/v1"))
        for definition in (
            "estateSummary", "applicationDetail", "repositoryDetail", "technologyDetail",
            "technologyHierarchy", "modernizationList", "graphNeighborhood", "evidenceDetail",
        ):
            contract.validate_read_model(definition, responses[definition].json())
        for name in ("unsupportedAsk", "viabilityAsk", "dependencyAsk", "indirectAsk"):
            contract.validate_read_model("askResponse", responses[name].json())

        summary = responses["estateSummary"].json()
        assert summary["counts"]["applications"] == 1
        assert summary["counts"]["repositories"] == 1
        assert summary["counts"]["services"] == 1
        # Only technologies evidenced by tenant relationships belong to the estate.
        assert summary["counts"]["technologies"] == 2
        assert summary["ranked_items"][0]["name"] == "Billing API"
        assert summary["ranked_items"][0]["priority"]["confidence_label"] == "HIGH"

        application = responses["applicationDetail"].json()
        assert {item["id"] for item in application["business_context"]} == {CAPABILITY_ID}
        assert {item["id"] for item in application["repositories"]} == {REPOSITORY_ID}
        assert PACKAGE_ID in {item["id"] for item in application["technologies"]}
        assert application["technology_groups"][0]["domain"]["key"] == "unclassified"
        grouped_package = application["technology_groups"][0]["functions"][0]["technologies"][0]
        assert grouped_package["technology"]["id"] == PACKAGE_ID
        assert grouped_package["classification"] == "UNCLASSIFIED"
        assert grouped_package["citations"][0]["fact_id"] == DEPENDENCY_FACT_ID
        hierarchy = application["dependency_hierarchies"][0]
        assert hierarchy["repository"]["id"] == REPOSITORY_ID
        dependency = hierarchy["components"][0]["dependencies"][0]
        assert dependency["technology"]["id"] == PACKAGE_ID
        assert dependency["direct"] is True
        assert dependency["scope"] == "runtime"
        assert dependency["citations"][0]["fact_id"] == DEPENDENCY_FACT_ID

        repository = responses["repositoryDetail"].json()
        assert repository["repository"]["id"] == REPOSITORY_ID
        assert {item["id"] for item in repository["applications"]} == {APPLICATION_ID}
        assert PACKAGE_ID in {item["id"] for item in repository["technologies"]}

        technology = responses["technologyDetail"].json()
        assert technology["internal_usage"]["repository_count"] == 1
        assert technology["internal_usage"]["application_count"] == 1
        assert {item["id"] for item in technology["projects"]} == {OSS_PROJECT_ID}

        hierarchy_node = responses["technologyHierarchy"].json()["nodes"][0]
        assert hierarchy_node["technology"]["id"] == PACKAGE_ID
        assert hierarchy_node["direct"] is True
        assert hierarchy_node["dependent_applications"][0]["id"] == APPLICATION_ID

        graph = responses["graphNeighborhood"].json()
        assert graph["highlighted_path"] == [PACKAGE_ID, REPOSITORY_ID, APPLICATION_ID]
        assert {edge["predicate"] for edge in graph["edges"]} <= {"DEPENDS_ON", "IMPLEMENTED_BY"}

        assert responses["unsupportedAsk"].json()["rows"][0]["application"] == "Billing API"
        assert responses["viabilityAsk"].json()["citations"]
        assert responses["dependencyAsk"].json()["text"] == "Billing API directly depends on axios 1.7.9."
        assert responses["dependencyAsk"].json()["citations"][0]["fact_id"] == DEPENDENCY_FACT_ID
        assert responses["indirectAsk"].json()["result_kind"] == "GRAPH"
        assert responses["indirectAsk"].json()["graph_highlight"]["highlighted_path"]
    finally:
        remove_golden_billing(admin_database_url)


def test_review_queue_aggregates_pending_items_over_live_schema() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    tenant_id = "00000000-0000-4000-8000-00000000a001"
    left_id = "00000000-0000-4000-8000-00000000a002"
    right_id = "00000000-0000-4000-8000-00000000a003"
    assertion_id = "00000000-0000-4000-8000-00000000a004"

    def configure_tenant(connection) -> None:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    with psycopg.connect(admin_database_url) as connection:
        configure_tenant(connection)
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'review-queue-test','Review queue test')",
            (tenant_id,),
        )
        connection.execute(
            """
            INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name) VALUES
              (%s,%s,'TECHNOLOGY','Technology','rq:left','stripe'),
              (%s,%s,'TECHNOLOGY','Technology','rq:right','stripe-node')
            """,
            (left_id, tenant_id, right_id, tenant_id),
        )
        connection.execute(
            """
            INSERT INTO identity_assertion
              (id,tenant_id,left_entity_id,right_entity_id,method,method_version,confidence,review_state)
            VALUES (%s,%s,%s,%s,'TEST','1.0.0',0.72,'POSSIBLE')
            """,
            (assertion_id, tenant_id, left_id, right_id),
        )

    try:
        async def query():
            settings = Settings(database_url=database_url)
            database = Database(settings)
            await database.open()
            try:
                store = ReadModelStore(database)
                unfiltered = await store.review_queue(
                    tenant_id=UUID(tenant_id), item_types=None, repository_id=None, cursor=None, limit=50,
                )
                filtered = await store.review_queue(
                    tenant_id=UUID(tenant_id), item_types=["CAPABILITY_INFERENCE"],
                    repository_id=None, cursor=None, limit=50,
                )
                return unfiltered, filtered
            finally:
                await database.close()

        unfiltered, filtered = asyncio.run(query())

        assert unfiltered.contract_version == "1.0.0"
        assert set(unfiltered.counts) == {
            "IDENTITY_ASSERTION", "CAPABILITY_INFERENCE", "DUPLICATE_CAPABILITY",
            "MODERNIZATION_CANDIDATE", "MODERNIZATION_RECOMMENDATION",
        }
        assert unfiltered.counts["IDENTITY_ASSERTION"] >= 1
        item = next(i for i in unfiltered.items if str(i.item_id) == assertion_id)
        assert item.item_type == "IDENTITY_ASSERTION"
        assert item.title == "stripe ↔ stripe-node"
        assert item.confidence_band == "MEDIUM"
        assert item.review_path == f"/identity-assertions/{assertion_id}/review"
        # The CAPABILITY_INFERENCE filter must exclude the identity assertion.
        assert all(str(i.item_id) != assertion_id for i in filtered.items)
    finally:
        with psycopg.connect(admin_database_url) as connection:
            configure_tenant(connection)
            connection.execute("DELETE FROM identity_assertion WHERE id=%s", (assertion_id,))
            connection.execute("DELETE FROM entity WHERE id IN (%s,%s)", (left_id, right_id))
            connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))


def test_admin_member_connector_scan_lifecycle_over_live_schema() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    tenant_id = "00000000-0000-4000-8000-00000000b001"

    def configure_tenant(connection) -> None:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

    with psycopg.connect(admin_database_url) as connection:
        configure_tenant(connection)
        connection.execute(
            "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,'admin-lifecycle-test','Admin lifecycle test')",
            (tenant_id,),
        )

    try:
        async def exercise():
            app = create_app(settings=Settings(
                environment="test",
                database_url=database_url,
                default_tenant_id=tenant_id,
                development_actor_key="admin-integration",
            ))
            hosted_github = DatabaseStubGitHubAppSetupClient()
            app.state.github_app_client = hosted_github
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app, raise_app_exceptions=False),
                    base_url="http://testserver",
                ) as client:
                    member = await client.post(
                        "/admin/members",
                        json={"actor_key": "dana@acme.example", "display_name": "Dana", "role": "review"},
                    )
                    members = await client.get("/admin/members")
                    connector = await client.post(
                        "/admin/connectors",
                        json={"provider": "GITHUB_APP", "display_name": "acme-corp",
                              "external_account_key": "acme", "scopes": ["repo:read"],
                              "credential_reference": "vault://gh/acme"},
                    )
                    repository = await client.post(
                        "/admin/github/repositories",
                        json={"repository": "acme/billing"},
                    )
                    installation = await client.post(
                        "/admin/github/installations",
                        json={
                            "installation_id": "900000000000000001",
                            "pilot_manual_binding_acknowledged": True,
                            "display_name": "Acme GitHub App",
                        },
                    )
                    hosted_setup = await client.post(
                        "/admin/github/installations/setup",
                        json={"return_to": "/admin?section=connections"},
                    )
                    hosted_installation = await client.get(
                        "/admin/github/installations/setup/callback",
                        params={
                            "code": "database-oauth-code",
                            "state": hosted_github.state,
                            "installation_id": "900000000000000002",
                            "setup_action": "install",
                        },
                        follow_redirects=False,
                    )
                    hosted_replay = await client.get(
                        "/admin/github/installations/setup/callback",
                        params={
                            "code": "database-oauth-code",
                            "state": hosted_github.state,
                            "installation_id": "900000000000000002",
                            "setup_action": "install",
                        },
                        follow_redirects=False,
                    )
                    with psycopg.connect(admin_database_url, row_factory=dict_row) as connection:
                        configure_tenant(connection)
                        target = connection.execute(
                            """
                            SELECT target.id,run.id run_id
                            FROM ingest_target target
                            JOIN ingest_run run ON run.ingest_target_id=target.id
                            WHERE target.tenant_id=%s
                              AND target.target_key='github:repo-name:acme/billing'
                            ORDER BY run.created_at DESC LIMIT 1
                            """,
                            (tenant_id,),
                        ).fetchone()
                        assert target is not None
                        connection.execute(
                            """
                            INSERT INTO entity(
                              tenant_id,namespace,entity_type,canonical_key,name,properties
                            ) VALUES (
                              %s,'ENTERPRISE','Repository',
                              'github:repo-name:acme/billing','Billing repository','{}'
                            )
                            """,
                            (tenant_id,),
                        )
                        connection.execute(
                            """
                            INSERT INTO source_snapshot(
                              tenant_id,ingest_run_id,ingest_target_id,source_revision,
                              extractor_key,extractor_version,completeness,status,observed_at,stats
                            ) VALUES (
                              %s,%s,%s,'configured-revision',
                              'repository-dependency-usage','1.0.0','COMPLETE','PUBLISHED',now(),'{}'
                            )
                            """,
                            (tenant_id, target["run_id"], target["id"]),
                        )
                    policy = await client.put(
                        "/admin/scan-policy", json={"cadence": "HOURLY", "enabled": True},
                    )
                    rescan_a = await client.post("/admin/rescans", json={"idempotency_key": "nightly"})
                    rescan_b = await client.post("/admin/rescans", json={"idempotency_key": "nightly"})
                    status = await client.get("/admin/scan-status")
                    services = await client.get("/admin/services")
                    raw = await client.post(
                        "/admin/connectors",
                        json={"provider": "OTHER", "display_name": "bad",
                              "credential_reference": "ghp_" + "a" * 36},
                    )
                    ai_saved = await client.put(
                        "/admin/ai-configuration",
                        json={"provider": "openrouter", "model": "test/model",
                              "api_key": "integration-secret-5678"},
                    )
                    ai_read = await client.get("/admin/ai-configuration")
                    tenant_ai = load_tenant_ai_settings(
                        admin_database_url,
                        tenant_id=UUID(tenant_id),
                        encryption_key="stackgraph-local-development-credential-key",
                    )
                    ai_removed = await client.delete("/admin/ai-configuration/key")
                    governance = await client.get("/admin/modernization-governance")
                    ecosystem = await client.put(
                        "/admin/modernization-governance/ecosystems/PYPI",
                        json={"minimum_repositories": 1, "minimum_dependency_share": 0.01},
                    )
                    return (
                        member, members, connector, repository, installation,
                        hosted_setup, hosted_installation, hosted_replay, policy,
                        rescan_a, rescan_b, status, services, raw, ai_saved, ai_read,
                        tenant_ai, ai_removed, governance, ecosystem,
                    )

        (
            member, members, connector, repository, installation,
            hosted_setup, hosted_installation, hosted_replay, policy, rescan_a,
            rescan_b, status, services, raw, ai_saved, ai_read, tenant_ai, ai_removed,
            governance, ecosystem,
        ) = asyncio.run(exercise())

        assert member.status_code == 201 and member.json()["role"] == "review"
        assert members.status_code == 200 and len(members.json()["members"]) == 1
        assert connector.status_code == 201 and connector.json()["provider"] == "GITHUB_APP"
        assert "credential_reference" not in connector.json()  # never surfaced
        assert repository.status_code == 201
        assert repository.json()["external_account_key"] == "github:repository:acme/billing"
        assert installation.status_code == 201
        assert installation.json()["external_account_key"] == (
            "github:installation:900000000000000001"
        )
        assert hosted_setup.status_code == 201
        assert hosted_installation.status_code == 303
        assert hosted_installation.headers["location"].endswith(
            "github=connected&installation_id=900000000000000002"
        )
        assert hosted_replay.status_code == 409
        assert hosted_replay.json()["code"] == "GITHUB_SETUP_STATE_REPLAYED"
        assert policy.status_code == 200 and policy.json()["cadence"] == "HOURLY"
        assert rescan_a.status_code == 201
        assert rescan_b.status_code == 200  # idempotent replay
        assert rescan_a.json()["id"] == rescan_b.json()["id"]
        assert status.status_code == 200 and status.json()["policy"]["cadence"] == "HOURLY"
        assert services.status_code == 200
        assert {service["key"] for service in services.json()["services"]} == {
            "web", "api", "database", "github-webhook", "github-control-loop",
            "depsdev", "osv", "projection", "intelligence",
        }
        assert raw.status_code == 422 and raw.json()["code"] == "CREDENTIAL_LOOKS_RAW"
        assert ai_saved.status_code == 200 and ai_saved.json()["key_fingerprint"] == "5678"
        assert ai_saved.json()["enrichment_status"] == "QUEUED"
        assert ai_saved.json()["pending_enrichment_jobs"] == 1
        assert "api_key" not in ai_saved.json()
        assert ai_read.json()["model"] == "test/model" and ai_read.json()["key_configured"] is True
        assert tenant_ai is not None
        assert tenant_ai.routes[0].provider == "openrouter"
        assert tenant_ai.routes[0].model == "test/model"
        assert tenant_ai.openrouter_api_key == "integration-secret-5678"
        assert ai_removed.json()["key_configured"] is False
        assert ai_removed.json()["enrichment_status"] == "DISABLED"
        assert governance.status_code == 200
        assert [item["ecosystem"] for item in governance.json()["ecosystem_admissions"]] == [
            "PYPI", "MAVEN", "CARGO", "NUGET",
        ]
        assert governance.json()["ecosystem_admissions"][0]["observed_repositories"] == 0
        assert ecosystem.status_code == 200
        assert ecosystem.json()["ecosystem_admissions"][0]["status"] == "PROPOSED"
        assert "calibration promotion gate has not passed" in (
            ecosystem.json()["ecosystem_admissions"][0]["reasons"]
        )

        with psycopg.connect(database_url) as connection:
            configure_tenant(connection)
            audits = connection.execute(
                "SELECT count(*) FROM admin_audit_log WHERE tenant_id=%s", (tenant_id,),
            ).fetchone()[0]
            assert audits >= 4
            target = connection.execute(
                """
                SELECT target.target_key,target.refresh_policy,run.trigger_kind,
                       run.status,run.stats
                FROM connector admin_connector
                JOIN ingest_target target
                  ON admin_connector.metadata->>'ingest_target_id'=target.id::text
                JOIN ingest_run run ON run.ingest_target_id=target.id
                WHERE admin_connector.id=%s
                ORDER BY run.created_at DESC,run.id DESC
                LIMIT 1
                """,
                (repository.json()["id"],),
            ).fetchone()
            assert target[0] == "github:repo-name:acme/billing"
            assert target[1]["direct_repository"] is True
            hosted = connection.execute(
                """
                SELECT metadata FROM connector
                WHERE tenant_id=%s AND external_account_key='github:installation:900000000000000002'
                """,
                (tenant_id,),
            ).fetchone()
            assert hosted[0]["binding_mode"] == "HOSTED_SETUP"
            assert target[2] == "MANUAL"
            # A continuously running discovery worker may claim this synthetic run.
            assert target[3] in {"PENDING", "RUNNING", "FAILED"}
            assert target[4]["rescan_job_ids"] == [rescan_a.json()["id"]]
            installation_target = connection.execute(
                """
                SELECT target.target_kind,target.target_key,target.refresh_policy,
                       account.credential_reference,run.trigger_kind
                FROM connector admin_connector
                JOIN ingest_target target
                  ON admin_connector.metadata->>'ingest_target_id'=target.id::text
                JOIN connector_account account ON account.id=target.connector_account_id
                JOIN ingest_run run ON run.ingest_target_id=target.id
                WHERE admin_connector.id=%s
                ORDER BY run.created_at LIMIT 1
                """,
                (installation.json()["id"],),
            ).fetchone()
            assert installation_target[0:2] == (
                "GITHUB_INSTALLATION", "github:installation:900000000000000001",
            )
            assert installation_target[2]["installation_id"] == "900000000000000001"
            assert installation_target[3] == (
                "github-app://installation/900000000000000001"
            )
            assert installation_target[4] == "MANUAL"
    finally:
        with psycopg.connect(admin_database_url) as connection:
            configure_tenant(connection)
            connection.execute("DELETE FROM ecosystem_admission WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM github_installation_setup WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM intelligence_job WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM source_snapshot WHERE tenant_id=%s", (tenant_id,))
            connection.execute(
                "DELETE FROM entity WHERE tenant_id=%s AND entity_type='Repository'",
                (tenant_id,),
            )
            connection.execute(
                """
                DELETE FROM ingest_run WHERE ingest_target_id IN (
                  SELECT id FROM ingest_target WHERE tenant_id=%s
                )
                """,
                (tenant_id,),
            )
            connection.execute("DELETE FROM ingest_target WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM connector_account WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM source_system WHERE tenant_id=%s", (tenant_id,))
            for table in (
                "ai_model_invocation", "admin_audit_log",
                "tenant_ai_configuration", "tenant_secret",
                "rescan_job", "connector_quota",
                "scan_policy", "connector", "tenant_member", "dead_letter",
            ):
                connection.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (tenant_id,))
            connection.execute("DELETE FROM tenant WHERE id=%s", (tenant_id,))

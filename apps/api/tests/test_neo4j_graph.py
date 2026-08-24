import asyncio
from unittest.mock import patch
from uuid import UUID

from app.neo4j_graph import Neo4jGraphReader


TENANT_ID = UUID("00000000-0000-4000-8000-000000000099")
CENTER_ID = UUID("00000000-0000-4000-8000-000000000001")
TARGET_ID = UUID("00000000-0000-4000-8000-000000000002")
FACT_ID = UUID("00000000-0000-4000-8000-000000000003")


class DeploymentDatabase:
    async def fetch_one(self, query, params=None, *, tenant_id=None):
        assert tenant_id == TENANT_ID
        if "deployment.endpoint" in query:
            assert params[1] == TENANT_ID
            return {
                "endpoint": "neo4j://tenant-graph:7687",
                "database_name": "neo4j",
                "username": "stackgraph",
                "credential_reference": "env://STACKGRAPH_TEST_GRAPH_PASSWORD",
                "stored_password": None,
                "desired_outbox_id": 42,
                "projected_outbox_id": 42,
            }
        return {
            "deployment_state": "ACTIVE",
            "desired_outbox_id": 42,
            "projected_outbox_id": 42,
        }


class FakeDriver:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    async def execute_query(self, query, **params):
        self.calls.append((query, params))
        if "min(length(path))" in query:
            return ([
                {"entity_id": str(CENTER_ID), "depth": 0},
                {"entity_id": str(TARGET_ID), "depth": 1},
            ], None, None)
        return ([{"fact_id": str(FACT_ID)}], None, None)

    async def close(self):
        self.closed = True


def test_neo4j_reader_is_tenant_bound_parameterized_and_returns_stable_ids() -> None:
    driver = FakeDriver()
    factory_calls = []

    def driver_factory(endpoint, *, auth):
        factory_calls.append((endpoint, auth))
        return driver

    reader = Neo4jGraphReader(
        DeploymentDatabase(),
        encryption_key="x" * 32,
        discovery_limit=10,
        driver_factory=driver_factory,
    )
    with patch.dict("os.environ", {"STACKGRAPH_TEST_GRAPH_PASSWORD": "secret"}):
        topology = asyncio.run(reader.neighborhood(
            CENTER_ID,
            tenant_id=TENANT_ID,
            depth=2,
            predicates=["DEPENDS_ON"],
            namespaces=["ENTERPRISE"],
            min_confidence=0.75,
        ))

    assert topology is not None
    assert topology.node_depths == {CENTER_ID: 0, TARGET_ID: 1}
    assert topology.fact_ids == [FACT_ID]
    assert factory_calls == [("neo4j://tenant-graph:7687", ("stackgraph", "secret"))]
    assert all(call[1]["tenant_id"] == str(TENANT_ID) for call in driver.calls)
    assert "$predicates" in driver.calls[0][0]
    assert "DEPENDS_ON" not in driver.calls[0][0]
    assert driver.closed


def test_projection_state_fails_closed_when_no_tenant_context() -> None:
    reader = Neo4jGraphReader(
        DeploymentDatabase(), encryption_key="x" * 32, driver_factory=lambda *args, **kwargs: None,
    )
    state = asyncio.run(reader.projection_state(None))

    assert not state.configured
    assert not state.current

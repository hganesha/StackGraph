import asyncio
from uuid import UUID

from app.neo4j_graph import Neo4jProjectionState
from app.read_models import ReadModelStore


CENTER_ID = UUID("00000000-0000-4000-8000-000000000001")
FACT_ID = UUID("00000000-0000-4000-8000-000000000301")


class GraphDatabaseStub:
    def __init__(self) -> None:
        self.real_nodes = [
            {
                "id": UUID(f"00000000-0000-4000-8000-{index:012d}"),
                "namespace": "TECHNOLOGY",
                "entity_type": "Technology",
                "canonical_key": f"technology:{index}",
                "name": f"Technology {index:02d}",
            }
            for index in range(1, 50)
        ]

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "count(*) total" in query:
            return {"total": 52}
        return {
            **self.real_nodes[0],
            "properties": {},
            "created_at": None,
            "updated_at": None,
            "last_seen_at": None,
            "observed_at": None,
        }

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        if "count(*)::integer member_count" in query:
            kept_real_count = params[-1]
            return [{
                "namespace": "TECHNOLOGY",
                "entity_type": "Capability",
                "member_count": 52 - kept_real_count,
                "min_depth": 1,
            }]
        if "FROM ranked WHERE node_rank<=" in query:
            return self.real_nodes[:params[-1]]
        if "SELECT r.*,coalesce" in query:
            return []
        if ", mapped AS" in query:
            return [{
                "source_real_id": CENTER_ID,
                "source_namespace": "TECHNOLOGY",
                "source_entity_type": "Technology",
                "target_real_id": None,
                "target_namespace": "TECHNOLOGY",
                "target_entity_type": "Capability",
                "relationship_type": "PROVIDES",
                "assertion_class": "CURATED",
                "review_state": "NOT_APPLICABLE",
                "confidence": 0.95,
                "citation_fact_ids": [FACT_ID],
            }]
        raise AssertionError(f"unexpected query: {query}")


class LaggedNeo4jReader:
    async def projection_state(self, tenant_id):
        return Neo4jProjectionState(True, True, 42, 40)


class UnavailableNeo4jReader:
    async def projection_state(self, tenant_id):
        raise RuntimeError("Neo4j connection unavailable")


class SlowNeo4jReader:
    async def projection_state(self, tenant_id):
        return Neo4jProjectionState(True, True, 42, 42)

    async def neighborhood(self, *args, **kwargs):
        await asyncio.sleep(0.05)
        return None


async def aggregate_graph():
    store = ReadModelStore(GraphDatabaseStub())
    return await store.graph_neighborhood(
        CENTER_ID,
        tenant_id=None,
        depth=1,
        real_node_limit=50,
    )


def test_aggregate_clusters_reserve_space_within_node_cap() -> None:
    graph = asyncio.run(aggregate_graph())
    real_nodes = [node for node in graph.nodes if not node.aggregate]
    aggregate_nodes = [node for node in graph.nodes if node.aggregate]

    assert graph.truncated
    assert len(graph.nodes) == 50
    assert len(real_nodes) == 49
    assert len(aggregate_nodes) == 1
    assert aggregate_nodes[0].member_count == 3
    assert graph.edges[0].citation_fact_ids == [FACT_ID]


def test_aggregate_node_and_edge_ids_are_deterministic() -> None:
    first = asyncio.run(aggregate_graph())
    second = asyncio.run(aggregate_graph())

    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert [edge.id for edge in first.edges] == [edge.id for edge in second.edges]


def test_auto_mode_falls_back_to_sql_when_projection_is_behind() -> None:
    store = ReadModelStore(GraphDatabaseStub(), graph_read_mode="auto")
    store.neo4j_graph = LaggedNeo4jReader()
    graph = asyncio.run(store.graph_neighborhood(
        CENTER_ID, tenant_id=CENTER_ID, depth=1, real_node_limit=50,
    ))

    assert graph.truncated
    assert store.graph_read_metrics.neo4j_reads == 0
    assert store.graph_read_metrics.lag_fallbacks == 1
    assert store.graph_read_metrics.sql_reads == 1


def test_auto_mode_falls_back_to_sql_when_neo4j_is_unavailable() -> None:
    store = ReadModelStore(GraphDatabaseStub(), graph_read_mode="auto")
    store.neo4j_graph = UnavailableNeo4jReader()
    graph = asyncio.run(store.graph_neighborhood(
        CENTER_ID, tenant_id=CENTER_ID, depth=1, real_node_limit=50,
    ))

    assert graph.truncated
    assert store.graph_read_metrics.neo4j_reads == 0
    assert store.graph_read_metrics.unavailable_fallbacks == 1
    assert store.graph_read_metrics.sql_reads == 1


def test_auto_mode_falls_back_to_sql_when_neo4j_exceeds_time_budget() -> None:
    store = ReadModelStore(
        GraphDatabaseStub(),
        graph_read_mode="auto",
        graph_age_timeout_seconds=0.001,
    )
    store.neo4j_graph = SlowNeo4jReader()
    graph = asyncio.run(store.graph_neighborhood(
        CENTER_ID, tenant_id=CENTER_ID, depth=1, real_node_limit=50,
    ))

    assert graph.truncated
    assert store.graph_read_metrics.neo4j_reads == 0
    assert store.graph_read_metrics.timeout_fallbacks == 1
    assert store.graph_read_metrics.sql_reads == 1

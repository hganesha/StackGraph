from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class QueryDatabase(Protocol):
    async def fetch_one(self, query, params=None, *, tenant_id=None): ...
    async def fetch_all(self, query, params=None, *, tenant_id=None): ...


@dataclass(frozen=True, slots=True)
class ProjectionState:
    pending_events: int
    oldest_pending_seconds: float | None

    @property
    def current(self) -> bool:
        return self.pending_events == 0


@dataclass(frozen=True, slots=True)
class AgeTopology:
    node_depths: dict[UUID, int]
    fact_ids: list[UUID]
    discovery_capped: bool = False


_AGE_ENTITIES = """
age_entity_properties AS MATERIALIZED (
  SELECT
    id::text::bigint graph_id,
    trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"entity_id"'::ag_catalog.agtype]
    )::text)::uuid entity_id,
    trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"namespace"'::ag_catalog.agtype]
    )::text) namespace,
    nullif(trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"tenant_id"'::ag_catalog.agtype]
    )::text),'null') tenant_id
  FROM stackgraph."Entity"
), age_entities AS MATERIALIZED (
  SELECT * FROM age_entity_properties
  WHERE tenant_id IS NULL
     OR tenant_id=nullif(current_setting('app.tenant_id',true),'')
)
"""

_AGE_EDGES = """
, age_edge_properties AS MATERIALIZED (
  SELECT
    start_id::text::bigint start_id,
    end_id::text::bigint end_id,
    trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"fact_id"'::ag_catalog.agtype]
    )::text)::uuid fact_id,
    trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"relationship_type"'::ag_catalog.agtype]
    )::text) relationship_type,
    (ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"confidence"'::ag_catalog.agtype]
    )::text)::numeric confidence,
    nullif(trim(both '"' from ag_catalog.agtype_access_operator(
      VARIADIC ARRAY[properties,'"tenant_id"'::ag_catalog.agtype]
    )::text),'null') tenant_id
  FROM stackgraph."Relationship"
), age_edges AS MATERIALIZED (
  SELECT edge.*
  FROM age_edge_properties edge
  JOIN age_entities source ON source.graph_id=edge.start_id
  JOIN age_entities target ON target.graph_id=edge.end_id
  LEFT JOIN identity_assertion identity ON edge.relationship_type='SAME_AS'
    AND ((identity.left_entity_id=source.entity_id AND identity.right_entity_id=target.entity_id)
      OR (identity.right_entity_id=source.entity_id AND identity.left_entity_id=target.entity_id))
  WHERE (edge.tenant_id IS NULL
      OR edge.tenant_id=nullif(current_setting('app.tenant_id',true),''))
    AND coalesce(identity.review_state,'NOT_APPLICABLE')<>'REJECTED'
)
"""


class AgeGraphReader:
    def __init__(self, database: QueryDatabase, *, discovery_limit: int = 5000) -> None:
        self.database = database
        self.discovery_limit = discovery_limit

    async def projection_state(self, tenant_id: UUID | None) -> ProjectionState:
        row = await self.database.fetch_one(
            """
            SELECT count(*)::integer pending_events,
                   extract(epoch FROM now()-min(created_at))::double precision oldest_pending_seconds
            FROM projection_outbox
            WHERE aggregate_type='FACT' AND processed_at IS NULL
            """,
            tenant_id=tenant_id,
        )
        return ProjectionState(
            pending_events=int(row["pending_events"]) if row else 0,
            oldest_pending_seconds=(
                float(row["oldest_pending_seconds"])
                if row and row.get("oldest_pending_seconds") is not None else None
            ),
        )

    async def neighborhood(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        predicates: list[str] | None,
        namespaces: list[str] | None,
        min_confidence: float,
    ) -> AgeTopology | None:
        rows = await self.database.fetch_all(
            "WITH RECURSIVE " + _AGE_ENTITIES + _AGE_EDGES + """
            , walk(graph_id,entity_id,depth) AS (
              SELECT entity.graph_id,entity.entity_id,0
              FROM age_entities entity WHERE entity.entity_id=%s
              UNION
              SELECT next.graph_id,next.entity_id,walk.depth+1
              FROM walk
              JOIN age_edges edge
                ON edge.start_id=walk.graph_id OR edge.end_id=walk.graph_id
              JOIN age_entities next ON next.graph_id=CASE
                WHEN edge.start_id=walk.graph_id THEN edge.end_id ELSE edge.start_id END
              WHERE walk.depth<%s
                AND (%s::text[] IS NULL OR edge.relationship_type=ANY(%s::text[]))
                AND (%s::text[] IS NULL OR next.namespace=ANY(%s::text[]))
                AND edge.confidence>=%s::numeric
            )
            SELECT entity_id,min(depth)::integer depth
            FROM walk GROUP BY entity_id
            ORDER BY min(depth),entity_id
            LIMIT %s
            """,
            (
                center_id, depth, predicates or None, predicates or None,
                namespaces or None, namespaces or None, min_confidence,
                self.discovery_limit + 1,
            ),
            tenant_id=tenant_id,
        )
        if not rows:
            return None
        capped = len(rows) > self.discovery_limit
        rows = rows[: self.discovery_limit]
        node_depths = {row["entity_id"]: int(row["depth"]) for row in rows}
        fact_rows = await self.database.fetch_all(
            "WITH " + _AGE_ENTITIES + _AGE_EDGES + """
            SELECT DISTINCT edge.fact_id
            FROM age_edges edge
            JOIN age_entities source ON source.graph_id=edge.start_id
            JOIN age_entities target ON target.graph_id=edge.end_id
            WHERE source.entity_id=ANY(%s::uuid[])
              AND target.entity_id=ANY(%s::uuid[])
              AND (%s::text[] IS NULL OR edge.relationship_type=ANY(%s::text[]))
              AND edge.confidence>=%s::numeric
            ORDER BY edge.fact_id
            """,
            (
                list(node_depths), list(node_depths), predicates or None,
                predicates or None, min_confidence,
            ),
            tenant_id=tenant_id,
        )
        return AgeTopology(
            node_depths=node_depths,
            fact_ids=[row["fact_id"] for row in fact_rows],
            discovery_capped=capped,
        )

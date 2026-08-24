from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from neo4j import AsyncGraphDatabase


class QueryDatabase(Protocol):
    async def fetch_one(self, query, params=None, *, tenant_id=None): ...


@dataclass(frozen=True, slots=True)
class Neo4jProjectionState:
    configured: bool
    active: bool
    desired_outbox_id: int
    projected_outbox_id: int

    @property
    def current(self) -> bool:
        return self.configured and self.active and self.projected_outbox_id >= self.desired_outbox_id

    @property
    def pending_events(self) -> int:
        return max(0, self.desired_outbox_id - self.projected_outbox_id)


@dataclass(frozen=True, slots=True)
class Neo4jTopology:
    node_depths: dict[UUID, int]
    fact_ids: list[UUID]
    discovery_capped: bool = False


@dataclass(frozen=True, slots=True)
class _Deployment:
    endpoint: str
    database_name: str
    username: str
    password: str
    desired_outbox_id: int
    projected_outbox_id: int


def _environment_secret(reference: str) -> str:
    if not reference.startswith("env://"):
        raise RuntimeError("the API supports only env:// Neo4j credential references")
    variable = reference.removeprefix("env://")
    if not variable or not variable.replace("_", "").isalnum():
        raise RuntimeError("invalid Neo4j environment credential reference")
    value = os.environ.get(variable, "")
    if not value:
        raise RuntimeError(f"Neo4j credential environment variable {variable} is empty")
    return value


class Neo4jGraphReader:
    """Tenant-bound bounded topology reader over the disposable Neo4j projection.

    Neo4j returns stable PostgreSQL UUIDs only. PostgreSQL subsequently hydrates and
    authorizes every node and fact, so a divergent or stale projection fails parity
    and the caller can fall back to the relational reader.
    """

    def __init__(
        self,
        database: QueryDatabase,
        *,
        encryption_key: str,
        discovery_limit: int = 5000,
        driver_factory: Any = AsyncGraphDatabase.driver,
    ) -> None:
        self.database = database
        self.encryption_key = encryption_key
        self.discovery_limit = discovery_limit
        self.driver_factory = driver_factory

    async def projection_state(self, tenant_id: UUID | None) -> Neo4jProjectionState:
        if tenant_id is None:
            return Neo4jProjectionState(False, False, 0, 0)
        row = await self.database.fetch_one(
            """
            SELECT deployment_state,desired_outbox_id,projected_outbox_id
            FROM tenant_graph_deployment
            WHERE tenant_id=%s
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        if row is None:
            return Neo4jProjectionState(False, False, 0, 0)
        return Neo4jProjectionState(
            configured=True,
            active=row["deployment_state"] == "ACTIVE",
            desired_outbox_id=int(row["desired_outbox_id"] or 0),
            projected_outbox_id=int(row["projected_outbox_id"] or 0),
        )

    async def _deployment(self, tenant_id: UUID) -> _Deployment:
        row = await self.database.fetch_one(
            """
            SELECT deployment.endpoint,deployment.database_name,deployment.username,
                   deployment.credential_reference,deployment.desired_outbox_id,
                   deployment.projected_outbox_id,
                   CASE WHEN secret.id IS NULL THEN NULL
                        ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS stored_password
            FROM tenant_graph_deployment deployment
            LEFT JOIN tenant_secret secret
              ON secret.id=deployment.credential_secret_id
             AND secret.tenant_id=deployment.tenant_id
            WHERE deployment.tenant_id=%s AND deployment.deployment_state='ACTIVE'
            """,
            (self.encryption_key, tenant_id),
            tenant_id=tenant_id,
        )
        if row is None:
            raise RuntimeError("active tenant Neo4j deployment is unavailable")
        password = row["stored_password"]
        if password is None:
            password = _environment_secret(row["credential_reference"])
        return _Deployment(
            endpoint=row["endpoint"],
            database_name=row["database_name"],
            username=row["username"],
            password=password,
            desired_outbox_id=int(row["desired_outbox_id"] or 0),
            projected_outbox_id=int(row["projected_outbox_id"] or 0),
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
    ) -> Neo4jTopology | None:
        if tenant_id is None:
            return None
        if depth < 1 or depth > 3:
            raise ValueError("Neo4j neighborhood depth must be between 1 and 3")
        deployment = await self._deployment(tenant_id)
        if deployment.projected_outbox_id < deployment.desired_outbox_id:
            return None

        driver = self.driver_factory(
            deployment.endpoint,
            auth=(deployment.username, deployment.password),
        )
        try:
            records, _, _ = await driver.execute_query(
                f"""
                MATCH (center:Entity {{entity_id:$center_id}})
                WHERE center.tenant_id IS NULL OR center.tenant_id=$tenant_id
                MATCH path=(center)-[relationships:Relationship*0..{depth}]-(entity:Entity)
                WHERE all(node IN nodes(path) WHERE node.tenant_id IS NULL OR node.tenant_id=$tenant_id)
                  AND all(relationship IN relationships WHERE
                    (relationship.tenant_id IS NULL OR relationship.tenant_id=$tenant_id)
                    AND ($predicates IS NULL OR relationship.relationship_type IN $predicates)
                    AND relationship.confidence >= $min_confidence)
                  AND ($namespaces IS NULL OR entity.namespace IN $namespaces)
                WITH entity,min(length(path)) AS depth
                RETURN entity.entity_id AS entity_id,depth
                ORDER BY depth,entity_id
                LIMIT $limit
                """,
                center_id=str(center_id),
                tenant_id=str(tenant_id),
                predicates=predicates or None,
                namespaces=namespaces or None,
                min_confidence=float(min_confidence),
                limit=self.discovery_limit + 1,
                database_=deployment.database_name,
                routing_="r",
            )
            if not records:
                return None
            capped = len(records) > self.discovery_limit
            records = records[: self.discovery_limit]
            node_depths = {
                UUID(str(record["entity_id"])): int(record["depth"])
                for record in records
            }
            edge_records, _, _ = await driver.execute_query(
                """
                MATCH (source:Entity)-[relationship:Relationship]->(target:Entity)
                WHERE source.entity_id IN $entity_ids AND target.entity_id IN $entity_ids
                  AND (source.tenant_id IS NULL OR source.tenant_id=$tenant_id)
                  AND (target.tenant_id IS NULL OR target.tenant_id=$tenant_id)
                  AND (relationship.tenant_id IS NULL OR relationship.tenant_id=$tenant_id)
                  AND ($predicates IS NULL OR relationship.relationship_type IN $predicates)
                  AND relationship.confidence >= $min_confidence
                RETURN DISTINCT relationship.fact_id AS fact_id
                ORDER BY fact_id
                """,
                entity_ids=[str(entity_id) for entity_id in node_depths],
                tenant_id=str(tenant_id),
                predicates=predicates or None,
                min_confidence=float(min_confidence),
                database_=deployment.database_name,
                routing_="r",
            )
            return Neo4jTopology(
                node_depths=node_depths,
                fact_ids=[UUID(str(record["fact_id"])) for record in edge_records],
                discovery_capped=capped,
            )
        finally:
            await driver.close()

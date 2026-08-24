from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Protocol
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .service_heartbeat import record_service_heartbeat

try:
    from neo4j import GraphDatabase
    from neo4j import Driver as Neo4jDriver
except ImportError:  # lets mapping-only tests run before the optional runtime dependency is installed
    GraphDatabase = None  # type: ignore[assignment]
    Neo4jDriver = Any  # type: ignore[misc,assignment]


ENTITY_CONSTRAINT_CYPHER = (
    "CREATE CONSTRAINT stackgraph_entity_id IF NOT EXISTS "
    "FOR (entity:Entity) REQUIRE entity.entity_id IS UNIQUE"
)
RELATIONSHIP_INDEX_CYPHER = (
    "CREATE INDEX stackgraph_relationship_logical_key IF NOT EXISTS "
    "FOR ()-[relationship:Relationship]-() ON (relationship.logical_key)"
)
NODE_UPSERT_CYPHER = """
UNWIND $rows AS row
MERGE (entity:Entity {entity_id: row.entity_id})
SET entity += row.properties
""".strip()
EDGE_DELETE_CYPHER = """
UNWIND $logical_keys AS logical_key
MATCH ()-[relationship:Relationship {logical_key: logical_key}]->()
DELETE relationship
""".strip()
EDGE_CREATE_CYPHER = """
UNWIND $rows AS row
MATCH (source:Entity {entity_id: row.source_entity_id})
MATCH (target:Entity {entity_id: row.target_entity_id})
CREATE (source)-[relationship:Relationship]->(target)
SET relationship = row.properties
""".strip()


@dataclass(frozen=True, slots=True)
class GraphDeployment:
    id: UUID
    tenant_id: UUID
    endpoint: str
    database_name: str
    username: str
    password: str


@dataclass(frozen=True, slots=True)
class ProjectionDelivery:
    outbox_id: int
    aggregate_id: UUID
    operation: str


@dataclass(frozen=True, slots=True)
class ClaimedBatch:
    deployment: GraphDeployment
    deliveries: tuple[ProjectionDelivery, ...]


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    batches: int = 0
    claimed: int = 0
    processed: int = 0
    node_upserts: int = 0
    edge_upserts: int = 0
    edge_closures: int = 0


@dataclass(frozen=True, slots=True)
class GraphMutationBatch:
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    relationship_deletions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphInventory:
    node_count: int
    edge_count: int
    node_checksum: str
    edge_checksum: str


def _ordered_checksum(values: Iterable[str]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
        count += 1
    return count, "sha256:" + digest.hexdigest()


def graph_inventory_from_sorted(
    node_ids: Iterable[str], relationship_keys: Iterable[str],
) -> GraphInventory:
    node_count, node_checksum = _ordered_checksum(node_ids)
    edge_count, edge_checksum = _ordered_checksum(relationship_keys)
    return GraphInventory(
        node_count=node_count,
        edge_count=edge_count,
        node_checksum=node_checksum,
        edge_checksum=edge_checksum,
    )


def graph_inventory(node_ids: list[str], relationship_keys: list[str]) -> GraphInventory:
    """Build a deterministic inventory for small in-memory fixtures."""
    return graph_inventory_from_sorted(sorted(node_ids), sorted(relationship_keys))


class GraphWriter(Protocol):
    def apply(self, batch: GraphMutationBatch) -> None: ...
    def close(self) -> None: ...


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entity_parameters(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    def field(name: str) -> Any:
        return row[f"{prefix}{name}"]

    tenant_id = field("tenant_id")
    entity_id = str(field("id"))
    return {
        "entity_id": entity_id,
        "properties": {
            "entity_id": entity_id,
            "tenant_id": str(tenant_id) if tenant_id is not None else None,
            "namespace": field("namespace"),
            "entity_type": field("entity_type"),
            "canonical_key": field("canonical_key"),
            "name": field("name"),
            "properties_json": _json_text(field("properties")),
            "first_seen_at": _timestamp(field("first_seen_at")),
            "last_seen_at": _timestamp(field("last_seen_at")),
        },
    }


def edge_parameters(row: dict[str, Any]) -> dict[str, Any]:
    tenant_id = row["tenant_id"]
    first_seen_at = row["effective_from"] or row["observed_at"]
    last_seen_at = row["effective_to"] or row["observed_at"]
    confidence = row["confidence"]
    return {
        "source_entity_id": str(row["subject_id"]),
        "target_entity_id": str(row["object_id"]),
        "properties": {
            "logical_key": row["logical_key"],
            "fact_id": str(row["fact_id"]),
            "tenant_id": str(tenant_id) if tenant_id is not None else None,
            "relationship_type": row["predicate"],
            "confidence": (
                float(confidence) if isinstance(confidence, Decimal) else confidence
            ),
            "assertion_class": row["assertion_class"],
            "first_seen_at": _timestamp(first_seen_at),
            "last_seen_at": _timestamp(last_seen_at),
            "source_snapshot_id": str(row["source_snapshot_id"]),
            "evidence_fact_ids": [str(row["fact_id"])],
            "properties_json": _json_text(row["fact_properties"]),
        },
    }


def build_mutation_batch(
    facts: list[tuple[ProjectionDelivery, dict[str, Any]]],
) -> GraphMutationBatch:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    relationship_deletions: list[str] = []

    for delivery, fact in facts:
        projects_as_edge = bool(fact["projects_as_edge"] and fact["object_id"] is not None)
        if projects_as_edge:
            relationship_deletions.append(fact["logical_key"])

        current_upsert = delivery.operation == "UPSERT" and fact["system_to"] is None
        if not current_upsert:
            continue

        subject = entity_parameters(fact, "subject_")
        nodes[subject["entity_id"]] = subject
        if not projects_as_edge:
            continue

        target = entity_parameters(fact, "object_")
        nodes[target["entity_id"]] = target
        edges[fact["logical_key"]] = edge_parameters(fact)

    return GraphMutationBatch(
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
        relationship_deletions=tuple(dict.fromkeys(relationship_deletions)),
    )


def resolve_credential_reference(reference: str) -> str:
    if not reference.startswith("env://"):
        raise ValueError(f"unsupported Neo4j credential reference: {reference!r}")
    variable = reference.removeprefix("env://")
    if not variable or not variable.replace("_", "").isalnum():
        raise ValueError("Neo4j environment credential reference is invalid")
    value = os.environ.get(variable, "")
    if not value:
        raise ValueError(f"Neo4j credential environment variable {variable} is empty")
    return value


class Neo4jGraphWriter:
    def __init__(self, deployment: GraphDeployment) -> None:
        if GraphDatabase is None:
            raise RuntimeError("the neo4j Python package is required for graph projection")
        self.deployment = deployment
        self.driver: Neo4jDriver = GraphDatabase.driver(
            deployment.endpoint,
            auth=(deployment.username, deployment.password),
        )
        self.driver.verify_connectivity()
        self.driver.execute_query(
            ENTITY_CONSTRAINT_CYPHER,
            database_=deployment.database_name,
        )
        self.driver.execute_query(
            RELATIONSHIP_INDEX_CYPHER,
            database_=deployment.database_name,
        )

    def apply(self, batch: GraphMutationBatch) -> None:
        def write(transaction: Any) -> None:
            if batch.nodes:
                transaction.run(NODE_UPSERT_CYPHER, rows=list(batch.nodes)).consume()
            if batch.relationship_deletions:
                transaction.run(
                    EDGE_DELETE_CYPHER,
                    logical_keys=list(batch.relationship_deletions),
                ).consume()
            if batch.edges:
                transaction.run(EDGE_CREATE_CYPHER, rows=list(batch.edges)).consume()

        with self.driver.session(database=self.deployment.database_name) as session:
            session.execute_write(write)

    def reset(self) -> None:
        with self.driver.session(database=self.deployment.database_name) as session:
            session.run("MATCH (node) DETACH DELETE node").consume()

    def inventory(self) -> GraphInventory:
        with self.driver.session(database=self.deployment.database_name) as session:
            nodes = session.run(
                "MATCH (entity:Entity) RETURN entity.entity_id AS entity_id ORDER BY entity_id"
            )
            relationships = session.run(
                "MATCH ()-[relationship:Relationship]->() "
                "RETURN relationship.logical_key AS logical_key ORDER BY logical_key"
            )
            return graph_inventory_from_sorted(
                (str(record["entity_id"]) for record in nodes),
                (str(record["logical_key"]) for record in relationships),
            )

    def close(self) -> None:
        self.driver.close()


class Neo4jProjectionWorker:
    def __init__(
        self,
        connection: Connection[dict[str, Any]],
        *,
        worker_id: str,
        batch_size: int,
        encryption_key: str,
        max_attempts: int = 5,
        writer_factory: type[GraphWriter] = Neo4jGraphWriter,
    ) -> None:
        self.connection = connection
        self.worker_id = worker_id
        self.batch_size = batch_size
        self.encryption_key = encryption_key
        self.max_attempts = max_attempts
        self.writer_factory = writer_factory
        self._writers: dict[UUID, GraphWriter] = {}
        self.batches = 0
        self.claimed = 0
        self.processed = 0
        self.node_upserts = 0
        self.edge_upserts = 0
        self.edge_closures = 0

    def run_until_empty(self, max_batches: int | None = None) -> ProjectionResult:
        try:
            while max_batches is None or self.batches < max_batches:
                claimed = self._claim_batch()
                if claimed is None:
                    break
                try:
                    facts = [
                        (delivery, self._load_fact(delivery.aggregate_id))
                        for delivery in claimed.deliveries
                    ]
                    mutation = build_mutation_batch(facts)
                    self._writer_for(claimed.deployment).apply(mutation)
                    self._mark_processed(claimed)
                except Exception as error:
                    self._record_failure(claimed, error)
                    raise

                self.batches += 1
                self.claimed += len(claimed.deliveries)
                self.processed += len(claimed.deliveries)
                self.node_upserts += len(mutation.nodes)
                self.edge_upserts += len(mutation.edges)
                self.edge_closures += len(mutation.relationship_deletions)
        finally:
            for writer in self._writers.values():
                writer.close()

        return ProjectionResult(
            batches=self.batches,
            claimed=self.claimed,
            processed=self.processed,
            node_upserts=self.node_upserts,
            edge_upserts=self.edge_upserts,
            edge_closures=self.edge_closures,
        )

    def _claim_batch(self) -> ClaimedBatch | None:
        with self.connection.transaction():
            deployment_row = self.connection.execute(
                """
                SELECT deployment.*,
                  CASE WHEN secret.id IS NULL THEN NULL
                       ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS stored_password
                FROM tenant_graph_deployment deployment
                LEFT JOIN tenant_secret secret
                  ON secret.id=deployment.credential_secret_id
                 AND secret.tenant_id=deployment.tenant_id
                JOIN LATERAL (
                  SELECT delivery.outbox_id,delivery.available_at,delivery.leased_until
                  FROM graph_projection_delivery delivery
                  WHERE delivery.deployment_id=deployment.id
                    AND delivery.status IN ('PENDING','PROCESSING')
                  ORDER BY delivery.outbox_id
                  LIMIT 1
                ) next_delivery ON true
                WHERE deployment.deployment_state='ACTIVE'
                  AND stackgraph_tenant_service_running(deployment.tenant_id,'projection')
                  AND (deployment.projection_leased_until IS NULL
                    OR deployment.projection_leased_until<now())
                  AND next_delivery.available_at<=now()
                  AND (next_delivery.leased_until IS NULL OR next_delivery.leased_until<now())
                ORDER BY next_delivery.outbox_id,deployment.tenant_id
                FOR UPDATE OF deployment SKIP LOCKED
                LIMIT 1
                """,
                (self.encryption_key,),
            ).fetchone()
            if deployment_row is None:
                return None

            self.connection.execute(
                """
                UPDATE tenant_graph_deployment
                SET projection_leased_by=%s,
                    projection_leased_until=now()+interval '5 minutes',
                    updated_at=now()
                WHERE id=%s
                """,
                (self.worker_id, deployment_row["id"]),
            )
            rows = self.connection.execute(
                """
                WITH candidates AS (
                  SELECT delivery.outbox_id
                  FROM graph_projection_delivery delivery
                  WHERE delivery.deployment_id=%s
                    AND delivery.status IN ('PENDING','PROCESSING')
                    AND delivery.available_at<=now()
                    AND (delivery.leased_until IS NULL OR delivery.leased_until<now())
                  ORDER BY delivery.outbox_id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
                )
                UPDATE graph_projection_delivery delivery
                SET status='PROCESSING',leased_by=%s,
                    leased_until=now()+interval '5 minutes',attempt=delivery.attempt+1
                FROM candidates,projection_outbox outbox
                WHERE delivery.outbox_id=candidates.outbox_id
                  AND delivery.tenant_id=%s
                  AND outbox.id=delivery.outbox_id
                RETURNING delivery.outbox_id,outbox.aggregate_id,outbox.operation
                """,
                (
                    deployment_row["id"],
                    self.batch_size,
                    self.worker_id,
                    deployment_row["tenant_id"],
                ),
            ).fetchall()
            if not rows:
                self.connection.execute(
                    """
                    UPDATE tenant_graph_deployment
                    SET projection_leased_by=NULL,projection_leased_until=NULL,updated_at=now()
                    WHERE id=%s
                    """,
                    (deployment_row["id"],),
                )
                return None

        reference = deployment_row["credential_reference"]
        password = (
            deployment_row["stored_password"]
            if deployment_row["stored_password"] is not None
            else resolve_credential_reference(reference)
        )
        deployment = GraphDeployment(
            id=deployment_row["id"],
            tenant_id=deployment_row["tenant_id"],
            endpoint=deployment_row["endpoint"],
            database_name=deployment_row["database_name"],
            username=deployment_row["username"],
            password=password,
        )
        return ClaimedBatch(
            deployment=deployment,
            deliveries=tuple(
                ProjectionDelivery(
                    outbox_id=row["outbox_id"],
                    aggregate_id=row["aggregate_id"],
                    operation=row["operation"],
                )
                for row in rows
            ),
        )

    def _load_fact(self, fact_id: UUID) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
              fact.id AS fact_id,fact.tenant_id,fact.predicate,fact.assertion_class,
              fact.confidence,fact.logical_key,fact.properties AS fact_properties,
              fact.effective_from,fact.effective_to,fact.observed_at,fact.system_to,
              fact.source_snapshot_id,predicate.projects_as_edge,
              subject.id AS subject_id,subject.tenant_id AS subject_tenant_id,
              subject.namespace AS subject_namespace,subject.entity_type AS subject_entity_type,
              subject.canonical_key AS subject_canonical_key,subject.name AS subject_name,
              subject.properties AS subject_properties,subject.first_seen_at AS subject_first_seen_at,
              subject.last_seen_at AS subject_last_seen_at,
              object.id AS object_id,object.tenant_id AS object_tenant_id,
              object.namespace AS object_namespace,object.entity_type AS object_entity_type,
              object.canonical_key AS object_canonical_key,object.name AS object_name,
              object.properties AS object_properties,object.first_seen_at AS object_first_seen_at,
              object.last_seen_at AS object_last_seen_at
            FROM fact_assertion fact
            JOIN predicate_definition predicate ON predicate.predicate=fact.predicate
            JOIN entity subject ON subject.id=fact.subject_entity_id
            LEFT JOIN entity object ON object.id=fact.object_entity_id
            WHERE fact.id=%s
            """,
            (fact_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"projection fact {fact_id} does not exist")
        return row

    def _writer_for(self, deployment: GraphDeployment) -> GraphWriter:
        writer = self._writers.get(deployment.id)
        if writer is None:
            writer = self.writer_factory(deployment)  # type: ignore[call-arg]
            self._writers[deployment.id] = writer
        return writer

    def _mark_processed(self, batch: ClaimedBatch) -> None:
        outbox_ids = [delivery.outbox_id for delivery in batch.deliveries]
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE graph_projection_delivery
                SET status='PROCESSED',processed_at=now(),leased_by=NULL,leased_until=NULL,
                    last_error=NULL
                WHERE tenant_id=%s AND outbox_id=ANY(%s) AND leased_by=%s
                """,
                (batch.deployment.tenant_id, outbox_ids, self.worker_id),
            )
            deployment = self.connection.execute(
                """
                UPDATE tenant_graph_deployment
                SET projected_outbox_id=greatest(projected_outbox_id,%s),
                    projection_leased_by=NULL,projection_leased_until=NULL,
                    last_error=NULL,updated_at=now()
                WHERE id=%s AND projection_leased_by=%s
                RETURNING tenant_id,deployment_state,desired_outbox_id,projected_outbox_id
                """,
                (max(outbox_ids), batch.deployment.id, self.worker_id),
            ).fetchone()
            if deployment is None or deployment["deployment_state"] != "ACTIVE":
                return

            has_unprocessed_delivery = self.connection.execute(
                """
                SELECT EXISTS(
                  SELECT 1
                  FROM graph_projection_delivery
                  WHERE deployment_id=%s AND status<>'PROCESSED'
                ) AS present
                """,
                (batch.deployment.id,),
            ).fetchone()["present"]
            if (
                not has_unprocessed_delivery
                and deployment["projected_outbox_id"] >= deployment["desired_outbox_id"]
            ):
                self.connection.execute(
                    "SELECT stackgraph_request_graph_analysis(%s,%s,%s)",
                    (
                        deployment["tenant_id"],
                        deployment["projected_outbox_id"],
                        "PROJECTION_ADVANCED",
                    ),
                )

    def _record_failure(self, batch: ClaimedBatch, error: Exception) -> None:
        outbox_ids = [delivery.outbox_id for delivery in batch.deliveries]
        detail = {
            "error_type": type(error).__name__,
            "message": str(error)[:1000],
            "worker_id": self.worker_id,
        }
        with self.connection.transaction():
            terminal_rows = self.connection.execute(
                """
                UPDATE graph_projection_delivery
                SET status=CASE WHEN attempt>=%s THEN 'DEAD_LETTER' ELSE 'PENDING' END,
                    available_at=CASE WHEN attempt>=%s THEN available_at
                      ELSE now()+least(300,power(2,attempt)::integer)*interval '1 second' END,
                    leased_by=NULL,leased_until=NULL,last_error=%s
                WHERE tenant_id=%s AND outbox_id=ANY(%s) AND leased_by=%s
                RETURNING outbox_id,status
                """,
                (
                    self.max_attempts,
                    self.max_attempts,
                    Jsonb(detail),
                    batch.deployment.tenant_id,
                    outbox_ids,
                    self.worker_id,
                ),
            ).fetchall()
            terminal_ids = [row["outbox_id"] for row in terminal_rows if row["status"] == "DEAD_LETTER"]
            for outbox_id in terminal_ids:
                self.connection.execute(
                    """
                    INSERT INTO dead_letter(
                      tenant_id,source_kind,source_id,error_class,error_detail,replay_metadata
                    ) VALUES (%s,'NEO4J_PROJECTION',%s,%s,%s,%s)
                    """,
                    (
                        batch.deployment.tenant_id,
                        str(outbox_id),
                        type(error).__name__,
                        Jsonb(detail),
                        Jsonb({"deployment_id": str(batch.deployment.id)}),
                    ),
                )
            self.connection.execute(
                """
                UPDATE tenant_graph_deployment
                SET deployment_state=CASE WHEN %s THEN 'ERROR' ELSE deployment_state END,
                    projection_leased_by=NULL,projection_leased_until=NULL,
                    last_error=%s,updated_at=now()
                WHERE id=%s AND projection_leased_by=%s
                """,
                (bool(terminal_ids), Jsonb(detail), batch.deployment.id, self.worker_id),
            )


def register_deployment(
    database_url: str,
    *,
    tenant_id: UUID,
    endpoint: str,
    database_name: str,
    username: str,
    credential_reference: str,
    create_local_tenant: bool = False,
) -> UUID:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if create_local_tenant:
            connection.execute(
                """
                INSERT INTO tenant(id,tenant_key,name,status)
                VALUES (%s,%s,'Local workspace','ACTIVE')
                ON CONFLICT(id) DO NOTHING
                """,
                (tenant_id, f"local-{tenant_id.hex[:12]}"),
            )
        row = connection.execute(
            """
            INSERT INTO tenant_graph_deployment(
              tenant_id,endpoint,database_name,username,credential_reference,deployment_state
            ) VALUES (%s,%s,%s,%s,%s,'ACTIVE')
            ON CONFLICT(tenant_id) DO UPDATE SET
              endpoint=EXCLUDED.endpoint,database_name=EXCLUDED.database_name,
              username=EXCLUDED.username,credential_secret_id=NULL,
              credential_reference=EXCLUDED.credential_reference,
              deployment_state='ACTIVE',last_error=NULL,updated_at=now()
            RETURNING id
            """,
            (tenant_id, endpoint, database_name, username, credential_reference),
        ).fetchone()
        assert row is not None
        return row["id"]


def project_database(
    database_url: str,
    *,
    batch_size: int,
    max_batches: int | None,
    encryption_key: str,
) -> ProjectionResult:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as connection:
        worker = Neo4jProjectionWorker(
            connection,
            worker_id=worker_id,
            batch_size=batch_size,
            encryption_key=encryption_key,
        )
        return worker.run_until_empty(max_batches=max_batches)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project StackGraph's authoritative PostgreSQL graph into tenant Neo4j deployments"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser("register-local")
    register.add_argument("--tenant-id", type=UUID, required=True)
    register.add_argument("--endpoint", default=os.environ.get("STACKGRAPH_NEO4J_URI", "neo4j://neo4j:7687"))
    register.add_argument("--database", default=os.environ.get("STACKGRAPH_NEO4J_DATABASE", "neo4j"))
    register.add_argument("--username", default=os.environ.get("STACKGRAPH_NEO4J_USERNAME", "neo4j"))
    register.add_argument("--credential-reference", default="env://STACKGRAPH_NEO4J_PASSWORD")
    register.add_argument("--create-local-tenant", action="store_true")

    rebuild = subparsers.add_parser("rebuild")
    rebuild.add_argument("--tenant-id", type=UUID, required=True)
    rebuild.add_argument("--candidate-database", required=True)
    rebuild.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("STACKGRAPH_PROJECTION_BATCH_SIZE", "1000")),
    )

    for name in ("work", "serve"):
        worker = subparsers.add_parser(name)
        worker.add_argument(
            "--batch-size",
            type=int,
            default=int(os.environ.get("STACKGRAPH_PROJECTION_BATCH_SIZE", "100")),
        )
        worker.add_argument("--max-batches", type=int)
        if name == "serve":
            worker.add_argument("--poll-seconds", type=float, default=2.0)

    args = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")

    if args.command == "register-local":
        deployment_id = register_deployment(
            database_url,
            tenant_id=args.tenant_id,
            endpoint=args.endpoint,
            database_name=args.database,
            username=args.username,
            credential_reference=args.credential_reference,
            create_local_tenant=args.create_local_tenant,
        )
        print(json.dumps({"deployment_id": str(deployment_id)}, sort_keys=True))
        return

    if args.command == "rebuild":
        if args.batch_size < 1:
            parser.error("--batch-size must be at least 1")
        from .neo4j_rebuild import Neo4jBlueGreenRebuilder

        result = Neo4jBlueGreenRebuilder(
            database_url,
            encryption_key=os.environ.get(
                "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY",
                "stackgraph-local-development-credential-key",
            ),
            batch_size=args.batch_size,
        ).rebuild(args.tenant_id, args.candidate_database)
        print(json.dumps(asdict(result), sort_keys=True, default=str))
        return

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    poll_seconds = args.poll_seconds if args.command == "serve" else 0
    if poll_seconds < 0:
        parser.error("--poll-seconds must not be negative")
    encryption_key = os.environ.get(
        "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY",
        "stackgraph-local-development-credential-key",
    )
    while True:
        if poll_seconds > 0:
            record_service_heartbeat(
                database_url,
                "projection",
                metadata={
                    "backend": "neo4j",
                    "poll_seconds": poll_seconds,
                    "batch_size": args.batch_size,
                },
            )
        result = project_database(
            database_url,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            encryption_key=encryption_key,
        )
        print(json.dumps(asdict(result), sort_keys=True), flush=True)
        if poll_seconds == 0:
            break
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()

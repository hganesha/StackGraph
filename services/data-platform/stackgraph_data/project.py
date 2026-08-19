from __future__ import annotations

import argparse
import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


NODE_UPSERT_CYPHER = """
MERGE (entity:Entity {entity_id: $entity_id})
SET entity.tenant_id = $tenant_id,
    entity.namespace = $namespace,
    entity.entity_type = $entity_type,
    entity.canonical_key = $canonical_key,
    entity.name = $name,
    entity.properties_json = $properties_json,
    entity.first_seen_at = $first_seen_at,
    entity.last_seen_at = $last_seen_at
""".strip()

EDGE_DELETE_CYPHER = """
MATCH ()-[relationship:Relationship {logical_key: $logical_key}]->()
DELETE relationship
""".strip()

EDGE_CREATE_CYPHER = """
MATCH (source:Entity {entity_id: $source_entity_id}),
      (target:Entity {entity_id: $target_entity_id})
CREATE (source)-[relationship:Relationship {
    logical_key: $logical_key,
    fact_id: $fact_id,
    tenant_id: $tenant_id,
    relationship_type: $relationship_type,
    confidence: $confidence,
    assertion_class: $assertion_class,
    first_seen_at: $first_seen_at,
    last_seen_at: $last_seen_at,
    source_snapshot_id: $source_snapshot_id,
    evidence_fact_ids: $evidence_fact_ids,
    properties_json: $properties_json
}]->(target)
""".strip()


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    batches: int = 0
    claimed: int = 0
    processed: int = 0
    node_upserts: int = 0
    edge_upserts: int = 0
    edge_closures: int = 0


@dataclass(frozen=True, slots=True)
class ProjectionJob:
    id: int
    aggregate_id: UUID
    operation: str


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entity_parameters(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    def field(name: str) -> Any:
        return row[f"{prefix}{name}"]

    tenant_id = field("tenant_id")
    return {
        "entity_id": str(field("id")),
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "namespace": field("namespace"),
        "entity_type": field("entity_type"),
        "canonical_key": field("canonical_key"),
        "name": field("name"),
        "properties_json": _json_text(field("properties")),
        "first_seen_at": _timestamp(field("first_seen_at")),
        "last_seen_at": _timestamp(field("last_seen_at")),
    }


def edge_parameters(row: dict[str, Any]) -> dict[str, Any]:
    tenant_id = row["tenant_id"]
    first_seen_at = row["effective_from"] or row["observed_at"]
    last_seen_at = row["effective_to"] or row["observed_at"]
    confidence = row["confidence"]
    return {
        "source_entity_id": str(row["subject_id"]),
        "target_entity_id": str(row["object_id"]),
        "logical_key": row["logical_key"],
        "fact_id": str(row["fact_id"]),
        "tenant_id": str(tenant_id) if tenant_id is not None else None,
        "relationship_type": row["predicate"],
        "confidence": float(confidence) if isinstance(confidence, Decimal) else confidence,
        "assertion_class": row["assertion_class"],
        "first_seen_at": _timestamp(first_seen_at),
        "last_seen_at": _timestamp(last_seen_at),
        "source_snapshot_id": str(row["source_snapshot_id"]),
        "evidence_fact_ids": [str(row["fact_id"])],
        "properties_json": _json_text(row["fact_properties"]),
    }


class ProjectionWorker:
    def __init__(
        self,
        connection: Connection[dict[str, Any]],
        *,
        graph_name: str,
        worker_id: str,
        batch_size: int,
    ) -> None:
        if graph_name != "stackgraph":
            raise ValueError("only the initialized stackgraph graph is supported")
        self.connection = connection
        self.graph_name = graph_name
        self.worker_id = worker_id
        self.batch_size = batch_size
        self.batches = 0
        self.claimed = 0
        self.processed = 0
        self.node_upserts = 0
        self.edge_upserts = 0
        self.edge_closures = 0

    def run_until_empty(self, max_batches: int | None = None) -> ProjectionResult:
        self._prepare_age_session()
        while max_batches is None or self.batches < max_batches:
            jobs: list[ProjectionJob] = []
            try:
                with self.connection.transaction():
                    jobs = self._claim_jobs()
                    if not jobs:
                        break
                    for job in jobs:
                        self._project(job)
                    self._mark_processed(jobs)
            except Exception as error:
                self._record_failure(jobs, error)
                raise

            self.batches += 1
            self.claimed += len(jobs)
            self.processed += len(jobs)

        return ProjectionResult(
            batches=self.batches,
            claimed=self.claimed,
            processed=self.processed,
            node_upserts=self.node_upserts,
            edge_upserts=self.edge_upserts,
            edge_closures=self.edge_closures,
        )

    def _prepare_age_session(self) -> None:
        self.connection.execute("LOAD 'age'")
        self.connection.execute('SET search_path = ag_catalog, "$user", public')
        self.connection.execute(
            """
            SELECT create_vlabel(%s, 'Entity')
            WHERE NOT EXISTS (
                SELECT 1
                FROM ag_catalog.ag_label label
                JOIN ag_catalog.ag_graph graph ON graph.graphid = label.graph
                WHERE graph.name = %s AND label.name = 'Entity' AND label.kind = 'v'
            )
            """,
            (self.graph_name, self.graph_name),
        )
        self.connection.execute(
            """
            SELECT create_elabel(%s, 'Relationship')
            WHERE NOT EXISTS (
                SELECT 1
                FROM ag_catalog.ag_label label
                JOIN ag_catalog.ag_graph graph ON graph.graphid = label.graph
                WHERE graph.name = %s AND label.name = 'Relationship' AND label.kind = 'e'
            )
            """,
            (self.graph_name, self.graph_name),
        )
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_stackgraph_entity_properties_gin '
            'ON stackgraph."Entity" USING gin (properties)'
        )
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_stackgraph_relationship_properties_gin '
            'ON stackgraph."Relationship" USING gin (properties)'
        )

    def _claim_jobs(self) -> list[ProjectionJob]:
        rows = self.connection.execute(
            """
            WITH candidates AS (
                SELECT id
                FROM projection_outbox
                WHERE aggregate_type = 'FACT'
                  AND processed_at IS NULL
                  AND available_at <= now()
                  AND (leased_until IS NULL OR leased_until < now())
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE projection_outbox outbox
            SET leased_by = %s,
                leased_until = now() + interval '5 minutes',
                attempt = attempt + 1
            FROM candidates
            WHERE outbox.id = candidates.id
            RETURNING outbox.id, outbox.aggregate_id, outbox.operation
            """,
            (self.batch_size, self.worker_id),
        ).fetchall()
        return [
            ProjectionJob(
                id=row["id"],
                aggregate_id=row["aggregate_id"],
                operation=row["operation"],
            )
            for row in rows
        ]

    def _project(self, job: ProjectionJob) -> None:
        fact = self._load_fact(job.aggregate_id)
        if fact is None:
            raise RuntimeError(f"projection fact {job.aggregate_id} does not exist")

        is_current_upsert = job.operation == "UPSERT" and fact["system_to"] is None
        if not is_current_upsert:
            if fact["projects_as_edge"] and fact["object_id"] is not None:
                self._execute_cypher(
                    EDGE_DELETE_CYPHER,
                    {"logical_key": fact["logical_key"]},
                )
                self.edge_closures += 1
            return

        self._execute_cypher(NODE_UPSERT_CYPHER, entity_parameters(fact, "subject_"))
        self.node_upserts += 1

        if not fact["projects_as_edge"] or fact["object_id"] is None:
            return

        self._execute_cypher(NODE_UPSERT_CYPHER, entity_parameters(fact, "object_"))
        self.node_upserts += 1
        self._execute_cypher(
            EDGE_DELETE_CYPHER,
            {"logical_key": fact["logical_key"]},
        )
        self._execute_cypher(EDGE_CREATE_CYPHER, edge_parameters(fact))
        self.edge_upserts += 1

    def _load_fact(self, fact_id: UUID) -> dict[str, Any] | None:
        return self.connection.execute(
            """
            SELECT
                fact.id AS fact_id,
                fact.tenant_id,
                fact.predicate,
                fact.assertion_class,
                fact.confidence,
                fact.logical_key,
                fact.properties AS fact_properties,
                fact.effective_from,
                fact.effective_to,
                fact.observed_at,
                fact.system_to,
                fact.source_snapshot_id,
                predicate.projects_as_edge,
                subject.id AS subject_id,
                subject.tenant_id AS subject_tenant_id,
                subject.namespace AS subject_namespace,
                subject.entity_type AS subject_entity_type,
                subject.canonical_key AS subject_canonical_key,
                subject.name AS subject_name,
                subject.properties AS subject_properties,
                subject.first_seen_at AS subject_first_seen_at,
                subject.last_seen_at AS subject_last_seen_at,
                object.id AS object_id,
                object.tenant_id AS object_tenant_id,
                object.namespace AS object_namespace,
                object.entity_type AS object_entity_type,
                object.canonical_key AS object_canonical_key,
                object.name AS object_name,
                object.properties AS object_properties,
                object.first_seen_at AS object_first_seen_at,
                object.last_seen_at AS object_last_seen_at
            FROM fact_assertion fact
            JOIN predicate_definition predicate ON predicate.predicate = fact.predicate
            JOIN entity subject ON subject.id = fact.subject_entity_id
            LEFT JOIN entity object ON object.id = fact.object_entity_id
            WHERE fact.id = %s
            """,
            (fact_id,),
        ).fetchone()

    def _execute_cypher(self, query: str, parameters: dict[str, Any]) -> None:
        statement = (
            "SELECT * FROM cypher('stackgraph', $cypher$"
            + query
            + "$cypher$, %s::agtype) AS (result agtype)"
        )
        self.connection.execute(statement, (_json_text(parameters),))

    def _mark_processed(self, jobs: list[ProjectionJob]) -> None:
        ids = [job.id for job in jobs]
        self.connection.execute(
            """
            UPDATE projection_outbox
            SET processed_at = now(), leased_by = NULL, leased_until = NULL,
                last_error = NULL
            WHERE id = ANY(%s)
            """,
            (ids,),
        )

    def _record_failure(self, jobs: list[ProjectionJob], error: Exception) -> None:
        if not jobs:
            return
        ids = [job.id for job in jobs]
        self.connection.execute(
            """
            UPDATE projection_outbox
            SET leased_by = NULL,
                leased_until = NULL,
                attempt = attempt + 1,
                available_at = now() + interval '30 seconds',
                last_error = %s
            WHERE id = ANY(%s) AND processed_at IS NULL
            """,
            (
                Jsonb(
                    {
                        "error_type": type(error).__name__,
                        "message": str(error)[:1000],
                        "worker_id": self.worker_id,
                    }
                ),
                ids,
            ),
        )


def project_database(
    database_url: str,
    *,
    graph_name: str,
    batch_size: int,
    max_batches: int | None,
) -> ProjectionResult:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
    ) as connection:
        worker = ProjectionWorker(
            connection,
            graph_name=graph_name,
            worker_id=worker_id,
            batch_size=batch_size,
        )
        return worker.run_until_empty(max_batches=max_batches)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project StackGraph outbox facts into AGE")
    parser.add_argument(
        "--graph-name",
        default=os.environ.get("STACKGRAPH_GRAPH_NAME", "stackgraph"),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("STACKGRAPH_PROJECTION_BATCH_SIZE", "100")),
    )
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")

    result = project_database(
        database_url,
        graph_name=args.graph_name,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
    )
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .neo4j_project import (
    GraphDeployment,
    GraphInventory,
    GraphMutationBatch,
    Neo4jGraphWriter,
    ProjectionDelivery,
    build_mutation_batch,
    graph_inventory_from_sorted,
    resolve_credential_reference,
)


_FACT_COLUMNS = """
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
"""


@dataclass(frozen=True, slots=True)
class RebuildResult:
    tenant_id: UUID
    deployment_id: UUID
    prior_database_name: str
    active_database_name: str
    snapshot_outbox_id: int
    activated_outbox_id: int
    snapshot_facts: int
    catchup_deliveries: int
    inventory: GraphInventory
    postgres_extract_ms: float
    neo4j_write_ms: float
    validation_ms: float
    total_ms: float


@dataclass(frozen=True, slots=True)
class TimedBatch:
    rows: list[Any]
    fetch_seconds: float


def assert_graph_parity(expected: GraphInventory, actual: GraphInventory) -> None:
    if expected != actual:
        raise RuntimeError(
            "Neo4j candidate parity failed: "
            f"expected={json.dumps(asdict(expected), sort_keys=True)} "
            f"actual={json.dumps(asdict(actual), sort_keys=True)}"
        )


def _current_fact_batches(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID,
    batch_size: int,
) -> Iterator[TimedBatch]:
    cursor_id: UUID | None = None
    while True:
        fetch_started = time.perf_counter()
        rows = connection.execute(
            f"""
            SELECT {_FACT_COLUMNS}
            FROM fact_assertion fact
            JOIN predicate_definition predicate ON predicate.predicate=fact.predicate
            JOIN entity subject ON subject.id=fact.subject_entity_id
            LEFT JOIN entity object ON object.id=fact.object_entity_id
            WHERE fact.system_to IS NULL
              AND (fact.tenant_id IS NULL OR fact.tenant_id=%s)
              AND (%s::uuid IS NULL OR fact.id>%s::uuid)
            ORDER BY fact.id
            LIMIT %s
            """,
            (tenant_id, cursor_id, cursor_id, batch_size),
        ).fetchall()
        fetch_seconds = time.perf_counter() - fetch_started
        if not rows:
            return
        yield TimedBatch(rows=rows, fetch_seconds=fetch_seconds)
        cursor_id = rows[-1]["fact_id"]


def _outbox_batches(
    connection: Connection[dict[str, Any]],
    tenant_id: UUID,
    after_outbox_id: int,
    through_outbox_id: int,
    batch_size: int,
) -> Iterator[TimedBatch]:
    cursor_id = after_outbox_id
    while cursor_id < through_outbox_id:
        fetch_started = time.perf_counter()
        rows = connection.execute(
            f"""
            SELECT outbox.id AS outbox_id,outbox.aggregate_id,outbox.operation,{_FACT_COLUMNS}
            FROM projection_outbox outbox
            JOIN fact_assertion fact ON fact.id=outbox.aggregate_id
            JOIN predicate_definition predicate ON predicate.predicate=fact.predicate
            JOIN entity subject ON subject.id=fact.subject_entity_id
            LEFT JOIN entity object ON object.id=fact.object_entity_id
            WHERE outbox.aggregate_type='FACT'
              AND outbox.id>%s AND outbox.id<=%s
              AND (outbox.tenant_id IS NULL OR outbox.tenant_id=%s)
            ORDER BY outbox.id
            LIMIT %s
            """,
            (cursor_id, through_outbox_id, tenant_id, batch_size),
        ).fetchall()
        fetch_seconds = time.perf_counter() - fetch_started
        if not rows:
            return
        pairs = [
            (
                ProjectionDelivery(
                    outbox_id=int(row["outbox_id"]),
                    aggregate_id=row["aggregate_id"],
                    operation=row["operation"],
                ),
                row,
            )
            for row in rows
        ]
        yield TimedBatch(rows=pairs, fetch_seconds=fetch_seconds)
        cursor_id = int(rows[-1]["outbox_id"])


def _maximum_outbox(connection: Connection[dict[str, Any]], tenant_id: UUID) -> int:
    row = connection.execute(
        """
        SELECT coalesce(max(id),0) AS watermark
        FROM projection_outbox
        WHERE aggregate_type='FACT' AND (tenant_id IS NULL OR tenant_id=%s)
        """,
        (tenant_id,),
    ).fetchone()
    return int(row["watermark"] if row else 0)


def _expected_inventory(
    connection: Connection[dict[str, Any]], tenant_id: UUID, batch_size: int,
) -> tuple[GraphInventory, int]:
    with connection.cursor(name="stackgraph_rebuild_expected_nodes") as node_cursor:
        node_cursor.itersize = batch_size
        node_cursor.execute(
            """
            SELECT entity_id::text AS entity_id
            FROM (
              SELECT fact.subject_entity_id AS entity_id
              FROM fact_assertion fact
              WHERE fact.system_to IS NULL
                AND (fact.tenant_id IS NULL OR fact.tenant_id=%s)
              UNION
              SELECT fact.object_entity_id AS entity_id
              FROM fact_assertion fact
              JOIN predicate_definition predicate ON predicate.predicate=fact.predicate
              WHERE fact.system_to IS NULL AND predicate.projects_as_edge
                AND fact.object_entity_id IS NOT NULL
                AND (fact.tenant_id IS NULL OR fact.tenant_id=%s)
            ) visible_entity
            ORDER BY entity_id
            """,
            (tenant_id, tenant_id),
        )
        node_ids = (str(row["entity_id"]) for row in node_cursor)
        with connection.cursor(name="stackgraph_rebuild_expected_edges") as edge_cursor:
            edge_cursor.itersize = batch_size
            edge_cursor.execute(
                """
                SELECT DISTINCT fact.logical_key AS logical_key
                FROM fact_assertion fact
                JOIN predicate_definition predicate ON predicate.predicate=fact.predicate
                WHERE fact.system_to IS NULL AND predicate.projects_as_edge
                  AND fact.object_entity_id IS NOT NULL
                  AND (fact.tenant_id IS NULL OR fact.tenant_id=%s)
                ORDER BY fact.logical_key
                """,
                (tenant_id,),
            )
            relationship_keys = (str(row["logical_key"]) for row in edge_cursor)
            inventory = graph_inventory_from_sorted(node_ids, relationship_keys)

    fact_count = connection.execute(
        """
        SELECT count(*) AS fact_count FROM fact_assertion
        WHERE system_to IS NULL AND (tenant_id IS NULL OR tenant_id=%s)
        """,
        (tenant_id,),
    ).fetchone()["fact_count"]
    return inventory, int(fact_count)


class Neo4jBlueGreenRebuilder:
    def __init__(
        self,
        database_url: str,
        *,
        encryption_key: str,
        batch_size: int = 1000,
        writer_factory: type[Neo4jGraphWriter] = Neo4jGraphWriter,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.database_url = database_url
        self.encryption_key = encryption_key
        self.batch_size = batch_size
        self.writer_factory = writer_factory
        self.worker_id = f"rebuild:{socket.gethostname()}:{__import__('os').getpid()}"

    def rebuild(self, tenant_id: UUID, candidate_database_name: str) -> RebuildResult:
        started = time.perf_counter()
        extract_seconds = 0.0
        write_seconds = 0.0
        validation_seconds = 0.0
        snapshot_facts = 0
        catchup_deliveries = 0
        writer: Neo4jGraphWriter | None = None

        with psycopg.connect(
            self.database_url, row_factory=dict_row, autocommit=True,
        ) as control:
            deployment = self._begin(control, tenant_id, candidate_database_name)
            password = deployment["stored_password"] or resolve_credential_reference(
                deployment["credential_reference"]
            )
            target = GraphDeployment(
                id=deployment["id"],
                tenant_id=tenant_id,
                endpoint=deployment["endpoint"],
                database_name=candidate_database_name,
                username=deployment["username"],
                password=password,
            )
            try:
                writer = self.writer_factory(target)
                writer.reset()

                with psycopg.connect(self.database_url, row_factory=dict_row) as snapshot:
                    snapshot.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    snapshot_watermark = _maximum_outbox(snapshot, tenant_id)
                    for batch in _current_fact_batches(snapshot, tenant_id, self.batch_size):
                        extract_started = time.perf_counter()
                        pairs = [
                            (
                                ProjectionDelivery(
                                    outbox_id=0,
                                    aggregate_id=row["fact_id"],
                                    operation="UPSERT",
                                ),
                                row,
                            )
                            for row in batch.rows
                        ]
                        mutation = build_mutation_batch(pairs)
                        extract_seconds += batch.fetch_seconds + time.perf_counter() - extract_started
                        write_started = time.perf_counter()
                        writer.apply(mutation)
                        write_seconds += time.perf_counter() - write_started
                        snapshot_facts += len(batch.rows)
                        self._heartbeat(control, deployment["id"], snapshot_watermark)
                    snapshot.commit()

                candidate_watermark = snapshot_watermark
                while True:
                    target_watermark = _maximum_outbox(control, tenant_id)
                    if target_watermark > candidate_watermark:
                        with psycopg.connect(
                            self.database_url, row_factory=dict_row, autocommit=True,
                        ) as catchup:
                            for batch in _outbox_batches(
                                catchup, tenant_id, candidate_watermark,
                                target_watermark, self.batch_size,
                            ):
                                extract_started = time.perf_counter()
                                mutation = build_mutation_batch(batch.rows)
                                extract_seconds += (
                                    batch.fetch_seconds + time.perf_counter() - extract_started
                                )
                                write_started = time.perf_counter()
                                writer.apply(mutation)
                                write_seconds += time.perf_counter() - write_started
                                catchup_deliveries += len(batch.rows)
                                self._heartbeat(control, deployment["id"], target_watermark)
                        candidate_watermark = target_watermark

                    validation_started = time.perf_counter()
                    with psycopg.connect(self.database_url, row_factory=dict_row) as validation:
                        validation.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                        validation_watermark = _maximum_outbox(validation, tenant_id)
                        if validation_watermark > candidate_watermark:
                            validation.rollback()
                            continue
                        expected, _ = _expected_inventory(validation, tenant_id, self.batch_size)
                        actual = writer.inventory()
                        assert_graph_parity(expected, actual)
                        validation.commit()
                    validation_seconds += time.perf_counter() - validation_started
                    candidate_watermark = validation_watermark
                    break

                self._activate(
                    control,
                    deployment_id=deployment["id"],
                    tenant_id=tenant_id,
                    candidate_database_name=candidate_database_name,
                    prior_database_name=deployment["database_name"],
                    watermark=candidate_watermark,
                    inventory=actual,
                )
                return RebuildResult(
                    tenant_id=tenant_id,
                    deployment_id=deployment["id"],
                    prior_database_name=deployment["database_name"],
                    active_database_name=candidate_database_name,
                    snapshot_outbox_id=snapshot_watermark,
                    activated_outbox_id=candidate_watermark,
                    snapshot_facts=snapshot_facts,
                    catchup_deliveries=catchup_deliveries,
                    inventory=actual,
                    postgres_extract_ms=round(extract_seconds * 1000, 3),
                    neo4j_write_ms=round(write_seconds * 1000, 3),
                    validation_ms=round(validation_seconds * 1000, 3),
                    total_ms=round((time.perf_counter() - started) * 1000, 3),
                )
            except Exception as error:
                self._fail(control, deployment["id"], error)
                raise
            finally:
                if writer is not None:
                    writer.close()

    def _begin(
        self, control: Connection[dict[str, Any]], tenant_id: UUID, candidate_database_name: str,
    ) -> dict[str, Any]:
        with control.transaction():
            row = control.execute(
                """
                SELECT deployment.*,
                  CASE WHEN secret.id IS NULL THEN NULL
                       ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS stored_password
                FROM tenant_graph_deployment deployment
                LEFT JOIN tenant_secret secret ON secret.id=deployment.credential_secret_id
                  AND secret.tenant_id=deployment.tenant_id
                WHERE deployment.tenant_id=%s AND deployment.deployment_state='ACTIVE'
                  AND deployment.rebuild_state<>'RUNNING'
                  AND (deployment.projection_leased_until IS NULL OR deployment.projection_leased_until<now())
                FOR UPDATE OF deployment
                """,
                (self.encryption_key, tenant_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("active tenant graph deployment is unavailable or busy")
            if row["database_name"] == candidate_database_name:
                raise ValueError("candidate database must differ from the active database")
            control.execute(
                """
                UPDATE tenant_graph_deployment
                SET rebuild_state='RUNNING',candidate_database_name=%s,
                    rebuild_started_outbox_id=desired_outbox_id,
                    candidate_projected_outbox_id=0,rebuild_started_at=now(),
                    rebuild_metadata='{}',projection_leased_by=%s,
                    projection_leased_until=now()+interval '5 minutes',last_error=NULL,updated_at=now()
                WHERE id=%s
                """,
                (candidate_database_name, self.worker_id, row["id"]),
            )
        return row

    def _heartbeat(self, control: Connection[dict[str, Any]], deployment_id: UUID, watermark: int) -> None:
        updated = control.execute(
            """
            UPDATE tenant_graph_deployment
            SET projection_leased_until=now()+interval '5 minutes',
                candidate_projected_outbox_id=greatest(candidate_projected_outbox_id,%s),
                updated_at=now()
            WHERE id=%s AND rebuild_state='RUNNING' AND projection_leased_by=%s
            """,
            (watermark, deployment_id, self.worker_id),
        ).rowcount
        if updated != 1:
            raise RuntimeError("Neo4j rebuild lease was lost")

    def _activate(
        self,
        control: Connection[dict[str, Any]],
        *,
        deployment_id: UUID,
        tenant_id: UUID,
        candidate_database_name: str,
        prior_database_name: str,
        watermark: int,
        inventory: GraphInventory,
    ) -> None:
        with control.transaction():
            updated = control.execute(
                """
                UPDATE tenant_graph_deployment
                SET prior_database_name=%s,database_name=%s,
                    projected_outbox_id=%s,candidate_projected_outbox_id=%s,
                    rebuild_state='IDLE',candidate_database_name=NULL,
                    projection_leased_by=NULL,projection_leased_until=NULL,
                    last_rebuild_at=now(),last_reconciled_at=now(),
                    rebuild_metadata=%s,last_error=NULL,updated_at=now()
                WHERE id=%s AND tenant_id=%s AND rebuild_state='RUNNING'
                  AND projection_leased_by=%s
                """,
                (
                    prior_database_name,candidate_database_name,watermark,watermark,
                    Jsonb(asdict(inventory)),deployment_id,tenant_id,self.worker_id,
                ),
            ).rowcount
            if updated != 1:
                raise RuntimeError("Neo4j rebuild activation lost its lease")
            control.execute(
                """
                UPDATE graph_projection_delivery
                SET status='PROCESSED',processed_at=coalesce(processed_at,now()),
                    leased_by=NULL,leased_until=NULL,last_error=NULL
                WHERE deployment_id=%s AND outbox_id<=%s AND status<>'DEAD_LETTER'
                """,
                (deployment_id, watermark),
            )
            control.execute(
                "SELECT stackgraph_request_graph_analysis(%s,%s,'BLUE_GREEN_REBUILD')",
                (tenant_id, watermark),
            )

    def _fail(
        self, control: Connection[dict[str, Any]], deployment_id: UUID, error: Exception,
    ) -> None:
        control.execute(
            """
            UPDATE tenant_graph_deployment
            SET rebuild_state='FAILED',projection_leased_by=NULL,projection_leased_until=NULL,
                last_error=%s,updated_at=now()
            WHERE id=%s AND projection_leased_by=%s
            """,
            (
                Jsonb({"code":"BLUE_GREEN_REBUILD_FAILED","error_type":type(error).__name__,
                       "message":str(error)[:1000]}),
                deployment_id,self.worker_id,
            ),
        )

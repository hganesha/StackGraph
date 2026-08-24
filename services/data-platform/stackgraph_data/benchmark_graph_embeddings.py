from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

import psycopg
from neo4j import GraphDatabase
from psycopg.rows import dict_row

from .neo4j_project import resolve_credential_reference


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _latencies(operation: Callable[[], Any], iterations: int) -> dict[str, float]:
    values: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    return {
        "iterations": iterations,
        "p50_ms": round(_percentile(values, 0.50), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "p99_ms": round(_percentile(values, 0.99), 3),
        "mean_ms": round(statistics.fmean(values), 3),
        "max_ms": round(max(values), 3),
    }


def benchmark(
    database_url: str,
    tenant_id: UUID,
    *,
    iterations: int,
    encryption_key: str,
    synthetic_vector_count: int = 0,
    synthetic_vector_dimensions: int = 128,
) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as connection:
        connection.execute("SELECT set_config('app.tenant_id',%s,false)", (str(tenant_id),))
        graph_counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM entity WHERE tenant_id=%s) AS tenant_nodes,
              (SELECT count(*) FROM current_relationship
               WHERE tenant_id IS NULL OR tenant_id=%s) AS current_relationships,
              (SELECT count(*) FROM current_fact
               WHERE tenant_id IS NULL OR tenant_id=%s) AS current_facts
            """,
            (tenant_id, tenant_id, tenant_id),
        ).fetchone()

        relational = _latencies(
            lambda: connection.execute(
                """
                SELECT fact.id,fact.subject_entity_id,fact.object_entity_id,fact.predicate,
                       fact.confidence,fact.logical_key
                FROM current_fact fact
                WHERE fact.tenant_id IS NULL OR fact.tenant_id=%s
                ORDER BY fact.id LIMIT 1000
                """,
                (tenant_id,),
            ).fetchall(),
            iterations,
        )

        projection = connection.execute(
            """
            SELECT count(*) FILTER (WHERE status='PROCESSED') AS processed,
                   count(*) FILTER (WHERE status<>'PROCESSED') AS pending,
                   percentile_cont(0.5) WITHIN GROUP (
                     ORDER BY extract(epoch FROM processed_at-created_at)*1000
                   ) FILTER (WHERE processed_at IS NOT NULL) AS p50_end_to_end_ms,
                   percentile_cont(0.95) WITHIN GROUP (
                     ORDER BY extract(epoch FROM processed_at-created_at)*1000
                   ) FILTER (WHERE processed_at IS NOT NULL) AS p95_end_to_end_ms
            FROM graph_projection_delivery WHERE tenant_id=%s
            """,
            (tenant_id,),
        ).fetchone()

        active_space = connection.execute(
            """
            SELECT space.id,space.space_key,space.dimensions,count(embedding.entity_id) AS vectors
            FROM active_embedding_space active
            JOIN embedding_space space ON space.id=active.embedding_space_id
            LEFT JOIN entity_embedding embedding ON embedding.embedding_space_id=space.id
            WHERE active.tenant_id=%s AND active.space_kind='SEMANTIC_ENTITY'
              AND space.lifecycle_state='ACTIVE'
              AND space.coverage_ratio>=0.95
              AND coalesce((space.evaluation->>'passed')::boolean,false)
            GROUP BY space.id,space.space_key,space.dimensions
            """,
            (tenant_id,),
        ).fetchone()
        exact_vector: dict[str, Any]
        if active_space and int(active_space["vectors"] or 0) > 0:
            samples = connection.execute(
                """
                SELECT embedding::text AS query_vector
                FROM entity_embedding
                WHERE tenant_id=%s AND embedding_space_id=%s
                ORDER BY entity_id LIMIT %s
                """,
                (tenant_id, active_space["id"], min(iterations, 20)),
            ).fetchall()
            index = 0

            def exact_search() -> None:
                nonlocal index
                query_vector = samples[index % len(samples)]["query_vector"]
                index += 1
                connection.execute(
                    """
                    SELECT entity_id,1-(embedding<=>%s::vector) AS similarity
                    FROM entity_embedding
                    WHERE tenant_id=%s AND embedding_space_id=%s
                    ORDER BY embedding<=>%s::vector,entity_id LIMIT 10
                    """,
                    (query_vector, tenant_id, active_space["id"], query_vector),
                ).fetchall()

            exact_vector = {
                "status": "measured",
                "space_key": active_space["space_key"],
                "dimensions": int(active_space["dimensions"]),
                "vectors": int(active_space["vectors"]),
                **_latencies(exact_search, iterations),
                "ann_enabled": False,
            }
        elif synthetic_vector_count > 0:
            connection.execute(
                f"CREATE TEMP TABLE stackgraph_exact_vector_benchmark("
                f"id integer PRIMARY KEY,tenant_id uuid NOT NULL,embedding vector({synthetic_vector_dimensions}) NOT NULL)"
            )
            rows = []
            for row_id in range(synthetic_vector_count):
                values = [
                    math.sin((row_id + 1) * (dimension + 1) * 0.017)
                    for dimension in range(synthetic_vector_dimensions)
                ]
                rows.append((row_id, tenant_id, "[" + ",".join(f"{value:.8f}" for value in values) + "]"))
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO stackgraph_exact_vector_benchmark(id,tenant_id,embedding) "
                    "VALUES (%s,%s,%s::vector)",
                    rows,
                )
            connection.execute(
                "CREATE INDEX stackgraph_exact_vector_tenant ON stackgraph_exact_vector_benchmark(tenant_id)"
            )
            connection.execute("ANALYZE stackgraph_exact_vector_benchmark")
            query_vectors = [rows[index % len(rows)][2] for index in range(min(iterations, 20))]
            index = 0

            def synthetic_exact_search() -> None:
                nonlocal index
                query_vector = query_vectors[index % len(query_vectors)]
                index += 1
                connection.execute(
                    """
                    SELECT id,1-(embedding<=>%s::vector) AS similarity
                    FROM stackgraph_exact_vector_benchmark
                    WHERE tenant_id=%s
                    ORDER BY embedding<=>%s::vector,id LIMIT 10
                    """,
                    (query_vector, tenant_id, query_vector),
                ).fetchall()

            exact_vector = {
                "status": "measured",
                "synthetic": True,
                "dimensions": synthetic_vector_dimensions,
                "vectors": synthetic_vector_count,
                **_latencies(synthetic_exact_search, iterations),
                "ann_enabled": False,
            }
        else:
            exact_vector = {
                "status": "skipped",
                "reason": "NO_QUALIFIED_ACTIVE_SEMANTIC_SPACE",
                "ann_enabled": False,
            }

        deployment = connection.execute(
            """
            SELECT deployment.*,
              CASE WHEN secret.id IS NULL THEN NULL
                   ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS stored_password
            FROM tenant_graph_deployment deployment
            LEFT JOIN tenant_secret secret ON secret.id=deployment.credential_secret_id
              AND secret.tenant_id=deployment.tenant_id
            WHERE deployment.tenant_id=%s AND deployment.deployment_state='ACTIVE'
            """,
            (encryption_key, tenant_id),
        ).fetchone()
        latest_runs = connection.execute(
            """
            SELECT DISTINCT ON (policy_key) policy_key,node_count,edge_count,resource_usage,
                   status,completed_at
            FROM graph_analysis_run
            WHERE tenant_id=%s AND status IN ('SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS')
            ORDER BY policy_key,completed_at DESC
            """,
            (tenant_id,),
        ).fetchall()

    neo4j_result: dict[str, Any]
    if deployment is None:
        neo4j_result = {"status": "skipped", "reason": "NO_ACTIVE_DEPLOYMENT"}
    else:
        password = deployment["stored_password"] or resolve_credential_reference(
            deployment["credential_reference"]
        )
        driver = GraphDatabase.driver(
            deployment["endpoint"], auth=(deployment["username"], password),
        )
        try:
            def neo4j_count() -> None:
                driver.execute_query(
                    "MATCH (entity:Entity) WITH count(entity) AS node_count "
                    "CALL () { MATCH ()-[relationship:Relationship]->() "
                    "RETURN count(relationship) AS edge_count } "
                    "RETURN node_count,edge_count",
                    database_=deployment["database_name"],
                    routing_="r",
                )

            neo4j_result = {
                "status": "measured",
                "database_name": deployment["database_name"],
                "desired_outbox_id": int(deployment["desired_outbox_id"]),
                "projected_outbox_id": int(deployment["projected_outbox_id"]),
                **_latencies(neo4j_count, iterations),
            }
        finally:
            driver.close()

    return {
        "schema_version": "graph-embeddings-benchmark/v1",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": str(tenant_id),
        "corpus": {key: int(value or 0) for key, value in graph_counts.items()},
        "postgres_current_fact_extract_1000": relational,
        "projection_delivery_end_to_end": {
            key: round(float(value), 3) if value is not None else 0
            for key, value in projection.items()
        },
        "neo4j_bounded_count": neo4j_result,
        "exact_pgvector_top10": exact_vector,
        "latest_gds_runs": [
            {
                **dict(row),
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            }
            for row in latest_runs
        ],
        "interpretation": {
            "projection_delivery_end_to_end_includes_queue_wait": True,
            "gds_timings_are_worker-recorded_and_separate_from_projection_delivery": True,
            "ann_intentionally_disabled_until_exact_slo_is_missed": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark tenant graph and exact vector serving paths")
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--synthetic-vector-count", type=int, default=0)
    parser.add_argument("--synthetic-vector-dimensions", type=int, default=128)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 1000:
        parser.error("--iterations must be between 1 and 1000")
    if args.synthetic_vector_count < 0 or args.synthetic_vector_count > 1_000_000:
        parser.error("--synthetic-vector-count must be between 0 and 1000000")
    if args.synthetic_vector_dimensions < 8 or args.synthetic_vector_dimensions > 4096:
        parser.error("--synthetic-vector-dimensions must be between 8 and 4096")
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    report = benchmark(
        database_url,
        args.tenant_id,
        iterations=args.iterations,
        synthetic_vector_count=args.synthetic_vector_count,
        synthetic_vector_dimensions=args.synthetic_vector_dimensions,
        encryption_key=os.environ.get(
            "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY",
            "stackgraph-local-development-credential-key",
        ),
    )
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from uuid import UUID

import psycopg
from neo4j import GraphDatabase, Query
from neo4j import Driver as Neo4jDriver
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .algorithms import (
    BridgeResult,
    CircularDependencyMotif,
    CohortAnomaly,
    MaterializedImpactPath,
    RankedMetric,
    articulation_points_and_bridges,
    circular_dependency_motifs,
    cohort_percentile_anomalies,
    materialize_impact_paths,
    rank_metrics,
    reachability_metrics,
)
from .embeddings import vector_literal


PROJECT_CYPHER = """
MATCH (source:Entity)
WHERE source.entity_type IN $entity_types
  AND (source.tenant_id IS NULL OR source.tenant_id=$tenant_id)
OPTIONAL MATCH (source)-[relationship:Relationship]->(target:Entity)
WHERE target.entity_type IN $entity_types
  AND (target.tenant_id IS NULL OR target.tenant_id=$tenant_id)
  AND relationship.relationship_type IN $predicates
  AND relationship.assertion_class IN $assertion_classes
  AND relationship.confidence >= $confidence_minimum
  AND (relationship.tenant_id IS NULL OR relationship.tenant_id=$tenant_id)
WITH source,target,relationship,
  coalesce($directions[relationship.relationship_type],'OUT') AS direction
WITH relationship,
  CASE
    WHEN relationship IS NULL THEN [[source,null]]
    WHEN direction='IN' THEN [[target,source]]
    WHEN direction='BOTH' THEN [[source,target],[target,source]]
    ELSE [[source,target]]
  END AS endpoint_pairs
UNWIND endpoint_pairs AS endpoints
RETURN gds.graph.project(
  $graph_name,
  endpoints[0],
  endpoints[1],
  CASE WHEN relationship IS NULL THEN {}
       ELSE {
         relationshipType: relationship.relationship_type,
         relationshipProperties: {confidence: relationship.confidence}
       }
  END,
  {readConcurrency: $read_concurrency}
) AS projection
""".strip()

EDGE_QUERY = """
MATCH (source:Entity)-[relationship:Relationship]->(target:Entity)
WHERE source.entity_type IN $entity_types
  AND target.entity_type IN $entity_types
  AND (source.tenant_id IS NULL OR source.tenant_id=$tenant_id)
  AND (target.tenant_id IS NULL OR target.tenant_id=$tenant_id)
  AND (relationship.tenant_id IS NULL OR relationship.tenant_id=$tenant_id)
  AND relationship.relationship_type IN $predicates
  AND relationship.assertion_class IN $assertion_classes
  AND relationship.confidence >= $confidence_minimum
RETURN source.entity_id AS source_entity_id,
       target.entity_id AS target_entity_id,
       relationship.fact_id AS fact_id,
       relationship.relationship_type AS relationship_type,
       relationship.confidence AS confidence
ORDER BY relationship.fact_id
""".strip()

NODE_QUERY = """
MATCH (entity:Entity)
WHERE entity.entity_type IN $entity_types
  AND (entity.tenant_id IS NULL OR entity.tenant_id=$tenant_id)
RETURN entity.entity_id AS entity_id,entity.entity_type AS entity_type
ORDER BY entity.entity_id
""".strip()


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    id: UUID
    tenant_id: UUID
    policy_id: UUID
    policy_key: str
    policy_version: int
    policy_hash: str
    configuration: dict[str, Any]
    requested_watermark: int
    projected_watermark: int
    run_id: UUID
    deployment_id: UUID
    endpoint: str
    database_name: str
    username: str
    password: str
    attempt: int


@dataclass(frozen=True, slots=True)
class EdgeMetric:
    fact_id: str
    source_entity_id: str
    target_entity_id: str
    metric_key: str
    numeric_value: float
    components: dict[str, object]
    limitations: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class CommunityMembership:
    entity_id: str
    algorithm_key: str
    community_key: str
    score: float | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class StructuralEmbedding:
    entity_id: str
    values: tuple[float,...]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    graph_name: str
    node_count: int
    edge_count: int
    metrics: tuple[RankedMetric, ...]
    edge_metrics: tuple[EdgeMetric, ...]
    communities: tuple[CommunityMembership, ...]
    impact_paths: tuple[MaterializedImpactPath, ...]
    algorithm_versions: dict[str, object]
    coverage: dict[str, object]
    resource_usage: dict[str, object]
    limitations: tuple[dict[str, object], ...]
    structural_embeddings: tuple[StructuralEmbedding,...] = ()
    anomalies: tuple[CohortAnomaly,...] = ()
    circular_motifs: tuple[CircularDependencyMotif,...] = ()


@dataclass(frozen=True, slots=True)
class WorkerResult:
    claimed: bool
    request_id: str | None = None
    run_id: str | None = None
    status: str = "IDLE"
    node_count: int = 0
    edge_count: int = 0
    metric_count: int = 0


def validate_projection_budget(
    node_count: int,
    relationship_count: int,
    estimate: Mapping[str, object],
    budget: Mapping[str, object],
) -> None:
    max_nodes = int(budget.get("max_nodes", node_count))
    max_edges = int(budget.get("max_edges", relationship_count))
    if node_count > max_nodes:
        raise RuntimeError(f"policy node budget exceeded: {node_count}>{max_nodes}")
    if relationship_count > max_edges:
        raise RuntimeError(
            f"policy edge budget exceeded: {relationship_count}>{max_edges}"
        )
    max_memory_bytes = budget.get("max_memory_bytes")
    if max_memory_bytes is not None and int(estimate.get("bytesMax", 0)) > int(max_memory_bytes):
        raise RuntimeError(
            "policy projection memory budget exceeded: "
            f"{int(estimate['bytesMax'])}>{int(max_memory_bytes)}"
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


def _policy_parameters(request: AnalysisRequest) -> dict[str, object]:
    configuration = request.configuration
    directions = dict(configuration.get("directions", {}))
    return {
        "tenant_id": str(request.tenant_id),
        "entity_types": list(configuration.get("entity_types", [])),
        "predicates": list(configuration.get("predicates", [])),
        "assertion_classes": list(configuration.get("assertion_classes", [])),
        "confidence_minimum": float(configuration.get("confidence_minimum", 0.0)),
        "directions": directions,
    }


class Neo4jGdsAnalyzer:
    def __init__(
        self,
        request: AnalysisRequest,
        *,
        concurrency: int = 2,
        query_timeout_seconds: int = 900,
        exact_reachability_node_limit: int = 10_000,
        bridge_node_limit: int = 100_000,
        max_projection_memory_bytes: int = 5_368_709_120,
        heartbeat: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self.request = request
        self.concurrency = max(1, concurrency)
        self.query_timeout_seconds = query_timeout_seconds
        self.exact_reachability_node_limit = exact_reachability_node_limit
        self.bridge_node_limit = bridge_node_limit
        self.max_projection_memory_bytes = max_projection_memory_bytes
        self.heartbeat = heartbeat or (lambda _stage, _job_id=None: None)
        self.neo4j_query_wall_seconds = 0.0
        self.neo4j_result_available_ms = 0
        self.neo4j_result_consumed_ms = 0
        self.driver: Neo4jDriver = GraphDatabase.driver(
            request.endpoint,auth=(request.username,request.password)
        )
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    def _query(self, cypher: str, parameters: Mapping[str, object] | None = None):
        started = time.monotonic()
        records, summary, keys = self.driver.execute_query(
            Query(cypher, timeout=self.query_timeout_seconds),
            parameters_=dict(parameters or {}),
            database_=self.request.database_name,
        )
        self.neo4j_query_wall_seconds += time.monotonic() - started
        self.neo4j_result_available_ms += int(getattr(summary, "result_available_after", 0) or 0)
        self.neo4j_result_consumed_ms += int(getattr(summary, "result_consumed_after", 0) or 0)
        return records, summary, keys

    def _resource_usage(
        self,
        started: float,
        *,
        gds_projection_seconds: float,
        gds_projection_estimate: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        server_seconds = (self.neo4j_result_available_ms + self.neo4j_result_consumed_ms) / 1000
        usage: dict[str, object] = {
            "wall_seconds": round(time.monotonic() - started, 6),
            "gds_concurrency": self.concurrency,
            "gds_projection_seconds": round(gds_projection_seconds, 6),
            "neo4j_query_wall_seconds": round(self.neo4j_query_wall_seconds, 6),
            "neo4j_server_result_available_ms": self.neo4j_result_available_ms,
            "neo4j_server_result_consumed_ms": self.neo4j_result_consumed_ms,
            "neo4j_client_and_transfer_overhead_seconds": round(
                max(0.0, self.neo4j_query_wall_seconds - server_seconds), 6,
            ),
        }
        if gds_projection_estimate:
            usage["gds_projection_estimate"] = dict(gds_projection_estimate)
        return usage

    def _stream_metric(
        self,
        cypher: str,
        parameters: Mapping[str, object],
        metric_key: str,
        components: Mapping[str, object],
        *,
        limitations: tuple[dict[str, object], ...] = (),
    ) -> list[RankedMetric]:
        records, _, _ = self._query(cypher, parameters)
        return rank_metrics(
            metric_key,
            (
                (record["entity_id"],record["score"],dict(components))
                for record in records
                if record["entity_id"] is not None and record["score"] is not None
            ),
            limitations=limitations,
        )

    def analyze(self) -> AnalysisResult:
        started = time.monotonic()
        gds_projection_seconds = 0.0
        gds_projection_estimate: dict[str, object] = {}
        graph_name = f"sg_{str(self.request.tenant_id).replace('-', '')[:12]}_{self.request.policy_key.replace('-', '_')}_{str(self.request.run_id).replace('-', '')[:12]}"
        policy = _policy_parameters(self.request)
        policy["graph_name"] = graph_name
        policy["read_concurrency"] = self.concurrency
        job_prefix = str(self.request.run_id)
        limitations: list[dict[str, object]] = []

        try:
            node_records, _, _ = self._query(
                "MATCH (entity:Entity) "
                "WHERE entity.entity_type IN $entity_types "
                "AND (entity.tenant_id IS NULL OR entity.tenant_id=$tenant_id) "
                "RETURN count(entity) AS node_count",
                policy,
            )
            estimated_node_count = int(node_records[0]["node_count"])
            if estimated_node_count == 0:
                version_records, _, _ = self._query("RETURN gds.version() AS gds_version")
                empty_limitation = {
                    "code":"EMPTY_POLICY_GRAPH",
                    "message":"No projected entities matched this analysis policy.",
                }
                return AnalysisResult(
                    graph_name=graph_name,node_count=0,edge_count=0,metrics=(),
                    edge_metrics=(),communities=(),impact_paths=(),
                    algorithm_versions={
                        "neo4j_gds":version_records[0]["gds_version"],"worker":"1.0.0"
                    },
                    coverage={
                        "policy_hash":self.request.policy_hash,
                        "entity_types":policy["entity_types"],"predicates":policy["predicates"],
                        "assertion_classes":policy["assertion_classes"],
                        "confidence_minimum":policy["confidence_minimum"],
                    },
                    resource_usage=self._resource_usage(
                        started,gds_projection_seconds=gds_projection_seconds,
                    ),
                    limitations=(empty_limitation,),
                )
            edge_count_records, _, _ = self._query(
                "MATCH (source:Entity)-[relationship:Relationship]->(target:Entity) "
                "WHERE source.entity_type IN $entity_types "
                "AND target.entity_type IN $entity_types "
                "AND (source.tenant_id IS NULL OR source.tenant_id=$tenant_id) "
                "AND (target.tenant_id IS NULL OR target.tenant_id=$tenant_id) "
                "AND (relationship.tenant_id IS NULL OR relationship.tenant_id=$tenant_id) "
                "AND relationship.relationship_type IN $predicates "
                "AND relationship.assertion_class IN $assertion_classes "
                "AND relationship.confidence >= $confidence_minimum "
                "RETURN coalesce(sum(CASE WHEN "
                "coalesce($directions[relationship.relationship_type],'OUT')='BOTH' "
                "THEN 2 ELSE 1 END),0) AS relationship_count",
                policy,
            )
            estimated_edge_count = int(edge_count_records[0]["relationship_count"])
            estimate_records, _, _ = self._query(
                "CALL gds.graph.project.estimate('*','*',{"
                "nodeCount:$node_count,relationshipCount:$relationship_count,"
                "readConcurrency:$read_concurrency}) "
                "YIELD requiredMemory,bytesMin,bytesMax,nodeCount,relationshipCount "
                "RETURN requiredMemory,bytesMin,bytesMax,nodeCount,relationshipCount",
                {
                    "node_count":estimated_node_count,
                    "relationship_count":estimated_edge_count,
                    "read_concurrency":self.concurrency,
                },
            )
            gds_projection_estimate = dict(estimate_records[0])
            budget = dict(self.request.configuration.get("projection_budget", {}))
            budget.setdefault("max_memory_bytes",self.max_projection_memory_bytes)
            gds_projection_estimate["budgetBytes"] = int(budget["max_memory_bytes"])
            validate_projection_budget(
                estimated_node_count,estimated_edge_count,gds_projection_estimate,budget,
            )
            self._query(
                "CALL gds.graph.exists($graph_name) YIELD exists "
                "WITH exists WHERE exists "
                "CALL gds.graph.drop($graph_name,false) YIELD graphName RETURN graphName",
                {"graph_name": graph_name},
            )
            self.heartbeat("PREPARING",f"{job_prefix}:project")
            projection_started = time.monotonic()
            projection_records, _, _ = self._query(PROJECT_CYPHER,policy)
            gds_projection_seconds = time.monotonic() - projection_started
            projection = dict(projection_records[0]["projection"])
            node_count = int(projection["nodeCount"])
            edge_count = int(projection["relationshipCount"])
            validate_projection_budget(node_count,edge_count,gds_projection_estimate,budget)

            version_records, _, _ = self._query(
                "RETURN gds.version() AS gds_version"
            )
            gds_version = version_records[0]["gds_version"]
            common = {
                "graph_name": graph_name,
                "concurrency": self.concurrency,
            }
            metrics: list[RankedMetric] = []

            self.heartbeat("LIGHTWEIGHT",f"{job_prefix}:degree-out")
            metrics.extend(
                self._stream_metric(
                    "CALL gds.degree.stream($graph_name,{orientation:'NATURAL',concurrency:$concurrency,jobId:$job_id}) "
                    "YIELD nodeId,score RETURN gds.util.asNode(nodeId).entity_id AS entity_id,score",
                    {**common,"job_id":f"{job_prefix}:degree-out"},
                    "degree.out",{"orientation":"NATURAL"},
                )
            )
            metrics.extend(
                self._stream_metric(
                    "CALL gds.degree.stream($graph_name,{orientation:'REVERSE',concurrency:$concurrency,jobId:$job_id}) "
                    "YIELD nodeId,score RETURN gds.util.asNode(nodeId).entity_id AS entity_id,score",
                    {**common,"job_id":f"{job_prefix}:degree-in"},
                    "degree.in",{"orientation":"REVERSE"},
                )
            )

            self.heartbeat("LIGHTWEIGHT",f"{job_prefix}:pagerank")
            metrics.extend(
                self._stream_metric(
                    "CALL gds.pageRank.stream($graph_name,{concurrency:$concurrency,maxIterations:20,dampingFactor:0.85,jobId:$job_id}) "
                    "YIELD nodeId,score RETURN gds.util.asNode(nodeId).entity_id AS entity_id,score",
                    {**common,"job_id":f"{job_prefix}:pagerank"},
                    "pagerank",{"max_iterations":20,"damping_factor":0.85},
                )
            )

            edge_records, _, _ = self._query(EDGE_QUERY,policy)
            node_records, _, _ = self._query(NODE_QUERY,policy)
            node_kinds = {
                record["entity_id"]:record["entity_type"] for record in node_records
                if record["entity_id"] is not None
            }
            node_ids = [metric.entity_id for metric in metrics if metric.metric_key == "degree.out"]
            directed_edges: list[tuple[str,str]] = []
            directed_evidence_edges: list[tuple[str,str,str,float]] = []
            undirected_edges: list[tuple[str,str,str]] = []
            directions = dict(self.request.configuration.get("directions", {}))
            for record in edge_records:
                source = record["source_entity_id"]
                target = record["target_entity_id"]
                fact_id = record["fact_id"]
                direction = directions.get(record["relationship_type"],"OUT")
                if direction == "IN":
                    source,target = target,source
                directed_edges.append((source,target))
                directed_evidence_edges.append((
                    source,target,fact_id,float(record["confidence"] or 0)
                ))
                if direction == "BOTH":
                    directed_edges.append((target,source))
                    directed_evidence_edges.append((
                        target,source,fact_id,float(record["confidence"] or 0)
                    ))
                undirected_edges.append((source,target,fact_id))

            reach = reachability_metrics(
                node_ids,directed_edges,
                exact_node_limit=self.exact_reachability_node_limit,
            )
            impact_reach = reachability_metrics(
                node_ids,((target,source) for source,target in directed_edges),
                exact_node_limit=self.exact_reachability_node_limit,
            )
            limited_reach_entities = reach.limited_entities|impact_reach.limited_entities
            reach_limitation = ({
                "code":"BOUNDED_REACHABILITY",
                "message":"Reachability used depth and visit caps for this graph size.",
                "affected_entity_count":len(limited_reach_entities),
            },) if limited_reach_entities else ()
            if reach_limitation:
                limitations.extend(reach_limitation)
            metrics.extend(rank_metrics(
                "reachability.downstream",
                ((entity_id,value,{"exact":entity_id not in reach.limited_entities}) for entity_id,value in reach.reachable.items()),
                limitations=reach_limitation,
            ))
            metrics.extend(rank_metrics(
                "reachability.depth",
                ((entity_id,value,{"exact":entity_id not in reach.limited_entities}) for entity_id,value in reach.depth.items()),
                limitations=reach_limitation,
            ))
            metrics.extend(rank_metrics(
                "reachability.upstream_impact",
                ((entity_id,value,{"exact":entity_id not in impact_reach.limited_entities}) for entity_id,value in impact_reach.reachable.items()),
                limitations=reach_limitation,
            ))
            metrics.extend(rank_metrics(
                "reachability.upstream_depth",
                ((entity_id,value,{"exact":entity_id not in impact_reach.limited_entities}) for entity_id,value in impact_reach.depth.items()),
                limitations=reach_limitation,
            ))

            bridge_result = BridgeResult(frozenset(),frozenset())
            if node_count <= self.bridge_node_limit:
                prior_limit = sys.getrecursionlimit()
                try:
                    sys.setrecursionlimit(max(prior_limit,node_count+100))
                    bridge_result = articulation_points_and_bridges(node_ids,undirected_edges)
                finally:
                    sys.setrecursionlimit(prior_limit)
                metrics.extend(rank_metrics(
                    "spof.articulation",
                    ((entity_id,1.0,{"algorithm":"tarjan"}) for entity_id in bridge_result.articulation_entities),
                ))
            else:
                limitations.append({
                    "code":"SPOF_SIZE_GATE",
                    "message":"Articulation and bridge detection skipped above the configured node gate.",
                    "node_limit":self.bridge_node_limit,
                })

            if edge_count == 0:
                metrics.extend(rank_metrics(
                    "betweenness",
                    ((entity_id,0.0,{"exact":True,"reason":"NO_RELATIONSHIPS"}) for entity_id in node_ids),
                ))
            else:
                self.heartbeat("HEAVYWEIGHT",f"{job_prefix}:betweenness")
                sampling_size = min(node_count,max(100,int(max(1,node_count) ** 0.5 * 10)))
                betweenness_limitations = ({
                    "code":"APPROXIMATE_BETWEENNESS",
                    "message":"Betweenness uses deterministic node sampling.",
                    "sampling_size":sampling_size,
                    "sampling_seed":42,
                },)
                metrics.extend(
                    self._stream_metric(
                        "CALL gds.betweenness.stream($graph_name,{concurrency:$concurrency,samplingSize:$sampling_size,samplingSeed:42,jobId:$job_id}) "
                        "YIELD nodeId,score RETURN gds.util.asNode(nodeId).entity_id AS entity_id,score",
                        {**common,"sampling_size":sampling_size,"job_id":f"{job_prefix}:betweenness"},
                        "betweenness",{"sampling_size":sampling_size,"sampling_seed":42},
                        limitations=betweenness_limitations,
                    )
                )
                limitations.extend(betweenness_limitations)

            self.heartbeat("HEAVYWEIGHT",f"{job_prefix}:wcc")
            community_records, _, _ = self._query(
                "CALL gds.wcc.stream($graph_name,{concurrency:$concurrency,jobId:$job_id}) "
                "YIELD nodeId,componentId RETURN gds.util.asNode(nodeId).entity_id AS entity_id,componentId",
                {**common,"job_id":f"{job_prefix}:wcc"},
            )
            communities = tuple(
                CommunityMembership(
                    entity_id=record["entity_id"],algorithm_key="wcc",
                    community_key=str(record["componentId"]),score=None,
                    metadata={"algorithm":"weakly_connected_components"},
                )
                for record in community_records if record["entity_id"] is not None
            )
            structural_embeddings: tuple[StructuralEmbedding,...] = ()
            structural_configuration = dict(self.request.configuration.get("structural_embedding",{}))
            if structural_configuration.get("enabled") and edge_count>0:
                dimensions = int(structural_configuration.get("dimensions",128))
                max_nodes = int(structural_configuration.get("max_nodes",200_000))
                if node_count>max_nodes:
                    limitations.append({
                        "code":"STRUCTURAL_EMBEDDING_SIZE_GATE",
                        "message":"Node2Vec was skipped above its configured graph-size gate.",
                        "node_count":node_count,"max_nodes":max_nodes,
                    })
                else:
                    self.heartbeat("HEAVYWEIGHT",f"{job_prefix}:node2vec")
                    try:
                        embedding_records,_,_ = self._query(
                            "CALL gds.node2vec.stream($graph_name,{embeddingDimension:$dimensions,"
                            "walkLength:$walk_length,walksPerNode:$walks_per_node,randomSeed:$random_seed,"
                            "concurrency:$concurrency,jobId:$job_id}) YIELD nodeId,embedding "
                            "RETURN gds.util.asNode(nodeId).entity_id AS entity_id,embedding",
                            {
                                **common,"dimensions":dimensions,
                                "walk_length":int(structural_configuration.get("walk_length",80)),
                                "walks_per_node":int(structural_configuration.get("walks_per_node",10)),
                                "random_seed":int(structural_configuration.get("random_seed",42)),
                                "job_id":f"{job_prefix}:node2vec",
                            },
                        )
                        structural_embeddings = tuple(
                            StructuralEmbedding(
                                entity_id=record["entity_id"],
                                values=tuple(float(value) for value in record["embedding"]),
                            )
                            for record in embedding_records if record["entity_id"] is not None
                        )
                    except Exception as error:
                        limitations.append({
                            "code":"STRUCTURAL_EMBEDDING_UNAVAILABLE",
                            "message":"The deterministic graph snapshot succeeded, but Node2Vec was unavailable.",
                            "error_type":type(error).__name__,
                        })
            edge_metrics = tuple(
                EdgeMetric(
                    fact_id=record["fact_id"],source_entity_id=record["source_entity_id"],
                    target_entity_id=record["target_entity_id"],metric_key="spof.bridge",
                    numeric_value=1.0,components={"algorithm":"tarjan"},
                )
                for record in edge_records if record["fact_id"] in bridge_result.bridge_fact_ids
            )
            impact_paths = materialize_impact_paths(
                node_kinds,(
                    (target,source,fact_id,confidence)
                    for source,target,fact_id,confidence in directed_evidence_edges
                ),
                max_depth=None if node_count<=self.exact_reachability_node_limit else 4,
            )
            circular_motifs = circular_dependency_motifs(node_ids,directed_evidence_edges)
            anomalies: list[CohortAnomaly] = []
            upstream_values = {
                metric.entity_id:metric.numeric_value for metric in metrics
                if metric.metric_key=="reachability.upstream_impact"
            }
            for entity_type in sorted(set(node_kinds.values())):
                cohort_values = [
                    (entity_id,value) for entity_id,value in upstream_values.items()
                    if node_kinds.get(entity_id)==entity_type
                ]
                anomalies.extend(cohort_percentile_anomalies(
                    "reachability.upstream_impact",cohort_values,
                    cohort_key=f"entity-type:{entity_type}",
                ))

            return AnalysisResult(
                graph_name=graph_name,node_count=node_count,edge_count=edge_count,
                metrics=tuple(metrics),edge_metrics=edge_metrics,communities=communities,
                impact_paths=impact_paths,
                algorithm_versions={
                    "neo4j_gds":gds_version,"worker":"1.0.0",
                    "degree":"gds.degree","pagerank":"gds.pageRank",
                    "betweenness":"gds.betweenness","communities":"gds.wcc",
                    "reachability":"stackgraph.bfs-v1","spof":"stackgraph.tarjan-v1",
                    "structural_embedding":"gds.node2vec",
                },
                coverage={
                    "policy_hash":self.request.policy_hash,"entity_types":policy["entity_types"],
                    "predicates":policy["predicates"],"assertion_classes":policy["assertion_classes"],
                    "confidence_minimum":policy["confidence_minimum"],
                },
                resource_usage=self._resource_usage(
                    started,gds_projection_seconds=gds_projection_seconds,
                    gds_projection_estimate=gds_projection_estimate,
                ),
                limitations=tuple(limitations),
                structural_embeddings=structural_embeddings,
                anomalies=tuple(anomalies),circular_motifs=circular_motifs,
            )
        finally:
            try:
                self._query("CALL gds.graph.drop($graph_name,false) YIELD graphName RETURN graphName",{"graph_name":graph_name})
            except Exception:
                pass


class GraphIntelligenceWorker:
    def __init__(
        self,database_url: str,*,worker_id: str | None = None,
        encryption_key: str,concurrency: int = 2,max_attempts: int = 3,
        max_projection_memory_bytes: int = 5_368_709_120,
        analyzer_factory: Callable[..., Neo4jGdsAnalyzer] = Neo4jGdsAnalyzer,
    ) -> None:
        self.database_url = database_url
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.encryption_key = encryption_key
        self.concurrency = concurrency
        self.max_attempts = max_attempts
        if max_projection_memory_bytes < 1:
            raise ValueError("max projection memory bytes must be positive")
        self.max_projection_memory_bytes = max_projection_memory_bytes
        self.analyzer_factory = analyzer_factory
        self.connection: Connection = psycopg.connect(
            database_url,row_factory=dict_row,autocommit=True
        )

    def close(self) -> None:
        self.connection.close()

    def _recover_expired(self) -> int:
        recovered = 0
        while recovered < 10:
            with self.connection.transaction():
                row = self.connection.execute(
                    """
                    SELECT run.id AS run_id,run.tenant_id,run.policy_id,run.policy_key,
                           run.requested_change_watermark,request.id AS request_id,
                           request.attempt
                    FROM graph_analysis_run run
                    JOIN graph_analysis_request request ON request.id=run.request_id
                    WHERE run.status='RUNNING' AND run.lease_expires_at<now()
                      AND request.status='RUNNING'
                      AND (request.leased_until IS NULL OR request.leased_until<now())
                    ORDER BY run.lease_expires_at
                    FOR UPDATE OF run,request SKIP LOCKED
                    LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    break
                detail = Jsonb({
                    "error_type":"LeaseExpired",
                    "message":"Graph analysis worker lease expired; a successor was scheduled.",
                    "recovered_by":self.worker_id,
                })
                self.connection.execute(
                    """
                    UPDATE graph_analysis_run
                    SET status='FAILED',stage='COMPLETE',error_detail=%s,
                        completed_at=now(),lease_expires_at=now()
                    WHERE id=%s AND status='RUNNING'
                    """,
                    (detail,row["run_id"]),
                )
                self.connection.execute(
                    """
                    UPDATE graph_analysis_request
                    SET status='FAILED',completed_at=now(),leased_by=NULL,leased_until=NULL,
                        last_error=%s,updated_at=now()
                    WHERE id=%s AND status='RUNNING'
                    """,
                    (detail,row["request_id"]),
                )
                if row["attempt"] < self.max_attempts:
                    self.connection.execute(
                        """
                        INSERT INTO graph_analysis_request(
                          tenant_id,policy_id,policy_key,requested_change_watermark,
                          reason,status,available_at,last_error
                        ) VALUES (%s,%s,%s,%s,'LEASE_RECOVERY','PENDING',now(),%s)
                        ON CONFLICT(tenant_id,policy_id)
                          WHERE status IN ('PENDING','WAITING_FOR_PROJECTION')
                        DO UPDATE SET
                          requested_change_watermark=greatest(
                            graph_analysis_request.requested_change_watermark,
                            EXCLUDED.requested_change_watermark
                          ),last_error=EXCLUDED.last_error,updated_at=now()
                        """,
                        (
                            row["tenant_id"],row["policy_id"],row["policy_key"],
                            row["requested_change_watermark"],detail,
                        ),
                    )
                recovered += 1
        return recovered

    def _claim(self) -> AnalysisRequest | None:
        with self.connection.transaction():
            row = self.connection.execute(
                """
                SELECT request.*,policy.version AS policy_version,
                  policy.content_hash AS policy_hash,policy.configuration,
                  deployment.id AS deployment_id,deployment.endpoint,
                  deployment.database_name,deployment.username,
                  deployment.credential_reference,deployment.projected_outbox_id,
                  deployment.deployment_state,
                  CASE WHEN secret.id IS NULL THEN NULL
                       ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS stored_password
                FROM graph_analysis_request request
                JOIN graph_analysis_policy policy ON policy.id=request.policy_id
                LEFT JOIN tenant_graph_deployment deployment
                  ON deployment.tenant_id=request.tenant_id
                LEFT JOIN tenant_secret secret
                  ON secret.id=deployment.credential_secret_id
                 AND secret.tenant_id=deployment.tenant_id
                WHERE request.status IN ('PENDING','WAITING_FOR_PROJECTION')
                  AND request.available_at<=now()
                  AND (request.leased_until IS NULL OR request.leased_until<now())
                  AND stackgraph_tenant_service_running(request.tenant_id,'graph-intelligence')
                  AND NOT EXISTS (
                    SELECT 1 FROM graph_analysis_run running
                    WHERE running.tenant_id=request.tenant_id
                      AND running.policy_key=request.policy_key
                      AND running.status='RUNNING'
                  )
                ORDER BY coalesce((
                  SELECT max(history.started_at) FROM graph_analysis_run history
                  WHERE history.tenant_id=request.tenant_id
                ),'-infinity'::timestamptz),request.created_at,request.tenant_id
                FOR UPDATE OF request SKIP LOCKED
                LIMIT 1
                """,
                (self.encryption_key,),
            ).fetchone()
            if row is None:
                return None
            if row["deployment_id"] is None or row["deployment_state"] != "ACTIVE":
                self.connection.execute(
                    """
                    UPDATE graph_analysis_request
                    SET status='WAITING_FOR_PROJECTION',available_at=now()+interval '1 minute',
                        leased_by=NULL,leased_until=NULL,
                        last_error=%s,updated_at=now()
                    WHERE id=%s
                    """,
                    (Jsonb({"code":"GRAPH_DEPLOYMENT_UNAVAILABLE"}),row["id"]),
                )
                return None
            if row["projected_outbox_id"] < row["requested_change_watermark"]:
                self.connection.execute(
                    """
                    UPDATE graph_analysis_request
                    SET status='WAITING_FOR_PROJECTION',available_at=now()+interval '15 seconds',
                        leased_by=NULL,leased_until=NULL,last_error=NULL,updated_at=now()
                    WHERE id=%s
                    """,
                    (row["id"],),
                )
                return None

            password = row["stored_password"] or resolve_credential_reference(
                row["credential_reference"]
            )
            claimed = self.connection.execute(
                """
                UPDATE graph_analysis_request
                SET status='RUNNING',started_at=now(),completed_at=NULL,
                    leased_by=%s,leased_until=now()+interval '30 minutes',
                    attempt=attempt+1,last_error=NULL,updated_at=now()
                WHERE id=%s
                RETURNING attempt
                """,
                (self.worker_id,row["id"]),
            ).fetchone()
            placeholder = "sha256:"+hashlib.sha256(
                f"{row['tenant_id']}:{row['projected_outbox_id']}:{row['policy_hash']}".encode()
            ).hexdigest()
            run = self.connection.execute(
                """
                INSERT INTO graph_analysis_run(
                  tenant_id,policy_id,policy_key,request_id,requested_change_watermark,
                  neo4j_projection_watermark,input_fingerprint,worker_id,lease_expires_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now()+interval '30 minutes')
                RETURNING id
                """,
                (
                    row["tenant_id"],row["policy_id"],row["policy_key"],row["id"],
                    row["requested_change_watermark"],row["projected_outbox_id"],
                    placeholder,self.worker_id,
                ),
            ).fetchone()
        return AnalysisRequest(
            id=row["id"],tenant_id=row["tenant_id"],policy_id=row["policy_id"],
            policy_key=row["policy_key"],policy_version=row["policy_version"],
            policy_hash=row["policy_hash"],configuration=dict(row["configuration"]),
            requested_watermark=row["requested_change_watermark"],
            projected_watermark=row["projected_outbox_id"],run_id=run["id"],
            deployment_id=row["deployment_id"],endpoint=row["endpoint"],
            database_name=row["database_name"],username=row["username"],password=password,
            attempt=claimed["attempt"],
        )

    def _heartbeat(self, request: AnalysisRequest, stage: str, job_id: str | None) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE graph_analysis_request
                SET leased_until=now()+interval '30 minutes',updated_at=now()
                WHERE id=%s AND status='RUNNING' AND leased_by=%s
                """,
                (request.id,self.worker_id),
            )
            self.connection.execute(
                """
                UPDATE graph_analysis_run
                SET stage=%s,lease_expires_at=now()+interval '30 minutes',
                    resource_usage=resource_usage||%s
                WHERE id=%s AND status='RUNNING' AND worker_id=%s
                """,
                (stage,Jsonb({"neo4j_job_id":job_id} if job_id else {}),request.run_id,self.worker_id),
            )

    def _input_fingerprint(self, request: AnalysisRequest) -> str:
        digest = hashlib.sha256()
        digest.update(request.policy_hash.encode())
        digest.update(str(request.projected_watermark).encode())
        with self.connection.transaction():
            cutoff = self.connection.execute(
                "SELECT created_at FROM projection_outbox WHERE id=%s",
                (request.projected_watermark,),
            ).fetchone()
            if cutoff is None:
                return "sha256:"+digest.hexdigest()
            configuration = request.configuration
            with self.connection.cursor(name=f"fingerprint_{request.run_id.hex}") as cursor:
                cursor.execute(
                    """
                    SELECT fact.id,fact.logical_key,fact.predicate,fact.assertion_class,
                           fact.confidence,fact.system_from,fact.system_to
                    FROM fact_assertion fact
                    JOIN entity subject ON subject.id=fact.subject_entity_id
                    JOIN entity object ON object.id=fact.object_entity_id
                    WHERE (fact.tenant_id IS NULL OR fact.tenant_id=%s)
                      AND fact.predicate=ANY(%s)
                      AND fact.assertion_class=ANY(%s)
                      AND fact.confidence>=%s
                      AND subject.entity_type=ANY(%s) AND object.entity_type=ANY(%s)
                      AND fact.system_from<=%s
                      AND (fact.system_to IS NULL OR fact.system_to>%s)
                    ORDER BY fact.id
                    """,
                    (
                        request.tenant_id,list(configuration.get("predicates",[])),
                        list(configuration.get("assertion_classes",[])),
                        float(configuration.get("confidence_minimum",0)),
                        list(configuration.get("entity_types",[])),
                        list(configuration.get("entity_types",[])),
                        cutoff["created_at"],cutoff["created_at"],
                    ),
                )
                for row in cursor:
                    digest.update("|".join(str(value) for value in row).encode())
                    digest.update(b"\n")
        return "sha256:"+digest.hexdigest()

    def _materialized_risks(
        self,request: AnalysisRequest,result: AnalysisResult,
    ) -> list[tuple[UUID,UUID,str,float,Jsonb,list[str],str]]:
        configured = dict(request.configuration.get("risk_weights") or {})
        family_weights = {
            key:float(value) for key,value in dict(configured.get("families") or {
                "structural":0.40,"business":0.25,"exposure":0.25,"lifecycle":0.10,
            }).items()
        }
        structural_weights = {
            key:float(value) for key,value in dict(configured.get("structural_metrics") or {
                "reachability.upstream_impact":0.40,"betweenness":0.30,
                "spof.articulation":0.20,"pagerank":0.10,
            }).items()
        }
        if sum(family_weights.values())<=0 or sum(structural_weights.values())<=0:
            raise ValueError("risk weights must have a positive total")
        metrics_by_entity: dict[str,dict[str,RankedMetric]] = {}
        for metric in result.metrics:
            if metric.metric_key in structural_weights and metric.percentile is not None:
                metrics_by_entity.setdefault(str(metric.entity_id),{})[metric.metric_key]=metric
        entity_ids = sorted(metrics_by_entity)
        if not entity_ids:
            return []
        signal_rows = self.connection.execute(
            """
            WITH requested AS (SELECT unnest(%s::uuid[]) entity_id), signals AS (
              SELECT requested.entity_id,
                (
                  WITH RECURSIVE nearby(id,depth,path) AS (
                    SELECT requested.entity_id,0,ARRAY[requested.entity_id]
                    UNION ALL
                    SELECT CASE WHEN relationship.source_entity_id=nearby.id
                             THEN relationship.target_entity_id ELSE relationship.source_entity_id END,
                           nearby.depth+1,
                           nearby.path||CASE WHEN relationship.source_entity_id=nearby.id
                             THEN relationship.target_entity_id ELSE relationship.source_entity_id END
                    FROM nearby
                    JOIN current_relationship relationship
                      ON relationship.source_entity_id=nearby.id
                      OR relationship.target_entity_id=nearby.id
                    WHERE nearby.depth<2
                      AND relationship.tenant_id=%s
                      AND relationship.relationship_type IN (
                        'DEPENDS_ON','USES','BUILT_ON','RUNS_ON','IMPLEMENTED_BY','IMPLEMENTS','CONTAINS'
                      )
                      AND NOT (CASE WHEN relationship.source_entity_id=nearby.id
                        THEN relationship.target_entity_id ELSE relationship.source_entity_id END)=ANY(nearby.path)
                  )
                  SELECT CASE WHEN count(mapping.application_entity_id)=0
                    AND count(*) FILTER (WHERE application.properties->>'tier' ~ '^[1-5]$')=0
                    THEN NULL ELSE greatest(
                    coalesce(max(mapping.criticality)::double precision/5.0,0),
                    coalesce(max(CASE
                      WHEN application.properties->>'tier' ~ '^[1-5]$'
                        THEN (6-(application.properties->>'tier')::integer)::double precision/5.0
                      ELSE 0 END),0)
                  ) END
                  FROM nearby
                  JOIN entity application ON application.id=nearby.id
                  LEFT JOIN current_capability_application_relationship mapping
                    ON mapping.application_entity_id=application.id
                  WHERE application.entity_type='Application'
                ) business_score,
                (
                  SELECT CASE WHEN count(*)=0 THEN NULL ELSE least(1.0,
                    count(DISTINCT affected.object_entity_id)::double precision*0.20
                    +max(CASE WHEN usage.static_reachability='OBSERVED' THEN 0.25 ELSE 0 END)
                    +max(CASE WHEN usage.runtime_observed='OBSERVED' THEN 0.30 ELSE 0 END)
                    +max(CASE WHEN deployment.id IS NOT NULL THEN 0.25 ELSE 0 END)
                  ) END
                  FROM fact_assertion dependency
                  LEFT JOIN dependency_usage_summary usage
                    ON usage.dependency_fact_assertion_id=dependency.id
                  LEFT JOIN fact_assertion affected
                    ON affected.subject_entity_id=requested.entity_id
                   AND affected.predicate='AFFECTED_BY' AND affected.system_to IS NULL
                  LEFT JOIN fact_assertion deployment
                    ON deployment.subject_entity_id=dependency.subject_entity_id
                   AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
                  WHERE dependency.object_entity_id=requested.entity_id
                    AND dependency.predicate='DEPENDS_ON' AND dependency.system_to IS NULL
                    AND dependency.tenant_id=%s
                ) exposure_score,
                ARRAY(
                  SELECT DISTINCT fact_id FROM (
                    SELECT dependency.id fact_id FROM fact_assertion dependency
                    WHERE dependency.object_entity_id=requested.entity_id
                      AND dependency.predicate='DEPENDS_ON' AND dependency.system_to IS NULL
                      AND dependency.tenant_id=%s
                    UNION ALL
                    SELECT affected.id FROM fact_assertion affected
                    WHERE affected.subject_entity_id=requested.entity_id
                      AND affected.predicate='AFFECTED_BY' AND affected.system_to IS NULL
                      AND (affected.tenant_id IS NULL OR affected.tenant_id=%s)
                  ) evidence
                ) exposure_fact_ids,
                (
                  SELECT CASE
                    WHEN bool_or(lower(coalesce(
                      fact.object_value->>'is_deprecated',fact.object_value->>'deprecated','false'
                    )) IN ('true','1','yes')) THEN 1.0
                    WHEN bool_or(upper(coalesce(
                      assessment.categorical_value,entity.properties->>'support_status',''
                    )) IN ('UNSUPPORTED','END_OF_LIFE','EOL')) THEN 0.9
                    WHEN count(assessment.id)>0 THEN greatest(0,least(1,1-coalesce(avg(assessment.score),0)/100.0))
                    ELSE NULL
                  END
                  FROM entity
                  LEFT JOIN fact_assertion fact ON fact.subject_entity_id=entity.id
                    AND fact.predicate='HAS_PROPERTY' AND fact.system_to IS NULL
                  LEFT JOIN assessment ON assessment.subject_entity_id=entity.id
                    AND assessment.status='CURRENT'
                    AND lower(assessment.dimension) IN ('viability','supportability','runtime_support','package_support')
                  WHERE entity.id=requested.entity_id
                ) lifecycle_score
              FROM requested
            ) SELECT * FROM signals
            """,
            (
                entity_ids,request.tenant_id,request.tenant_id,
                request.tenant_id,request.tenant_id,
            ),
        ).fetchall()
        signals = {str(row["entity_id"]):row for row in signal_rows}
        persisted = []
        for entity_id,metric_map in metrics_by_entity.items():
            available_structural = {
                key:metric for key,metric in metric_map.items() if metric.percentile is not None
            }
            structural_total = sum(structural_weights[key] for key in available_structural)
            structural_score = (
                sum(structural_weights[key]*float(metric.percentile or 0)
                    for key,metric in available_structural.items())/structural_total
                if structural_total else None
            )
            row = signals.get(entity_id,{})
            raw_scores: dict[str,float | None] = {
                "structural":structural_score,
                "business":float(row["business_score"]) if row.get("business_score") is not None else None,
                "exposure":float(row["exposure_score"]) if row.get("exposure_score") is not None else None,
                "lifecycle":float(row["lifecycle_score"]) if row.get("lifecycle_score") is not None else None,
            }
            available = {key:value for key,value in raw_scores.items() if value is not None}
            total = sum(family_weights[key] for key in available)
            if total<=0:
                continue
            normalized = {key:family_weights[key]/total for key in available}
            contributions: dict[str,dict[str,object]] = {}
            for key,value in available.items():
                contribution: dict[str,object] = {
                    "score":value,"weight":normalized[key],
                    "normalized_contribution":value*normalized[key],
                }
                if key=="structural":
                    contribution["metric_keys"]=sorted(available_structural)
                elif key=="exposure":
                    contribution["fact_ids"]=[str(item) for item in (row.get("exposure_fact_ids") or [])]
                elif key=="business":
                    contribution["metric_keys"]=["business.criticality","application.tier"]
                elif key=="lifecycle":
                    contribution["metric_keys"]=["lifecycle.deprecation","lifecycle.support","catalog.viability"]
                contributions[key]=contribution
            score=sum(float(available[key])*normalized[key] for key in available)
            persisted.append((
                request.run_id,request.tenant_id,entity_id,max(0,min(1,score)),
                Jsonb(contributions),sorted(set(family_weights)-set(available)),
                "graph-systemic-risk/v2",
            ))
        return persisted

    def _persist(self, request: AnalysisRequest, result: AnalysisResult, fingerprint: str) -> None:
        terminal_status = "SUCCEEDED_WITH_LIMITATIONS" if result.limitations else "SUCCEEDED"
        with self.connection.transaction():
            locked = self.connection.execute(
                "SELECT status,worker_id FROM graph_analysis_run WHERE id=%s FOR UPDATE",
                (request.run_id,),
            ).fetchone()
            if locked is None or locked["status"] != "RUNNING" or locked["worker_id"] != self.worker_id:
                raise RuntimeError("graph analysis run lease was lost before persistence")
            with self.connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO graph_entity_metric(
                      run_id,tenant_id,entity_id,metric_key,numeric_value,percentile,rank,
                      components,limitations
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,metric.entity_id,metric.metric_key,
                            metric.numeric_value,metric.percentile,metric.rank,
                            Jsonb(metric.components),Jsonb(list(metric.limitations)),
                        ) for metric in result.metrics
                    ),
                )
                cursor.executemany(
                    """
                    INSERT INTO graph_entity_risk(
                      run_id,tenant_id,entity_id,systemic_risk,contributions,
                      renormalized_families,method_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    self._materialized_risks(request,result),
                )
                cursor.executemany(
                    """
                    INSERT INTO graph_impact_path(
                      run_id,tenant_id,source_entity_id,target_entity_id,impact_kind,
                      distance,path_entity_ids,path_fact_ids,minimum_confidence
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,path.source_entity_id,
                            path.target_entity_id,path.target_kind,path.distance,
                            list(path.entity_ids),list(path.fact_ids),path.minimum_confidence,
                        ) for path in result.impact_paths
                    ),
                )
                cursor.executemany(
                    """
                    INSERT INTO graph_edge_metric(
                      run_id,tenant_id,fact_assertion_id,subject_entity_id,object_entity_id,
                      metric_key,numeric_value,components,limitations
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,metric.fact_id,
                            metric.source_entity_id,metric.target_entity_id,metric.metric_key,
                            metric.numeric_value,Jsonb(metric.components),Jsonb(list(metric.limitations)),
                        ) for metric in result.edge_metrics
                    ),
                )
                cursor.executemany(
                    """
                    INSERT INTO graph_community_membership(
                      run_id,tenant_id,entity_id,algorithm_key,community_key,score,metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,membership.entity_id,
                            membership.algorithm_key,membership.community_key,membership.score,
                            Jsonb(membership.metadata),
                        ) for membership in result.communities
                    ),
                )
            if result.structural_embeddings:
                structural_configuration = dict(request.configuration.get("structural_embedding",{}))
                dimensions = len(result.structural_embeddings[0].values)
                configuration_hash = "sha256:"+hashlib.sha256(
                    json.dumps(structural_configuration,sort_keys=True,separators=(",",":")).encode()
                ).hexdigest()
                coverage_ratio = min(1.0,len(result.structural_embeddings)/max(1,result.node_count))
                space = self.connection.execute(
                    """
                    INSERT INTO embedding_space(
                      tenant_id,space_key,space_kind,provider,model_or_algorithm,dimensions,
                      normalization,template_version,configuration,content_hash,lifecycle_state,
                      evaluation,coverage_ratio
                    ) VALUES (%s,%s,'STRUCTURAL_GRAPH','NEO4J_GDS','gds.node2vec',%s,
                      'L2','structural-node2vec/v1',%s,%s,'SHADOW',%s,%s)
                    RETURNING id
                    """,
                    (
                        request.tenant_id,
                        f"structural-{request.policy_key}-{request.run_id.hex[:12]}",dimensions,
                        Jsonb(structural_configuration),configuration_hash,
                        Jsonb({
                            "passed":False,"method_version":"structural-stability/v1",
                            "reason":"AWAITING_REVISION_STABILITY_EVALUATION",
                        }),coverage_ratio,
                    ),
                ).fetchone()
                if space is None:
                    raise RuntimeError("failed to create structural embedding space")
                with self.connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO entity_embedding(
                          tenant_id,embedding_space_id,entity_id,dimensions,input_hash,embedding,
                          provider_usage
                        ) VALUES (%s,%s,%s,%s,%s,%s::vector,%s)
                        """,
                        (
                            (
                                request.tenant_id,space["id"],embedding.entity_id,dimensions,
                                fingerprint,vector_literal(embedding.values),
                                Jsonb({"analysis_run_id":str(request.run_id),"algorithm":"gds.node2vec"}),
                            ) for embedding in result.structural_embeddings
                        ),
                    )
                self.connection.execute(
                    """
                    INSERT INTO structural_embedding_run(
                      tenant_id,analysis_run_id,embedding_space_id,algorithm_key,
                      algorithm_version,configuration,input_fingerprint,status,node_count,limitations
                    ) VALUES (%s,%s,%s,'node2vec','gds.node2vec',%s,%s,'SUCCEEDED',%s,%s)
                    """,
                    (
                        request.tenant_id,request.run_id,space["id"],Jsonb(structural_configuration),
                        fingerprint,len(result.structural_embeddings),Jsonb([]),
                    ),
                )
            with self.connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO graph_anomaly(
                      run_id,tenant_id,entity_id,anomaly_key,score,cohort_key,
                      cohort_definition,observed_components,reasons,limitations
                    ) VALUES (%s,%s,%s,'COHORT_HIGH_UPSTREAM_IMPACT',%s,%s,%s,%s,%s,'[]')
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,anomaly.entity_id,anomaly.score,
                            anomaly.cohort_key,
                            Jsonb({"minimum_size":5,"cohort_size":anomaly.cohort_size}),
                            Jsonb({"metric_key":anomaly.metric_key,"numeric_value":anomaly.numeric_value}),
                            Jsonb([f"{anomaly.metric_key} is at or above the 95th cohort percentile."]),
                        ) for anomaly in result.anomalies
                    ),
                )
                cursor.executemany(
                    """
                    INSERT INTO graph_motif(
                      run_id,tenant_id,motif_key,entity_ids,supporting_fact_ids,
                      confidence,components,limitations
                    ) VALUES (%s,%s,'CIRCULAR_DEPENDENCY',%s,%s,%s,%s,'[]')
                    """,
                    (
                        (
                            request.run_id,request.tenant_id,list(motif.entity_ids),
                            list(motif.fact_ids),motif.minimum_confidence,
                            Jsonb({"algorithm":"strongly-connected-components","entity_count":len(motif.entity_ids)}),
                        ) for motif in result.circular_motifs
                    ),
                )
            self.connection.execute(
                """
                UPDATE graph_analysis_run
                SET input_fingerprint=%s,gds_graph_name=%s,algorithm_versions=%s,
                    status=%s,stage='COMPLETE',node_count=%s,edge_count=%s,coverage=%s,
                    resource_usage=resource_usage||%s,limitations=%s,
                    completed_at=now(),lease_expires_at=now()
                WHERE id=%s AND status='RUNNING' AND worker_id=%s
                """,
                (
                    fingerprint,result.graph_name,Jsonb(result.algorithm_versions),terminal_status,
                    result.node_count,result.edge_count,Jsonb(result.coverage),
                    Jsonb(result.resource_usage),Jsonb(list(result.limitations)),
                    request.run_id,self.worker_id,
                ),
            )
            self.connection.execute(
                """
                INSERT INTO active_graph_analysis_run(tenant_id,policy_key,run_id)
                VALUES (%s,%s,%s)
                ON CONFLICT(tenant_id,policy_key) DO UPDATE SET
                  run_id=EXCLUDED.run_id,activated_at=now()
                """,
                (request.tenant_id,request.policy_key,request.run_id),
            )
            self.connection.execute(
                """
                UPDATE graph_analysis_request
                SET status='SUCCEEDED',completed_at=now(),leased_by=NULL,leased_until=NULL,
                    last_error=NULL,updated_at=now()
                WHERE id=%s AND status='RUNNING' AND leased_by=%s
                """,
                (request.id,self.worker_id),
            )

    def _fail(self, request: AnalysisRequest, error: Exception) -> None:
        detail = {"error_type":type(error).__name__,"message":str(error)[:2000],"worker_id":self.worker_id}
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE graph_analysis_run
                SET status='FAILED',stage='COMPLETE',error_detail=%s,completed_at=now(),
                    lease_expires_at=now()
                WHERE id=%s AND status='RUNNING' AND worker_id=%s
                """,
                (Jsonb(detail),request.run_id,self.worker_id),
            )
            self.connection.execute(
                """
                UPDATE graph_analysis_request
                SET status='FAILED',completed_at=now(),leased_by=NULL,leased_until=NULL,
                    last_error=%s,updated_at=now()
                WHERE id=%s AND status='RUNNING' AND leased_by=%s
                """,
                (Jsonb(detail),request.id,self.worker_id),
            )
            if request.attempt < self.max_attempts:
                self.connection.execute(
                    """
                    INSERT INTO graph_analysis_request(
                      tenant_id,policy_id,policy_key,requested_change_watermark,reason,
                      status,available_at,last_error
                    ) VALUES (%s,%s,%s,%s,'RETRY_AFTER_FAILURE','PENDING',
                      now()+least(300,power(2,%s)::integer)*interval '1 second',%s)
                    ON CONFLICT(tenant_id,policy_id)
                      WHERE status IN ('PENDING','WAITING_FOR_PROJECTION')
                    DO UPDATE SET
                      requested_change_watermark=greatest(
                        graph_analysis_request.requested_change_watermark,
                        EXCLUDED.requested_change_watermark
                      ),last_error=EXCLUDED.last_error,updated_at=now()
                    """,
                    (
                        request.tenant_id,request.policy_id,request.policy_key,
                        request.requested_watermark,request.attempt,Jsonb(detail),
                    ),
                )

    def run_once(self) -> WorkerResult:
        self._recover_expired()
        request = self._claim()
        if request is None:
            return WorkerResult(claimed=False)
        analyzer = self.analyzer_factory(
            request,concurrency=self.concurrency,
            max_projection_memory_bytes=self.max_projection_memory_bytes,
            heartbeat=lambda stage,job_id: self._heartbeat(request,stage,job_id),
        )
        try:
            fingerprint = self._input_fingerprint(request)
            result = analyzer.analyze()
            self._heartbeat(request,"PERSISTING",None)
            self._persist(request,result,fingerprint)
            return WorkerResult(
                claimed=True,request_id=str(request.id),run_id=str(request.run_id),
                status="SUCCEEDED_WITH_LIMITATIONS" if result.limitations else "SUCCEEDED",
                node_count=result.node_count,edge_count=result.edge_count,
                metric_count=len(result.metrics)+len(result.edge_metrics),
            )
        except Exception as error:
            self._fail(request,error)
            return WorkerResult(
                claimed=True,request_id=str(request.id),run_id=str(request.run_id),status="FAILED"
            )
        finally:
            analyzer.close()


def record_heartbeat(database_url: str,worker_id: str,metadata: Mapping[str,object]) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO service_heartbeat(service_key,instance_id,status,metadata)
            VALUES ('graph-intelligence',%s,'RUNNING',%s)
            ON CONFLICT(service_key) DO UPDATE SET
              instance_id=EXCLUDED.instance_id,status='RUNNING',metadata=EXCLUDED.metadata,
              started_at=CASE WHEN service_heartbeat.instance_id=EXCLUDED.instance_id
                THEN service_heartbeat.started_at ELSE now() END,last_heartbeat_at=now()
            """,
            (worker_id,Jsonb(dict(metadata))),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tenant-safe Neo4j graph intelligence")
    parser.add_argument("command",choices=("work","serve"),nargs="?",default="work")
    parser.add_argument("--poll-seconds",type=float,default=2.0)
    parser.add_argument("--max-jobs",type=int)
    parser.add_argument("--concurrency",type=int,default=int(os.environ.get("STACKGRAPH_GDS_CONCURRENCY","2")))
    args = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    if args.poll_seconds < 0 or args.concurrency < 1:
        parser.error("poll seconds must be non-negative and concurrency must be positive")
    encryption_key = os.environ.get(
        "STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY","stackgraph-local-development-credential-key"
    )
    worker = GraphIntelligenceWorker(
        database_url,encryption_key=encryption_key,concurrency=args.concurrency,
        max_projection_memory_bytes=int(os.environ.get(
            "STACKGRAPH_GDS_MAX_PROJECTION_BYTES","5368709120",
        )),
    )
    completed = 0
    try:
        while True:
            if args.command == "serve":
                record_heartbeat(database_url,worker.worker_id,{"gds_concurrency":args.concurrency,"poll_seconds":args.poll_seconds})
            result = worker.run_once()
            print(json.dumps(asdict(result),sort_keys=True),flush=True)
            if result.claimed:
                completed += 1
            if args.command == "work" and (not result.claimed or (args.max_jobs and completed>=args.max_jobs)):
                break
            if args.command == "serve" and not result.claimed:
                time.sleep(args.poll_seconds)
    finally:
        worker.close()


if __name__ == "__main__":
    main()

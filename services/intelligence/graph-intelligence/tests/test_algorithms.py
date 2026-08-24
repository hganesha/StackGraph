import unittest
from types import SimpleNamespace
from uuid import UUID

from stackgraph_graph_intelligence.algorithms import (
    articulation_points_and_bridges,
    circular_dependency_motifs,
    cohort_percentile_anomalies,
    materialize_impact_paths,
    RankedMetric,
    rank_metrics,
    reachability_metrics,
)
from stackgraph_graph_intelligence.worker import (
    AnalysisRequest, AnalysisResult, GraphIntelligenceWorker, validate_projection_budget,
)


class GraphAlgorithmTests(unittest.TestCase):
    def test_materialized_risk_renormalizes_only_observed_families(self) -> None:
        entity_id="00000000-0000-4000-8000-000000000201"
        tenant_id=UUID("00000000-0000-4000-8000-000000000001")

        class SignalConnection:
            def execute(self,query,params):
                return SimpleNamespace(fetchall=lambda:[{
                    "entity_id":UUID(entity_id),"business_score":None,
                    "exposure_score":None,"exposure_fact_ids":[],"lifecycle_score":None,
                }])

        worker=object.__new__(GraphIntelligenceWorker)
        worker.connection=SignalConnection()
        request=AnalysisRequest(
            id=UUID("00000000-0000-4000-8000-000000000101"),tenant_id=tenant_id,
            policy_id=UUID("00000000-0000-4000-8000-000000000102"),
            policy_key="runtime-dependency",policy_version=4,policy_hash="sha256:"+"a"*64,
            configuration={"risk_weights":{
                "families":{"structural":0.4,"business":0.25,"exposure":0.25,"lifecycle":0.1},
                "structural_metrics":{"pagerank":1.0},
            }},requested_watermark=1,projected_watermark=1,
            run_id=UUID("00000000-0000-4000-8000-000000000103"),
            deployment_id=UUID("00000000-0000-4000-8000-000000000104"),
            endpoint="neo4j://example",database_name="neo4j",username="neo4j",password="secret",
            attempt=1,
        )
        result=AnalysisResult(
            graph_name="graph",node_count=1,edge_count=0,
            metrics=(RankedMetric(
                entity_id=entity_id,metric_key="pagerank",numeric_value=1,
                percentile=0.8,rank=1,components={},
            ),),edge_metrics=(),communities=(),impact_paths=(),algorithm_versions={},
            coverage={},resource_usage={},limitations=(),
        )

        rows=worker._materialized_risks(request,result)

        self.assertEqual(rows[0][3],0.8)
        self.assertEqual(rows[0][5],["business","exposure","lifecycle"])
        self.assertEqual(rows[0][6],"graph-systemic-risk/v2")

    def test_rank_metrics_is_deterministic_and_uses_competition_rank(self) -> None:
        ranked = rank_metrics(
            "pagerank",[("c",1.0,{}),("b",2.0,{}),("a",2.0,{})]
        )
        self.assertEqual([row.entity_id for row in ranked],["a","b","c"])
        self.assertEqual([row.rank for row in ranked],[1,1,3])
        self.assertEqual([row.percentile for row in ranked],[0.75,0.75,0.0])

    def test_rank_metrics_assigns_a_neutral_percentile_when_all_values_tie(self) -> None:
        ranked = rank_metrics("degree",[("a",0,{}),("b",0,{}),("c",0,{})])
        self.assertEqual([row.percentile for row in ranked],[0.5,0.5,0.5])

    def test_reachability_is_exact_for_small_directed_graph(self) -> None:
        result = reachability_metrics(
            ["a","b","c","d"],[('a','b'),('b','c'),('a','d')]
        )
        self.assertEqual(result.reachable,{"a":3,"b":1,"c":0,"d":0})
        self.assertEqual(result.depth["a"],2)
        self.assertFalse(result.limited_entities)

    def test_reachability_discloses_bounded_large_graph(self) -> None:
        result = reachability_metrics(
            ["a","b","c","d"],[('a','b'),('b','c'),('c','d')],
            exact_node_limit=2,bounded_max_depth=1,
        )
        self.assertEqual(result.reachable["a"],1)
        self.assertIn("a",result.limited_entities)

    def test_tarjan_handles_parallel_edges_without_false_bridge(self) -> None:
        result = articulation_points_and_bridges(
            ["a","b","c"],
            [("a","b","f1"),("a","b","f2"),("b","c","f3")],
        )
        self.assertEqual(result.articulation_entities,frozenset({"b"}))
        self.assertEqual(result.bridge_fact_ids,frozenset({"f3"}))

    def test_impact_paths_are_shortest_deterministic_and_evidence_backed(self) -> None:
        paths = materialize_impact_paths(
            {"package":"Package","service":"Service","app":"Application"},
            [
                ("package","service","f1",0.9),
                ("service","app","f2",0.8),
                ("package","app","f3",0.7),
            ],
        )
        package_path = next(path for path in paths if path.source_entity_id=="package")
        self.assertEqual(package_path.entity_ids,("package","app"))
        self.assertEqual(package_path.fact_ids,("f3",))
        self.assertEqual(package_path.minimum_confidence,0.7)

    def test_circular_dependency_motif_retains_supporting_facts(self) -> None:
        motifs = circular_dependency_motifs(
            ["a","b","c","outside"],
            [
                ("a","b","fact-ab",0.9),("b","c","fact-bc",0.8),
                ("c","a","fact-ca",0.7),("c","outside","fact-out",1.0),
            ],
        )
        self.assertEqual(len(motifs),1)
        self.assertEqual(motifs[0].entity_ids,("a","b","c"))
        self.assertEqual(motifs[0].fact_ids,("fact-ab","fact-bc","fact-ca"))
        self.assertEqual(motifs[0].minimum_confidence,0.7)

    def test_anomalies_use_an_explicit_sufficient_cohort(self) -> None:
        anomalies = cohort_percentile_anomalies(
            "reachability.upstream_impact",
            [("app-a",1),("app-b",2),("app-c",3),("app-d",4),("app-e",100)],
            cohort_key="entity-type:Application",
        )
        self.assertEqual(
            [(item.entity_id,item.score,item.cohort_key) for item in anomalies],
            [("app-e",1.0,"entity-type:Application")],
        )
        self.assertEqual(cohort_percentile_anomalies(
            "reachability.upstream_impact",[("a",1),("b",100)],
            cohort_key="entity-type:Service",
        ),())

    def test_projection_budget_checks_estimated_memory_before_projection(self) -> None:
        validate_projection_budget(
            100,500,{"bytesMax":1_000_000},{"max_nodes":100,"max_edges":500,"max_memory_bytes":1_000_000},
        )
        with self.assertRaisesRegex(RuntimeError,"memory budget exceeded"):
            validate_projection_budget(
                100,500,{"bytesMax":1_000_001},{"max_memory_bytes":1_000_000},
            )


if __name__ == "__main__":
    unittest.main()

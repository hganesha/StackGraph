from __future__ import annotations

import math
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
from urllib import error

from stackgraph_graph_intelligence.embeddings import (
    content_hash,
    cosine_similarity,
    EmbeddingFailure,
    OpenAICompatibleEmbeddingAdapter,
    local_hash_embedding,
    render_entity_document,
    vector_literal,
)
from stackgraph_graph_intelligence.evaluation import RelevanceCaseResult,evaluate_relevance,top_k_stability
from stackgraph_graph_intelligence.embedding_worker import EmbeddingWorker
from stackgraph_graph_intelligence.similarity import (
    ApplicationFeatures,
    dependency_frequencies,
    deterministic_application_similarity,
    hybrid_application_similarity,
)


class EmbeddingTests(unittest.TestCase):
    def test_local_embedding_is_deterministic_normalized_and_dimension_safe(self) -> None:
        first = local_hash_embedding("Billing service PostgreSQL invoices",64)
        second = local_hash_embedding("Billing service PostgreSQL invoices",64)
        self.assertEqual(first,second)
        self.assertEqual(len(first),64)
        self.assertTrue(math.isclose(math.sqrt(sum(value * value for value in first)),1.0))
        self.assertTrue(vector_literal(first).startswith("["))
        with self.assertRaisesRegex(ValueError,"at least 8"):
            local_hash_embedding("bad",7)

    def test_local_embedding_ranks_related_text_above_unrelated_text(self) -> None:
        query = local_hash_embedding("invoice billing payment service",256)
        related = local_hash_embedding("billing application creates invoices and processes payments",256)
        unrelated = local_hash_embedding("mobile game texture rendering audio",256)
        self.assertGreater(cosine_similarity(query,related),cosine_similarity(query,unrelated))

    def test_canonical_renderer_is_order_independent_and_tracks_fact_ids(self) -> None:
        entity = {
            "entity_type":"Application","name":"Billing","properties":{
                "description":"Creates invoices","owner":"Finance Platform",
            },
        }
        relationships = [
            {"fact_id":"2","predicate":"USES","object_name":"PostgreSQL"},
            {"fact_id":"1","predicate":"IMPLEMENTS","object_name":"Billing capability"},
        ]
        rendered,facts = render_entity_document(entity,relationships,template_version="semantic-entity/v1")
        reverse_rendered,reverse_facts = render_entity_document(entity,reversed(relationships),template_version="semantic-entity/v1")
        self.assertEqual(rendered,reverse_rendered)
        self.assertEqual(facts,reverse_facts)
        self.assertEqual(facts,["1","2"])
        self.assertTrue(content_hash(rendered).startswith("sha256:"))

    def test_inverse_frequency_prevents_ubiquitous_foundation_false_positive(self) -> None:
        applications = {
        "billing":ApplicationFeatures(
            dependencies=frozenset({"react","node","aws","stripe-sdk","ledger-core"}),
            capabilities=frozenset({"billing","collections"}),
            technologies=frozenset({"postgresql"}),
        ),
        "ledger":ApplicationFeatures(
            dependencies=frozenset({"react","node","aws","stripe-sdk","ledger-core"}),
            capabilities=frozenset({"billing","collections"}),
            technologies=frozenset({"postgresql"}),
        ),
        "game":ApplicationFeatures(
            dependencies=frozenset({"react","node","aws","webgl"}),
            capabilities=frozenset({"gaming"}),
            technologies=frozenset({"webgl"}),
        ),
        "portal":ApplicationFeatures(
            dependencies=frozenset({"react","node","aws","design-system"}),
            capabilities=frozenset({"employee-experience"}),
            technologies=frozenset({"nextjs"}),
        ),
        }
        frequencies = dependency_frequencies(applications)
        similar = deterministic_application_similarity(
            applications["billing"],applications["ledger"],
            dependency_frequency=frequencies,corpus_size=len(applications),
        )
        foundation_only = deterministic_application_similarity(
            applications["billing"],applications["game"],
            dependency_frequency=frequencies,corpus_size=len(applications),
        )
        self.assertGreater(similar["score"],0.9)
        self.assertLess(foundation_only["score"],0.45)

    def test_similarity_discloses_missing_business_context_and_differences(self) -> None:
        result = deterministic_application_similarity(
            ApplicationFeatures(dependencies=frozenset({"unique-a"}),owners=frozenset({"team-a"})),
            ApplicationFeatures(dependencies=frozenset({"unique-b"}),owners=frozenset({"team-b"})),
            dependency_frequency={"unique-a":1,"unique-b":1},corpus_size=2,
        )
        self.assertEqual(result["limitations"],[{
            "code":"BUSINESS_CONTEXT_MISSING",
            "message":"Capability overlap was omitted and remaining weights were renormalized.",
        }])
        self.assertIs(result["differences"]["different_ownership"],True)

    def test_provider_rate_limit_preserves_retry_after(self) -> None:
        headers = Message()
        headers["Retry-After"] = "17"
        response = error.HTTPError("https://provider.test/embeddings",429,"rate limited",headers,None)
        adapter = OpenAICompatibleEmbeddingAdapter(base_url="https://provider.test",api_key="secret")

        with patch("stackgraph_graph_intelligence.embeddings.request.urlopen",side_effect=response):
            with self.assertRaises(EmbeddingFailure) as raised:
                adapter.embed("billing",dimensions=8,model="test")

        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.retry_after_seconds,17)
        self.assertEqual(raised.exception.failure_kind,"EMBEDDING_RATE_LIMIT")

    def test_provider_outage_is_retryable(self) -> None:
        adapter = OpenAICompatibleEmbeddingAdapter(base_url="https://provider.test",api_key="secret")
        with patch(
            "stackgraph_graph_intelligence.embeddings.request.urlopen",
            side_effect=error.URLError("offline"),
        ):
            with self.assertRaises(EmbeddingFailure) as raised:
                adapter.embed("billing",dimensions=8,model="test")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.failure_kind,"EMBEDDING_PROVIDER_UNAVAILABLE")

    def test_content_hash_cache_reuses_only_the_same_space_and_marks_usage(self) -> None:
        class Result:
            def fetchone(self):
                return {
                    "embedding":"[0.5,-0.5]","token_count":7,
                    "provider_usage":{"model":"fixture"},
                }

        class Connection:
            def __init__(self):
                self.params = None

            def execute(self, query, params):
                self.params = params
                self.assert_query = query
                return Result()

        connection = Connection()
        worker = EmbeddingWorker.__new__(EmbeddingWorker)
        worker.connection = connection
        job = SimpleNamespace(
            tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
            space_id=UUID("00000000-0000-4000-8000-000000000002"),
        )

        result = worker._cached_result(job,"sha256:"+"a"*64)

        self.assertIsNotNone(result)
        self.assertEqual(result.values,[0.5,-0.5])
        self.assertTrue(result.usage["cache_hit"])
        self.assertEqual(connection.params,(job.tenant_id,job.space_id,"sha256:"+"a"*64))

    def test_hybrid_similarity_renormalizes_only_available_signals(self) -> None:
        deterministic = {"score":0.8,"components":{},"limitations":[]}
        semantic_only = hybrid_application_similarity(deterministic,semantic_score=0.6)
        deterministic_only = hybrid_application_similarity(deterministic)

        self.assertAlmostEqual(semantic_only["score"],(0.8*0.65+0.6*0.25)/0.9)
        self.assertEqual(deterministic_only["score"],0.8)
        self.assertEqual(
            {item["code"] for item in deterministic_only["limitations"]},
            {"SEMANTIC_SIGNAL_UNAVAILABLE","STRUCTURAL_SIGNAL_UNAVAILABLE"},
        )

        semantic_without_features = hybrid_application_similarity(
            {"score":0,"components":{},"limitations":[],"coverage":{"deterministic_signal_available":False}},
            semantic_score=0.72,
        )
        self.assertEqual(semantic_without_features["score"],0.72)

    def test_relevance_metrics_and_revision_stability_are_explicit(self) -> None:
        metrics = evaluate_relevance([
            RelevanceCaseResult(
                ranked_entity_ids=("billing","game"),
                relevant_entity_ids=frozenset({"billing"}),
                hard_negative_entity_ids=frozenset({"game"}),
            ),
            RelevanceCaseResult(
                ranked_entity_ids=("ledger","billing"),
                relevant_entity_ids=frozenset({"ledger","billing"}),
            ),
        ])
        self.assertEqual(metrics["case_count"],2)
        self.assertEqual(metrics["recall_at_k"],1)
        self.assertEqual(metrics["hard_negative_rate"],1)
        self.assertEqual(top_k_stability({"billing","ledger"},{"billing","game"}),1/3)


if __name__ == "__main__":
    unittest.main()

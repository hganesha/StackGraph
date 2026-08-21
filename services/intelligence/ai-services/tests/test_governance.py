from __future__ import annotations

import unittest

from stackgraph_ai.governance import (
    CalibrationMetrics,
    CalibrationThresholds,
    CapabilityFootprint,
    EcosystemDemand,
    PortfolioCandidate,
    PortfolioScoringPolicy,
    evaluate_ecosystem_admission,
    evaluate_promotion_gate,
    governance_fingerprint,
    optimize_portfolio,
    score_portfolio_candidate,
)


class GovernanceTests(unittest.TestCase):
    def test_governance_fingerprint_is_order_stable_and_policy_sensitive(self) -> None:
        components = [
            {"key": "b", "version": "1", "status": "APPROVED"},
            {"key": "a", "version": "2", "status": "APPROVED"},
        ]
        first = governance_fingerprint(
            analyzer_key="modernization", analyzer_version="2",
            taxonomy_hash="sha256:taxonomy", alternatives_hash="sha256:alternatives",
            policy={"version": "1", "licenses": ["MIT"]},
            internal_components=components,
        )
        replay = governance_fingerprint(
            analyzer_key="modernization", analyzer_version="2",
            taxonomy_hash="sha256:taxonomy", alternatives_hash="sha256:alternatives",
            policy={"licenses": ["MIT"], "version": "1"},
            internal_components=list(reversed(components)),
        )
        changed = governance_fingerprint(
            analyzer_key="modernization", analyzer_version="2",
            taxonomy_hash="sha256:taxonomy", alternatives_hash="sha256:alternatives",
            policy={"version": "2", "licenses": ["MIT"]},
            internal_components=components,
        )
        self.assertEqual(first, replay)
        self.assertNotEqual(first, changed)

    def test_calibration_gate_fails_closed_on_missing_or_insufficient_evidence(self) -> None:
        result = evaluate_promotion_gate(
            CalibrationMetrics(
                candidate_precision=0.91, recommendation_acceptance=None,
                validation_success=0.9, affected_scope_mae=0.1,
                effort_accuracy=0.8, reviewed_cases=8,
            ),
            CalibrationThresholds(minimum_reviewed_cases=20),
        )
        self.assertFalse(result.passed)
        self.assertIn("recommendation_acceptance is unavailable", result.failures)
        self.assertTrue(result.fingerprint.startswith("sha256:"))

    def test_shared_footprint_feeds_scoring_and_budget_optimization(self) -> None:
        footprint = CapabilityFootprint(
            application_count=5, repository_count=8,
            technology_counts={"a": 4, "b": 4},
        )
        self.assertAlmostEqual(footprint.technology_entropy, 1.0)
        policy = PortfolioScoringPolicy()
        high = score_portfolio_candidate(PortfolioCandidate(
            id="high", business_importance=0.9, viability_gap=0.8,
            confidence=0.9, effort_points=8, footprint=footprint,
        ), policy)
        low = score_portfolio_candidate(PortfolioCandidate(
            id="low", business_importance=0.3, viability_gap=0.3,
            confidence=0.8, effort_points=5,
            footprint=CapabilityFootprint(1, 1, {"a": 1}),
        ), policy)
        expensive = score_portfolio_candidate(PortfolioCandidate(
            id="expensive", business_importance=1, viability_gap=1,
            confidence=1, effort_points=13, footprint=footprint,
        ), policy)
        selected = optimize_portfolio((high, low, expensive), budget_points=13)
        self.assertEqual([item.candidate.id for item in selected], ["high", "low"])

    def test_ecosystems_are_admitted_sequentially_on_measured_demand(self) -> None:
        blocked = evaluate_ecosystem_admission(
            EcosystemDemand("MAVEN", 50, 0.2, True, True),
            predecessor_admitted=False,
        )
        admitted = evaluate_ecosystem_admission(
            EcosystemDemand("MAVEN", 50, 0.2, True, True),
            predecessor_admitted=True,
        )
        self.assertFalse(blocked.admitted)
        self.assertTrue(admitted.admitted)


if __name__ == "__main__":
    unittest.main()

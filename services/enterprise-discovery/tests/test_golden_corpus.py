"""Correctness gate over the versioned golden repository corpus.

This is the test the Phase 2 plan's §9.1 objectives are measured by. Expectations are curated,
so the bar is total: every labelled fact must be emitted and no labelled false positive may
appear. A regression here is a correctness regression, not a flake.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from golden_corpus import evaluate, load_cases, score


class GoldenCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()
        cls.workspace = TemporaryDirectory()
        cls.results = [evaluate(case, Path(cls.workspace.name)) for case in cls.cases]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.workspace.cleanup()

    def test_every_case_meets_its_labelled_expectations(self) -> None:
        for result in self.results:
            with self.subTest(case=result.case.identifier):
                self.assertEqual(
                    [], list(result.missing),
                    f"{result.case.identifier} did not emit: "
                    + "; ".join(matcher.describe() for matcher in result.missing),
                )
                self.assertEqual(
                    [], list(result.unexpected),
                    f"{result.case.identifier} emitted a labelled false positive: "
                    + "; ".join(matcher.describe() for matcher in result.unexpected),
                )

    def test_completeness_and_classifications_are_pinned(self) -> None:
        for result in self.results:
            with self.subTest(case=result.case.identifier):
                self.assertEqual(
                    result.case.expected_completeness, result.result["completeness"],
                )
                if result.case.expected_classifications is not None:
                    self.assertEqual(
                        sorted(result.case.expected_classifications),
                        list(result.actual_classifications),
                    )

    def test_declared_diagnostics_are_raised(self) -> None:
        for result in self.results:
            codes = {item["code"] for item in result.result.get("diagnostics") or ()}
            for expected in result.case.expected_diagnostic_codes:
                with self.subTest(case=result.case.identifier, code=expected):
                    self.assertIn(expected, codes)

    def test_corpus_precision_and_recall_hold_at_one(self) -> None:
        report = score(self.results)
        self.assertEqual(
            0, report["false_negatives"], json.dumps(report["per_case"], indent=2),
        )
        self.assertEqual(
            0, report["false_positives"], json.dumps(report["per_case"], indent=2),
        )
        self.assertEqual(1.0, report["recall"])
        self.assertEqual(1.0, report["precision"])

    def test_the_corpus_covers_every_shape_the_plan_names(self) -> None:
        # B0 enumerates the repository shapes the baseline must cover. Losing one silently
        # would shrink the corpus while the score still read 100%.
        self.assertEqual(
            {
                "containerized-service", "data-analytics", "generated-vendor-tree",
                "kubernetes-terraform", "large-bounded-repo", "malformed-input",
                "npm-single-app", "pnpm-monorepo", "python-library", "runtime-contradiction",
                "serverless-app",
            },
            {case.identifier for case in self.cases},
        )

    def test_scanning_is_deterministic_over_the_corpus(self) -> None:
        with TemporaryDirectory() as directory:
            for case in self.cases:
                with self.subTest(case=case.identifier):
                    first = evaluate(case, Path(directory)).result
                    second = evaluate(case, Path(directory)).result
                    self.assertEqual(
                        [fact["idempotency_key"] for fact in first["facts"]],
                        [fact["idempotency_key"] for fact in second["facts"]],
                    )


if __name__ == "__main__":
    unittest.main()

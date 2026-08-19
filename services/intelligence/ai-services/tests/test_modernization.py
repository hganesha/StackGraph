from __future__ import annotations

import unittest
from pathlib import Path
from uuid import UUID

from stackgraph_ai.modernization import (
    AlternativeCatalog,
    DependencyUsage,
    DuplicateInput,
    analyze_duplicate,
)


CATALOG = Path(__file__).resolve().parents[1] / "alternatives" / "default.json"


def dependency(index: int, package: str, references: int) -> DependencyUsage:
    return DependencyUsage(
        entity_id=UUID(f"00000000-0000-4000-8000-{index:012d}"),
        canonical_key=f"pkg:npm/{package}@1.0.0",
        name=package,
        inference_id=UUID(f"00000000-0000-4000-8100-{index:012d}"),
        supporting_fact_ids=(UUID(f"00000000-0000-4000-9000-{index:012d}"),),
        confidence=0.99,
        reference_count=references,
        referenced_symbols=("get",),
        source_locations=({"path": f"src/{package}.ts", "line_start": index},),
    )


class ModernizationTests(unittest.TestCase):
    def test_catalog_is_versioned_and_bounded(self) -> None:
        catalog = AlternativeCatalog.load(CATALOG)
        self.assertEqual(catalog.version, "1.0.0")
        self.assertRegex(catalog.content_hash, r"^sha256:[a-f0-9]{64}$")
        self.assertTrue(all(item.validation_gaps for item in catalog.alternatives))

    def test_duplicate_analysis_prefers_observed_option_with_smaller_replacement_surface(self) -> None:
        result = analyze_duplicate(
            DuplicateInput(
                id=UUID("00000000-0000-4000-8000-000000000001"),
                repository_id=UUID("00000000-0000-4000-8000-000000000002"),
                source_revision="revision-1",
                capability_definition_id=UUID("00000000-0000-4000-8000-000000000003"),
                capability_key="http-client",
                capability_name="HTTP Client",
                confidence=0.98,
                dependencies=(dependency(10, "axios", 12), dependency(11, "undici", 2)),
            ),
            AlternativeCatalog.load(CATALOG),
        )

        self.assertEqual(result.candidate_kind, "DEPENDENCY_CONSOLIDATION")
        self.assertEqual(result.options[0].name, "axios")
        self.assertEqual(result.recommendation.affected_call_sites, 2)
        self.assertEqual(result.recommendation.affected_files, 2)
        self.assertEqual(result.recommendation.estimated_effort, "LOW")
        self.assertTrue(any("do not prove" in item.lower() for item in result.validation_gaps))
        self.assertTrue(any(item.kind == "NATIVE" for item in result.options))

    def test_analysis_fingerprints_are_replay_stable(self) -> None:
        duplicate = DuplicateInput(
            id=UUID("00000000-0000-4000-8000-000000000001"),
            repository_id=UUID("00000000-0000-4000-8000-000000000002"),
            source_revision="revision-1",
            capability_definition_id=UUID("00000000-0000-4000-8000-000000000003"),
            capability_key="http-client",
            capability_name="HTTP Client",
            confidence=0.98,
            dependencies=(dependency(10, "axios", 12), dependency(11, "undici", 2)),
        )
        catalog = AlternativeCatalog.load(CATALOG)
        first = analyze_duplicate(duplicate, catalog)
        second = analyze_duplicate(duplicate, catalog)
        self.assertEqual(first.analysis_fingerprint, second.analysis_fingerprint)
        self.assertEqual(
            first.recommendation.analysis_fingerprint,
            second.recommendation.analysis_fingerprint,
        )


if __name__ == "__main__":
    unittest.main()

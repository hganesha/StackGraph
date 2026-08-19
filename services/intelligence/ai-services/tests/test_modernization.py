from __future__ import annotations

import unittest
from pathlib import Path
from uuid import UUID

from stackgraph_ai.modernization import (
    AlternativeDefinition,
    AlternativeCatalog,
    CodeUnitEvidence,
    DependencyUsage,
    DuplicateInput,
    ModernizationPolicyInput,
    analyze_duplicate,
    analyze_native_replacement,
    analyze_structural_duplication,
    evaluate_alternative,
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
        self.assertEqual(catalog.version, "2.0.0")
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

    def test_alternative_requires_every_eligibility_dimension_to_pass(self) -> None:
        alternative = AlternativeDefinition(
            capability_key="http-client", kind="NATIVE", key="runtime:web-fetch",
            name="Fetch", rationale="Native runtime option.",
            provided_symbols=("get", "post"), runtime_constraints={"node": ">=18"},
            license="RUNTIME", security_status="CLEAR", policy_tags=("runtime-native",),
            behavior_verified=True,
        )
        policy = ModernizationPolicyInput(
            key="production", version="1", runtime_versions={"node": "20.11.0"},
            allowed_licenses=("RUNTIME", "MIT"), allowed_security_statuses=("CLEAR",),
            required_policy_tags=("runtime-native",),
        )

        eligible = evaluate_alternative(
            alternative, required_symbols=("get",), policy=policy,
            supporting_fact_ids=(UUID("00000000-0000-4000-9000-000000000001"),),
        )
        blocked = evaluate_alternative(
            alternative, required_symbols=("stream",), policy=policy,
            supporting_fact_ids=(UUID("00000000-0000-4000-9000-000000000001"),),
        )

        self.assertTrue(eligible.eligible)
        self.assertFalse(eligible.unknowns)
        self.assertFalse(blocked.eligible)
        self.assertEqual(blocked.api_fit, "FAIL")

    def test_structural_duplication_is_tenant_evidence_backed_and_maps_impact(self) -> None:
        repository = UUID("00000000-0000-4000-8000-000000000020")

        def unit(index: int, repository_id: UUID, path: str) -> CodeUnitEvidence:
            return CodeUnitEvidence(
                id=UUID(f"00000000-0000-4000-8100-{index:012d}"),
                repository_id=repository_id,
                fact_id=UUID(f"00000000-0000-4000-9100-{index:012d}"),
                source_revision="revision-1", language="python",
                qualified_name="normalize_token", path=path, line_start=4, line_end=9,
                structural_fingerprint="sha256:" + "a" * 64,
                semantic_tokens=("normalize", "token"), dependency_keys=(),
                covering_tests=(path.replace(".py", "_test.py"),),
                dynamic_signals=(), touchpoints=({"kind": "BUILD", "path": "pyproject.toml"},),
            )

        analysis = analyze_structural_duplication(
            repository_id=repository, source_revision="revision-1",
            units=(
                unit(1, repository, "src/token.py"),
                unit(2, UUID("00000000-0000-4000-8000-000000000021"), "src/auth.py"),
            ),
        )

        self.assertEqual(analysis.candidate_kind, "INTERNAL_DUPLICATION")
        self.assertEqual(len(analysis.source_code_unit_ids), 2)
        self.assertEqual(analysis.impact.covered_call_sites, 1)
        self.assertIn("src/token_test.py", analysis.impact.affected_test_files)
        self.assertEqual(analysis.recommendation.action, "REFACTOR")

    def test_native_replacement_requires_eligible_alternative_before_replace(self) -> None:
        repository = UUID("00000000-0000-4000-8000-000000000020")
        observed = dependency(10, "axios", 4)
        policy = ModernizationPolicyInput(
            key="production", version="1", runtime_versions={"node": "20.11.0"},
            allowed_licenses=("RUNTIME",), allowed_security_statuses=("CLEAR",),
            required_policy_tags=("runtime-native",),
        )
        catalog = AlternativeCatalog.load(CATALOG)

        investigate = analyze_native_replacement(
            repository_id=repository, source_revision="revision-1",
            capability_definition_id=UUID("00000000-0000-4000-8000-000000000030"),
            capability_key="http-client", capability_name="HTTP Client",
            dependency=observed, catalog=catalog, policy=policy,
        )
        replace = analyze_native_replacement(
            repository_id=repository, source_revision="revision-1",
            capability_definition_id=UUID("00000000-0000-4000-8000-000000000030"),
            capability_key="http-client", capability_name="HTTP Client",
            dependency=observed, catalog=catalog, policy=policy,
            additional_alternatives=(AlternativeDefinition(
                capability_key="http-client", kind="NATIVE", key="runtime:verified-fetch",
                name="Verified Fetch", rationale="Validated runtime replacement.",
                provided_symbols=("get",), runtime_constraints={"node": ">=18"},
                license="RUNTIME", security_status="CLEAR",
                policy_tags=("runtime-native",), behavior_verified=True,
            ),),
        )

        self.assertIsNotNone(investigate)
        self.assertIsNotNone(replace)
        self.assertEqual(investigate.recommendation.action, "INVESTIGATE")
        self.assertEqual(replace.recommendation.action, "REPLACE")
        selected = next(
            option for option in replace.options
            if option.canonical_key == replace.recommendation.selected_option_key
        )
        self.assertTrue(selected.eligibility.eligible)
        self.assertEqual(selected.compatibility, "COMPATIBLE")


if __name__ == "__main__":
    unittest.main()

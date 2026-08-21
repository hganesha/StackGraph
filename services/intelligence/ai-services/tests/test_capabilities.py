from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from stackgraph_ai.capabilities import (
    LocalCapabilityCatalog,
    PackageUsage,
    PersistedInference,
    curated_inferences,
    duplicate_capability_candidates,
    infer_with_ai,
)
from stackgraph_ai.models import (
    ModelResponse,
    ModelRoute,
    PromptDefinition,
    PromptInvocation,
    PromptMessageTemplate,
)


CATALOG = Path(__file__).resolve().parents[1] / "capabilities"
TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-000000000002")


def usage(
    subject_suffix: int,
    package: str,
    *,
    symbols: tuple[str, ...] = ("get",),
    ecosystem: str = "npm",
) -> PackageUsage:
    subject_id = UUID(f"00000000-0000-4000-8000-{subject_suffix:012d}")
    fact_id = UUID(f"00000000-0000-4000-9000-{subject_suffix:012d}")
    return PackageUsage(
        repository_id=REPOSITORY_ID,
        repository_key="github:repo:123",
        subject_entity_id=subject_id,
        subject_key=f"pkg:{ecosystem}/{package}@1.0.0",
        source_revision="a" * 40,
        ecosystem=ecosystem,
        package_name=package,
        referenced_symbols=symbols,
        supporting_fact_ids=(fact_id,),
    )


class FakeAI:
    def __init__(self, output: dict) -> None:
        self.output = output

    async def invoke(self, *args, **kwargs) -> PromptInvocation:
        del args, kwargs
        prompt = PromptDefinition(
            key="capability.inference",
            version="1.3.0",
            status="ACTIVE",
            messages=(PromptMessageTemplate(role="system", content="Classify."),),
            metadata={"policy_version": "capability-inference/v1.3"},
        )
        return PromptInvocation(
            prompt=prompt,
            route=ModelRoute("default", "fake", "fake-model"),
            input_fingerprint="sha256:" + "b" * 64,
            response=ModelResponse(
                provider="fake",
                model="fake-model",
                text=None,
                structured_output=self.output,
            ),
            invocation_id=UUID("00000000-0000-4000-8000-000000000099"),
        )


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = LocalCapabilityCatalog(CATALOG).definitions()[0]

    def test_catalog_is_versioned_and_mappings_reference_known_capabilities(self) -> None:
        self.assertEqual(self.taxonomy.version, "1.0.0")
        self.assertEqual(self.taxonomy.status, "ACTIVE")
        self.assertRegex(self.taxonomy.content_hash, r"^sha256:[a-f0-9]{64}$")
        self.assertGreaterEqual(len(self.taxonomy.capabilities), 10)
        self.assertTrue(all(
            mapping.capability_key in self.taxonomy.capability_by_key
            for mapping in self.taxonomy.mappings
        ))

    def test_curated_mapping_uses_referenced_symbols_and_is_idempotent(self) -> None:
        lodash = usage(10, "lodash", symbols=("debounce",))
        first = curated_inferences(self.taxonomy, lodash)
        second = curated_inferences(self.taxonomy, lodash)

        self.assertEqual(
            {item.capability_key for item in first},
            {"rate-control", "collection-object-utilities"},
        )
        self.assertEqual(
            [item.analysis_fingerprint for item in first],
            [item.analysis_fingerprint for item in second],
        )

    def test_inactive_usage_does_not_create_capability_truth(self) -> None:
        inactive = replace(
            usage(11, "axios"),
            referenced=False,
            runtime_observed="NOT_OBSERVED",
        )
        self.assertEqual(curated_inferences(self.taxonomy, inactive), ())

    def test_ai_output_must_use_known_capability_and_supplied_evidence(self) -> None:
        subject = usage(12, "mystery-client")
        fact_id = str(subject.supporting_fact_ids[0])
        output = {
            "capability": "http-client",
            "confidence": 0.8,
            "evidence_refs": [fact_id],
            "rationale": "The supplied symbol evidence indicates HTTP use.",
        }
        proposal = asyncio.run(infer_with_ai(
            FakeAI(output), self.taxonomy, subject, tenant_id=TENANT_ID,
        ))
        self.assertEqual(proposal.assertion_class, "INFERRED")
        self.assertEqual(proposal.model_provider, "fake")

        output["evidence_refs"] = []
        proposal = asyncio.run(infer_with_ai(
            FakeAI(output), self.taxonomy, subject, tenant_id=TENANT_ID,
        ))
        self.assertEqual(proposal.supporting_fact_ids, subject.supporting_fact_ids)

        output["evidence_refs"] = ["00000000-0000-4000-9000-999999999999"]
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            asyncio.run(infer_with_ai(
                FakeAI(output), self.taxonomy, subject, tenant_id=TENANT_ID,
            ))

    def test_duplicate_candidate_requires_two_distinct_dependencies(self) -> None:
        axios = curated_inferences(self.taxonomy, usage(20, "axios"))[0]
        undici = curated_inferences(self.taxonomy, usage(21, "undici"))[0]
        candidates = duplicate_capability_candidates((
            PersistedInference(UUID("00000000-0000-4000-8000-000000000020"), axios),
            PersistedInference(UUID("00000000-0000-4000-8000-000000000021"), undici),
        ))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].capability_key, "http-client")
        self.assertIn("does not prove", candidates[0].limitations[0])


if __name__ == "__main__":
    unittest.main()

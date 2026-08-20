from __future__ import annotations

import json
import unittest
from pathlib import Path

from stackgraph_discovery.runtime_import import import_runtime_observation


class RuntimeObservationImportTests(unittest.TestCase):
    def test_verified_runtime_event_becomes_evidence_backed_observed_fact(self) -> None:
        fixture = Path(__file__).resolve().parents[3] / "stackgraph-foundation/contracts/v1/fixtures/runtime-observation.json"
        observation = json.loads(fixture.read_text(encoding="utf-8"))
        facts = import_runtime_observation(observation)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["assertion_class"], "OBSERVED")
        self.assertTrue(facts[0]["properties"]["absence_is_unknown"])
        self.assertEqual(facts[0]["evidence"][0]["locator"]["json_pointer"], "/resource/container/image/id")

    def test_unverified_observation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "verified"):
            import_runtime_observation({
                "runtime_contract_version": "1.0.0",
                "absence_is_unknown": True,
                "source": {"verified": False},
            })


if __name__ == "__main__":
    unittest.main()

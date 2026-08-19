import os
import unittest
from pathlib import Path

from stackgraph_data.catalog import load_catalog, sha256_key


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(Path(os.environ.get("STACKGRAPH_SEED_DIR", "/seed")))

    def test_manifest_counts_match_catalog(self) -> None:
        self.assertEqual(len(self.catalog.technologies), 192)
        self.assertEqual(len(self.catalog.capabilities), 38)
        self.assertEqual(len(self.catalog.relationships), 101)
        self.assertEqual(len(self.catalog.assessments), 6)

    def test_catalog_bundle_hash_is_stable(self) -> None:
        self.assertEqual(self.catalog.bundle_hash, self.catalog.bundle_hash)
        self.assertTrue(self.catalog.bundle_hash.startswith("sha256:"))

    def test_semantic_keys_are_order_independent_for_json(self) -> None:
        self.assertEqual(
            sha256_key({"a": 1, "b": 2}),
            sha256_key({"b": 2, "a": 1}),
        )


if __name__ == "__main__":
    unittest.main()

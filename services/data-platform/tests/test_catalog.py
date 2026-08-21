import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stackgraph_data.catalog import load_catalog, sha256_key
from stackgraph_data.migrate import (
    CANONICAL_DEPENDENCY_USAGE_CHECKSUM,
    LEGACY_DEPENDENCY_USAGE_CHECKSUM,
    LEGACY_DEPENDENCY_USAGE_VERSION,
    file_checksum,
    legacy_checksum_candidate,
    migration_paths,
)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(Path(os.environ.get("STACKGRAPH_SEED_DIR", "/seed")))

    def test_manifest_counts_match_catalog(self) -> None:
        self.assertEqual(len(self.catalog.technologies), 234)
        self.assertEqual(len(self.catalog.categories), 44)
        self.assertEqual(len(self.catalog.capabilities), 38)
        self.assertEqual(len(self.catalog.relationships), 101)
        self.assertEqual(len(self.catalog.assessments), 6)

    def test_oss_core_categories_and_package_aliases_are_loaded(self) -> None:
        categories = {item["id"] for item in self.catalog.categories}
        self.assertTrue({
            "js-ts-compiler-transpilation",
            "build-tools-bundlers",
            "code-quality-linting",
            "styling-ui",
            "frontend-framework-routing",
            "python-data-backend",
            "filesystem-path-utilities",
            "data-algorithm-utilities",
        }.issubset(categories))
        technologies = {item["id"]: item for item in self.catalog.technologies}
        self.assertIn("@babel/helper-*", technologies["babel-code-generation-helpers"]["aliases"])
        self.assertIn("@rolldown/binding-*", technologies["rolldown-rspack-esbuild-swc"]["aliases"])
        self.assertEqual(
            technologies["typescript-eslint-toolchain"]["category_id"],
            "code-quality-linting",
        )
        self.assertEqual(technologies["pandas"]["seed_file"], "oss-core.json")
        self.assertEqual(
            technologies["react-router"]["seed_file"],
            "oss-core.json",
        )

    def test_catalog_bundle_hash_is_stable(self) -> None:
        self.assertEqual(self.catalog.bundle_hash, self.catalog.bundle_hash)
        self.assertTrue(self.catalog.bundle_hash.startswith("sha256:"))

    def test_semantic_keys_are_order_independent_for_json(self) -> None:
        self.assertEqual(
            sha256_key({"a": 1, "b": 2}),
            sha256_key({"b": 2, "a": 1}),
        )

    def test_migration_checksum_detects_content_changes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "001_example.sql"
            path.write_text("SELECT 1;\n", encoding="utf-8")
            first_checksum = file_checksum(path)
            path.write_text("SELECT 2;\n", encoding="utf-8")
            self.assertNotEqual(first_checksum, file_checksum(path))

    def test_migration_discovery_ignores_noncanonical_duplicate_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "001_example.sql").write_text("SELECT 1;\n", encoding="utf-8")
            (root / "001_example 2.sql").write_text("SELECT 2;\n", encoding="utf-8")
            (root / "notes.sql").write_text("SELECT 3;\n", encoding="utf-8")
            self.assertEqual(
                [path.name for path in migration_paths(root)],
                ["001_example.sql"],
            )

    def test_only_the_known_005_checksum_pair_is_a_legacy_candidate(self) -> None:
        self.assertTrue(legacy_checksum_candidate(
            LEGACY_DEPENDENCY_USAGE_VERSION,
            LEGACY_DEPENDENCY_USAGE_CHECKSUM,
            CANONICAL_DEPENDENCY_USAGE_CHECKSUM,
        ))
        self.assertFalse(legacy_checksum_candidate(
            LEGACY_DEPENDENCY_USAGE_VERSION,
            "0" * 64,
            CANONICAL_DEPENDENCY_USAGE_CHECKSUM,
        ))
        self.assertFalse(legacy_checksum_candidate(
            LEGACY_DEPENDENCY_USAGE_VERSION,
            LEGACY_DEPENDENCY_USAGE_CHECKSUM,
            "f" * 64,
        ))
        self.assertFalse(legacy_checksum_candidate(
            "006_capability_intelligence.sql",
            LEGACY_DEPENDENCY_USAGE_CHECKSUM,
            CANONICAL_DEPENDENCY_USAGE_CHECKSUM,
        ))


if __name__ == "__main__":
    unittest.main()

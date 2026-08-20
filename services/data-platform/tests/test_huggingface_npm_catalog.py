from __future__ import annotations

import unittest

from stackgraph_data.huggingface_npm_catalog import (
    DATASET_EFFECTIVE_AT,
    DATASET_ID,
    DATASET_REVISION,
    _validate_dataset_url,
    parse_dataset,
)


HEADER = (
    "package_name,description,installation_command,latest_version,last_published,"
    "dependents,dependencies,versions,license,total_files,unpacked_size,"
    "weekly_downloads,package_url,homepage,repository\n"
)


class DatasetParsingTests(unittest.TestCase):
    def test_dataset_url_allowlist_accepts_hugging_face_cache_redirect(self) -> None:
        _validate_dataset_url(
            "https://huggingface.co/api/resolve-cache/datasets/"
            "deepklarity/top-npm-packages/revision/npm_packages.csv?etag=abc"
        )
        with self.assertRaises(ValueError):
            _validate_dataset_url("https://example.com/npm_packages.csv")

    def test_preserves_all_fields_and_normalizes_graph_identity(self) -> None:
        content = (
            HEADER
            + "@Scope/Demo,Demo package,npm i @scope/demo,1.2.3,4 months ago,"
            "1,2,12,MIT,7.0,2.23 MB,345,"
            "https://www.npmjs.com/package/%40scope%2Fdemo,"
            "https://example.com/docs,https://github.com/acme/demo.git/#readme\n"
        ).encode()

        records = parse_dataset(content)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.package_purl, "pkg:npm/%40scope/demo")
        self.assertEqual(record.version_purl, "pkg:npm/%40scope/demo@1.2.3")
        self.assertEqual(record.repository_url, "https://github.com/acme/demo")
        self.assertEqual(record.metadata["dataset_id"], DATASET_ID)
        self.assertEqual(record.metadata["dataset_revision"], DATASET_REVISION)
        self.assertEqual(
            record.metadata["dataset_effective_at"], DATASET_EFFECTIVE_AT.isoformat()
        )
        self.assertEqual(record.metadata["source_fields"]["package_name"], "@Scope/Demo")
        self.assertEqual(record.metadata["last_published_text"], "4 months ago")
        self.assertEqual(record.metadata["unpacked_size"], "2.23 MB")
        self.assertEqual(record.metadata["unpacked_size_bytes"], 2_230_000)
        self.assertEqual(record.metadata["weekly_downloads"], 345)
        self.assertEqual(record.metadata["total_files"], 7)

    def test_handles_multiline_descriptions_and_missing_optional_values(self) -> None:
        content = (
            HEADER
            + 'demo,"first line\nsecond line",npm i demo,1.0.0,a year ago,'
            "0,0,1,,1.0,43.7 kB,1,https://www.npmjs.com/package/demo,,\n"
        ).encode()

        record = parse_dataset(content)[0]

        self.assertEqual(record.metadata["description"], "first line\nsecond line")
        self.assertEqual(record.metadata["unpacked_size_bytes"], 43_700)
        self.assertIsNone(record.metadata["license"])
        self.assertIsNone(record.repository_url)

    def test_rejects_duplicate_packages_after_npm_normalization(self) -> None:
        rows = (
            "Demo,one,npm i demo,1.0.0,today,0,0,1,MIT,1,1 kB,1,"
            "https://www.npmjs.com/package/demo,,\n"
            "demo,two,npm i demo,2.0.0,today,0,0,2,MIT,2,2 kB,2,"
            "https://www.npmjs.com/package/demo,,\n"
        )

        with self.assertRaisesRegex(ValueError, "duplicates npm package"):
            parse_dataset((HEADER + rows).encode())

    def test_rejects_missing_columns_and_invalid_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing columns"):
            parse_dataset(b"package_name,latest_version\ndemo,1.0.0\n")
        invalid = (
            HEADER
            + "demo,desc,npm i demo,1.0.0,today,-1,0,1,MIT,1,1 kB,1,"
            "https://www.npmjs.com/package/demo,,\n"
        )
        with self.assertRaisesRegex(ValueError, "invalid dependents"):
            parse_dataset(invalid.encode())

    def test_captures_future_dataset_columns(self) -> None:
        content = (
            HEADER.rstrip("\n")
            + ",quality_score\n"
            + "demo,desc,npm i demo,1.0.0,today,0,0,1,MIT,1,1 kB,1,"
            "https://www.npmjs.com/package/demo,,,gold\n"
        ).encode()

        record = parse_dataset(content)[0]

        self.assertEqual(record.metadata["extra_fields"], {"quality_score": "gold"})

    def test_repairs_missing_name_from_the_canonical_npm_url(self) -> None:
        content = (
            HEADER
            + ",Native abstractions,npm i nan,2.20.0,3 months ago,7880,0,87,"
            "MIT,48,430 kB,17540715,https://www.npmjs.com/package/nan,,\n"
        ).encode()

        record = parse_dataset(content)[0]

        self.assertEqual(record.package_purl, "pkg:npm/nan")
        self.assertTrue(record.metadata["package_name_inferred"])
        self.assertIsNone(record.metadata["source_fields"]["package_name"])


if __name__ == "__main__":
    unittest.main()

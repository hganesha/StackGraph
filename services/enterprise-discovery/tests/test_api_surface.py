from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stackgraph_discovery.api_surface import analyze_artifact


CHECKSUM = "sha256:" + "a" * 64


class ApiSurfaceTests(unittest.TestCase):
    def test_extracts_javascript_exports_with_checksum_keyed_fingerprint(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.js").write_text(
                "export function debounce() {}\nexport class Cache {}\nexport { Cache as MemoryCache };\n"
            )

            first = analyze_artifact(
                root,
                ecosystem="npm",
                package_purl="pkg:npm/example@1.0.0",
                artifact_checksum=CHECKSUM,
            )
            replay = analyze_artifact(
                root,
                ecosystem="npm",
                package_purl="pkg:npm/example@1.0.0",
                artifact_checksum=CHECKSUM,
            )

        self.assertEqual(first["analysis_fingerprint"], replay["analysis_fingerprint"])
        self.assertEqual(
            {symbol["name"] for symbol in first["symbols"]},
            {"debounce", "Cache", "MemoryCache"},
        )

    def test_python_all_limits_public_surface(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "library.py").write_text(
                "__all__ = ['public']\n\ndef public(): pass\ndef also_public_without_all(): pass\ndef _private(): pass\n"
            )
            result = analyze_artifact(
                root,
                ecosystem="pypi",
                package_purl="pkg:pypi/example@1.0.0",
                artifact_checksum=CHECKSUM,
            )

        self.assertEqual([symbol["name"] for symbol in result["symbols"]], ["public"])


if __name__ == "__main__":
    unittest.main()

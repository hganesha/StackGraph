from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stackgraph_discovery.repository_scanner import scan_repository

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError:  # runtime scanner has no schema-validation dependency
    Draft202012Validator = None


REVISION = "a" * 40
SNAPSHOT_DIGEST = "b" * 64
SNAPSHOT_URI = (
    "stackgraph-evidence://local/tenants/"
    f"{'c' * 64}/sha256/{SNAPSHOT_DIGEST}"
)


def request(root: Path, *, max_files: int = 100) -> dict:
    return {
        "scanner_contract_version": "1.0.0",
        "run_id": "00000000-0000-4000-8000-000000000101",
        "tenant_key": "acme",
        "target": {
            "provider": "github",
            "repository_id": "123",
            "canonical_key": "github:repo:123",
            "name": "billing-api",
            "default_branch": "main",
        },
        "snapshot": {
            "source_revision": REVISION,
            "checkout_root": str(root),
            "requested_at": "2026-08-19T14:00:00Z",
            "blob_uri": SNAPSHOT_URI,
            "content_hash": f"sha256:{SNAPSHOT_DIGEST}",
            "content_size_bytes": 4096,
        },
        "limits": {
            "max_files": max_files,
            "max_bytes": 1_000_000,
            "deadline_seconds": 30,
        },
    }


class RepositoryScannerTests(unittest.TestCase):
    @unittest.skipUnless(Draft202012Validator, "jsonschema is not installed")
    def test_generated_result_validates_frozen_scanner_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("requests==2.32.3\n")
            (root / "main.py").write_text("import requests\nrequests.get('https://example.test')\n")
            result = scan_repository(request(root))

        contracts = Path(__file__).resolve().parents[3] / "stackgraph-foundation/contracts/v1/schemas"
        schemas = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in contracts.glob("*.schema.json")
        ]
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in schemas
        )
        scanner_schema = next(schema for schema in schemas if schema["$id"].endswith("scanner-result.schema.json"))

        Draft202012Validator(
            scanner_schema,
            registry=registry,
            format_checker=FormatChecker(),
        ).validate(result)

    def test_npm_lock_and_typescript_import_emit_resolved_usage_and_narrow_candidate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({
                "name": "billing-api",
                "dependencies": {"lodash": "^4.17.0"},
            }))
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "": {"dependencies": {"lodash": "^4.17.0"}},
                    "node_modules/lodash": {
                        "version": "4.17.21",
                        "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                        "integrity": "sha512-example",
                    },
                },
            }))
            (root / "index.ts").write_text(
                "import { debounce, get as read } from 'lodash';\nconsole.log(debounce, read);\n"
            )

            result = scan_repository(request(root))

        self.assertEqual(result["completeness"], "COMPLETE")
        dependency = next(fact for fact in result["facts"] if fact["predicate"] == "DEPENDS_ON")
        self.assertEqual(dependency["object_entity"]["key"], "pkg:npm/lodash@4.17.21")
        self.assertTrue(dependency["properties"]["usage"]["referenced"])
        self.assertEqual(
            dependency["properties"]["usage"]["referenced_symbols"],
            ["debounce", "get"],
        )
        self.assertEqual(dependency["properties"]["usage"]["static_reachability"], "OBSERVED")
        finding = next(fact for fact in result["facts"] if fact["predicate"] == "HAS_PROPERTY")
        self.assertEqual(finding["object_value"]["finding_type"], "NARROW_USE_DEPENDENCY_CANDIDATE")
        self.assertGreaterEqual(len(dependency["evidence"]), 3)
        self.assertEqual(
            dependency["evidence"][0]["source_artifact"]["uri"],
            f"{SNAPSHOT_URI}#path=files/package.json",
        )
        application = next(
            fact for fact in result["facts"] if fact["predicate"] == "IMPLEMENTED_BY"
        )
        self.assertEqual(application["subject"]["type"], "Application")
        self.assertEqual(application["object_entity"]["type"], "Repository")
        self.assertEqual(application["assertion_class"], "INFERRED")
        self.assertEqual(application["properties"]["boundary_strategy"], "REPOSITORY_FALLBACK")
        self.assertEqual(application["evidence"][0]["locator"]["path"], "package.json")

    def test_monorepo_application_boundary_is_explicitly_provisional(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({
                "name": "portfolio", "private": True, "workspaces": ["apps/*"],
            }))
            (root / "apps").mkdir()
            (root / "apps" / "web").mkdir()
            (root / "apps" / "web" / "package.json").write_text(json.dumps({"name": "web"}))
            (root / "apps" / "api").mkdir()
            (root / "apps" / "api" / "package.json").write_text(json.dumps({"name": "api"}))

            result = scan_repository(request(root))

        application = next(
            fact for fact in result["facts"] if fact["predicate"] == "IMPLEMENTED_BY"
        )
        self.assertEqual(application["properties"]["boundary_strategy"], "REPOSITORY_PORTFOLIO")
        self.assertTrue(application["properties"]["provisional"])
        self.assertEqual(application["properties"]["review_state"], "UNREVIEWED")
        self.assertLess(application["confidence"], 0.6)
        self.assertIn("package.json#workspaces", application["properties"]["monorepo_signals"])

    def test_snapshot_blob_descriptor_must_be_complete(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scan_request = request(root)
            del scan_request["snapshot"]["content_hash"]

            with self.assertRaisesRegex(ValueError, "must be supplied together"):
                scan_repository(scan_request)

    def test_python_lock_import_and_reachability_are_distinct_measurements(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[project]\nname="analytics"\ndependencies=["pandas>=2"]\n'
            )
            (root / "uv.lock").write_text(
                'version=1\n[[package]]\nname="pandas"\nversion="2.2.3"\n'
            )
            (root / "main.py").write_text("from pandas import DataFrame\nprint(DataFrame)\n")

            result = scan_repository(request(root))

        dependency = next(fact for fact in result["facts"] if fact["predicate"] == "DEPENDS_ON")
        self.assertEqual(dependency["object_entity"]["key"], "pkg:pypi/pandas@2.2.3")
        usage = dependency["properties"]["usage"]
        self.assertTrue(usage["resolved"])
        self.assertTrue(usage["referenced"])
        self.assertEqual(usage["referenced_symbols"], ["DataFrame"])
        self.assertEqual(usage["static_reachability"], "OBSERVED")
        self.assertEqual(usage["runtime_observed"], "UNKNOWN")

    def test_yarn_and_pnpm_locks_resolve_manifest_dependencies_with_line_evidence(self) -> None:
        locks = {
            "yarn.lock": (
                'lodash@^4.17.0:\n'
                '  version "4.17.21"\n'
                '  resolved "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz"\n'
                '  integrity sha512-example\n'
            ),
            "pnpm-lock.yaml": (
                "lockfileVersion: '9.0'\n"
                "packages:\n"
                "  lodash@4.17.21:\n"
                "    resolution: {integrity: sha512-example}\n"
            ),
        }
        for lock_name, lock_content in locks.items():
            with self.subTest(lock=lock_name), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "package.json").write_text(json.dumps({
                    "dependencies": {"lodash": "^4.17.0"},
                }))
                (root / lock_name).write_text(lock_content)
                (root / "index.js").write_text("const lodash = require('lodash');\n")

                result = scan_repository(request(root))

                dependency = next(
                    fact for fact in result["facts"] if fact["predicate"] == "DEPENDS_ON"
                )
                self.assertEqual(dependency["object_entity"]["key"], "pkg:npm/lodash@4.17.21")
                lock_evidence = next(
                    item for item in dependency["evidence"] if item["type"] == "LOCKFILE"
                )
                self.assertEqual(lock_evidence["locator"]["path"], lock_name)
                self.assertGreaterEqual(lock_evidence["locator"]["line_start"], 1)

    def test_complete_scan_surfaces_unused_candidate_but_partial_scan_does_not(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1.3.0"}}))
            (root / "index.js").write_text("console.log('no imports');\n")
            complete = scan_repository(request(root))
            partial = scan_repository(request(root, max_files=1))

        unused = [
            fact for fact in complete["facts"]
            if fact["predicate"] == "HAS_PROPERTY"
            and fact["object_value"]["finding_type"] == "UNUSED_DECLARED_DEPENDENCY_CANDIDATE"
        ]
        self.assertEqual(len(unused), 1)
        self.assertEqual(partial["completeness"], "PARTIAL")
        self.assertFalse(any(fact["predicate"] == "HAS_PROPERTY" for fact in partial["facts"]))

    def test_runtime_trace_is_reported_separately_from_static_reference(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("requests==2.32.3\n")
            (root / "main.py").write_text("print('loaded indirectly')\n")
            (root / "stackgraph-runtime.json").write_text(json.dumps({
                "events": [{"ecosystem": "pypi", "package": "requests", "symbol": "get", "count": 3}],
            }))

            result = scan_repository(request(root))

        dependency = next(fact for fact in result["facts"] if fact["predicate"] == "DEPENDS_ON")
        usage = dependency["properties"]["usage"]
        self.assertFalse(usage["referenced"])
        self.assertEqual(usage["runtime_observed"], "OBSERVED")
        self.assertFalse(any(fact["predicate"] == "HAS_PROPERTY" for fact in result["facts"]))

    def test_code_units_capture_structure_tests_dynamic_gaps_and_touchpoints(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"dependencies": {"axios": "1.7.0"}}))
            (root / "index.ts").write_text(
                "import axios from 'axios';\n"
                "export function fetchInvoice(id: string) {\n"
                "  return axios.get('/invoice/' + id);\n"
                "}\n"
            )
            (root / "index.test.ts").write_text(
                "import { fetchInvoice } from './index';\n"
                "test('invoice', () => fetchInvoice('1'));\n"
            )
            (root / "plugins.ts").write_text(
                "export function loadPlugin(name: string) { return import(name); }\n"
            )
            (root / "compose.yaml").write_text("services: {}\n")

            result = scan_repository(request(root))

        summaries = [
            fact["object_value"] for fact in result["facts"]
            if fact["predicate"] == "HAS_PROPERTY"
            and fact["object_value"].get("record_kind") == "code_implementation_summary"
        ]
        invoice = next(item for item in summaries if item["qualified_name"] == "fetchInvoice")
        plugin = next(item for item in summaries if item["qualified_name"] == "loadPlugin")
        self.assertRegex(invoice["structural_fingerprint"], r"^sha256:[a-f0-9]{64}$")
        self.assertIn("pkg:npm/axios", invoice["dependency_keys"])
        self.assertEqual(invoice["covering_tests"], ["index.test.ts"])
        self.assertIn({"kind": "DEPLOYMENT", "path": "compose.yaml"}, invoice["touchpoints"])
        self.assertIn("DYNAMIC_IMPORT", plugin["dynamic_signals"])
        self.assertEqual(result["stats"]["code_units_emitted"], len(summaries))

    def test_python_structural_fingerprint_ignores_local_names_and_literals(self) -> None:
        with TemporaryDirectory() as first_directory, TemporaryDirectory() as second_directory:
            first = Path(first_directory)
            second = Path(second_directory)
            (first / "main.py").write_text("def calculate_total(value):\n    return value + 1\n")
            (second / "main.py").write_text("def sum_amount(amount):\n    return amount + 9\n")

            first_result = scan_repository(request(first))
            second_result = scan_repository(request(second))

        def fingerprint(result):
            return next(
                fact["object_value"]["structural_fingerprint"]
                for fact in result["facts"]
                if fact.get("object_value", {}).get("record_kind") == "code_implementation_summary"
            )

        self.assertEqual(fingerprint(first_result), fingerprint(second_result))


if __name__ == "__main__":
    unittest.main()

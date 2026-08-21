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
        finding = next(
            fact for fact in result["facts"]
            if fact.get("object_value", {}).get("finding_type") == "NARROW_USE_DEPENDENCY_CANDIDATE"
        )
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

    def test_repository_profile_uses_readme_and_manifest_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Billing API\n\n"
                "Billing API creates invoices and coordinates payment collection for customer orders.\n\n"
                "## Installation\n\nRun `pnpm install`.\n"
            )
            (root / "package.json").write_text(json.dumps({
                "name": "billing-api",
                "description": "A service for the billing domain.",
                "dependencies": {},
            }))
            (root / "src.ts").write_text("export const bill = true;\n")
            (root / "Dockerfile").write_text("FROM node:22-slim\n")

            result = scan_repository(request(root))

        profile_fact = next(
            fact for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "repository_profile"
        )
        profile = profile_fact["object_value"]
        self.assertEqual(
            profile["purpose"],
            "Billing API creates invoices and coordinates payment collection for customer orders.",
        )
        self.assertEqual(profile["purpose_source"], {"kind": "README", "path": "README.md"})
        self.assertEqual(profile["languages"], ["TypeScript"])
        self.assertEqual(profile["components"], ["Repository root"])
        self.assertIn("Container build", profile["operational_signals"])
        self.assertEqual(profile_fact["assertion_class"], "DECLARED")
        self.assertEqual(profile_fact["confidence"], 0.95)
        self.assertEqual(profile_fact["evidence"][0]["locator"]["path"], "README.md")
        self.assertEqual(profile_fact["evidence"][0]["locator"]["line_start"], 3)

    def test_repository_profile_does_not_invent_missing_purpose(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("print('hello')\n")

            result = scan_repository(request(root))

        profile_fact = next(
            fact for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "repository_profile"
        )
        self.assertNotIn("purpose", profile_fact["object_value"])
        self.assertEqual(profile_fact["object_value"]["languages"], ["Python"])
        self.assertEqual(profile_fact["assertion_class"], "INFERRED")

    def test_database_inference_correlates_psycopg_import_and_sanitized_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("psycopg[binary]==3.2.9\n")
            (root / "main.py").write_text(
                "import os\nimport psycopg\n"
                "psycopg.connect(os.environ['DATABASE_URL'])\n"
            )
            (root / ".env.example").write_text(
                "DATABASE_URL=postgresql://billing:do-not-emit@example.test/billing\n"
            )

            result = scan_repository(request(root))

        database = next(
            fact for fact in result["facts"]
            if fact["predicate"] == "USES"
            and fact.get("object_entity", {}).get("type") == "Database"
            and fact["object_entity"]["name"] == "PostgreSQL"
        )
        self.assertEqual(database["assertion_class"], "DECLARED")
        self.assertGreaterEqual(database["confidence"], 0.96)
        self.assertEqual(database["properties"]["engine"], "postgresql")
        self.assertEqual(database["properties"]["package_dependencies"], ["pypi:psycopg"])
        self.assertIn("DATABASE_URL", database["properties"]["config_keys"])
        self.assertTrue(database["properties"]["source_referenced"])
        self.assertIn("URL_SCHEME", database["properties"]["signal_kinds"])
        serialized = json.dumps(database)
        self.assertNotIn("do-not-emit", serialized)
        self.assertNotIn("billing@example.test", serialized)

    def test_compose_and_terraform_emit_normalized_database_and_storage_technologies(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.production.yaml").write_text(
                "services:\n"
                "  db:\n    image: postgres:16\n"
                "  object-store:\n    image: minio/minio:latest\n"
            )
            (root / "infra.tf").write_text(
                'resource "aws_s3_bucket" "documents" {\n  bucket = "documents"\n}\n'
            )

            result = scan_repository(request(root))

        resources = {
            (fact["object_entity"]["type"], fact["object_entity"]["name"]): fact
            for fact in result["facts"]
            if fact["predicate"] == "USES"
            and fact.get("object_entity", {}).get("type") in {"Database", "Storage"}
        }
        self.assertIn(("Database", "PostgreSQL"), resources)
        self.assertIn(("Storage", "S3-compatible object storage"), resources)
        self.assertIn(("Storage", "Amazon S3"), resources)
        self.assertEqual(
            resources[("Storage", "Amazon S3")]["properties"]["providers"], ["aws"],
        )
        self.assertIn(
            "TERRAFORM_RESOURCE",
            resources[("Storage", "Amazon S3")]["properties"]["signal_kinds"],
        )

    def test_generic_database_key_without_corroboration_does_not_invent_engine(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text(
                "DATABASE_URL=replace-me\nPOSTGRES_ERROR=connection-failed\n"
            )

            result = scan_repository(request(root))

        self.assertFalse(any(
            fact.get("object_entity", {}).get("type") == "Database"
            for fact in result["facts"]
        ))

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

    def test_deployment_and_terraform_files_emit_canonical_evidence_backed_facts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text("FROM python:3.13-slim\n")
            (root / "compose.yaml").write_text(
                "services:\n  api:\n    image: ghcr.io/acme/billing:1.2.3\n"
            )
            (root / "k8s").mkdir()
            (root / "k8s" / "deployment.yaml").write_text(
                "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n"
                "  name: billing\n  namespace: production\nspec:\n  template:\n"
                "    spec:\n      containers:\n        - name: api\n"
                "          image: ghcr.io/acme/billing:1.2.3\n"
            )
            (root / "infra.tf").write_text(
                'resource "aws_s3_bucket" "invoices" {\n  bucket = "invoices"\n}\n'
            )

            result = scan_repository(request(root))

        relationships = {
            (fact["predicate"], fact["object_entity"]["type"])
            for fact in result["facts"] if "object_entity" in fact
        }
        self.assertIn(("DEPLOYED_AS", "Deployment"), relationships)
        self.assertIn(("RUNS_ON", "ContainerImage"), relationships)
        self.assertIn(("LOCATED_IN", "Environment"), relationships)
        self.assertIn(("USES", "InfrastructureResource"), relationships)
        terraform = next(
            fact for fact in result["facts"]
            if fact.get("object_entity", {}).get("type") == "InfrastructureResource"
        )
        self.assertEqual(terraform["object_entity"]["name"], "aws_s3_bucket.invoices")
        self.assertEqual(terraform["evidence"][0]["locator"]["path"], "infra.tf")
        self.assertEqual(terraform["assertion_class"], "DECLARED")

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
            if fact.get("object_value", {}).get("finding_type") == "UNUSED_DECLARED_DEPENDENCY_CANDIDATE"
        ]
        self.assertEqual(len(unused), 1)
        self.assertEqual(partial["completeness"], "PARTIAL")
        self.assertFalse(any(
            fact.get("object_value", {}).get("finding_type")
            for fact in partial["facts"]
        ))

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
        self.assertFalse(any(
            fact.get("object_value", {}).get("finding_type")
            for fact in result["facts"]
        ))

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
        self.assertGreater(result["stats"]["pass_a_inventory_items"], 0)
        self.assertIn("pass_a_inventory", result["stats"]["phase_timings_ms"])
        self.assertIn("pass_b_refinement", result["stats"]["phase_timings_ms"])

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

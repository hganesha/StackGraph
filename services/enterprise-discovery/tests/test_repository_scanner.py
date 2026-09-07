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

    def test_repository_profile_records_hygiene_signals(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "README.md").write_text("Nested documentation only.\n")
            (root / ".github" / "CODEOWNERS").write_text("* @acme/platform\n")
            (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
            (root / "LICENSE.md").write_text("Internal use only.\n")
            (root / "package.json").write_text(json.dumps({
                "name": "billing-api",
                "dependencies": {"fastify": "5.5.0"},
            }))
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3,
                "packages": {},
            }))
            (root / "src.ts").write_text("export const bill = true;\n")
            (root / "src.test.ts").write_text("export const tested = true;\n")

            result = scan_repository(request(root))

        profile = next(
            fact["object_value"] for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "repository_profile"
        )
        hygiene = profile["hygiene"]
        self.assertFalse(hygiene["readme"]["present"])
        self.assertTrue(hygiene["license"]["present"])
        self.assertTrue(hygiene["codeowners"]["present"])
        self.assertTrue(hygiene["ci"]["present"])
        self.assertTrue(hygiene["dependency_lockfile"]["applicable"])
        self.assertTrue(hygiene["dependency_lockfile"]["present"])
        self.assertTrue(hygiene["tests"]["applicable"])
        self.assertTrue(hygiene["tests"]["present"])

    def test_repository_profile_marks_applicable_missing_lockfile_and_tests(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Billing API\n\nRuns billing workflows.\n")
            (root / "package.json").write_text(json.dumps({
                "name": "billing-api",
                "dependencies": {"fastify": "5.5.0"},
            }))
            (root / "src.ts").write_text("export const bill = true;\n")

            result = scan_repository(request(root))

        profile = next(
            fact["object_value"] for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "repository_profile"
        )
        hygiene = profile["hygiene"]
        self.assertTrue(hygiene["readme"]["present"])
        self.assertFalse(hygiene["license"]["present"])
        self.assertFalse(hygiene["codeowners"]["present"])
        self.assertFalse(hygiene["ci"]["present"])
        self.assertTrue(hygiene["dependency_lockfile"]["applicable"])
        self.assertFalse(hygiene["dependency_lockfile"]["present"])
        self.assertEqual(hygiene["dependency_lockfile"]["missing_component_paths"], ["."])
        self.assertTrue(hygiene["tests"]["applicable"])
        self.assertFalse(hygiene["tests"]["present"])

    def test_monorepo_manifests_become_evidence_backed_components(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({
                "name": "portfolio", "private": True, "workspaces": ["apps/*"],
            }))
            (root / "pnpm-workspace.yaml").write_text("packages:\n  - apps/*\n")
            (root / "apps" / "api").mkdir(parents=True)
            (root / "apps" / "api" / "package.json").write_text(json.dumps({
                "name": "api", "dependencies": {"fastify": "5.5.0"},
            }))
            (root / "apps" / "api" / "Dockerfile").write_text("FROM node:22-slim\n")
            (root / "apps" / "web").mkdir(parents=True)
            (root / "apps" / "web" / "package.json").write_text(json.dumps({
                "name": "web", "dependencies": {"react": "19.1.0"},
            }))

            result = scan_repository(request(root))

        contains = [
            fact for fact in result["facts"]
            if fact["predicate"] == "CONTAINS"
            and fact.get("subject", {}).get("type") == "Repository"
            and fact.get("object_entity", {}).get("type") == "Component"
        ]
        component_paths = {fact["properties"]["path"] for fact in contains}
        self.assertEqual(component_paths, {".", "apps/api", "apps/web"})
        api_component = next(fact for fact in contains if fact["properties"]["path"] == "apps/api")
        self.assertTrue(api_component["properties"]["independently_deployable"])
        self.assertEqual(api_component["properties"]["frameworks"], ["fastify"])
        self.assertEqual(api_component["evidence"][0]["locator"]["path"], "apps/api/package.json")
        profile = next(
            fact["object_value"] for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "repository_profile"
        )
        labels = {item["classification"] for item in profile["classifications"]}
        self.assertIn("MONOREPO", labels)
        self.assertIn("FULL_STACK_APPLICATION", labels)
        component_dependencies = [
            fact for fact in result["facts"]
            if fact["predicate"] == "DEPENDS_ON"
            and fact.get("subject", {}).get("type") == "Component"
        ]
        self.assertEqual(
            {fact["properties"]["component_path"] for fact in component_dependencies},
            {"apps/api", "apps/web"},
        )

    def test_container_digest_is_canonical_and_mutable_tag_is_limited(self) -> None:
        digest = "a" * 64
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile").write_text(
                f"FROM ghcr.io/acme/runtime@sha256:{digest}\nFROM node:22-slim\n"
            )

            result = scan_repository(request(root))

        based_on = [fact for fact in result["facts"] if fact["predicate"] == "BASED_ON"]
        immutable = next(fact for fact in based_on if fact["properties"]["image_digest"])
        mutable = next(fact for fact in based_on if fact["properties"]["image_digest"] is None)
        self.assertEqual(immutable["object_entity"]["key"], f"container-image:sha256:{digest}")
        self.assertEqual(immutable["properties"]["identity_state"], "DIGEST_RESOLVED")
        self.assertEqual(mutable["properties"]["identity_state"], "MUTABLE_TAG_UNRESOLVED")
        self.assertTrue(mutable["properties"]["limitations"])

    def test_custom_registry_manifest_emits_internal_package_publication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".npmrc").write_text(
                "@acme:registry=https://npm.acme.example/\n"
            )
            (root / "package.json").write_text(json.dumps({
                "name": "@acme/billing-client",
                "version": "2.4.0",
                "dependencies": {},
            }))

            result = scan_repository(request(root))

        publication = next(
            fact for fact in result["facts"] if fact["predicate"] == "PUBLISHES"
        )
        self.assertEqual(publication["assertion_class"], "DECLARED")
        self.assertEqual(publication["confidence"], 1)
        self.assertEqual(publication["subject"]["type"], "Repository")
        self.assertEqual(publication["object_entity"]["type"], "PackageVersion")
        self.assertTrue(publication["object_entity"]["key"].startswith("registry:npm-"))
        self.assertIn("pkg:npm/%40acme/billing-client@2.4.0", publication["object_entity"]["key"])
        self.assertEqual(publication["properties"]["package_name"], "@acme/billing-client")
        self.assertEqual(publication["properties"]["registry_source"], "NPMRC_SCOPE")
        self.assertEqual(len(publication["evidence"]), 2)

    def test_private_or_public_npm_manifest_is_not_an_internal_publication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({
                "name": "private-app", "version": "1.0.0", "private": True,
            }))
            private_result = scan_repository(request(root))
            (root / "package.json").write_text(json.dumps({
                "name": "public-library", "version": "1.0.0",
            }))
            public_result = scan_repository(request(root))

        self.assertFalse(any(
            fact["predicate"] == "PUBLISHES" for fact in private_result["facts"]
        ))
        self.assertFalse(any(
            fact["predicate"] == "PUBLISHES" for fact in public_result["facts"]
        ))

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
            (root / "k8s" / "service.yaml").write_text(
                "apiVersion: v1\nkind: Service\nmetadata:\n  name: billing-public\n"
                "  namespace: production\nspec:\n  type: LoadBalancer\n"
                "  selector:\n    app: billing\n  ports:\n    - port: 443\n"
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
        public_entrypoint = next(
            fact for fact in result["facts"]
            if fact.get("properties", {}).get("external_exposure") == "PUBLIC"
        )
        self.assertEqual(public_entrypoint["properties"]["source_kind"], "KUBERNETES")
        self.assertEqual(public_entrypoint["evidence"][0]["locator"]["path"], "k8s/service.yaml")

    def test_deployment_profile_detects_planned_provider_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vercel.json").write_text('{"framework":"nextjs"}\n')
            (root / "supabase").mkdir()
            (root / "supabase" / "config.toml").write_text('project_id = "billing"\n')
            (root / "serverless.yml").write_text("provider:\n  name: aws\n")
            (root / "app.yaml").write_text("runtime: python313\n")
            (root / "azure.yaml").write_text("name: billing\n")
            (root / "databricks.yml").write_text("bundle:\n  name: billing\n")
            (root / "fabric").mkdir()
            (root / "fabric" / "item.metadata.json").write_text('{"type":"DataPipeline"}\n')

            result = scan_repository(request(root))

        fact = next(
            item for item in result["facts"]
            if item.get("object_value", {}).get("record_kind") == "deployment_profile"
        )
        profile = fact["object_value"]
        self.assertEqual(
            profile["providers"],
            ["AWS", "AZURE", "DATABRICKS", "GCP", "MICROSOFT_FABRIC", "SUPABASE", "VERCEL"],
        )
        self.assertTrue({
            "WEB_APPLICATION", "MANAGED_BACKEND", "SERVERLESS_FUNCTION",
            "APP_ENGINE_SERVICE", "AZURE_DEVELOPER_PROJECT", "DATABRICKS_BUNDLE",
            "FABRIC_ITEM",
        }.issubset(profile["workload_types"]))
        self.assertEqual(profile["verification_level"], "DECLARED_CONFIGURATION")
        self.assertEqual(profile["coverage"]["live_state"], "NOT_VERIFIED")
        self.assertEqual(len(fact["evidence"]), 7)

    def test_local_compose_builds_emit_services_but_image_dependencies_do_not(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(
                "services:\n"
                "  api:\n    build: .\n"
                "  worker:\n    build:\n      context: ./worker\n      dockerfile: Dockerfile\n"
                "  postgres:\n    image: postgres:16\n"
            )

            result = scan_repository(request(root))

        services = {
            entity["name"]
            for fact in result["facts"]
            for entity in (fact.get("subject"), fact.get("object_entity"))
            if entity and entity.get("type") == "Service"
        }
        self.assertEqual(services, {"api", "worker"})
        for service_name in services:
            service_facts = [
                fact for fact in result["facts"]
                if fact.get("subject", {}).get("name") == service_name
                or fact.get("object_entity", {}).get("name") == service_name
            ]
            self.assertEqual(
                {fact["predicate"] for fact in service_facts},
                {"IMPLEMENTED_BY", "CONTAINS", "DEPLOYED_AS"},
            )
            self.assertTrue(all(
                fact["evidence"][0]["locator"]["path"] == "compose.yaml"
                for fact in service_facts
            ))

    def test_openapi_contract_emits_service_api_and_operation_profile(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "contracts").mkdir()
            (root / "contracts" / "openapi.json").write_text(json.dumps({
                "openapi": "3.1.0",
                "info": {
                    "title": "Invoice Service",
                    "version": "2026-08",
                    "description": "Creates and retrieves customer invoices.",
                },
                "servers": [{"url": "https://billing.example.test"}],
                "tags": [{"name": "invoices"}],
                "paths": {
                    "/invoices": {
                        "get": {
                            "operationId": "listInvoices",
                            "tags": ["invoices"],
                            "responses": {"200": {"description": "ok"}},
                        },
                        "post": {
                            "operationId": "createInvoice",
                            "tags": ["invoices"],
                            "responses": {"201": {"description": "created"}},
                        },
                    },
                    "/health": {
                        "get": {"responses": {"200": {"description": "ok"}}},
                    },
                },
                "components": {
                    "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
                },
            }))

            result = scan_repository(request(root))

        service = next(
            fact["subject"] for fact in result["facts"]
            if fact["predicate"] == "IMPLEMENTED_BY"
            and fact.get("subject", {}).get("type") == "Service"
        )
        self.assertEqual(service["name"], "Invoice Service")
        exposed = next(
            fact for fact in result["facts"]
            if fact["predicate"] == "EXPOSES"
        )
        self.assertEqual(exposed["subject"]["key"], service["key"])
        self.assertEqual(exposed["object_entity"]["type"], "API")
        self.assertEqual(exposed["object_entity"]["name"], "Invoice Service")
        self.assertEqual(exposed["evidence"][0]["type"], "API_CONTRACT")
        profile = next(
            fact["object_value"] for fact in result["facts"]
            if fact.get("object_value", {}).get("record_kind") == "openapi_service_profile"
        )
        self.assertEqual(profile["specification_version"], "3.1.0")
        self.assertEqual(profile["service_version"], "2026-08")
        self.assertEqual(profile["path_count"], 2)
        self.assertEqual(profile["operation_count"], 3)
        self.assertEqual(profile["operation_id_count"], 2)
        self.assertEqual(profile["methods"], ["GET", "POST"])
        self.assertEqual(profile["tags"], ["invoices"])
        self.assertEqual(profile["server_count"], 1)
        self.assertEqual(profile["security_scheme_count"], 1)
        self.assertEqual(result["stats"]["services_discovered"], 1)
        self.assertEqual(result["stats"]["api_contracts_discovered"], 1)
        self.assertEqual(result["stats"]["api_operations_discovered"], 3)

    def test_openapi_enriches_single_compose_service_without_inflating_count(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(
                "services:\n  api:\n    build: .\n"
            )
            (root / "openapi.yaml").write_text(
                "openapi: 3.0.3\n"
                "info:\n  title: Billing public API\n  version: 1.0.0\n"
                "paths:\n  /charges:\n    post:\n      responses:\n"
                "        '201':\n          description: created\n"
            )

            result = scan_repository(request(root))

        services = {
            entity["name"]
            for fact in result["facts"]
            for entity in (fact.get("subject"), fact.get("object_entity"))
            if entity and entity.get("type") == "Service"
        }
        self.assertEqual(services, {"api"})
        exposed = next(fact for fact in result["facts"] if fact["predicate"] == "EXPOSES")
        self.assertEqual(exposed["subject"]["name"], "api")
        self.assertEqual(exposed["object_entity"]["name"], "Billing public API")
        self.assertEqual(result["stats"]["services_discovered"], 1)
        self.assertEqual(result["stats"]["api_contracts_discovered"], 1)

    def test_openapi_title_matches_service_in_multi_service_repository(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(
                "services:\n"
                "  billing-api:\n    build: ./services/billing\n"
                "  notifications-worker:\n    build: ./services/notifications\n"
            )
            (root / "services" / "billing").mkdir(parents=True)
            (root / "services" / "billing" / "openapi.json").write_text(json.dumps({
                "openapi": "3.0.3",
                "info": {"title": "Billing public API", "version": "1.0.0"},
                "paths": {},
            }))

            result = scan_repository(request(root))

        services = {
            entity["name"]
            for fact in result["facts"]
            for entity in (fact.get("subject"), fact.get("object_entity"))
            if entity and entity.get("type") == "Service"
        }
        self.assertEqual(services, {"billing-api", "notifications-worker"})
        exposed = next(fact for fact in result["facts"] if fact["predicate"] == "EXPOSES")
        self.assertEqual(exposed["subject"]["name"], "billing-api")
        self.assertEqual(result["stats"]["services_discovered"], 2)

    def test_dockerfile_is_a_provisional_service_fallback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Dockerfile.api").write_text(
                "FROM python:3.13-slim AS build\nFROM python:3.13-slim\n"
            )

            result = scan_repository(request(root))

        service_fact = next(
            fact for fact in result["facts"]
            if fact["predicate"] == "IMPLEMENTED_BY"
            and fact.get("subject", {}).get("type") == "Service"
        )
        self.assertEqual(service_fact["subject"]["name"], "api")
        self.assertEqual(service_fact["properties"]["boundary_strategy"], "DOCKERFILE_FALLBACK")
        self.assertTrue(service_fact["properties"]["provisional"])
        self.assertEqual(service_fact["confidence"], 0.8)

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

    def test_vendored_code_carries_upstream_package_identity_when_metadata_exists(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package_root = root / "vendor" / "@acme" / "payments"
            package_root.mkdir(parents=True)
            (package_root / "package.json").write_text(json.dumps({
                "name": "@acme/payments", "version": "2.4.1",
            }))
            (package_root / "index.js").write_text(
                "export function authorizePayment() { return true; }\n"
            )

            result = scan_repository(request(root))

        summary = next(
            fact["object_value"] for fact in result["facts"]
            if fact.get("object_value", {}).get("qualified_name") == "authorizePayment"
        )
        self.assertTrue(summary["vendored"])
        self.assertEqual(summary["vendored_package_key"], "pkg:npm/%40acme/payments")
        self.assertEqual(summary["vendored_package_version"], "2.4.1")
        self.assertEqual(
            summary["vendored_identity_source"],
            "vendor/@acme/payments/package.json",
        )


class PolyglotDependencyTests(unittest.TestCase):
    """JVM, .NET, Rust, and Go manifests.

    Before these parsers a Java service scanned as a repository that depends on nothing, and
    nothing downstream could tell that apart from a repository that genuinely has none. What
    these tests hold is not the happy path but the three places the parsers must refuse to
    guess: an unresolvable Maven property, a Cargo path dependency, and a replaced Go module.
    """

    def dependencies(self, files: dict[str, str]) -> dict[str, dict]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            result = scan_repository(request(root))
        return {
            fact["object_entity"]["key"]: fact["properties"]
            for fact in result["facts"]
            if fact.get("predicate") == "DEPENDS_ON"
            and fact["subject"]["type"] == "Repository"
        }

    def test_a_maven_property_is_resolved_and_an_unresolvable_one_stays_unresolved(self) -> None:
        found = self.dependencies({"pom.xml": """<?xml version="1.0"?>
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <groupId>com.acme</groupId><artifactId>b</artifactId><version>1.0.0</version>
              <properties><spring.version>5.3.30</spring.version></properties>
              <dependencies>
                <dependency><groupId>org.springframework</groupId>
                  <artifactId>spring-core</artifactId><version>${spring.version}</version></dependency>
                <dependency><groupId>com.acme</groupId><artifactId>bom</artifactId>
                  <version>${defined.in.parent}</version></dependency>
              </dependencies>
            </project>"""})

        self.assertIn("pkg:maven/org.springframework/spring-core@5.3.30", found)
        # The unresolved one is still a declared dependency; it just has no version.
        self.assertIn("pkg:maven/com.acme/bom", found)
        self.assertIsNone(found["pkg:maven/com.acme/bom"].get("resolved_version"))

    def test_a_maven_coordinate_keeps_its_slash_so_the_purl_resolves(self) -> None:
        found = self.dependencies({"pom.xml": """<?xml version="1.0"?>
            <project><groupId>a</groupId><artifactId>b</artifactId><version>1</version>
            <dependencies><dependency><groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId><version>6.1.5</version></dependency>
            </dependencies></project>"""})

        # Percent-encoding the group/artifact separator would produce a purl no registry
        # can resolve, and the catalogue would report the package as unpublished.
        self.assertIn("pkg:maven/org.springframework/spring-core@6.1.5", found)

    def test_a_pom_with_a_document_type_declaration_is_refused(self) -> None:
        found = self.dependencies({"pom.xml": (
            '<?xml version="1.0"?><!DOCTYPE project [<!ENTITY x "y">]>'
            "<project><dependencies><dependency><groupId>a.b</groupId>"
            "<artifactId>c</artifactId><version>1</version></dependency></dependencies></project>"
        )})

        self.assertEqual({}, found)

    def test_gradle_reads_string_coordinates_and_ignores_other_colon_literals(self) -> None:
        found = self.dependencies({"build.gradle": """
            dependencies {
              implementation 'com.google.guava:guava:33.0.0-jre'
              testImplementation "org.mockito:mockito-core:5.11.0"
              implementation project(':shared:core')
            }
        """})

        self.assertIn("pkg:maven/com.google.guava/guava@33.0.0-jre", found)
        self.assertIn("pkg:maven/org.mockito/mockito-core@5.11.0", found)
        # `:shared:core` is a Gradle project path, not a Maven coordinate. Its first segment
        # carries no dot, which is what separates the two.
        self.assertFalse([key for key in found if "shared" in key])

    def test_a_gradle_version_catalog_alias_resolves_to_its_module_and_version(self) -> None:
        found = self.dependencies({
            "gradle/libs.versions.toml": (
                '[versions]\nguava = "33.0.0-jre"\n'
                '[libraries]\nguava = { module = "com.google.guava:guava", version.ref = "guava" }\n'
            ),
            "build.gradle": "dependencies {\n  implementation libs.guava\n}\n",
        })

        self.assertIn("pkg:maven/com.google.guava/guava@33.0.0-jre", found)

    def test_nuget_reads_both_the_attribute_and_the_child_element_form(self) -> None:
        found = self.dependencies({"Billing.csproj": """<Project Sdk="Microsoft.NET.Sdk">
            <ItemGroup>
              <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
              <PackageReference Include="Serilog"><Version>3.1.1</Version></PackageReference>
            </ItemGroup></Project>"""})

        self.assertIn("pkg:nuget/newtonsoft.json@13.0.3", found)
        self.assertIn("pkg:nuget/serilog@3.1.1", found)

    def test_a_nuget_lockfile_resolves_a_floating_version(self) -> None:
        found = self.dependencies({
            "Billing.csproj": (
                '<Project><ItemGroup><PackageReference Include="Serilog" Version="3.*" />'
                "</ItemGroup></Project>"
            ),
            "packages.lock.json": json.dumps({
                "version": 1,
                "dependencies": {"net8.0": {"Serilog": {"resolved": "3.1.1"}}},
            }),
        })

        self.assertIn("pkg:nuget/serilog@3.1.1", found)

    def test_a_cargo_path_dependency_never_becomes_a_registry_package(self) -> None:
        found = self.dependencies({
            "Cargo.toml": (
                '[package]\nname = "b"\nversion = "0.1.0"\n\n[dependencies]\n'
                'serde = "1.0.197"\n'
                'tokio = { version = "^1.36", features = ["full"] }\n'
                'helpers = { path = "../helpers" }\n'
                'patched = { git = "https://example.test/patched" }\n'
            ),
            "Cargo.lock": (
                'version = 3\n\n[[package]]\nname = "serde"\nversion = "1.0.197"\n\n'
                '[[package]]\nname = "tokio"\nversion = "1.36.0"\n'
            ),
        })

        self.assertIn("pkg:cargo/serde@1.0.197", found)
        # The lockfile, not the caret range, states what is built.
        self.assertIn("pkg:cargo/tokio@1.36.0", found)
        # Neither of these is a crates.io package; offering upgrade targets for them would
        # invent releases the registry has never published.
        self.assertFalse([key for key in found if "helpers" in key or "patched" in key])

    def test_a_replaced_go_module_keeps_no_resolved_version(self) -> None:
        found = self.dependencies({"go.mod": """module github.com/acme/billing

go 1.22

require (
\tgithub.com/gin-gonic/gin v1.9.1
\tgithub.com/Azure/azure-sdk-for-go v68.0.0+incompatible // indirect
)

require github.com/acme/shared v0.4.0

replace github.com/acme/shared => ../shared
"""})

        self.assertIn("pkg:golang/github.com/gin-gonic/gin@v1.9.1", found)
        self.assertFalse(found["pkg:golang/github.com/Azure/azure-sdk-for-go@v68.0.0+incompatible"]["direct"])
        # `replace` redirects the build, so the declared version is not what runs.
        self.assertIn("pkg:golang/github.com/acme/shared", found)
        self.assertIsNone(found["pkg:golang/github.com/acme/shared"].get("resolved_version"))

    def test_a_go_module_path_keeps_its_case(self) -> None:
        found = self.dependencies({"go.mod": (
            "module github.com/acme/b\n\ngo 1.22\n\n"
            "require github.com/Azure/azure-sdk-for-go v68.0.0+incompatible\n"
        )})

        # Lower-casing a Go module path names a module the proxy has never heard of.
        self.assertIn(
            "pkg:golang/github.com/Azure/azure-sdk-for-go@v68.0.0+incompatible", found,
        )


if __name__ == "__main__":
    unittest.main()

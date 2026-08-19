from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from stackgraph_discovery.npm_resolution import (
    PUBLIC_NPM_ORIGIN,
    normalize_registry_origin,
    parse_npmrc,
    resolve_npm_dependency,
)


class NpmConfigTests(unittest.TestCase):
    def test_parses_default_and_scoped_registries_without_secret_values(self) -> None:
        config = parse_npmrc(
            """
            registry=https://registry.npmjs.org/
            @acme:registry=https://npm.acme.example/repository/npm/
            //npm.acme.example/:_authToken=${NPM_TOKEN}
            //npm.acme.example/:username=build-user
            """
        )

        self.assertEqual(config.default_registry, PUBLIC_NPM_ORIGIN)
        self.assertEqual(
            config.scoped_registries["@acme"],
            "https://npm.acme.example/repository/npm/",
        )
        self.assertEqual(len(config.credential_keys), 2)
        serialized = json.dumps(asdict(config))
        self.assertNotIn("NPM_TOKEN", serialized)
        self.assertNotIn("build-user", serialized)

    def test_rejects_credentialed_and_insecure_origins(self) -> None:
        for value in (
            "https://token@registry.npmjs.org/",
            "http://registry.npmjs.org/",
            "https://registry.npmjs.org/?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_registry_origin(value)

        self.assertEqual(
            normalize_registry_origin(
                "http://localhost:4873", allow_insecure_localhost=True
            ),
            "http://localhost:4873/",
        )


class NpmResolutionTests(unittest.TestCase):
    def test_public_default_resolution_keeps_public_purl_identity(self) -> None:
        result = resolve_npm_dependency(
            "Axios",
            requested_spec="^1.7.0",
            resolved_version="1.7.9",
            resolved_uri="https://registry.npmjs.org/axios/-/axios-1.7.9.tgz",
            integrity="sha512-example",
        )

        self.assertEqual(result.registry_origin, PUBLIC_NPM_ORIGIN)
        self.assertEqual(result.resolution_source, "LOCKFILE")
        self.assertEqual(result.lockfile_behavior, "CONFIGURED_DEFAULT")
        self.assertEqual(result.visibility, "PUBLIC")
        self.assertEqual(result.canonical_key, "pkg:npm/axios@1.7.9")
        self.assertEqual(
            result.fact_properties(dependency_scope="runtime", direct=True)[
                "registry_resolution"
            ]["origin"],
            PUBLIC_NPM_ORIGIN,
        )

    def test_scoped_custom_registry_is_tenant_qualified(self) -> None:
        config = parse_npmrc(
            "@acme:registry=https://npm.acme.example/repository/npm/"
        )
        result = resolve_npm_dependency(
            "@Acme/Billing-SDK",
            requested_spec="2.4.1",
            resolved_version="2.4.1",
            npm_config=config,
            config_path="services/billing/.npmrc",
            resolved_uri=(
                "https://npm.acme.example/repository/npm/"
                "@acme/billing-sdk/-/billing-sdk-2.4.1.tgz"
            ),
            known_visibility={
                "https://npm.acme.example/repository/npm/": "PRIVATE"
            },
        )

        self.assertEqual(result.package_scope, "@acme")
        self.assertEqual(result.resolution_source, "LOCKFILE")
        self.assertEqual(result.lockfile_behavior, "CUSTOM_PINNED")
        self.assertEqual(result.visibility, "PRIVATE")
        self.assertTrue(result.canonical_key.startswith("registry:npm-"))
        self.assertTrue(result.canonical_key.endswith(":pkg:npm/%40acme/billing-sdk@2.4.1"))

    def test_public_default_lockfile_follows_current_registry_config(self) -> None:
        config = parse_npmrc(
            "registry=https://npm.acme.example/repository/npm/"
        )
        result = resolve_npm_dependency(
            "demo",
            requested_spec="^1.0.0",
            resolved_version="1.2.0",
            npm_config=config,
            config_path=".npmrc",
            resolved_uri="https://registry.npmjs.org/demo/-/demo-1.2.0.tgz",
        )

        self.assertEqual(
            result.registry_origin,
            "https://npm.acme.example/repository/npm/",
        )
        self.assertEqual(result.resolution_source, "NPMRC_DEFAULT")
        self.assertEqual(result.lockfile_behavior, "CONFIGURED_DEFAULT")

    def test_custom_registry_lockfile_remains_pinned(self) -> None:
        result = resolve_npm_dependency(
            "demo",
            requested_spec="^1.0.0",
            resolved_version="1.2.0",
            resolved_uri=(
                "https://npm.acme.example/repository/npm/"
                "demo/-/demo-1.2.0.tgz"
            ),
        )

        self.assertEqual(
            result.registry_origin,
            "https://npm.acme.example/",
        )
        self.assertEqual(result.resolution_source, "LOCKFILE")
        self.assertEqual(result.lockfile_behavior, "CUSTOM_PINNED")

    def test_explicit_tarball_does_not_masquerade_as_configured_registry(self) -> None:
        result = resolve_npm_dependency(
            "demo",
            requested_spec="https://downloads.example/demo-1.0.0.tgz",
            resolved_version="1.0.0",
            resolved_uri="https://downloads.example/demo-1.0.0.tgz",
        )
        self.assertEqual(result.resolution_source, "EXPLICIT_TARBALL")
        self.assertEqual(result.registry_origin, "https://downloads.example/")
        self.assertEqual(result.visibility, "UNKNOWN")

    def test_rejects_credentials_in_resolved_artifact(self) -> None:
        with self.assertRaises(ValueError):
            resolve_npm_dependency(
                "demo",
                requested_spec="1.0.0",
                resolved_version="1.0.0",
                resolved_uri="https://token@registry.npmjs.org/demo.tgz",
            )


if __name__ == "__main__":
    unittest.main()

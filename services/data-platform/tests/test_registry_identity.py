"""Registry identity for every ecosystem, not only npm.

`package_registry_identity` is what the catalogue enumerator reads to decide which packages to
enumerate. While only npm wrote a row there, the PyPI enumerator could never see a package and
every non-npm dependency reported no upgrade targets — which reads as "this package has no newer
release" rather than "nothing ever asked the registry".
"""

from __future__ import annotations

import unittest
from uuid import UUID, uuid4

from stackgraph_data.scanner_ingest import PUBLIC_REGISTRIES, _persist_registry_identity


TENANT = UUID("00000000-0000-4000-8000-0000000f0001")
ENTITY = UUID("00000000-0000-4000-8000-0000000f0002")


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self):
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, query, params=None):
        self.statements.append((query, tuple(params or ())))
        return Cursor({"id": uuid4()})

    def written(self, fragment: str) -> list[tuple]:
        return [params for query, params in self.statements if fragment in query]


def dependency_fact(ecosystem: str, key: str, version: str | None, **properties):
    return {
        "object_entity": {"key": key},
        "properties": {"ecosystem": ecosystem, "resolved_version": version, **properties},
        "observed_at": "2026-09-06T09:00:00Z",
    }


class RegistryIdentityTests(unittest.TestCase):
    def test_every_supported_ecosystem_records_an_identity(self) -> None:
        for ecosystem, key in (
            ("npm", "pkg:npm/left-pad@1.3.0"),
            ("pypi", "pkg:pypi/requests@2.32.3"),
            ("maven", "pkg:maven/org.springframework/spring-core@6.1.5"),
            ("cargo", "pkg:cargo/serde@1.0.197"),
            ("nuget", "pkg:nuget/newtonsoft.json@13.0.3"),
            ("golang", "pkg:golang/github.com/gin-gonic/gin@v1.9.1"),
        ):
            connection = Connection()
            result = _persist_registry_identity(
                connection, TENANT, ENTITY, dependency_fact(ecosystem, key, "1"),
            )
            self.assertIsNotNone(result, ecosystem)
            identities = connection.written("INSERT INTO package_registry_identity")
            self.assertEqual(1, len(identities), ecosystem)

    def test_a_maven_identity_keeps_the_group_and_artifact_together(self) -> None:
        connection = Connection()
        _persist_registry_identity(
            connection, TENANT, ENTITY,
            dependency_fact("maven", "pkg:maven/org.springframework/spring-core@6.1.5", "6.1.5"),
        )
        params = connection.written("INSERT INTO package_registry_identity")[0]

        self.assertIn("org.springframework/spring-core", params)
        self.assertIn("pkg:maven/org.springframework/spring-core@6.1.5", params)

    def test_a_go_module_identity_keeps_its_case(self) -> None:
        connection = Connection()
        _persist_registry_identity(
            connection, TENANT, ENTITY,
            dependency_fact(
                "golang", "pkg:golang/github.com/Azure/azure-sdk-for-go@v68.0.0", "v68.0.0",
            ),
        )
        params = connection.written("INSERT INTO package_registry_identity")[0]

        self.assertIn("github.com/Azure/azure-sdk-for-go", params)

    def test_a_public_default_registry_is_global_rather_than_tenant_scoped(self) -> None:
        connection = Connection()
        _persist_registry_identity(
            connection, TENANT, ENTITY,
            dependency_fact("cargo", "pkg:cargo/serde@1.0.197", "1.0.197"),
        )
        registries = connection.written("INSERT INTO package_registry")[0]

        # crates.io's catalogue is public knowledge; scoping it to one tenant would re-fetch it
        # per tenant and fragment the catalogue.
        self.assertIsNone(registries[0])
        self.assertIn("cargo-public", registries)
        self.assertIn("CARGO", registries)

    def test_a_private_npm_registry_stays_tenant_scoped(self) -> None:
        connection = Connection()
        _persist_registry_identity(
            connection, TENANT, ENTITY,
            dependency_fact(
                "npm", "pkg:npm/@acme/internal@1.0.0", "1.0.0",
                registry_resolution={
                    "origin": "https://npm.acme.internal/", "visibility": "PRIVATE",
                    "custom_registry": True,
                },
            ),
        )
        registries = connection.written("INSERT INTO package_registry")[0]

        self.assertEqual(TENANT, registries[0])
        self.assertIn("OTHER", registries)

    def test_an_ecosystem_with_no_adapter_records_nothing_rather_than_guessing(self) -> None:
        connection = Connection()
        result = _persist_registry_identity(
            connection, TENANT, ENTITY, dependency_fact("conan", "pkg:conan/openssl@3.0.0", "3"),
        )

        self.assertIsNone(result)
        self.assertEqual([], connection.statements)

    def test_the_public_registry_table_names_a_real_ecosystem_code_for_each(self) -> None:
        # These strings go straight into a CHECK constraint. A typo would fail at ingest time
        # against a live database and nowhere earlier.
        allowed = {"NPM", "PYPI", "MAVEN", "CARGO", "NUGET", "GO", "OTHER"}
        for ecosystem, (_, code, origin) in PUBLIC_REGISTRIES.items():
            self.assertIn(code, allowed, ecosystem)
            self.assertTrue(origin.startswith("https://"), ecosystem)
            self.assertTrue(origin.endswith("/"), ecosystem)


if __name__ == "__main__":
    unittest.main()

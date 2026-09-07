"""Tests for enumerating what a registry offers.

The catalogue is what makes §6's "candidate upgrade" reachable: without it a target list can
only contain versions some repository already runs, so an estate nobody has upgraded yet has
nothing to upgrade to. These tests hold the distinctions that make the catalogue safe to offer —
prerelease from release, yanked from deprecated, bounded from complete.
"""

from __future__ import annotations

import json
import unittest
from uuid import UUID

from stackgraph_data.registry_catalog import (
    MAX_VERSIONS_PER_PACKAGE,
    CatalogResult,
    enumerate_package,
    is_prerelease,
    cargo_catalog,
    go_catalog,
    go_module_path,
    maven_catalog,
    npm_catalog,
    nuget_catalog,
    persist_catalog,
    pypi_catalog,
)


TENANT_ID = UUID("00000000-0000-4000-8000-00000010a001")

PACKUMENT = {
    "name": "left-pad",
    "versions": {
        "1.2.0": {"name": "left-pad", "version": "1.2.0"},
        "1.3.0": {"name": "left-pad", "version": "1.3.0"},
        "2.0.0-rc1": {"name": "left-pad", "version": "2.0.0-rc1"},
        "0.9.0": {"name": "left-pad", "version": "0.9.0", "deprecated": "use 1.x"},
    },
    "time": {"1.3.0": "2026-01-05T00:00:00.000Z"},
}

PROJECT = {
    "info": {"name": "attrs"},
    "releases": {
        "23.1.0": [{"upload_time_iso_8601": "2026-01-05T00:00:00Z", "yanked": False}],
        "23.2.0": [{"upload_time_iso_8601": "2026-02-05T00:00:00Z", "yanked": True}],
        "24.0.0b1": [{"upload_time_iso_8601": "2026-03-05T00:00:00Z", "yanked": False}],
        "0.0.1": [],
    },
}


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {}
        self.final_url = "https://registry.npmjs.org/left-pad"


class Transport:
    def __init__(self, response):
        self.response = response
        self.requests: list[tuple] = []

    def request(self, url, headers, timeout_seconds):
        self.requests.append((url, headers, timeout_seconds))
        return self.response


class RecordingConnection:
    def __init__(self):
        self.versions: list[tuple] = []
        self.collections: list[tuple] = []

    def execute(self, query, params=()):
        if "INSERT INTO package_version_catalog" in query:
            self.versions.append(params)
        elif "INSERT INTO package_catalog_collection" in query:
            self.collections.append(params)
        else:
            raise AssertionError(f"unexpected query: {query.strip()[:80]}")
        return self


class PrereleaseTests(unittest.TestCase):
    def test_recognised_prerelease_markers(self) -> None:
        for version in ("2.0.0-rc1", "1.0.0-beta.2", "3.1.0-alpha", "4.0.0-next.1", "1.0.0b1"):
            with self.subTest(version=version):
                self.assertTrue(is_prerelease(version))

    def test_a_plain_release_is_not_a_prerelease(self) -> None:
        for version in ("1.2.0", "20.11.1", "4.0.0", "1.0.0+build.5"):
            with self.subTest(version=version):
                self.assertFalse(is_prerelease(version))


class NpmCatalogTests(unittest.TestCase):
    def result(self):
        return npm_catalog(PACKUMENT, registry_key="npm-public", source_uri="https://x/left-pad")

    def test_every_offered_version_is_catalogued(self) -> None:
        versions = {item.version for item in self.result().versions}
        self.assertEqual({"1.2.0", "1.3.0", "2.0.0-rc1", "0.9.0"}, versions)

    def test_a_deprecated_release_keeps_its_reason(self) -> None:
        by_version = {item.version: item for item in self.result().versions}
        self.assertTrue(by_version["0.9.0"].is_deprecated)
        self.assertEqual("use 1.x", by_version["0.9.0"].deprecation_reason)
        # Deprecated is not yanked: it still installs.
        self.assertFalse(by_version["0.9.0"].is_yanked)

    def test_publish_dates_are_carried_when_the_registry_states_them(self) -> None:
        by_version = {item.version: item for item in self.result().versions}
        self.assertEqual("2026-01-05T00:00:00.000Z", by_version["1.3.0"].published_at)
        self.assertIsNone(by_version["1.2.0"].published_at)

    def test_a_document_without_a_version_map_is_an_error_not_an_empty_catalogue(self) -> None:
        result = npm_catalog({"name": "x"}, registry_key="npm-public", source_uri="u")
        # An empty catalogue would read as "this package has no versions", which is false.
        self.assertEqual("ERROR", result.status)
        self.assertEqual((), result.versions)


class PyPICatalogTests(unittest.TestCase):
    def result(self):
        return pypi_catalog(PROJECT, registry_key="pypi-public", source_uri="https://x/attrs")

    def test_a_release_whose_artifacts_are_all_yanked_is_recorded_as_yanked(self) -> None:
        by_version = {item.version: item for item in self.result().versions}
        self.assertTrue(by_version["23.2.0"].is_yanked)
        self.assertFalse(by_version["23.1.0"].is_yanked)

    def test_a_release_with_no_artifacts_is_not_offered(self) -> None:
        # PyPI keeps the key after every file is removed; the release is not installable.
        self.assertNotIn("0.0.1", {item.version for item in self.result().versions})

    def test_prereleases_are_catalogued_and_flagged(self) -> None:
        by_version = {item.version: item for item in self.result().versions}
        self.assertTrue(by_version["24.0.0b1"].is_prerelease)
        self.assertFalse(by_version["23.1.0"].is_prerelease)


class BoundingTests(unittest.TestCase):
    def test_a_large_catalogue_is_truncated_to_the_newest_and_says_so(self) -> None:
        document = {
            "name": "big",
            "versions": {f"1.0.{index}": {} for index in range(MAX_VERSIONS_PER_PACKAGE + 25)},
            "time": {},
        }
        result = npm_catalog(document, registry_key="npm-public", source_uri="u")
        self.assertEqual("PARTIAL", result.status)
        self.assertEqual(MAX_VERSIONS_PER_PACKAGE, len(result.versions))
        # A truncated list that claimed to be complete would hide newer releases behind older.
        self.assertIn("1.0.224", {item.version for item in result.versions})
        self.assertNotIn("1.0.0", {item.version for item in result.versions})
        self.assertTrue(any("225" in item for item in result.limitations))


class EnumerationTests(unittest.TestCase):
    def test_npm_enumeration_requests_the_packument(self) -> None:
        transport = Transport(Response(200, PACKUMENT))
        result = enumerate_package(
            "left-pad", "npm", registry_key="npm-public", transport=transport,
        )
        self.assertEqual("AVAILABLE", result.status)
        self.assertTrue(transport.requests[0][0].endswith("/left-pad"))

    def test_pypi_enumeration_requests_the_project_endpoint_not_a_version(self) -> None:
        transport = Transport(Response(200, PROJECT))
        enumerate_package("attrs", "pypi", registry_key="pypi-public", transport=transport)
        # The per-version endpoint does not carry the release map, so asking for one would
        # silently produce a catalogue of exactly one version.
        self.assertTrue(transport.requests[0][0].endswith("/pypi/attrs/json"))

    def test_a_missing_package_is_not_found_rather_than_an_error(self) -> None:
        result = enumerate_package(
            "ghost", "npm", registry_key="npm-public", transport=Transport(Response(404, b"{}")),
        )
        self.assertEqual("NOT_FOUND", result.status)
        self.assertIn("does not publish", result.limitations[0])

    def test_a_failing_registry_records_the_status_and_no_versions(self) -> None:
        result = enumerate_package(
            "left-pad", "npm", registry_key="npm-public",
            transport=Transport(Response(503, b"{}")),
        )
        self.assertEqual("ERROR", result.status)
        self.assertEqual((), result.versions)
        self.assertIn("503", result.limitations[0])

    def test_a_non_json_response_never_becomes_a_catalogue(self) -> None:
        result = enumerate_package(
            "left-pad", "npm", registry_key="npm-public",
            transport=Transport(Response(200, b"<html>proxy error</html>")),
        )
        self.assertEqual("ERROR", result.status)

    def test_an_unsupported_ecosystem_is_refused_without_a_request(self) -> None:
        transport = Transport(Response(200, b"{}"))
        result = enumerate_package(
            "openssl", "conan", registry_key="conan-public", transport=transport,
        )
        self.assertEqual("ERROR", result.status)
        self.assertEqual([], transport.requests)

    def test_each_ecosystem_is_asked_the_endpoint_its_own_tooling_uses(self) -> None:
        for name, ecosystem, expected in (
            ("serde", "cargo", "https://crates.io/api/v1/crates/serde"),
            ("Newtonsoft.Json", "nuget",
             "https://api.nuget.org/v3-flatcontainer/newtonsoft.json/index.json"),
            ("org.springframework/spring-core", "maven",
             "https://repo1.maven.org/maven2/org/springframework/spring-core/maven-metadata.xml"),
            ("github.com/gin-gonic/gin", "go",
             "https://proxy.golang.org/github.com/gin-gonic/gin/@v/list"),
        ):
            transport = Transport(Response(200, b"{}"))
            enumerate_package(name, ecosystem, registry_key="k", transport=transport)
            self.assertEqual(expected, transport.requests[0][0], ecosystem)

    def test_a_maven_name_without_an_artifact_is_refused_before_a_request(self) -> None:
        transport = Transport(Response(200, b"<metadata/>"))
        result = enumerate_package(
            "org.springframework", "maven", registry_key="maven-central", transport=transport,
        )
        self.assertEqual("ERROR", result.status)
        self.assertEqual([], transport.requests)


class OtherEcosystemCatalogTests(unittest.TestCase):
    def test_crates_io_yanks_are_recorded_rather_than_dropped(self) -> None:
        result = cargo_catalog(
            {
                "crate": {"name": "serde"},
                "versions": [
                    {"num": "1.0.197", "yanked": False, "created_at": "2024-02-16T00:00:00Z"},
                    {"num": "1.0.196", "yanked": True, "created_at": "2024-02-01T00:00:00Z"},
                    {"num": "2.0.0-rc1", "yanked": False},
                ],
            },
            registry_key="cargo-public", source_uri="u",
        )
        versions = {item.version: item for item in result.versions}
        self.assertEqual("AVAILABLE", result.status)
        self.assertTrue(versions["1.0.196"].is_yanked)
        self.assertFalse(versions["1.0.197"].is_yanked)
        self.assertTrue(versions["2.0.0-rc1"].is_prerelease)

    def test_nuget_states_what_the_flat_container_cannot_tell_it(self) -> None:
        result = nuget_catalog(
            {"versions": ["13.0.1", "13.0.3", "14.0.0-beta1"]},
            package_name="Newtonsoft.Json", registry_key="nuget-public", source_uri="u",
        )
        self.assertEqual("AVAILABLE", result.status)
        self.assertEqual(3, len(result.versions))
        self.assertTrue(any("deprecation" in item for item in result.limitations))
        self.assertTrue(any("no release dates" in item for item in result.limitations))
        # A missing signal must never arrive as a value: nothing here may claim a release date.
        self.assertTrue(all(item.published_at is None for item in result.versions))

    def test_maven_metadata_yields_versions_and_names_its_blind_spots(self) -> None:
        body = b"""<?xml version="1.0"?>
        <metadata><groupId>org.springframework</groupId><artifactId>spring-core</artifactId>
        <versioning><latest>6.1.5</latest>
        <versions><version>5.3.30</version><version>6.1.5</version>
        <version>6.2.0-M1</version></versions>
        <lastUpdated>20240301120000</lastUpdated></versioning></metadata>"""
        result = maven_catalog(
            body, package_name="org.springframework/spring-core",
            registry_key="maven-central", source_uri="u",
        )
        self.assertEqual("AVAILABLE", result.status)
        self.assertEqual({"5.3.30", "6.1.5", "6.2.0-M1"}, {item.version for item in result.versions})
        self.assertTrue(any("yank or deprecation" in item for item in result.limitations))

    def test_maven_metadata_with_a_doctype_is_refused(self) -> None:
        result = maven_catalog(
            b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY x "y">]><metadata/>',
            package_name="a/b", registry_key="maven-central", source_uri="u",
        )
        self.assertEqual("ERROR", result.status)

    def test_the_go_proxy_list_is_read_as_text_and_names_what_it_hides(self) -> None:
        result = go_catalog(
            b"v1.9.0\nv1.9.1\nv2.0.0-beta.1\n", package_name="github.com/gin-gonic/gin",
            registry_key="go-proxy", source_uri="u",
        )
        self.assertEqual("AVAILABLE", result.status)
        self.assertEqual(3, len(result.versions))
        self.assertTrue(any("retractions" in item for item in result.limitations))

    def test_a_go_module_with_no_tagged_release_is_partial_not_absent(self) -> None:
        result = go_catalog(
            b"", package_name="github.com/acme/internal", registry_key="go-proxy", source_uri="u",
        )
        self.assertEqual("PARTIAL", result.status)
        self.assertEqual((), result.versions)
        self.assertTrue(any("pseudo-version" in item for item in result.limitations))

    def test_go_module_paths_are_case_escaped_the_way_the_proxy_expects(self) -> None:
        self.assertEqual(
            "github.com/!azure/azure-sdk-for-go",
            go_module_path("github.com/Azure/azure-sdk-for-go"),
        )
        self.assertEqual("github.com/gin-gonic/gin", go_module_path("github.com/gin-gonic/gin"))


class PersistenceTests(unittest.TestCase):
    def test_every_version_and_one_collection_record_are_written(self) -> None:
        connection = RecordingConnection()
        stored = persist_catalog(
            connection,
            npm_catalog(PACKUMENT, registry_key="npm-public", source_uri="u"),
        )
        self.assertEqual(4, stored)
        self.assertEqual(4, len(connection.versions))
        self.assertEqual(1, len(connection.collections))

    def test_an_error_result_still_records_that_collection_was_attempted(self) -> None:
        connection = RecordingConnection()
        persist_catalog(connection, CatalogResult(
            ecosystem="npm", registry_key="npm-public", package_name="left-pad",
            status="ERROR", versions=(), limitations=("the registry answered with status 503",),
        ))
        # Without this row a package the enumerator failed on is indistinguishable from one it
        # never tried, and §9.1 forbids reading the first as the second.
        self.assertEqual([], connection.versions)
        self.assertEqual("ERROR", connection.collections[0][4])

    def test_the_public_catalogue_is_written_without_a_tenant(self) -> None:
        connection = RecordingConnection()
        persist_catalog(
            connection, npm_catalog(PACKUMENT, registry_key="npm-public", source_uri="u"),
        )
        # A public registry's catalogue is the same for everyone; scoping it per tenant would
        # re-fetch the same document once per customer.
        self.assertIsNone(connection.versions[0][0])


if __name__ == "__main__":
    unittest.main()

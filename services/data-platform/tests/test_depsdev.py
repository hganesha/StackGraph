from __future__ import annotations

import json
import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from stackgraph_data.catalog import sha256_key
from stackgraph_data.depsdev import (
    DepsDevApiError,
    DepsDevBundle,
    DepsDevClient,
    HttpResponse,
    PackageVersionKey,
    build_fact_specs,
    normalize_bundle,
)


FIXTURE_DIR = Path(
    os.environ.get("STACKGRAPH_TEST_FIXTURE_DIR", "/code/tests/fixtures")
) / "depsdev"


@dataclass(frozen=True)
class RecordedRequest:
    url: str
    headers: Mapping[str, str]


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[RecordedRequest] = []

    def request(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.requests.append(RecordedRequest(url, dict(headers)))
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses.pop(0)


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def response(document: object) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(document).encode("utf-8"))


def fixture_bundle() -> DepsDevBundle:
    target = PackageVersionKey.from_purl("pkg:npm/demo-root@1.0.0")
    return DepsDevBundle(
        requested=target,
        version=fixture("version.json"),
        dependencies=fixture("dependencies.json"),
        version_uri="https://api.deps.dev/version",
        dependencies_uri="https://api.deps.dev/dependencies",
    )


class PackageVersionKeyTests(unittest.TestCase):
    def test_canonicalizes_npm_and_pypi_purls(self) -> None:
        self.assertEqual(
            PackageVersionKey.from_purl(
                "pkg:npm/%40Babel/Core@7.25.0"
            ).purl,
            "pkg:npm/%40babel/core@7.25.0",
        )
        self.assertEqual(
            PackageVersionKey.from_purl("pkg:pypi/Django_REST.Framework@3.15.2").purl,
            "pkg:pypi/django-rest-framework@3.15.2",
        )

    def test_rejects_unversioned_or_unsupported_purls(self) -> None:
        for value in (
            "pkg:npm/react",
            "pkg:maven/org.example/demo@1.0.0",
            "pkg:npm/react@1.0.0?repository=private",
            "not-a-purl",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PackageVersionKey.from_purl(value)


class DepsDevClientTests(unittest.TestCase):
    def test_fetches_version_and_dependency_endpoints_with_encoded_name(self) -> None:
        transport = FakeTransport(
            [response(fixture("version.json")), response(fixture("dependencies.json"))]
        )
        client = DepsDevClient(transport=transport)
        client.fetch(PackageVersionKey.from_purl("pkg:npm/%40scope/demo@1.2.3"))

        self.assertEqual(len(transport.requests), 2)
        self.assertIn("/systems/npm/packages/%40scope%2Fdemo/", transport.requests[0].url)
        self.assertTrue(transport.requests[1].url.endswith(":dependencies"))
        self.assertNotIn("Authorization", transport.requests[0].headers)

    def test_classifies_provider_failures_for_scheduler_retry(self) -> None:
        transport = FakeTransport(
            [HttpResponse(429, {"Retry-After": "17"}, b'{"message":"slow down"}')]
        )
        with self.assertRaises(DepsDevApiError) as context:
            DepsDevClient(transport=transport).fetch(
                PackageVersionKey.from_purl("pkg:npm/react@18.2.0")
            )
        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.retry_after_seconds, 17)

    def test_rejects_credentialed_or_insecure_base_urls(self) -> None:
        for value in ("http://api.deps.dev", "https://token@api.deps.dev"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DepsDevClient(base_url=value)


class NormalizationTests(unittest.TestCase):
    def test_normalizes_complete_dependency_graph(self) -> None:
        result = normalize_bundle(fixture_bundle())
        self.assertEqual(result.completeness, "COMPLETE")
        self.assertEqual(result.root.purl, "pkg:npm/demo-root@1.0.0")
        self.assertEqual(len(result.nodes), 3)
        self.assertEqual(len(result.edges), 2)
        self.assertEqual(result.edges[0].to_key.purl, "pkg:npm/alpha@2.1.0")
        self.assertEqual(result.root_properties["licenses"], ["MIT"])
        self.assertEqual(
            result.root_properties["advisory_ids"], ["GHSA-demo-0000-0000"]
        )
        self.assertRegex(result.source_revision, r"^sha256:[a-f0-9]{64}$")

        facts = build_fact_specs(result)
        self.assertEqual(len(facts), 6)
        self.assertEqual(
            [fact.predicate for fact in facts],
            [
                "HAS_PROPERTY",
                "HAS_VERSION",
                "HAS_VERSION",
                "HAS_VERSION",
                "DEPENDS_ON",
                "DEPENDS_ON",
            ],
        )
        self.assertEqual(
            facts[-2].evidence_pointer,
            "/edges/0",
        )
        self.assertEqual(facts[0].evidence_hash, sha256_key(fixture("version.json")))
        self.assertEqual(
            facts[-2].evidence_hash,
            sha256_key(fixture("dependencies.json")["edges"][0]),
        )
        self.assertRegex(facts[-1].logical_key, r"^sha256:[a-f0-9]{64}$")

    def test_limits_and_bundled_nodes_make_snapshot_partial(self) -> None:
        dependencies = fixture("dependencies.json")
        dependencies["nodes"][1]["bundled"] = True
        result = normalize_bundle(
            DepsDevBundle(
                requested=fixture_bundle().requested,
                version=fixture("version.json"),
                dependencies=dependencies,
                version_uri="https://api.deps.dev/version",
                dependencies_uri="https://api.deps.dev/dependencies",
            ),
            max_nodes=2,
            max_edges=1,
        )
        self.assertEqual(result.completeness, "PARTIAL")
        codes = {item["code"] for item in result.limitations}
        self.assertIn("BUNDLED_DEPENDENCY_SKIPPED", codes)
        self.assertIn("EDGE_ENDPOINT_SKIPPED", codes)


if __name__ == "__main__":
    unittest.main()

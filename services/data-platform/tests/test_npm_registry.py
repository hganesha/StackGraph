from __future__ import annotations

import json
import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.npm_registry import (
    HttpResponse,
    NpmRegistryApiError,
    NpmRegistryClient,
    normalize_version,
)


FIXTURE_DIR = Path(
    os.environ.get("STACKGRAPH_TEST_FIXTURE_DIR", "/code/tests/fixtures")
) / "npm"


@dataclass(frozen=True)
class RecordedRequest:
    url: str
    headers: Mapping[str, str]


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[RecordedRequest] = []

    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        self.requests.append(RecordedRequest(url, dict(headers)))
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses.pop(0)


def fixture() -> dict[str, object]:
    return json.loads((FIXTURE_DIR / "packument.json").read_text(encoding="utf-8"))


def response(
    document: object,
    *,
    status: int = 200,
    final_url: str = "https://npm.acme.example/repository/npm/%40acme%2Fbilling-sdk",
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    return HttpResponse(
        status,
        headers or {},
        json.dumps(document).encode("utf-8"),
        final_url,
    )


class NpmRegistryClientTests(unittest.TestCase):
    def test_fetches_scoped_packument_with_registry_scoped_auth(self) -> None:
        transport = FakeTransport(
            [response(fixture(), headers={"ETag": '"packument-v1"'})]
        )
        client = NpmRegistryClient(
            registry_key="acme-npm",
            registry_origin="https://npm.acme.example/repository/npm/",
            visibility="PRIVATE",
            token="secret-token",
            transport=transport,
        )
        bundle = client.fetch(
            PackageVersionKey.from_purl("pkg:npm/%40acme/billing-sdk@2.4.1")
        )

        self.assertIsNotNone(bundle)
        self.assertTrue(transport.requests[0].url.endswith("/%40acme%2Fbilling-sdk"))
        self.assertEqual(
            transport.requests[0].headers["Authorization"], "Bearer secret-token"
        )
        observation = bundle.raw_observation("tenant-one")
        serialized = json.dumps(observation)
        self.assertNotIn("secret-token", serialized)
        self.assertEqual(observation["tenant_key"], "tenant-one")
        self.assertEqual(
            observation["target_key"],
            "registry:acme-npm:pkg:npm/%40acme/billing-sdk@2.4.1",
        )

    def test_uses_etag_and_handles_not_modified(self) -> None:
        transport = FakeTransport(
            [
                HttpResponse(
                    304,
                    {"ETag": '"packument-v1"'},
                    b"",
                    "https://registry.npmjs.org/react",
                )
            ]
        )
        result = NpmRegistryClient(transport=transport).fetch(
            PackageVersionKey.from_purl("pkg:npm/react@19.1.0"),
            etag='"packument-v1"',
        )
        self.assertIsNone(result)
        self.assertEqual(
            transport.requests[0].headers["If-None-Match"], '"packument-v1"'
        )

    def test_rejects_cross_origin_redirects_and_credentialed_origins(self) -> None:
        with self.assertRaises(ValueError):
            NpmRegistryClient(registry_origin="https://token@registry.npmjs.org/")
        transport = FakeTransport(
            [response({}, final_url="https://attacker.example/react")]
        )
        with self.assertRaises(ValueError):
            NpmRegistryClient(transport=transport).fetch(
                PackageVersionKey.from_purl("pkg:npm/react@19.1.0")
            )

    def test_classifies_provider_failures_for_retry(self) -> None:
        transport = FakeTransport(
            [
                HttpResponse(
                    429,
                    {"Retry-After": "23"},
                    b"{}",
                    "https://registry.npmjs.org/react",
                )
            ]
        )
        with self.assertRaises(NpmRegistryApiError) as context:
            NpmRegistryClient(transport=transport).fetch(
                PackageVersionKey.from_purl("pkg:npm/react@19.1.0")
            )
        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.retry_after_seconds, 23)


class NpmNormalizationTests(unittest.TestCase):
    def test_normalizes_exact_version_metadata_and_evidence(self) -> None:
        target = PackageVersionKey.from_purl(
            "pkg:npm/%40acme/billing-sdk@2.4.1"
        )
        bundle = NpmRegistryClient(
            registry_key="acme-npm",
            registry_origin="https://npm.acme.example/repository/npm/",
            visibility="PRIVATE",
            transport=FakeTransport(
                [response(fixture(), headers={"ETag": '"packument-v1"'})]
            ),
        ).fetch(target)
        metadata = normalize_version(bundle)

        self.assertEqual(metadata.key, target)
        self.assertEqual(metadata.visibility, "PRIVATE")
        self.assertEqual(metadata.deprecated, "Use @acme/payments-sdk instead")
        self.assertEqual(metadata.engines, {"node": ">=18"})
        self.assertEqual(metadata.published_at, "2026-07-01T12:00:00.000Z")
        self.assertEqual(metadata.source_revision, '"packument-v1"')
        self.assertRegex(metadata.logical_key, r"^sha256:[a-f0-9]{64}$")
        self.assertRegex(metadata.evidence_hash, r"^sha256:[a-f0-9]{64}$")

    def test_rejects_requested_version_identity_mismatch(self) -> None:
        document = fixture()
        document["versions"]["2.4.1"]["version"] = "2.4.2"
        bundle = NpmRegistryClient(
            registry_key="acme-npm",
            registry_origin="https://npm.acme.example/repository/npm/",
            transport=FakeTransport([response(document)]),
        ).fetch(
            PackageVersionKey.from_purl("pkg:npm/%40acme/billing-sdk@2.4.1")
        )
        with self.assertRaises(ValueError):
            normalize_version(bundle)

    def test_rejects_credentialed_tarball_url(self) -> None:
        document = fixture()
        document["versions"]["2.4.1"]["dist"]["tarball"] = (
            "https://token@npm.acme.example/package.tgz"
        )
        bundle = NpmRegistryClient(
            registry_key="acme-npm",
            registry_origin="https://npm.acme.example/repository/npm/",
            transport=FakeTransport([response(document)]),
        ).fetch(
            PackageVersionKey.from_purl("pkg:npm/%40acme/billing-sdk@2.4.1")
        )
        with self.assertRaises(ValueError):
            normalize_version(bundle)


if __name__ == "__main__":
    unittest.main()

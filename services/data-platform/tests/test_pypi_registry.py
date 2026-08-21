from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Mapping

from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.pypi_registry import (
    HttpResponse,
    PyPIRegistryApiError,
    PyPIRegistryClient,
    normalize_version,
)


@dataclass(frozen=True)
class Request:
    url: str
    headers: Mapping[str, str]


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[Request] = []

    def request(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> HttpResponse:
        self.requests.append(Request(url, dict(headers)))
        return self.responses.pop(0)


def document() -> dict[str, object]:
    return {
        "info": {
            "name": "Demo_Project", "version": "1.2.3", "summary": "Demo package",
            "license": "MIT", "classifiers": ["Programming Language :: Python :: 3"],
            "requires_python": ">=3.11", "requires_dist": ["httpx>=0.27"],
            "project_urls": {"Source": "https://github.com/example/demo"},
            "home_page": "https://example.test/demo", "author": "Example",
        },
        "urls": [{
            "packagetype": "sdist", "url": "https://files.pythonhosted.org/demo.tar.gz",
            "size": 123, "digests": {"sha256": "abc"}, "yanked": False,
            "upload_time_iso_8601": "2026-01-01T00:00:00Z",
        }],
    }


class PyPIRegistryTests(unittest.TestCase):
    def test_fetch_normalize_and_observation_have_npm_metadata_parity(self) -> None:
        body = json.dumps(document()).encode()
        transport = FakeTransport([HttpResponse(
            200, {"ETag": '"revision"'}, body,
            "https://pypi.org/pypi/demo-project/1.2.3/json",
        )])
        bundle = PyPIRegistryClient(transport=transport).fetch(
            PackageVersionKey.from_purl("pkg:pypi/demo-project@1.2.3")
        )
        assert bundle is not None
        metadata = normalize_version(bundle)
        self.assertEqual(metadata.key.name, "demo-project")
        self.assertEqual(metadata.requires_python, ">=3.11")
        self.assertEqual(metadata.requires_dist, ("httpx>=0.27",))
        self.assertEqual(metadata.properties["artifact"]["hashes"], {"sha256": "abc"})
        self.assertEqual(bundle.raw_observation()["source"]["schema_version"], "pypi-json-v1")
        self.assertNotIn("Authorization", transport.requests[0].headers)

    def test_conditional_fetch_and_retry_classification(self) -> None:
        unchanged = FakeTransport([HttpResponse(
            304, {}, b"", "https://pypi.org/pypi/demo/1/json",
        )])
        self.assertIsNone(PyPIRegistryClient(transport=unchanged).fetch(
            PackageVersionKey.from_purl("pkg:pypi/demo@1"), etag='"a"',
        ))
        limited = FakeTransport([HttpResponse(
            429, {"Retry-After": "12"}, b"", "https://pypi.org/pypi/demo/1/json",
        )])
        with self.assertRaises(PyPIRegistryApiError) as context:
            PyPIRegistryClient(transport=limited).fetch(
                PackageVersionKey.from_purl("pkg:pypi/demo@1")
            )
        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.retry_after_seconds, 12)

    def test_rejects_cross_origin_redirect_and_credentialed_origin(self) -> None:
        with self.assertRaises(ValueError):
            PyPIRegistryClient(registry_origin="https://token@pypi.org/")
        transport = FakeTransport([HttpResponse(200, {}, b"{}", "https://evil.test/demo")])
        with self.assertRaises(ValueError):
            PyPIRegistryClient(transport=transport).fetch(
                PackageVersionKey.from_purl("pkg:pypi/demo@1")
            )


if __name__ == "__main__":
    unittest.main()

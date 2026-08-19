from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from stackgraph_data.catalog import sha256_key
from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.osv import (
    HttpResponse,
    OsvApiError,
    OsvBundle,
    OsvClient,
    QueryPage,
    QueryResult,
    VulnerabilityRef,
    build_fact_specs,
    normalize_bundle,
)


FIXTURE_DIR = Path(
    os.environ.get("STACKGRAPH_TEST_FIXTURE_DIR", "/code/tests/fixtures")
) / "osv"


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[RecordedRequest] = []

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> HttpResponse:
        self.requests.append(RecordedRequest(method, url, dict(headers), body))
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        return self.responses.pop(0)


def response(document: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(document).encode("utf-8"))


def fixture() -> dict[str, object]:
    return json.loads((FIXTURE_DIR / "vulnerability.json").read_text(encoding="utf-8"))


def query_result(*refs: VulnerabilityRef, truncated: bool = False) -> QueryResult:
    target = PackageVersionKey.from_purl("pkg:npm/lodash@4.17.20")
    result = {
        "vulns": [
            {"id": ref.osv_id, "modified": ref.modified} for ref in refs
        ]
    }
    return QueryResult(
        target=target,
        vulnerabilities=refs,
        pages=(
            QueryPage(
                request_query={"package": {"purl": target.purl}},
                result=result,
            ),
        ),
        truncated=truncated,
    )


def bundle(
    result: QueryResult,
    *documents: dict[str, object],
) -> OsvBundle:
    return OsvBundle(
        target=result.target,
        query=result,
        vulnerability_documents=documents,
        query_uri="https://api.osv.dev/v1/querybatch",
        detail_uris=tuple(
            f"https://api.osv.dev/v1/vulns/{document['id']}"
            for document in documents
        ),
    )


class OsvClientTests(unittest.TestCase):
    def test_batches_targets_and_paginates_only_the_target_with_a_token(self) -> None:
        first = {
            "results": [
                {
                    "vulns": [
                        {"id": "GHSA-demo-0000-0001", "modified": "2026-08-19T12:00:00Z"}
                    ],
                    "next_page_token": "next-lodash",
                },
                {"vulns": []},
            ]
        }
        second = {
            "results": [
                {
                    "vulns": [
                        {"id": "CVE-2026-0002", "modified": "2026-08-19T13:00:00Z"}
                    ]
                }
            ]
        }
        transport = FakeTransport([response(first), response(second)])
        client = OsvClient(transport=transport)
        results = client.query_batch(
            [
                PackageVersionKey.from_purl("pkg:npm/lodash@4.17.20"),
                PackageVersionKey.from_purl("pkg:pypi/idna@3.7"),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [item.osv_id for item in results[0].vulnerabilities],
            ["GHSA-demo-0000-0001", "CVE-2026-0002"],
        )
        self.assertEqual(results[1].vulnerabilities, ())
        first_body = json.loads(transport.requests[0].body or b"{}")
        second_body = json.loads(transport.requests[1].body or b"{}")
        self.assertEqual(len(first_body["queries"]), 2)
        self.assertEqual(
            second_body,
            {
                "queries": [
                    {
                        "package": {"purl": "pkg:npm/lodash@4.17.20"},
                        "page_token": "next-lodash",
                    }
                ]
            },
        )
        self.assertNotIn("Authorization", transport.requests[0].headers)

    def test_fetches_and_validates_vulnerability_details(self) -> None:
        transport = FakeTransport([response(fixture())])
        document, uri = OsvClient(transport=transport).fetch_vulnerability(
            "GHSA-demo-0000-0001"
        )
        self.assertEqual(document["id"], "GHSA-demo-0000-0001")
        self.assertTrue(uri.endswith("/v1/vulns/GHSA-demo-0000-0001"))
        self.assertEqual(transport.requests[0].method, "GET")

    def test_classifies_provider_failures_for_scheduler_retry(self) -> None:
        transport = FakeTransport(
            [HttpResponse(429, {"Retry-After": "23"}, b'{"message":"slow down"}')]
        )
        with self.assertRaises(OsvApiError) as context:
            OsvClient(transport=transport).query_batch(
                [PackageVersionKey.from_purl("pkg:npm/lodash@4.17.20")]
            )
        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.retry_after_seconds, 23)

    def test_rejects_credentialed_or_insecure_base_urls(self) -> None:
        for value in ("http://api.osv.dev", "https://token@api.osv.dev"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                OsvClient(base_url=value)


class OsvNormalizationTests(unittest.TestCase):
    def test_normalizes_vulnerability_and_emits_exact_dual_evidence(self) -> None:
        ref = VulnerabilityRef("GHSA-demo-0000-0001", "2026-08-19T12:00:00Z")
        result = normalize_bundle(bundle(query_result(ref), fixture()))
        self.assertEqual(result.completeness, "COMPLETE")
        self.assertEqual(result.target.purl, "pkg:npm/lodash@4.17.20")
        self.assertEqual(result.vulnerabilities[0].aliases, ("CVE-2026-0001",))
        self.assertRegex(result.source_revision, r"^sha256:[a-f0-9]{64}$")

        facts = build_fact_specs(result)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].properties["matched_purl"], result.target.purl)
        self.assertEqual(len(facts[0].evidence), 2)
        self.assertEqual(
            facts[0].evidence[1].excerpt_hash,
            sha256_key(fixture()),
        )
        self.assertEqual(
            facts[0].evidence[0].locator["json_pointer"],
            "/results/0/vulns/0",
        )

    def test_budget_marks_snapshot_partial_without_unbacked_facts(self) -> None:
        first = VulnerabilityRef("GHSA-demo-0000-0001", "2026-08-19T12:00:00Z")
        second = VulnerabilityRef("CVE-2026-0002", "2026-08-19T13:00:00Z")
        result = normalize_bundle(
            bundle(query_result(first, second), fixture()),
            max_vulnerabilities=1,
        )
        self.assertEqual(result.completeness, "PARTIAL")
        self.assertEqual(len(result.vulnerabilities), 1)
        self.assertEqual(result.limitations[0]["code"], "VULNERABILITY_BUDGET")

    def test_query_error_is_partial_and_cannot_close_prior_facts(self) -> None:
        target = PackageVersionKey.from_purl("pkg:npm/lodash@4.17.20")
        result = normalize_bundle(
            bundle(
                QueryResult(
                    target=target,
                    vulnerabilities=(),
                    pages=(
                        QueryPage(
                            request_query={"package": {"purl": target.purl}},
                            result={"error": "temporary match failure"},
                        ),
                    ),
                    truncated=False,
                    errors=("temporary match failure",),
                )
            )
        )
        self.assertEqual(result.completeness, "PARTIAL")
        self.assertEqual(result.limitations[0]["code"], "QUERY_ERROR")
        self.assertEqual(build_fact_specs(result), ())

    def test_withdrawn_record_is_preserved_but_does_not_emit_current_edge(self) -> None:
        document = deepcopy(fixture())
        document["withdrawn"] = "2026-08-19T14:00:00Z"
        ref = VulnerabilityRef("GHSA-demo-0000-0001", "2026-08-19T12:00:00Z")
        result = normalize_bundle(bundle(query_result(ref), document))
        self.assertEqual(len(result.vulnerabilities), 1)
        self.assertEqual(build_fact_specs(result), ())


if __name__ == "__main__":
    unittest.main()

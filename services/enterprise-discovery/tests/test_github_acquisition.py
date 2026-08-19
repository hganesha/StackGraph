from __future__ import annotations

import base64
import json
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from stackgraph_discovery.github_client import (
    GitHubApiError,
    GitHubClient,
    HttpResponse,
)
from stackgraph_discovery.github_snapshot import (
    GitHubRepositoryAcquirer,
    SnapshotLimits,
    _github_error_summary,
    manifest_kind,
    parse_repository,
)


COMMIT_SHA = "a" * 40
TREE_SHA = "b" * 40
PACKAGE_SHA = "c" * 40
PYPROJECT_SHA = "d" * 40


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


def response(document: object, **headers: str) -> HttpResponse:
    return HttpResponse(200, headers, json.dumps(document).encode("utf-8"))


def blob(sha: str, content: bytes) -> HttpResponse:
    return response(
        {
            "sha": sha,
            "size": len(content),
            "encoding": "base64",
            "content": base64.b64encode(content).decode("ascii"),
        }
    )


def repository_response() -> HttpResponse:
    return response(
        {
            "id": 1234,
            "node_id": "R_kgDOExample",
            "full_name": "acme/widgets",
            "private": True,
            "visibility": "private",
            "archived": False,
            "default_branch": "main",
        },
        ETag='"repo-etag"',
        **{"X-RateLimit-Remaining": "4998", "X-RateLimit-Reset": "1900000000"},
    )


def commit_response() -> HttpResponse:
    return response(
        {
            "sha": COMMIT_SHA,
            "commit": {
                "tree": {"sha": TREE_SHA},
                "committer": {"date": "2026-08-19T12:00:00Z"},
            },
        }
    )


class GitHubAcquisitionTests(unittest.TestCase):
    def test_acquires_only_target_files_and_writes_contract_envelope(self) -> None:
        package = b'{"dependencies":{"react":"19.1.0"}}\n'
        pyproject = b'[project]\nname = "widgets"\n'
        transport = FakeTransport(
            [
                repository_response(),
                commit_response(),
                response(
                    {
                        "truncated": False,
                        "tree": [
                            {
                                "path": "README.md",
                                "type": "blob",
                                "sha": "e" * 40,
                                "size": 10,
                            },
                            {
                                "path": "package.json",
                                "type": "blob",
                                "sha": PACKAGE_SHA,
                                "size": len(package),
                            },
                            {
                                "path": "services/api/pyproject.toml",
                                "type": "blob",
                                "sha": PYPROJECT_SHA,
                                "size": len(pyproject),
                            },
                        ],
                    },
                    **{"X-RateLimit-Remaining": "4996"},
                ),
                blob(PACKAGE_SHA, package),
                blob(PYPROJECT_SHA, pyproject),
            ]
        )
        client = GitHubClient(token="secret-token", transport=transport)

        with TemporaryDirectory() as directory:
            result = GitHubRepositoryAcquirer(client).acquire(
                "acme/widgets",
                tenant_key="tenant-one",
                installation_id="9876",
                output_root=Path(directory),
            )

            self.assertEqual(result.status, "CHANGED")
            self.assertEqual(result.snapshot.completeness, "COMPLETE")
            self.assertEqual(len(result.snapshot.files), 2)
            self.assertEqual(
                (result.output_path / "files/package.json").read_bytes(), package
            )
            self.assertEqual(
                (result.output_path / "files/services/api/pyproject.toml").read_bytes(),
                pyproject,
            )
            observation = json.loads(
                (result.output_path / "raw-observation.json").read_text()
            )
            self.assertEqual(observation["tenant_key"], "tenant-one")
            self.assertEqual(observation["target_key"], "github:repo:9876/1234")
            self.assertEqual(
                observation["content"]["inline"]["repository"]["installation_id"],
                "9876",
            )
            self.assertRegex(observation["idempotency_key"], r"^sha256:[a-f0-9]{64}$")
            self.assertNotIn("secret-token", json.dumps(observation))

        self.assertEqual(len(transport.requests), 5)
        self.assertTrue(
            all(
                request.headers["Authorization"] == "Bearer secret-token"
                for request in transport.requests
            )
        )
        self.assertNotIn("secret-token", " ".join(item.url for item in transport.requests))

    def test_unchanged_revision_skips_tree_and_blob_requests(self) -> None:
        transport = FakeTransport([repository_response(), commit_response()])
        result = GitHubRepositoryAcquirer(
            GitHubClient(transport=transport)
        ).acquire("acme/widgets", previous_revision=COMMIT_SHA)

        self.assertEqual(result.status, "UNCHANGED")
        self.assertIsNone(result.snapshot)
        self.assertEqual(len(transport.requests), 2)
        self.assertNotIn("Authorization", transport.requests[0].headers)

    def test_truncated_tree_and_limits_produce_partial_snapshot(self) -> None:
        content = b"x" * 20
        transport = FakeTransport(
            [
                repository_response(),
                commit_response(),
                response(
                    {
                        "truncated": True,
                        "tree": [
                            {
                                "path": "package-lock.json",
                                "type": "blob",
                                "sha": PACKAGE_SHA,
                                "size": len(content),
                            }
                        ],
                    }
                ),
            ]
        )
        result = GitHubRepositoryAcquirer(
            GitHubClient(transport=transport)
        ).acquire(
            "acme/widgets",
            limits=SnapshotLimits(max_files=1, max_bytes=100, max_file_bytes=10),
        )

        self.assertEqual(result.snapshot.completeness, "PARTIAL")
        self.assertEqual(result.snapshot.files, ())
        self.assertEqual(
            {item.code for item in result.snapshot.diagnostics},
            {"GITHUB_TREE_TRUNCATED", "FILE_SIZE_LIMIT"},
        )
        self.assertEqual(len(transport.requests), 3)

    def test_unsafe_target_path_is_reported_and_not_materialized(self) -> None:
        transport = FakeTransport(
            [
                repository_response(),
                commit_response(),
                response(
                    {
                        "truncated": False,
                        "tree": [
                            {
                                "path": "../package.json",
                                "type": "blob",
                                "sha": PACKAGE_SHA,
                                "size": 2,
                            }
                        ],
                    }
                ),
            ]
        )
        result = GitHubRepositoryAcquirer(
            GitHubClient(transport=transport)
        ).acquire("acme/widgets")

        self.assertEqual(result.snapshot.files, ())
        self.assertEqual(result.snapshot.diagnostics[0].code, "UNSAFE_REPOSITORY_PATH")
        self.assertEqual(len(transport.requests), 3)

    def test_rate_limit_response_is_retryable_and_preserves_reset(self) -> None:
        transport = FakeTransport(
            [
                HttpResponse(
                    403,
                    {
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": "1900000000",
                    },
                    b'{"message":"API rate limit exceeded"}',
                )
            ]
        )
        with self.assertRaises(GitHubApiError) as context:
            GitHubClient(transport=transport).get_json("/repos/acme/widgets")

        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.rate_limit_reset, 1900000000)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(
            _github_error_summary(context.exception),
            {
                "status": "ERROR",
                "error_class": "GITHUB_PROVIDER",
                "error": "GitHub API request failed with status 403: API rate limit exceeded",
                "http_status": 403,
                "retriable": True,
                "rate_limit_reset": 1900000000,
            },
        )

    def test_secondary_limit_without_headers_is_retryable(self) -> None:
        transport = FakeTransport(
            [
                HttpResponse(
                    403,
                    {},
                    b'{"message":"You have exceeded a secondary rate limit"}',
                )
            ]
        )
        with self.assertRaises(GitHubApiError) as context:
            GitHubClient(transport=transport).get_json("/repos/acme/widgets")

        self.assertTrue(context.exception.retriable)

    def test_repository_and_manifest_validation(self) -> None:
        self.assertEqual(parse_repository("acme/widgets"), ("acme", "widgets"))
        with self.assertRaises(ValueError):
            parse_repository("https://github.com/acme/widgets")
        with self.assertRaises(ValueError):
            parse_repository("acme/widgets.git")
        self.assertEqual(manifest_kind("services/api/requirements-dev.txt"), "PYTHON_REQUIREMENTS")
        self.assertEqual(manifest_kind("packages/web/pnpm-lock.yaml"), "PNPM_LOCK")
        self.assertIsNone(manifest_kind("README.md"))

        transport = FakeTransport([])
        with self.assertRaises(ValueError):
            GitHubRepositoryAcquirer(GitHubClient(transport=transport)).acquire(
                "acme/widgets",
                installation_id="not-a-number",
            )

    def test_client_rejects_insecure_or_credentialed_base_urls(self) -> None:
        with self.assertRaises(ValueError):
            GitHubClient(base_url="http://api.github.com")
        with self.assertRaises(ValueError):
            GitHubClient(base_url="https://token@api.github.com")


if __name__ == "__main__":
    unittest.main()

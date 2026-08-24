from __future__ import annotations

import base64
import io
import json
import tarfile
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
from stackgraph_discovery.evidence_store import LocalEvidenceStore
from stackgraph_discovery.github_snapshot import (
    GitHubRepositoryAcquirer,
    SnapshotLimits,
    _github_error_summary,
    manifest_kind,
    manifest_kind_or_none,
    parse_repository,
)


COMMIT_SHA = "a" * 40
TREE_SHA = "b" * 40
PACKAGE_SHA = "c" * 40
PYPROJECT_SHA = "d" * 40
SOURCE_SHA = "f" * 40


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
        **{
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4998",
            "X-RateLimit-Reset": "1900000000",
        },
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
    def test_repository_hygiene_files_are_acquisition_targets(self) -> None:
        expected = {
            "LICENSE.md": "REPOSITORY_GOVERNANCE",
            ".github/CODEOWNERS": "REPOSITORY_GOVERNANCE",
            ".github/workflows/ci.yml": "BUILD_OR_DEPLOYMENT_CONFIG",
            ".gitlab-ci.yml": "CI_CONFIGURATION",
            ".circleci/config.yml": "CI_CONFIGURATION",
            "pytest.ini": "TEST_CONFIGURATION",
            "vitest.config.ts": "TEST_CONFIGURATION",
        }

        self.assertEqual(
            {path: manifest_kind(path) for path in expected},
            expected,
        )

    def test_acquires_only_target_files_and_writes_contract_envelope(self) -> None:
        readme = b"# Widgets\n"
        package = b'{"dependencies":{"react":"19.1.0"}}\n'
        pyproject = b'[project]\nname = "widgets"\n'
        source = b'import React from "react";\n'
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
                            {
                                "path": "packages/web/src/index.tsx",
                                "type": "blob",
                                "sha": SOURCE_SHA,
                                "size": len(source),
                            },
                        ],
                    },
                    **{"X-RateLimit-Remaining": "4996"},
                ),
                blob("e" * 40, readme),
                blob(PACKAGE_SHA, package),
                blob(SOURCE_SHA, source),
                blob(PYPROJECT_SHA, pyproject),
            ]
        )
        client = GitHubClient(token="secret-token", transport=transport)

        with TemporaryDirectory() as directory:
            evidence_store = LocalEvidenceStore(Path(directory) / "evidence")
            result = GitHubRepositoryAcquirer(client).acquire(
                "acme/widgets",
                tenant_key="tenant-one",
                installation_id="9876",
                output_root=Path(directory) / "snapshots",
                evidence_store=evidence_store,
            )

            self.assertEqual(result.status, "CHANGED")
            self.assertEqual(result.rate_limit_limit, 5000)
            self.assertEqual(result.rate_limit_remaining, 4996)
            self.assertEqual(result.rate_limit_reset, 1900000000)
            self.assertEqual(result.snapshot.completeness, "COMPLETE")
            self.assertEqual(len(result.snapshot.files), 4)
            self.assertEqual(
                (result.output_path / "files/README.md").read_bytes(), readme
            )
            self.assertEqual(
                (result.output_path / "files/package.json").read_bytes(), package
            )
            self.assertEqual(
                (result.output_path / "files/services/api/pyproject.toml").read_bytes(),
                pyproject,
            )
            self.assertEqual(
                (result.output_path / "files/packages/web/src/index.tsx").read_bytes(),
                source,
            )
            observation = json.loads(
                (result.output_path / "raw-observation.json").read_text()
            )
            self.assertEqual(observation["tenant_key"], "tenant-one")
            self.assertEqual(observation["target_key"], "github:repo:9876/1234")
            self.assertNotIn("inline", observation["content"])
            self.assertEqual(observation["content"]["blob_uri"], result.stored_evidence.uri)
            self.assertEqual(observation["content"]["hash"], result.stored_evidence.content_hash)
            self.assertEqual(
                result.summary()["content_size_bytes"],
                result.stored_evidence.size_bytes,
            )
            self.assertNotEqual(
                observation["idempotency_key"],
                result.snapshot.raw_observation(
                    "tenant-two", result.stored_evidence
                )["idempotency_key"],
            )
            archive = evidence_store.read_bytes("tenant-one", result.stored_evidence)
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as stored:
                self.assertEqual(
                    sorted(stored.getnames()),
                    [
                        "files/README.md",
                        "files/package.json",
                        "files/packages/web/src/index.tsx",
                        "files/services/api/pyproject.toml",
                        "snapshot.json",
                    ],
                )
                snapshot_document = json.load(stored.extractfile("snapshot.json"))
                self.assertEqual(snapshot_document["repository"]["installation_id"], "9876")
            self.assertRegex(observation["idempotency_key"], r"^sha256:[a-f0-9]{64}$")
            self.assertNotIn("secret-token", json.dumps(observation))

        self.assertEqual(len(transport.requests), 7)
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
        self.assertEqual(result.full_name, "acme/widgets")
        self.assertEqual(result.default_branch, "main")
        self.assertIs(result.archived, False)
        self.assertEqual(result.rate_limit_limit, 5000)
        self.assertEqual(result.rate_limit_remaining, 4998)
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
                        "X-RateLimit-Limit": "5000",
                        "X-RateLimit-Reset": "1900000000",
                    },
                    b'{"message":"API rate limit exceeded"}',
                )
            ]
        )
        with self.assertRaises(GitHubApiError) as context:
            GitHubClient(transport=transport).get_json("/repos/acme/widgets")

        self.assertTrue(context.exception.retriable)
        self.assertEqual(context.exception.rate_limit_remaining, 0)
        self.assertEqual(context.exception.rate_limit_limit, 5000)
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
        self.assertEqual(manifest_kind("packages/web/src/index.tsx"), "TYPESCRIPT_SOURCE")
        self.assertEqual(manifest_kind("README.md"), "REPOSITORY_DOCUMENTATION")
        self.assertEqual(manifest_kind(".env.example"), "CONFIG_TEMPLATE")
        self.assertEqual(manifest_kind(".env.production.example"), "CONFIG_TEMPLATE")
        self.assertEqual(manifest_kind("application.yml"), "APPLICATION_CONFIG")
        self.assertEqual(manifest_kind("compose.production.yaml"), "DEPLOYMENT_CONFIG")
        self.assertEqual(manifest_kind("docker-compose.dev.yml"), "DEPLOYMENT_CONFIG")
        self.assertEqual(manifest_kind("Dockerfile.worker"), "DEPLOYMENT_CONFIG")
        self.assertEqual(manifest_kind("openapi.json"), "API_CONTRACT")
        self.assertEqual(manifest_kind("services/billing/billing.openapi.yaml"), "API_CONTRACT")
        self.assertEqual(manifest_kind("docs/swagger-v2.yml"), "API_CONTRACT")
        self.assertEqual(manifest_kind("config/database.properties"), "BUILD_OR_DEPLOYMENT_CONFIG")
        self.assertEqual(manifest_kind_or_none("../index.ts"), "UNSAFE_TARGET")

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

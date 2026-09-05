from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from stackgraph_discovery.github_activity import GitHubRepositoryActivityCollector
from stackgraph_discovery.github_client import GitHubClient, HttpResponse


class ActivityTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def request(self, url, headers, timeout_seconds):
        self.urls.append(url)
        if "/commits?" in url:
            body = [{
                "sha": "a" * 40,
                "html_url": f"https://github.com/acme/billing/commit/{'a' * 40}",
                "author": {
                    "id": 42, "login": "dana", "type": "User",
                    "avatar_url": "https://avatars.githubusercontent.com/u/42",
                },
                "commit": {
                    "message": "Tighten invoice validation\n\nKeep provider errors bounded.",
                    "author": {"date": "2026-08-18T12:00:00Z"},
                    "committer": {"date": "2026-08-18T12:05:00Z"},
                },
            }]
        elif "/pulls?" in url:
            body = [{
                "number": 284,
                "title": "Harden provider timeouts",
                "html_url": "https://github.com/acme/billing/pull/284",
                "created_at": "2026-08-15T12:00:00Z",
                "updated_at": "2026-08-17T12:00:00Z",
                "merged_at": "2026-08-17T12:00:00Z",
                "user": {"id": 57, "login": "priya", "type": "User"},
                "base": {"ref": "main"},
            }]
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return HttpResponse(status=200, headers={}, body=json.dumps(body).encode())


class GitHubActivityTests(unittest.TestCase):
    def test_collects_bounded_default_branch_and_pull_request_activity(self) -> None:
        transport = ActivityTransport()
        collector = GitHubRepositoryActivityCollector(
            GitHubClient(transport=transport), max_pages=2,
        )

        result = collector.collect(
            "acme/billing", default_branch="main", include_pull_requests=True,
            now=datetime(2026, 8, 19, tzinfo=UTC),
        )

        self.assertEqual(result.commits_status, "AVAILABLE")
        self.assertEqual(result.pull_requests_status, "AVAILABLE")
        self.assertEqual(
            [event.event_type for event in result.events],
            ["COMMIT", "PULL_REQUEST_MERGED", "PULL_REQUEST_OPENED"],
        )
        self.assertEqual(result.events[0].title, "Tighten invoice validation")
        self.assertEqual(result.events[0].actor.login, "dana")
        self.assertEqual(result.events[0].actor.classification, "HUMAN")
        self.assertEqual(result.events[0].actor.classification_confidence, 1.0)
        self.assertTrue(any("sha=main" in url and "since=" in url for url in transport.urls))

    def test_pull_request_coverage_names_missing_permission_without_requesting_it(self) -> None:
        transport = ActivityTransport()
        result = GitHubRepositoryActivityCollector(
            GitHubClient(transport=transport),
        ).collect(
            "acme/billing", default_branch="main", include_pull_requests=False,
            now=datetime(2026, 8, 19, tzinfo=UTC),
        )

        self.assertEqual(result.commits_status, "AVAILABLE")
        self.assertEqual(result.pull_requests_status, "PERMISSION_REQUIRED")
        self.assertFalse(any("/pulls?" in url for url in transport.urls))
        self.assertTrue(any("pull_requests:read" in value for value in result.limitations))

    def test_collects_release_and_deployment_events_when_permissions_allow(self) -> None:
        class ExtendedTransport(ActivityTransport):
            def request(self, url, headers, timeout_seconds):
                if "/releases?" in url:
                    body = [{
                        "id": 77, "name": "v2.0.0", "tag_name": "v2.0.0",
                        "published_at": "2026-08-18T14:00:00Z",
                        "target_commitish": "main",
                        "html_url": "https://github.com/acme/billing/releases/tag/v2.0.0",
                        "author": {"id": 9, "login": "dependabot[bot]", "type": "Bot"},
                    }]
                    self.urls.append(url)
                    return HttpResponse(status=200, headers={}, body=json.dumps(body).encode())
                if "/deployments?" in url:
                    body = [{
                        "id": 88, "environment": "production",
                        "created_at": "2026-08-18T15:00:00Z", "sha": "d" * 40,
                        "ref": "main", "url": "https://api.github.com/repos/acme/billing/deployments/88",
                        "creator": {"id": 10, "login": "github-actions[bot]", "type": "Bot"},
                    }]
                    self.urls.append(url)
                    return HttpResponse(status=200, headers={}, body=json.dumps(body).encode())
                return super().request(url, headers, timeout_seconds)

        result = GitHubRepositoryActivityCollector(
            GitHubClient(transport=ExtendedTransport()),
        ).collect(
            "acme/billing", default_branch="main", include_pull_requests=False,
            include_releases=True, include_deployments=True,
            now=datetime(2026, 8, 19, tzinfo=UTC),
        )

        release = next(event for event in result.events if event.event_type == "RELEASE")
        deployment = next(event for event in result.events if event.event_type == "DEPLOYMENT")
        self.assertEqual(release.actor.classification, "DEPENDENCY_BOT")
        self.assertEqual(deployment.actor.classification, "CI_AUTOMATION")
        self.assertEqual(result.releases_status, "AVAILABLE")
        self.assertEqual(result.deployments_status, "AVAILABLE")


if __name__ == "__main__":
    unittest.main()

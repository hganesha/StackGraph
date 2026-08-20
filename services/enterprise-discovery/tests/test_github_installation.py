from __future__ import annotations

import unittest

from stackgraph_discovery.github_client import ApiResult
from stackgraph_discovery.github_installation import InstallationRepositoryDiscovery


def repository(repository_id: int, name: str, **overrides: object) -> dict:
    value = {
        "id": repository_id,
        "name": name,
        "full_name": f"acme/{name}",
        "owner": {"login": "acme"},
        "default_branch": "main",
        "visibility": "private",
        "archived": False,
        "disabled": False,
    }
    value.update(overrides)
    return value


class StubClient:
    def __init__(self, responses: list[ApiResult]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get_json(self, path: str, *, query=None, etag=None) -> ApiResult:
        self.requests.append((path, dict(query or {})))
        if not self.responses:
            raise AssertionError("unexpected GitHub request")
        return self.responses.pop(0)


class InstallationRepositoryDiscoveryTests(unittest.TestCase):
    def test_paginates_and_builds_stable_tenant_repository_keys(self) -> None:
        client = StubClient([
            ApiResult(
                200,
                {"etag": '"installation-v1"'},
                {"total_count": 3, "repositories": [repository(20, "billing"), repository(10, "web")]},
            ),
            ApiResult(
                200,
                {},
                {"total_count": 3, "repositories": [repository(30, "worker", visibility="internal")]},
            ),
        ])

        snapshot = InstallationRepositoryDiscovery(client, per_page=2).discover("9876")

        self.assertEqual(snapshot.page_count, 2)
        self.assertEqual(snapshot.observed_total, 3)
        self.assertEqual(snapshot.response_etag, '"installation-v1"')
        self.assertEqual(
            [item.target_key("9876") for item in snapshot.repositories],
            ["github:repo:9876/10", "github:repo:9876/20", "github:repo:9876/30"],
        )
        self.assertEqual(snapshot.repositories[-1].visibility, "INTERNAL")
        self.assertRegex(snapshot.source_revision, r"^sha256:[a-f0-9]{64}$")
        self.assertEqual(
            client.requests,
            [
                ("/installation/repositories", {"per_page": "2", "page": "1"}),
                ("/installation/repositories", {"per_page": "2", "page": "2"}),
            ],
        )

    def test_rejects_duplicate_or_incomplete_pagination(self) -> None:
        duplicate = StubClient([
            ApiResult(
                200,
                {},
                {"total_count": 2, "repositories": [repository(10, "web"), repository(10, "web")]},
            )
        ])
        with self.assertRaisesRegex(ValueError, "duplicate ID"):
            InstallationRepositoryDiscovery(duplicate, per_page=2).discover("9876")

        incomplete = StubClient([
            ApiResult(200, {}, {"total_count": 2, "repositories": [repository(10, "web")]})
        ])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            InstallationRepositoryDiscovery(incomplete, per_page=2).discover("9876")

    def test_rejects_repository_identity_mismatch(self) -> None:
        client = StubClient([
            ApiResult(
                200,
                {},
                {
                    "total_count": 1,
                    "repositories": [repository(10, "web", full_name="attacker/web")],
                },
            )
        ])
        with self.assertRaisesRegex(ValueError, "full_name"):
            InstallationRepositoryDiscovery(client).discover("9876")


if __name__ == "__main__":
    unittest.main()

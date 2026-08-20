from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .github_client import ApiResult


INSTALLATION_ID = re.compile(r"^[1-9][0-9]*$")
REPOSITORY_ID = re.compile(r"^[1-9][0-9]*$")
OWNER_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        etag: str | None = None,
    ) -> ApiResult: ...


@dataclass(frozen=True, slots=True)
class InstallationRepository:
    repository_id: str
    owner: str
    name: str
    full_name: str
    default_branch: str
    visibility: str
    archived: bool
    disabled: bool

    def target_key(self, installation_id: str) -> str:
        validate_installation_id(installation_id)
        return f"github:repo:{installation_id}/{self.repository_id}"

    def refresh_policy(self, installation_id: str) -> dict[str, Any]:
        return {
            "provider": "github",
            "installation_id": installation_id,
            "repository_id": self.repository_id,
            "owner": self.owner,
            "name": self.name,
            "full_name": self.full_name,
            "default_branch": self.default_branch,
            "visibility": self.visibility,
            "archived": self.archived,
            "disabled": self.disabled,
            "removed_from_installation": False,
            "installation_revoked": False,
            "cadence_seconds": 3600,
        }


@dataclass(frozen=True, slots=True)
class InstallationRepositorySnapshot:
    installation_id: str
    repositories: tuple[InstallationRepository, ...]
    page_count: int
    observed_total: int
    response_etag: str | None

    @property
    def source_revision(self) -> str:
        identity = [
            {
                "id": item.repository_id,
                "owner": item.owner,
                "name": item.name,
                "default_branch": item.default_branch,
                "visibility": item.visibility,
                "archived": item.archived,
                "disabled": item.disabled,
            }
            for item in self.repositories
        ]
        content = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


class InstallationRepositoryDiscovery:
    def __init__(self, client: GitHubJsonClient, *, per_page: int = 100, max_pages: int = 100) -> None:
        if per_page < 1 or per_page > 100:
            raise ValueError("per_page must be between 1 and 100")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        self._client = client
        self._per_page = per_page
        self._max_pages = max_pages

    def discover(self, installation_id: str) -> InstallationRepositorySnapshot:
        validate_installation_id(installation_id)
        repositories: list[InstallationRepository] = []
        seen_ids: set[str] = set()
        total_count: int | None = None
        first_etag: str | None = None

        for page in range(1, self._max_pages + 1):
            result = self._client.get_json(
                "/installation/repositories",
                query={"per_page": str(self._per_page), "page": str(page)},
            )
            if result.data is None:
                raise ValueError("GitHub installation repository response has no document")
            if page == 1:
                first_etag = result.etag
            document = result.data
            count = document.get("total_count")
            entries = document.get("repositories")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("GitHub installation repository response has an invalid total_count")
            if not isinstance(entries, list):
                raise ValueError("GitHub installation repository response has no repositories array")
            if total_count is None:
                total_count = count
            elif total_count != count:
                raise ValueError("GitHub installation repository total changed during pagination")
            for entry in entries:
                repository = _repository(entry)
                if repository.repository_id in seen_ids:
                    raise ValueError("GitHub installation repository pagination returned a duplicate ID")
                seen_ids.add(repository.repository_id)
                repositories.append(repository)
            if len(entries) < self._per_page or len(repositories) >= count:
                if len(repositories) != count:
                    raise ValueError("GitHub installation repository response is incomplete")
                return InstallationRepositorySnapshot(
                    installation_id=installation_id,
                    repositories=tuple(sorted(repositories, key=lambda item: item.repository_id)),
                    page_count=page,
                    observed_total=count,
                    response_etag=first_etag,
                )
        raise ValueError("GitHub installation repository pagination exceeded max_pages")


def validate_installation_id(value: str) -> None:
    if not INSTALLATION_ID.fullmatch(value):
        raise ValueError("installation_id must be a positive decimal GitHub installation ID")


def _repository(value: object) -> InstallationRepository:
    if not isinstance(value, Mapping):
        raise ValueError("GitHub installation repository entry must be an object")
    repository_id = str(value.get("id") or "")
    name = value.get("name")
    full_name = value.get("full_name")
    owner_value = value.get("owner")
    default_branch = value.get("default_branch")
    visibility = value.get("visibility", "private" if value.get("private") else "public")
    if not REPOSITORY_ID.fullmatch(repository_id):
        raise ValueError("GitHub installation repository has an invalid ID")
    if not isinstance(name, str) or not REPOSITORY_NAME.fullmatch(name):
        raise ValueError("GitHub installation repository has an invalid name")
    if not isinstance(owner_value, Mapping) or not isinstance(owner_value.get("login"), str):
        raise ValueError("GitHub installation repository has no owner login")
    owner = owner_value["login"]
    if not OWNER_NAME.fullmatch(owner):
        raise ValueError("GitHub installation repository has an invalid owner login")
    if full_name != f"{owner}/{name}":
        raise ValueError("GitHub installation repository full_name does not match owner/name")
    if not isinstance(default_branch, str) or not default_branch:
        raise ValueError("GitHub installation repository has no default branch")
    if visibility not in {"public", "private", "internal"}:
        raise ValueError("GitHub installation repository has an invalid visibility")
    return InstallationRepository(
        repository_id=repository_id,
        owner=owner,
        name=name,
        full_name=full_name,
        default_branch=default_branch,
        visibility=visibility.upper(),
        archived=bool(value.get("archived", False)),
        disabled=bool(value.get("disabled", False)),
    )

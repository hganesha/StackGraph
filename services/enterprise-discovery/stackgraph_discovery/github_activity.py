from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .github_client import GitHubApiError, GitHubClient, GitHubTransportError


ACTIVITY_SOURCE_KEY = "github-activity"
ACTIVITY_WINDOW_DAYS = 90
ACTIVITY_MAX_PAGES = 10
ACTIVITY_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ActivityActor:
    actor_key: str
    login: str
    avatar_url: str | None
    is_bot: bool


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    provider_event_key: str
    event_type: str
    occurred_at: datetime
    title: str
    actor: ActivityActor | None = None
    revision: str | None = None
    branch: str | None = None
    pull_request_number: int | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class ActivityCollection:
    window_started_at: datetime
    window_ended_at: datetime
    commits_status: str
    pull_requests_status: str
    events: tuple[ActivityEvent, ...]
    limitations: tuple[str, ...]


class GitHubRepositoryActivityCollector:
    def __init__(
        self,
        client: GitHubClient,
        *,
        max_pages: int = ACTIVITY_MAX_PAGES,
        page_size: int = ACTIVITY_PAGE_SIZE,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        self._client = client
        self._max_pages = max_pages
        self._page_size = page_size

    def collect(
        self,
        repository: str,
        *,
        default_branch: str,
        include_pull_requests: bool,
        now: datetime | None = None,
    ) -> ActivityCollection:
        if not default_branch.strip():
            raise ValueError("default_branch must not be empty")
        parts = repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("repository must use the owner/name form")
        window_ended_at = (now or datetime.now(UTC)).astimezone(UTC)
        window_started_at = window_ended_at - timedelta(days=ACTIVITY_WINDOW_DAYS)
        repo_path = f"/repos/{quote(parts[0], safe='')}/{quote(parts[1], safe='')}"
        events: list[ActivityEvent] = []
        limitations: list[str] = []

        try:
            commit_events, truncated = self._commits(
                repo_path, default_branch, window_started_at,
            )
        except (GitHubApiError, GitHubTransportError) as error:
            commits_status = "ERROR"
            limitations.append(f"Commit activity could not be collected: {type(error).__name__}.")
        else:
            commits_status = "PARTIAL" if truncated else "AVAILABLE"
            events.extend(commit_events)
            if truncated:
                limitations.append(
                    f"Commit activity exceeded the bounded {self._max_pages * self._page_size}-event collection limit."
                )
            if any(event.actor is None for event in commit_events):
                limitations.append(
                    "Contributor totals exclude commits without a linked GitHub identity."
                )

        if not include_pull_requests:
            pull_requests_status = "PERMISSION_REQUIRED"
            limitations.append(
                "Merged pull-request activity requires the GitHub pull_requests:read permission."
            )
        else:
            try:
                pull_request_events, truncated = self._pull_requests(
                    repo_path, window_started_at,
                )
            except GitHubApiError as error:
                pull_requests_status = (
                    "PERMISSION_REQUIRED" if error.status_code in {403, 404} else "ERROR"
                )
                limitations.append(
                    "Pull-request activity is unavailable for the connected GitHub installation."
                    if pull_requests_status == "PERMISSION_REQUIRED"
                    else f"Pull-request activity could not be collected: {type(error).__name__}."
                )
            except GitHubTransportError as error:
                pull_requests_status = "ERROR"
                limitations.append(
                    f"Pull-request activity could not be collected: {type(error).__name__}."
                )
            else:
                pull_requests_status = "PARTIAL" if truncated else "AVAILABLE"
                events.extend(pull_request_events)
                if truncated:
                    limitations.append(
                        f"Pull-request activity exceeded the bounded {self._max_pages * self._page_size}-event collection limit."
                    )

        events.sort(key=lambda event: (event.occurred_at, event.provider_event_key), reverse=True)
        return ActivityCollection(
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
            commits_status=commits_status,
            pull_requests_status=pull_requests_status,
            events=tuple(events),
            limitations=tuple(dict.fromkeys(limitations)),
        )

    def _commits(
        self,
        repo_path: str,
        default_branch: str,
        since: datetime,
    ) -> tuple[list[ActivityEvent], bool]:
        events: list[ActivityEvent] = []
        truncated = False
        for page in range(1, self._max_pages + 1):
            result = self._client.get_array(
                f"{repo_path}/commits",
                query={
                    "sha": default_branch,
                    "since": _github_timestamp(since),
                    "per_page": str(self._page_size),
                    "page": str(page),
                },
            )
            for item in result.data:
                sha = item.get("sha")
                commit = item.get("commit")
                if not isinstance(sha, str) or not isinstance(commit, dict):
                    continue
                committer = commit.get("committer")
                author = commit.get("author")
                occurred_at = _timestamp(
                    committer.get("date") if isinstance(committer, dict) else None,
                ) or _timestamp(author.get("date") if isinstance(author, dict) else None)
                message = commit.get("message")
                if occurred_at is None or not isinstance(message, str) or not message.strip():
                    continue
                events.append(ActivityEvent(
                    provider_event_key=f"commit:{sha}",
                    event_type="COMMIT",
                    occurred_at=occurred_at,
                    title=message.strip().splitlines()[0][:500],
                    actor=_actor(item.get("author") or item.get("committer")),
                    revision=sha,
                    branch=default_branch,
                    source_url=_https_url(item.get("html_url")),
                ))
            if len(result.data) < self._page_size:
                break
            if page == self._max_pages:
                truncated = True
        return events, truncated

    def _pull_requests(
        self,
        repo_path: str,
        since: datetime,
    ) -> tuple[list[ActivityEvent], bool]:
        events: list[ActivityEvent] = []
        truncated = False
        for page in range(1, self._max_pages + 1):
            result = self._client.get_array(
                f"{repo_path}/pulls",
                query={
                    "state": "all", "sort": "updated", "direction": "desc",
                    "per_page": str(self._page_size), "page": str(page),
                },
            )
            oldest_update: datetime | None = None
            for item in result.data:
                number = item.get("number")
                title = item.get("title")
                if not isinstance(number, int) or not isinstance(title, str) or not title.strip():
                    continue
                updated_at = _timestamp(item.get("updated_at"))
                if updated_at is not None:
                    oldest_update = min(oldest_update or updated_at, updated_at)
                actor = _actor(item.get("user"))
                source_url = _https_url(item.get("html_url"))
                base = item.get("base")
                branch = base.get("ref") if isinstance(base, dict) and isinstance(base.get("ref"), str) else None
                created_at = _timestamp(item.get("created_at"))
                if created_at is not None and created_at >= since:
                    events.append(ActivityEvent(
                        provider_event_key=f"pull:{number}:opened",
                        event_type="PULL_REQUEST_OPENED", occurred_at=created_at,
                        title=title.strip()[:500], actor=actor, branch=branch,
                        pull_request_number=number, source_url=source_url,
                    ))
                merged_at = _timestamp(item.get("merged_at"))
                if merged_at is not None and merged_at >= since:
                    events.append(ActivityEvent(
                        provider_event_key=f"pull:{number}:merged",
                        event_type="PULL_REQUEST_MERGED", occurred_at=merged_at,
                        title=title.strip()[:500], actor=actor, branch=branch,
                        pull_request_number=number, source_url=source_url,
                    ))
            if len(result.data) < self._page_size or (
                oldest_update is not None and oldest_update < since
            ):
                break
            if page == self._max_pages:
                truncated = True
        return events, truncated


def persist_repository_activity(
    database_url: str,
    *,
    tenant_id: UUID,
    repository_key: str,
    collection: ActivityCollection,
) -> bool:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return persist_repository_activity_connection(
            connection,
            tenant_id=tenant_id,
            repository_key=repository_key,
            collection=collection,
        )


def persist_repository_activity_connection(
    connection: Connection[dict[str, Any]],
    *,
    tenant_id: UUID,
    repository_key: str,
    collection: ActivityCollection,
) -> bool:
    repository = connection.execute(
        """
        SELECT id FROM entity
        WHERE tenant_id=%s AND namespace='ENTERPRISE' AND entity_type='Repository'
          AND canonical_key=%s
        """,
        (tenant_id, repository_key),
    ).fetchone()
    if repository is None:
        return False
    repository_id = repository["id"]
    for event in collection.events:
        connection.execute(
            """
            INSERT INTO repository_activity_event(
              tenant_id,repository_entity_id,provider,provider_event_key,event_type,
              occurred_at,title,actor_key,actor_login,actor_avatar_url,actor_is_bot,
              revision,branch,pull_request_number,source_url
            ) VALUES (%s,%s,'GITHUB',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,repository_entity_id,provider,provider_event_key)
            DO UPDATE SET event_type=EXCLUDED.event_type,occurred_at=EXCLUDED.occurred_at,
              title=EXCLUDED.title,actor_key=EXCLUDED.actor_key,
              actor_login=EXCLUDED.actor_login,actor_avatar_url=EXCLUDED.actor_avatar_url,
              actor_is_bot=EXCLUDED.actor_is_bot,revision=EXCLUDED.revision,
              branch=EXCLUDED.branch,pull_request_number=EXCLUDED.pull_request_number,
              source_url=EXCLUDED.source_url,observed_at=now()
            """,
            (
                tenant_id, repository_id, event.provider_event_key, event.event_type,
                event.occurred_at, event.title,
                event.actor.actor_key if event.actor else None,
                event.actor.login if event.actor else None,
                event.actor.avatar_url if event.actor else None,
                event.actor.is_bot if event.actor else False,
                event.revision, event.branch, event.pull_request_number, event.source_url,
            ),
        )
    connection.execute(
        """
        INSERT INTO repository_activity_collection(
          tenant_id,repository_entity_id,source_key,window_started_at,window_ended_at,
          commits_status,pull_requests_status,limitations,collected_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT(tenant_id,repository_entity_id,source_key) DO UPDATE
          SET window_started_at=EXCLUDED.window_started_at,
              window_ended_at=EXCLUDED.window_ended_at,
              commits_status=EXCLUDED.commits_status,
              pull_requests_status=EXCLUDED.pull_requests_status,
              limitations=EXCLUDED.limitations,collected_at=now()
        """,
        (
            tenant_id, repository_id, ACTIVITY_SOURCE_KEY,
            collection.window_started_at, collection.window_ended_at,
            collection.commits_status, collection.pull_requests_status,
            Jsonb(list(collection.limitations)),
        ),
    )
    connection.execute(
        """
        DELETE FROM repository_activity_event
        WHERE tenant_id=%s AND repository_entity_id=%s AND occurred_at<%s
        """,
        (tenant_id, repository_id, collection.window_started_at - timedelta(days=30)),
    )
    return True


def _actor(value: object) -> ActivityActor | None:
    if not isinstance(value, dict):
        return None
    actor_id = value.get("id")
    login = value.get("login")
    if not isinstance(actor_id, (int, str)) or not isinstance(login, str) or not login.strip():
        return None
    actor_type = value.get("type")
    normalized_login = login.strip()
    return ActivityActor(
        actor_key=f"github:user:{actor_id}", login=normalized_login,
        avatar_url=_https_url(value.get("avatar_url")),
        is_bot=actor_type == "Bot" or normalized_login.casefold().endswith("[bot]"),
    )


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _github_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _https_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value

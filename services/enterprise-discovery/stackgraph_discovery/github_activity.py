from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from urllib.parse import quote, urlsplit
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .github_client import GitHubApiError, GitHubClient, GitHubTransportError
from .github_snapshot import manifest_kind_or_none


ACTIVITY_SOURCE_KEY = "github-activity"
ACTIVITY_WINDOW_DAYS = 90
ACTIVITY_MAX_PAGES = 10
ACTIVITY_PAGE_SIZE = 100
# Detecting a dependency change costs one file listing per merged pull request, so the
# newest are inspected and the rest are reported as a bounded limitation rather than
# silently skipped.
ACTIVITY_MAX_DEPENDENCY_PULL_REQUESTS = 50
# Manifests and lockfiles are the only files whose change moves a declared dependency.
DEPENDENCY_MANIFEST_KINDS = frozenset({
    "NPM_MANIFEST", "NPM_LOCK", "YARN_LOCK", "PNPM_LOCK", "PNPM_WORKSPACE",
    "PYTHON_MANIFEST", "POETRY_LOCK", "UV_LOCK", "PIPENV_MANIFEST", "PIPENV_LOCK",
    "PYTHON_REQUIREMENTS",
    "MAVEN_MANIFEST", "GRADLE_MANIFEST", "GRADLE_VERSION_CATALOG",
    "NUGET_MANIFEST", "NUGET_LOCK", "CARGO_MANIFEST", "CARGO_LOCK",
    "GO_MANIFEST", "GO_LOCK",
})


@dataclass(frozen=True, slots=True)
class ActivityActor:
    actor_key: str
    login: str
    avatar_url: str | None
    is_bot: bool
    classification: str
    classification_confidence: float
    classification_basis: str


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
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActivityCollection:
    window_started_at: datetime
    window_ended_at: datetime
    commits_status: str
    pull_requests_status: str
    events: tuple[ActivityEvent, ...]
    limitations: tuple[str, ...]
    releases_status: str = "NOT_COLLECTED"
    deployments_status: str = "NOT_COLLECTED"
    dependency_changes_status: str = "NOT_COLLECTED"


class GitHubRepositoryActivityCollector:
    def __init__(
        self,
        client: GitHubClient,
        *,
        max_pages: int = ACTIVITY_MAX_PAGES,
        page_size: int = ACTIVITY_PAGE_SIZE,
        max_dependency_pull_requests: int = ACTIVITY_MAX_DEPENDENCY_PULL_REQUESTS,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        if max_dependency_pull_requests < 0:
            raise ValueError("max_dependency_pull_requests must not be negative")
        self._client = client
        self._max_pages = max_pages
        self._page_size = page_size
        self._max_dependency_pull_requests = max_dependency_pull_requests

    def collect(
        self,
        repository: str,
        *,
        default_branch: str,
        include_pull_requests: bool,
        include_releases: bool = False,
        include_deployments: bool = False,
        include_dependency_changes: bool = False,
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

        releases_status = "NOT_COLLECTED"
        if include_releases:
            try:
                release_events, truncated = self._releases(repo_path, window_started_at)
            except (GitHubApiError, GitHubTransportError) as error:
                releases_status = "PERMISSION_REQUIRED" if isinstance(error, GitHubApiError) and error.status_code in {403, 404} else "ERROR"
                limitations.append(f"Release activity could not be collected: {type(error).__name__}.")
            else:
                releases_status = "PARTIAL" if truncated else "AVAILABLE"
                events.extend(release_events)

        deployments_status = "NOT_COLLECTED"
        if include_deployments:
            try:
                deployment_events, truncated = self._deployments(repo_path, window_started_at)
            except (GitHubApiError, GitHubTransportError) as error:
                deployments_status = "PERMISSION_REQUIRED" if isinstance(error, GitHubApiError) and error.status_code in {403, 404} else "ERROR"
                limitations.append(f"Deployment activity could not be collected: {type(error).__name__}.")
            else:
                deployments_status = "PARTIAL" if truncated else "AVAILABLE"
                events.extend(deployment_events)

        dependency_changes_status = "NOT_COLLECTED"
        if include_dependency_changes:
            merged = [
                event for event in events
                if event.event_type == "PULL_REQUEST_MERGED"
                and event.pull_request_number is not None
            ]
            try:
                dependency_events, truncated = self._dependency_changes(repo_path, merged)
            except (GitHubApiError, GitHubTransportError) as error:
                dependency_changes_status = (
                    "PERMISSION_REQUIRED"
                    if isinstance(error, GitHubApiError) and error.status_code in {403, 404}
                    else "ERROR"
                )
                limitations.append(
                    f"Dependency-change activity could not be collected: {type(error).__name__}."
                )
            else:
                dependency_changes_status = "PARTIAL" if truncated else "AVAILABLE"
                events.extend(dependency_events)
                if truncated:
                    limitations.append(
                        "Dependency-change detection inspected only the most recent merged pull "
                        f"requests, bounded at {self._max_dependency_pull_requests}."
                    )

        events.sort(key=lambda event: (event.occurred_at, event.provider_event_key), reverse=True)
        return ActivityCollection(
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
            commits_status=commits_status,
            pull_requests_status=pull_requests_status,
            events=tuple(events),
            limitations=tuple(dict.fromkeys(limitations)),
            releases_status=releases_status,
            deployments_status=deployments_status,
            dependency_changes_status=dependency_changes_status,
        )

    def _releases(self, repo_path: str, since: datetime) -> tuple[list[ActivityEvent], bool]:
        events: list[ActivityEvent] = []
        truncated = False
        for page in range(1, self._max_pages + 1):
            result = self._client.get_array(
                f"{repo_path}/releases",
                query={"per_page": str(self._page_size), "page": str(page)},
            )
            for item in result.data:
                release_id = item.get("id")
                occurred_at = _timestamp(item.get("published_at") or item.get("created_at"))
                if release_id is None or occurred_at is None or occurred_at < since:
                    continue
                title = str(item.get("name") or item.get("tag_name") or f"Release {release_id}")
                events.append(ActivityEvent(
                    provider_event_key=f"release:{release_id}", event_type="RELEASE",
                    occurred_at=occurred_at, title=title[:500], actor=_actor(item.get("author")),
                    revision=str(item.get("target_commitish") or "") or None,
                    source_url=_https_url(item.get("html_url")),
                ))
            if len(result.data) < self._page_size:
                break
            if page == self._max_pages:
                truncated = True
        return events, truncated

    def _deployments(self, repo_path: str, since: datetime) -> tuple[list[ActivityEvent], bool]:
        events: list[ActivityEvent] = []
        truncated = False
        for page in range(1, self._max_pages + 1):
            result = self._client.get_array(
                f"{repo_path}/deployments",
                query={"per_page": str(self._page_size), "page": str(page)},
            )
            for item in result.data:
                deployment_id = item.get("id")
                occurred_at = _timestamp(item.get("created_at") or item.get("updated_at"))
                if deployment_id is None or occurred_at is None or occurred_at < since:
                    continue
                environment = str(item.get("environment") or "deployment")
                events.append(ActivityEvent(
                    provider_event_key=f"deployment:{deployment_id}", event_type="DEPLOYMENT",
                    occurred_at=occurred_at, title=f"Deploy to {environment}"[:500],
                    actor=_actor(item.get("creator")), revision=str(item.get("sha") or "") or None,
                    branch=str(item.get("ref") or "") or None,
                    source_url=_https_url(item.get("url")),
                ))
            if len(result.data) < self._page_size:
                break
            if page == self._max_pages:
                truncated = True
        return events, truncated

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

    def _dependency_changes(
        self,
        repo_path: str,
        merged_pull_requests: list[ActivityEvent],
    ) -> tuple[list[ActivityEvent], bool]:
        """Emit a DEPENDENCY_CHANGE event for each merged pull request that moved a manifest.

        H1 needs to correlate dependency changes with outcomes, and the aggregate query has
        counted `DEPENDENCY_CHANGE` since migration 050 — but nothing produced one, so the
        column was structurally zero and change memory could never fill itself.

        A merged pull request that touches a manifest or lockfile is the authoritative signal
        that a declared dependency moved. The manifest paths travel in the event's metadata so
        the correlation step can name what changed without re-fetching.
        """
        if not merged_pull_requests:
            return [], False
        ordered = sorted(
            merged_pull_requests,
            key=lambda event: (event.occurred_at, event.provider_event_key),
            reverse=True,
        )
        truncated = len(ordered) > self._max_dependency_pull_requests
        events: list[ActivityEvent] = []
        for pull_request in ordered[: self._max_dependency_pull_requests]:
            number = pull_request.pull_request_number
            result = self._client.get_array(
                f"{repo_path}/pulls/{number}/files",
                query={"per_page": str(self._page_size), "page": "1"},
            )
            manifests = sorted({
                path for item in result.data
                if isinstance(item, dict) and isinstance((path := item.get("filename")), str)
                and manifest_kind_or_none(path) in DEPENDENCY_MANIFEST_KINDS
            })
            if not manifests:
                continue
            # A pull request can list more files than one page holds. Saying so keeps a
            # manifest that was changed beyond the page boundary from reading as absent.
            complete = len(result.data) < self._page_size
            events.append(ActivityEvent(
                provider_event_key=f"pull:{number}:dependency-change",
                event_type="DEPENDENCY_CHANGE",
                occurred_at=pull_request.occurred_at,
                title=pull_request.title,
                actor=pull_request.actor,
                branch=pull_request.branch,
                pull_request_number=number,
                source_url=pull_request.source_url,
                metadata={
                    "manifest_paths": manifests,
                    "file_listing_complete": complete,
                    "detected_from": "PULL_REQUEST_FILES",
                },
            ))
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
              actor_classification,actor_classification_confidence,actor_classification_basis,
              revision,branch,pull_request_number,source_url,metadata
            ) VALUES (%s,%s,'GITHUB',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,repository_entity_id,provider,provider_event_key)
            DO UPDATE SET event_type=EXCLUDED.event_type,occurred_at=EXCLUDED.occurred_at,
              title=EXCLUDED.title,actor_key=EXCLUDED.actor_key,
              actor_login=EXCLUDED.actor_login,actor_avatar_url=EXCLUDED.actor_avatar_url,
              actor_is_bot=EXCLUDED.actor_is_bot,
              actor_classification=EXCLUDED.actor_classification,
              actor_classification_confidence=EXCLUDED.actor_classification_confidence,
              actor_classification_basis=EXCLUDED.actor_classification_basis,
              revision=EXCLUDED.revision,
              branch=EXCLUDED.branch,pull_request_number=EXCLUDED.pull_request_number,
              source_url=EXCLUDED.source_url,metadata=EXCLUDED.metadata,observed_at=now()
            """,
            (
                tenant_id, repository_id, event.provider_event_key, event.event_type,
                event.occurred_at, event.title,
                event.actor.actor_key if event.actor else None,
                event.actor.login if event.actor else None,
                event.actor.avatar_url if event.actor else None,
                event.actor.is_bot if event.actor else False,
                event.actor.classification if event.actor else "UNKNOWN",
                event.actor.classification_confidence if event.actor else 0,
                event.actor.classification_basis if event.actor else "NO_LINKED_PROVIDER_IDENTITY",
                event.revision, event.branch, event.pull_request_number, event.source_url,
                Jsonb(dict(event.metadata)),
            ),
        )
    connection.execute(
        """
        INSERT INTO repository_activity_collection(
          tenant_id,repository_entity_id,source_key,window_started_at,window_ended_at,
          commits_status,pull_requests_status,limitations,collected_at
          ,releases_status,deployments_status,dependency_changes_status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s)
        ON CONFLICT(tenant_id,repository_entity_id,source_key) DO UPDATE
          SET window_started_at=EXCLUDED.window_started_at,
              window_ended_at=EXCLUDED.window_ended_at,
              commits_status=EXCLUDED.commits_status,
              pull_requests_status=EXCLUDED.pull_requests_status,
              releases_status=EXCLUDED.releases_status,
              deployments_status=EXCLUDED.deployments_status,
              dependency_changes_status=EXCLUDED.dependency_changes_status,
              limitations=EXCLUDED.limitations,collected_at=now()
        """,
        (
            tenant_id, repository_id, ACTIVITY_SOURCE_KEY,
            collection.window_started_at, collection.window_ended_at,
            collection.commits_status, collection.pull_requests_status,
            Jsonb(list(collection.limitations)),
            collection.releases_status, collection.deployments_status,
            collection.dependency_changes_status,
        ),
    )
    _refresh_activity_aggregates(connection, tenant_id, repository_id, collection)
    connection.execute(
        """
        DELETE FROM repository_activity_event
        WHERE tenant_id=%s AND repository_entity_id=%s AND occurred_at<%s
        """,
        (tenant_id, repository_id, collection.window_started_at - timedelta(days=30)),
    )
    return True


def _refresh_activity_aggregates(
    connection: Connection[dict[str, Any]], tenant_id: UUID, repository_id: UUID,
    collection: ActivityCollection,
) -> None:
    for window_key, days in (("7d", 7), ("30d", 30), ("90d", 90)):
        window_started_at = collection.window_ended_at - timedelta(days=days)
        connection.execute(
            """
            WITH events AS (
              SELECT * FROM repository_activity_event
              WHERE tenant_id=%s AND repository_entity_id=%s
                AND occurred_at>=%s AND occurred_at<=%s
            ), totals AS (
              SELECT count(*) total,
                     count(*) FILTER (WHERE event_type='COMMIT') commits,
                     count(*) FILTER (WHERE event_type='PULL_REQUEST_OPENED') prs_opened,
                     count(*) FILTER (WHERE event_type='PULL_REQUEST_MERGED') prs_merged,
                     count(*) FILTER (WHERE event_type='DEPLOYMENT') deployments,
                     count(*) FILTER (WHERE event_type='DEPENDENCY_CHANGE') dependency_changes,
                     count(*) FILTER (WHERE event_type='ARCHITECTURE_CHANGE') architecture_changes,
                     count(*) FILTER (WHERE event_type='INCIDENT') incidents,
                     count(*) FILTER (WHERE event_type='INTERVENTION') interventions,
                     count(*) FILTER (WHERE event_type='ROLLBACK') rollbacks,
                     count(DISTINCT actor_key) FILTER (WHERE actor_key IS NOT NULL) contributors,
                     min(occurred_at) first_change_at,max(occurred_at) last_change_at
              FROM events
            ), ownership AS (
              SELECT coalesce(max(actor_events),0) maximum_actor_events
              FROM (SELECT count(*) actor_events FROM events
                    WHERE actor_key IS NOT NULL GROUP BY actor_key) actor_counts
            ), payload AS (
              SELECT jsonb_build_object(
                'commits',commits,'pull_requests_opened',prs_opened,
                'pull_requests_merged',prs_merged,'contributors',contributors,
                'velocity_per_week',round(total::numeric/%s::numeric,4),
                'deployment_frequency_per_week',round(deployments::numeric/%s::numeric,4),
                'dependency_changes',dependency_changes,
                'architecture_changes',architecture_changes,'incidents',incidents,
                'interventions',interventions,'rollbacks',rollbacks,
                'ownership_concentration',CASE WHEN total=0 THEN NULL
                  ELSE round(ownership.maximum_actor_events::numeric/total,4) END,
                'revert_rate',CASE WHEN commits=0 THEN NULL
                  ELSE round(rollbacks::numeric/commits,4) END,
                'first_change_at',first_change_at,'last_change_at',last_change_at
              ) metrics
              FROM totals,ownership
            )
            INSERT INTO repository_activity_aggregate(
              tenant_id,repository_entity_id,window_key,window_started_at,window_ended_at,
              metrics,coverage,limitations,input_fingerprint
            )
            SELECT %s,%s,%s,%s,%s,payload.metrics,%s,%s,
                   'sha256:'||encode(digest((payload.metrics||%s::jsonb)::text,'sha256'),'hex')
            FROM payload
            ON CONFLICT(tenant_id,repository_entity_id,window_key,window_ended_at)
            DO UPDATE SET metrics=EXCLUDED.metrics,coverage=EXCLUDED.coverage,
              limitations=EXCLUDED.limitations,input_fingerprint=EXCLUDED.input_fingerprint,
              computed_at=now()
            """,
            (
                tenant_id, repository_id, window_started_at, collection.window_ended_at,
                days / 7, days / 7, tenant_id, repository_id, window_key,
                window_started_at, collection.window_ended_at,
                Jsonb({
                    "commits": collection.commits_status,
                    "pull_requests": collection.pull_requests_status,
                    "releases": collection.releases_status,
                    "deployments": collection.deployments_status,
                }),
                Jsonb(list(collection.limitations)),
                Jsonb({"window_key": window_key, "metrics_version": "repository-activity/1.0.0"}),
            ),
        )


def _actor(value: object) -> ActivityActor | None:
    if not isinstance(value, dict):
        return None
    actor_id = value.get("id")
    login = value.get("login")
    if not isinstance(actor_id, (int, str)) or not isinstance(login, str) or not login.strip():
        return None
    actor_type = value.get("type")
    normalized_login = login.strip()
    lowered = normalized_login.casefold()
    if any(marker in lowered for marker in ("dependabot", "renovate", "snyk-bot")):
        classification = "DEPENDENCY_BOT"
        basis = "AUTHORITATIVE_BOT_TYPE_AND_PROVIDER_LOGIN"
    elif lowered in {"github-actions[bot]", "github-actions"}:
        classification = "CI_AUTOMATION"
        basis = "AUTHORITATIVE_BOT_TYPE_AND_PROVIDER_LOGIN"
    elif actor_type == "Bot" or lowered.endswith("[bot]"):
        classification = "BOT"
        basis = "AUTHORITATIVE_PROVIDER_BOT_TYPE"
    elif actor_type == "User":
        classification = "HUMAN"
        basis = "AUTHORITATIVE_PROVIDER_USER_TYPE"
    else:
        classification = "UNKNOWN"
        basis = "PROVIDER_TYPE_UNRECOGNIZED"
    return ActivityActor(
        actor_key=f"github:user:{actor_id}", login=normalized_login,
        avatar_url=_https_url(value.get("avatar_url")),
        is_bot=actor_type == "Bot" or normalized_login.casefold().endswith("[bot]"),
        classification=classification,
        classification_confidence=1.0 if classification != "UNKNOWN" else 0.0,
        classification_basis=basis,
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

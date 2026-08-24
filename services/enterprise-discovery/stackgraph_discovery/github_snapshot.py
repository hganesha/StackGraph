from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import quote

from .evidence_store import EvidenceStore, LocalEvidenceStore, StoredEvidence, deterministic_tar
from .github_client import (
    ApiResult,
    GitHubApiError,
    GitHubClient,
    GitHubTransportError,
    JsonObject,
    utc_now,
)


ADAPTER_VERSION = "github-repository-snapshot/1.3.0"
REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
INSTALLATION_ID = re.compile(r"^[0-9]+$")
GIT_OBJECT_ID = re.compile(r"^(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$")
COMPOSE_FILE = re.compile(r"^(?:docker-)?compose(?:\.[a-z0-9_-]+)*\.ya?ml$", re.I)

EXACT_MANIFEST_NAMES = {
    ".npmrc": "NPM_CONFIG",
    ".travis.yml": "CI_CONFIGURATION",
    "CODEOWNERS": "REPOSITORY_GOVERNANCE",
    "Jenkinsfile": "CI_CONFIGURATION",
    "pytest.ini": "TEST_CONFIGURATION",
    "tox.ini": "TEST_CONFIGURATION",
    "package.json": "NPM_MANIFEST",
    "package-lock.json": "NPM_LOCK",
    "npm-shrinkwrap.json": "NPM_LOCK",
    "yarn.lock": "YARN_LOCK",
    "pnpm-lock.yaml": "PNPM_LOCK",
    "pnpm-workspace.yaml": "PNPM_WORKSPACE",
    "pyproject.toml": "PYTHON_MANIFEST",
    "poetry.lock": "POETRY_LOCK",
    "uv.lock": "UV_LOCK",
    "Pipfile": "PIPENV_MANIFEST",
    "Pipfile.lock": "PIPENV_LOCK",
    ".env.example": "CONFIG_TEMPLATE",
    ".env.sample": "CONFIG_TEMPLATE",
    "env.example": "CONFIG_TEMPLATE",
    "env.sample": "CONFIG_TEMPLATE",
    "stackgraph-runtime.json": "RUNTIME_TRACE",
    "Dockerfile": "DEPLOYMENT_CONFIG",
    "docker-compose.yml": "DEPLOYMENT_CONFIG",
    "docker-compose.yaml": "DEPLOYMENT_CONFIG",
    "compose.yml": "DEPLOYMENT_CONFIG",
    "compose.yaml": "DEPLOYMENT_CONFIG",
    "Makefile": "BUILD_CONFIG",
}

SOURCE_SUFFIXES = {
    ".js": "JAVASCRIPT_SOURCE",
    ".jsx": "JAVASCRIPT_SOURCE",
    ".mjs": "JAVASCRIPT_SOURCE",
    ".cjs": "JAVASCRIPT_SOURCE",
    ".ts": "TYPESCRIPT_SOURCE",
    ".tsx": "TYPESCRIPT_SOURCE",
    ".mts": "TYPESCRIPT_SOURCE",
    ".cts": "TYPESCRIPT_SOURCE",
    ".py": "PYTHON_SOURCE",
}

README_SUFFIXES = {"", ".md", ".markdown", ".mdown", ".rst", ".txt"}


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_files: int = 500
    max_bytes: int = 10 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_files <= 0:
            raise ValueError("max_files must be positive")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None

    def as_dict(self) -> JsonObject:
        value: JsonObject = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            value["path"] = self.path
        return value


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    path: str
    kind: str
    git_blob_sha: str
    size_bytes: int
    content_sha256: str
    content: bytes = field(repr=False)

    def as_dict(self) -> JsonObject:
        return {
            "path": self.path,
            "kind": self.kind,
            "git_blob_sha": self.git_blob_sha,
            "size_bytes": self.size_bytes,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_id: str
    repository_node_id: str
    full_name: str
    canonical_key: str
    visibility: str
    archived: bool
    default_branch: str
    source_revision: str
    tree_sha: str
    observed_at: str
    effective_at: str | None
    completeness: str
    files: tuple[SnapshotFile, ...]
    diagnostics: tuple[Diagnostic, ...]
    repository_etag: str | None
    rate_limit_remaining: int | None
    rate_limit_limit: int | None
    rate_limit_reset: int | None
    api_version: str
    repository_api_uri: str
    installation_id: str | None

    def as_dict(self) -> JsonObject:
        repository: JsonObject = {
            "repository_id": self.repository_id,
            "node_id": self.repository_node_id,
            "full_name": self.full_name,
            "canonical_key": self.canonical_key,
            "visibility": self.visibility,
            "archived": self.archived,
            "default_branch": self.default_branch,
        }
        if self.installation_id is not None:
            repository["installation_id"] = self.installation_id
        value: JsonObject = {
            "snapshot_contract_version": "1.0.0",
            "provider": "github",
            "adapter_version": ADAPTER_VERSION,
            "repository": repository,
            "source_revision": self.source_revision,
            "tree_sha": self.tree_sha,
            "observed_at": self.observed_at,
            "completeness": self.completeness,
            "files": [item.as_dict() for item in self.files],
            "stats": {
                "files_retrieved": len(self.files),
                "bytes_retrieved": sum(item.size_bytes for item in self.files),
            },
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "provider_state": {
                "repository_etag": self.repository_etag,
                "rate_limit_remaining": self.rate_limit_remaining,
                "rate_limit_limit": self.rate_limit_limit,
                "rate_limit_reset": self.rate_limit_reset,
            },
        }
        if self.effective_at is not None:
            value["effective_at"] = self.effective_at
        return value

    def raw_observation(
        self,
        tenant_key: str | None = None,
        stored_evidence: StoredEvidence | None = None,
    ) -> JsonObject:
        snapshot = self.as_dict()
        content_bytes = _canonical_json(snapshot)
        request: JsonObject = {
            "uri": self.repository_api_uri,
        }
        if self.repository_etag:
            request["etag"] = self.repository_etag

        identity = {
            "adapter_version": ADAPTER_VERSION,
            "tenant_key": tenant_key,
            "target_key": self.canonical_key,
            "source_revision": self.source_revision,
            # One immutable revision can be observed more than once with different
            # provider metadata. Bind idempotency to this exact observation so a
            # replay is stable while a later observation cannot collide.
            "observed_at": self.observed_at,
            "completeness": self.completeness,
            "files": [item.as_dict() for item in self.files],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }
        content: JsonObject
        if stored_evidence is None:
            content = {
                "hash": f"sha256:{hashlib.sha256(content_bytes).hexdigest()}",
                "media_type": "application/vnd.stackgraph.repository-snapshot+json",
                "size_bytes": len(content_bytes),
                "inline": snapshot,
            }
        else:
            content = {
                "hash": stored_evidence.content_hash,
                "media_type": stored_evidence.media_type,
                "size_bytes": stored_evidence.size_bytes,
                "blob_uri": stored_evidence.uri,
            }
        envelope: JsonObject = {
            "observation_contract_version": "1.0.0",
            "idempotency_key": f"sha256:{hashlib.sha256(_canonical_json(identity)).hexdigest()}",
            "source": {
                "key": "github-repository",
                "kind": "GITHUB",
                "adapter_version": ADAPTER_VERSION,
                "schema_version": self.api_version,
            },
            "target_key": self.canonical_key,
            "source_revision": self.source_revision,
            "observed_at": self.observed_at,
            "request": request,
            "content": content,
        }
        if tenant_key is not None:
            envelope["tenant_key"] = tenant_key
        if self.effective_at is not None:
            envelope["effective_at"] = self.effective_at
        return envelope


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    status: str
    repository_id: str
    canonical_key: str
    full_name: str
    visibility: str
    archived: bool
    default_branch: str
    source_revision: str
    snapshot: RepositorySnapshot | None
    output_path: Path | None
    stored_evidence: StoredEvidence | None
    rate_limit_remaining: int | None
    rate_limit_limit: int | None
    rate_limit_reset: int | None

    def summary(self) -> JsonObject:
        result: JsonObject = {
            "status": self.status,
            "repository_id": self.repository_id,
            "canonical_key": self.canonical_key,
            "source_revision": self.source_revision,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_limit": self.rate_limit_limit,
            "rate_limit_reset": self.rate_limit_reset,
        }
        if self.snapshot is not None:
            result.update(
                {
                    "completeness": self.snapshot.completeness,
                    "files_retrieved": len(self.snapshot.files),
                    "bytes_retrieved": sum(
                        item.size_bytes for item in self.snapshot.files
                    ),
                }
            )
        if self.output_path is not None:
            result["output_path"] = str(self.output_path)
        if self.stored_evidence is not None:
            result["blob_uri"] = self.stored_evidence.uri
            result["content_hash"] = self.stored_evidence.content_hash
            result["content_size_bytes"] = self.stored_evidence.size_bytes
        return result


class GitHubRepositoryAcquirer:
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    def acquire(
        self,
        repository: str,
        *,
        previous_revision: str | None = None,
        installation_id: str | None = None,
        output_root: Path | None = None,
        tenant_key: str | None = None,
        evidence_store: EvidenceStore | None = None,
        limits: SnapshotLimits | None = None,
    ) -> AcquisitionResult:
        owner, name = parse_repository(repository)
        if installation_id is not None and not INSTALLATION_ID.fullmatch(
            installation_id
        ):
            raise ValueError("installation_id must contain only digits")
        limits = limits or SnapshotLimits()
        repo_path = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        repo_result = self._client.get_json(repo_path)
        repo_data = _require_data(repo_result, "repository")

        repository_id = str(_required(repo_data, "id", (int, str)))
        node_id = str(_required(repo_data, "node_id", str))
        full_name = str(_required(repo_data, "full_name", str))
        default_branch = str(_required(repo_data, "default_branch", str))
        canonical_key = (
            f"github:repo:{installation_id}/{repository_id}"
            if installation_id is not None
            else f"github:repo:{repository_id}"
        )

        commit_result = self._client.get_json(
            f"{repo_path}/commits/{quote(default_branch, safe='')}"
        )
        commit_data = _require_data(commit_result, "commit")
        source_revision = str(_required(commit_data, "sha", str))
        _validate_object_id(source_revision, "commit SHA")
        tree = _required(_required(commit_data, "commit", dict), "tree", dict)
        tree_sha = str(_required(tree, "sha", str))
        _validate_object_id(tree_sha, "tree SHA")
        api_results = [repo_result, commit_result]

        if previous_revision == source_revision:
            return AcquisitionResult(
                status="UNCHANGED",
                repository_id=repository_id,
                canonical_key=canonical_key,
                full_name=full_name,
                visibility=str(repo_data.get(
                    "visibility", "private" if repo_data.get("private") else "public",
                )),
                archived=bool(repo_data.get("archived", False)),
                default_branch=default_branch,
                source_revision=source_revision,
                snapshot=None,
                output_path=None,
                stored_evidence=None,
                rate_limit_remaining=_latest_remaining(*api_results),
                rate_limit_limit=_latest_limit(*api_results),
                rate_limit_reset=_latest_reset(*api_results),
            )

        tree_result = self._client.get_json(
            f"{repo_path}/git/trees/{quote(tree_sha, safe='')}",
            query={"recursive": "1"},
        )
        api_results.append(tree_result)
        tree_data = _require_data(tree_result, "tree")
        entries = _required(tree_data, "tree", list)
        diagnostics: list[Diagnostic] = []
        completeness = "COMPLETE"
        if tree_data.get("truncated") is True:
            completeness = "PARTIAL"
            diagnostics.append(
                Diagnostic(
                    "WARNING",
                    "GITHUB_TREE_TRUNCATED",
                    "GitHub truncated the recursive tree; discovered files are incomplete",
                )
            )

        candidates = sorted(
            _manifest_candidates(entries, diagnostics),
            key=lambda item: item["path"],
        )
        if diagnostics:
            completeness = "PARTIAL"
        files: list[SnapshotFile] = []
        bytes_retrieved = 0
        for candidate in candidates:
            path = candidate["path"]
            size = candidate["size"]
            if len(files) >= limits.max_files:
                completeness = "PARTIAL"
                diagnostics.append(
                    Diagnostic(
                        "WARNING",
                        "FILE_COUNT_LIMIT",
                        f"Skipped target file after reaching max_files={limits.max_files}",
                        path,
                    )
                )
                continue
            if size > limits.max_file_bytes:
                completeness = "PARTIAL"
                diagnostics.append(
                    Diagnostic(
                        "WARNING",
                        "FILE_SIZE_LIMIT",
                        f"Skipped target file larger than max_file_bytes={limits.max_file_bytes}",
                        path,
                    )
                )
                continue
            if bytes_retrieved + size > limits.max_bytes:
                completeness = "PARTIAL"
                diagnostics.append(
                    Diagnostic(
                        "WARNING",
                        "SNAPSHOT_BYTE_LIMIT",
                        f"Skipped target file after reaching max_bytes={limits.max_bytes}",
                        path,
                    )
                )
                continue

            blob_sha = candidate["sha"]
            blob_result = self._client.get_json(
                f"{repo_path}/git/blobs/{quote(blob_sha, safe='')}"
            )
            api_results.append(blob_result)
            blob = _require_data(blob_result, f"blob {blob_sha}")
            content = _decode_blob(blob, blob_sha, size)
            files.append(
                SnapshotFile(
                    path=path,
                    kind=manifest_kind(path) or "UNKNOWN",
                    git_blob_sha=blob_sha,
                    size_bytes=len(content),
                    content_sha256=f"sha256:{hashlib.sha256(content).hexdigest()}",
                    content=content,
                )
            )
            bytes_retrieved += len(content)

        observed_at = utc_now()
        commit_details = _required(commit_data, "commit", dict)
        committer = commit_details.get("committer")
        effective_at = (
            committer.get("date")
            if isinstance(committer, dict) and isinstance(committer.get("date"), str)
            else None
        )
        snapshot = RepositorySnapshot(
            repository_id=repository_id,
            repository_node_id=node_id,
            full_name=full_name,
            canonical_key=canonical_key,
            visibility=str(
                repo_data.get(
                    "visibility",
                    "private" if repo_data.get("private") else "public",
                )
            ),
            archived=bool(repo_data.get("archived", False)),
            default_branch=default_branch,
            source_revision=source_revision,
            tree_sha=tree_sha,
            observed_at=observed_at,
            effective_at=effective_at,
            completeness=completeness,
            files=tuple(files),
            diagnostics=tuple(diagnostics),
            repository_etag=repo_result.etag,
            rate_limit_remaining=_latest_remaining(*api_results),
            rate_limit_limit=_latest_limit(*api_results),
            rate_limit_reset=_latest_reset(*api_results),
            api_version=self._client.api_version,
            repository_api_uri=f"{self._client.base_url}{repo_path}",
            installation_id=installation_id,
        )
        stored_evidence = (
            _store_snapshot(snapshot, evidence_store, tenant_key)
            if evidence_store is not None
            else None
        )
        output_path = (
            materialize_snapshot(
                snapshot,
                output_root,
                tenant_key,
                stored_evidence=stored_evidence,
            )
            if output_root is not None
            else None
        )
        return AcquisitionResult(
            status="CHANGED",
            repository_id=repository_id,
            canonical_key=canonical_key,
            full_name=full_name,
            visibility=snapshot.visibility,
            archived=snapshot.archived,
            default_branch=snapshot.default_branch,
            source_revision=source_revision,
            snapshot=snapshot,
            output_path=output_path,
            stored_evidence=stored_evidence,
            rate_limit_remaining=snapshot.rate_limit_remaining,
            rate_limit_limit=snapshot.rate_limit_limit,
            rate_limit_reset=snapshot.rate_limit_reset,
        )


def parse_repository(value: str) -> tuple[str, str]:
    parts = value.split("/")
    if (
        len(parts) != 2
        or not all(REPOSITORY_PART.fullmatch(part) for part in parts)
        or any(part in {".", ".."} for part in parts)
        or parts[1].endswith(".git")
    ):
        raise ValueError("repository must use the owner/name form")
    return parts[0], parts[1]


def manifest_kind(path: str) -> str | None:
    pure_path = _safe_repo_path(path)
    name = pure_path.name
    if name in EXACT_MANIFEST_NAMES:
        return EXACT_MANIFEST_NAMES[name]
    lower_name = name.lower()
    lowered_parts = tuple(part.lower() for part in pure_path.parts)
    if lower_name == "codeowners":
        return "REPOSITORY_GOVERNANCE"
    if (
        (lower_name == "license" or lower_name.startswith("license.")
         or lower_name == "copying" or lower_name.startswith("copying."))
        and pure_path.suffix.lower() in README_SUFFIXES
    ):
        return "REPOSITORY_GOVERNANCE"
    if (
        lower_name in {
            ".gitlab-ci.yml", ".gitlab-ci.yaml", "azure-pipelines.yml",
            "azure-pipelines.yaml", "bitbucket-pipelines.yml",
            "bitbucket-pipelines.yaml",
        }
        or (lowered_parts[:1] == (".circleci",) and lower_name in {"config.yml", "config.yaml"})
    ):
        return "CI_CONFIGURATION"
    if re.fullmatch(
        r"(?:jest|vitest|playwright|cypress)\.config\.(?:js|jsx|mjs|cjs|ts|tsx|mts|cts)",
        lower_name,
    ):
        return "TEST_CONFIGURATION"
    if lower_name == "dockerfile" or lower_name.startswith("dockerfile."):
        return "DEPLOYMENT_CONFIG"
    if COMPOSE_FILE.fullmatch(lower_name):
        return "DEPLOYMENT_CONFIG"
    if (
        (lower_name.startswith(".env.") or lower_name.startswith("env."))
        and lower_name.endswith((".example", ".sample", ".template"))
    ):
        return "CONFIG_TEMPLATE"
    if lower_name in {
        "application.yml", "application.yaml", "application.properties",
        "appsettings.json", "config.yml", "config.yaml", "config.json", "config.toml",
    }:
        return "APPLICATION_CONFIG"
    if (
        (lower_name == "readme" or lower_name.startswith("readme."))
        and pure_path.suffix.lower() in README_SUFFIXES
    ):
        return "REPOSITORY_DOCUMENTATION"
    if lower_name == "requirements.txt" or (
        lower_name.startswith("requirements-") and lower_name.endswith(".txt")
    ):
        return "PYTHON_REQUIREMENTS"
    if len(pure_path.parts) >= 2 and pure_path.parts[-2].lower() == "requirements":
        if lower_name.endswith(".txt"):
            return "PYTHON_REQUIREMENTS"
    if pure_path.suffix.lower() in SOURCE_SUFFIXES:
        return SOURCE_SUFFIXES[pure_path.suffix.lower()]
    if pure_path.suffix.lower() == ".tf":
        return "INFRASTRUCTURE_CONFIG"
    if pure_path.suffix.lower() in {".yaml", ".yml", ".toml", ".json", ".properties"} and any(
        part in {".github", "workflows", "deploy", "deployment", "k8s", "kubernetes", "config"}
        for part in lowered_parts
    ):
        return "BUILD_OR_DEPLOYMENT_CONFIG"
    return None


def materialize_snapshot(
    snapshot: RepositorySnapshot,
    output_root: Path,
    tenant_key: str | None,
    *,
    stored_evidence: StoredEvidence | None = None,
) -> Path:
    root = output_root.resolve()
    repository_root = root / f"github-repo-{snapshot.repository_id}"
    repository_root.mkdir(parents=True, exist_ok=True)
    repository_root = repository_root.resolve()
    if not repository_root.is_relative_to(root):
        raise ValueError("snapshot repository directory escapes output root")
    revision_root = repository_root / snapshot.source_revision
    revision_root.mkdir(exist_ok=True)
    destination = revision_root / _adapter_cache_key(ADAPTER_VERSION)
    if destination.exists():
        return _validate_existing_snapshot(destination, snapshot.source_revision)

    temporary = repository_root / f".{snapshot.source_revision}.{uuid.uuid4().hex}.tmp"
    files_root = temporary / "files"
    temporary.mkdir()
    files_root.mkdir()
    try:
        for item in snapshot.files:
            relative = _safe_repo_path(item.path)
            target = files_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content)

        _write_json(temporary / "snapshot.json", snapshot.as_dict())
        _write_json(
            temporary / "raw-observation.json",
            snapshot.raw_observation(tenant_key, stored_evidence),
        )
        try:
            temporary.replace(destination)
        except OSError:
            if destination.exists():
                shutil.rmtree(temporary, ignore_errors=True)
                return _validate_existing_snapshot(destination, snapshot.source_revision)
            raise
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def materialized_snapshot_path(
    output_root: Path,
    repository_id: str,
    source_revision: str,
    *,
    adapter_version: str = ADAPTER_VERSION,
) -> Path:
    """Return the adapter-scoped location for a materialized repository snapshot."""
    return (
        output_root.resolve()
        / f"github-repo-{repository_id}"
        / source_revision
        / _adapter_cache_key(adapter_version)
    )


def _adapter_cache_key(adapter_version: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", adapter_version).strip("-")


def _validate_existing_snapshot(destination: Path, source_revision: str) -> Path:
    existing = destination / "snapshot.json"
    if not existing.is_file():
        raise FileExistsError(f"snapshot destination is incomplete: {destination}")
    document = json.loads(existing.read_text(encoding="utf-8"))
    if document.get("source_revision") != source_revision:
        raise FileExistsError(f"snapshot destination has conflicting content: {destination}")
    return destination


def _manifest_candidates(
    entries: Iterable[object],
    diagnostics: list[Diagnostic],
) -> Iterable[dict[str, Any]]:
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = entry.get("path")
        sha = entry.get("sha")
        size = entry.get("size")
        if not isinstance(path, str) or manifest_kind_or_none(path) is None:
            continue
        try:
            _safe_repo_path(path)
        except ValueError:
            diagnostics.append(
                Diagnostic(
                    "WARNING",
                    "UNSAFE_REPOSITORY_PATH",
                    "Skipped a target file with an unsafe repository path",
                    path,
                )
            )
            continue
        if not isinstance(sha, str) or not GIT_OBJECT_ID.fullmatch(sha):
            diagnostics.append(
                Diagnostic(
                    "WARNING",
                    "INVALID_BLOB_ID",
                    "Skipped a target file with an invalid Git blob identifier",
                    path,
                )
            )
            continue
        if not isinstance(size, int) or size < 0:
            diagnostics.append(
                Diagnostic(
                    "WARNING",
                    "MISSING_BLOB_SIZE",
                    "Skipped a target file without a safe declared size",
                    path,
                )
            )
            continue
        yield {"path": path, "sha": sha, "size": size}


def manifest_kind_or_none(path: str) -> str | None:
    try:
        return manifest_kind(path)
    except ValueError:
        name = PurePosixPath(path).name
        if (
            name in EXACT_MANIFEST_NAMES
            or name.lower() == "readme"
            or name.lower().startswith("readme.")
            or name.lower().startswith("requirements")
            or name.lower() == "dockerfile"
            or name.lower().startswith("dockerfile.")
            or COMPOSE_FILE.fullmatch(name.lower()) is not None
            or (
                (name.lower().startswith(".env.") or name.lower().startswith("env."))
                and name.lower().endswith((".example", ".sample", ".template"))
            )
            or name.lower() in {
                "application.yml", "application.yaml", "application.properties",
                "appsettings.json", "config.yml", "config.yaml", "config.json", "config.toml",
            }
            or PurePosixPath(name).suffix.lower() in SOURCE_SUFFIXES
        ):
            return "UNSAFE_TARGET"
        return None


def _safe_repo_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError("repository path must be relative POSIX path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("repository path contains unsafe segments")
    return path


def _decode_blob(blob: JsonObject, expected_sha: str, expected_size: int) -> bytes:
    if blob.get("sha") != expected_sha:
        raise ValueError(f"GitHub blob SHA mismatch for {expected_sha}")
    if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
        raise ValueError(f"GitHub blob {expected_sha} is not base64 encoded")
    try:
        encoded = "".join(blob["content"].split())
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"GitHub blob {expected_sha} has invalid base64 content") from error
    if len(content) != expected_size or blob.get("size") != expected_size:
        raise ValueError(f"GitHub blob size mismatch for {expected_sha}")
    return content


def _required(document: JsonObject, key: str, expected_type: type | tuple[type, ...]) -> Any:
    value = document.get(key)
    if not isinstance(value, expected_type):
        raise ValueError(f"GitHub response is missing valid {key}")
    return value


def _require_data(result: ApiResult, label: str) -> JsonObject:
    if result.data is None:
        raise ValueError(f"GitHub returned no {label} data")
    return result.data


def _validate_object_id(value: str, label: str) -> None:
    if not GIT_OBJECT_ID.fullmatch(value):
        raise ValueError(f"GitHub response contains an invalid {label}")


def _latest_remaining(*results: ApiResult) -> int | None:
    values = [item.rate_limit_remaining for item in results]
    return next((value for value in reversed(values) if value is not None), None)


def _latest_limit(*results: ApiResult) -> int | None:
    values = [item.rate_limit_limit for item in results]
    return next((value for value in reversed(values) if value is not None), None)


def _latest_reset(*results: ApiResult) -> int | None:
    values = [item.rate_limit_reset for item in results]
    return next((value for value in reversed(values) if value is not None), None)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _store_snapshot(
    snapshot: RepositorySnapshot,
    evidence_store: EvidenceStore,
    tenant_key: str | None,
) -> StoredEvidence:
    if tenant_key is None:
        raise ValueError("tenant_key is required when durable evidence storage is enabled")
    entries = {"snapshot.json": _canonical_json(snapshot.as_dict())}
    entries.update({f"files/{item.path}": item.content for item in snapshot.files})
    content = deterministic_tar(entries)
    return evidence_store.put_bytes(
        tenant_key,
        content,
        media_type="application/vnd.stackgraph.repository-snapshot+tar",
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire a bounded GitHub dependency-manifest snapshot"
    )
    parser.add_argument("repository", help="GitHub repository in owner/name form")
    parser.add_argument("--output-dir", type=Path, required=True)
    evidence_root = os.environ.get("STACKGRAPH_EVIDENCE_STORE_ROOT")
    parser.add_argument(
        "--evidence-store-root",
        type=Path,
        default=Path(evidence_root) if evidence_root else None,
    )
    parser.add_argument("--tenant-key")
    parser.add_argument("--installation-id")
    parser.add_argument("--previous-revision")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--api-version", default="2026-03-10")
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--max-file-bytes", type=int, default=2 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get(args.token_env)
    client = GitHubClient(token=token, api_version=args.api_version)
    acquirer = GitHubRepositoryAcquirer(client)
    evidence_store = (
        LocalEvidenceStore(args.evidence_store_root)
        if args.evidence_store_root is not None
        else None
    )
    try:
        result = acquirer.acquire(
            args.repository,
            previous_revision=args.previous_revision,
            installation_id=args.installation_id,
            output_root=args.output_dir,
            tenant_key=args.tenant_key,
            evidence_store=evidence_store,
            limits=SnapshotLimits(
                max_files=args.max_files,
                max_bytes=args.max_bytes,
                max_file_bytes=args.max_file_bytes,
            ),
        )
    except GitHubApiError as error:
        print(json.dumps(_github_error_summary(error), sort_keys=True), file=sys.stderr)
        return 75 if error.retriable else 1
    except GitHubTransportError as error:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_class": "GITHUB_TRANSPORT",
                    "error": str(error),
                    "retriable": True,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 75
    except (RuntimeError, ValueError, OSError) as error:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_class": "ACQUISITION_INVALID",
                    "error": str(error),
                    "retriable": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result.summary(), sort_keys=True))
    return 0


def _github_error_summary(error: GitHubApiError) -> JsonObject:
    value: JsonObject = {
        "status": "ERROR",
        "error_class": "GITHUB_PROVIDER",
        "error": str(error),
        "http_status": error.status_code,
        "retriable": error.retriable,
    }
    if error.retry_after_seconds is not None:
        value["retry_after_seconds"] = error.retry_after_seconds
    if error.rate_limit_reset is not None:
        value["rate_limit_reset"] = error.rate_limit_reset
    return value


if __name__ == "__main__":
    raise SystemExit(main())

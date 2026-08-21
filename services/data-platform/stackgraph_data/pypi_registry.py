from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from stackgraph_data.catalog import canonical_json, sha256_key
from stackgraph_data.depsdev import PackageVersionKey


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class HttpTransport(Protocol):
    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float,
    ) -> HttpResponse: ...


class UrlLibTransport:
    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float,
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    response.status, dict(response.headers.items()), response.read(), response.geturl(),
                )
        except HTTPError as error:
            return HttpResponse(
                error.code, dict(error.headers.items()) if error.headers else {},
                error.read(), error.geturl(),
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            raise PyPIRegistryTransportError(
                f"PyPI registry request failed: {getattr(error, 'reason', error)}"
            ) from error


class PyPIRegistryTransportError(RuntimeError):
    pass


class PyPIRegistryApiError(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int, retriable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class PyPIRegistryBundle:
    requested: PackageVersionKey
    registry_key: str
    registry_origin: str
    visibility: str
    document: JsonObject
    request_uri: str
    etag: str | None
    observed_at: str

    @property
    def source_revision(self) -> str:
        return self.etag or sha256_key(self.document)

    def raw_observation(self, tenant_key: str | None = None) -> JsonObject:
        content = canonical_json(self.document).encode("utf-8")
        envelope: JsonObject = {
            "observation_contract_version": "1.0.0",
            "idempotency_key": sha256_key(
                self.registry_key, self.requested.purl, self.source_revision, "pypi-registry/1.0.0",
            ),
            "source": {
                "key": self.registry_key,
                "kind": "PACKAGE_REGISTRY",
                "adapter_version": "1.0.0",
                "schema_version": "pypi-json-v1",
            },
            "target_key": f"registry:{self.registry_key}:{self.requested.purl}",
            "source_revision": self.source_revision,
            "observed_at": self.observed_at,
            "request": {"uri": self.request_uri},
            "content": {
                "hash": f"sha256:{hashlib.sha256(content).hexdigest()}",
                "media_type": "application/json",
                "size_bytes": len(content),
                "inline": self.document,
            },
        }
        if self.etag:
            envelope["request"]["etag"] = self.etag
        if tenant_key:
            envelope["tenant_key"] = tenant_key
        return envelope


@dataclass(frozen=True, slots=True)
class PyPIVersionMetadata:
    key: PackageVersionKey
    registry_key: str
    registry_origin: str
    visibility: str
    summary: str | None
    license: str | None
    classifiers: tuple[str, ...]
    requires_python: str | None
    requires_dist: tuple[str, ...]
    project_urls: Mapping[str, str]
    home_page: str | None
    author: str | None
    yanked: bool
    yanked_reason: str | None
    published_at: str | None
    artifact_uri: str | None
    artifact_type: str | None
    artifact_size: int | None
    hashes: Mapping[str, str]
    source_revision: str
    observed_at: str
    request_uri: str
    evidence_hash: str

    @property
    def properties(self) -> JsonObject:
        return {
            "record_kind": "pypi_registry_version_metadata",
            "ecosystem": "pypi",
            "package_name": self.key.name,
            "version": self.key.version,
            "registry_key": self.registry_key,
            "registry_origin": self.registry_origin,
            "visibility": self.visibility,
            "summary": self.summary,
            "license": self.license,
            "classifiers": list(self.classifiers),
            "requires_python": self.requires_python,
            "requires_dist": list(self.requires_dist),
            "project_urls": dict(self.project_urls),
            "home_page": self.home_page,
            "author": self.author,
            "yanked": self.yanked,
            "yanked_reason": self.yanked_reason,
            "published_at": self.published_at,
            "artifact": {
                "uri": self.artifact_uri,
                "type": self.artifact_type,
                "size": self.artifact_size,
                "hashes": dict(self.hashes),
            },
        }

    @property
    def logical_key(self) -> str:
        return sha256_key(
            self.registry_origin, self.key.purl, "HAS_PROPERTY", "pypi-registry-version-metadata",
        )


class PyPIRegistryClient:
    def __init__(
        self, *, registry_key: str = "pypi-public",
        registry_origin: str = "https://pypi.org/", visibility: str = "PUBLIC",
        token: str | None = None, timeout_seconds: float = 20.0,
        max_response_bytes: int = 16 * 1024 * 1024,
        transport: HttpTransport | None = None,
    ) -> None:
        self.registry_origin = _normalize_origin(registry_origin)
        if not registry_key.strip():
            raise ValueError("registry_key must not be empty")
        if visibility not in {"PUBLIC", "PRIVATE", "UNKNOWN"}:
            raise ValueError("registry visibility is invalid")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("PyPI registry client limits must be positive")
        self.registry_key = registry_key.strip()
        self.visibility = visibility
        self._token = token
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrlLibTransport()

    def fetch(
        self, target: PackageVersionKey, *, etag: str | None = None,
    ) -> PyPIRegistryBundle | None:
        if target.system != "PYPI":
            raise ValueError("PyPI registry client only accepts PyPI purls")
        request_uri = (
            f"{self.registry_origin}pypi/{quote(target.name, safe='')}/"
            f"{quote(target.version, safe='.-_~+')}/json"
        )
        headers = {"Accept": "application/json", "User-Agent": "StackGraph-pypi-registry/1.0"}
        if etag:
            headers["If-None-Match"] = etag
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = self.transport.request(request_uri, headers, self.timeout_seconds)
        _assert_same_registry(response.final_url, self.registry_origin)
        normalized_headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status == 304:
            return None
        if response.status < 200 or response.status >= 300:
            raise PyPIRegistryApiError(
                f"PyPI registry request failed with status {response.status}",
                status_code=response.status,
                retriable=response.status == 429 or response.status >= 500,
                retry_after_seconds=_optional_int(normalized_headers.get("retry-after")),
            )
        if len(response.body) > self.max_response_bytes:
            raise ValueError("PyPI registry response exceeds max_response_bytes")
        try:
            document = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("PyPI registry returned invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("PyPI registry returned an unexpected JSON document")
        return PyPIRegistryBundle(
            requested=target, registry_key=self.registry_key,
            registry_origin=self.registry_origin, visibility=self.visibility,
            document=document, request_uri=request_uri,
            etag=normalized_headers.get("etag"),
            observed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )


def normalize_version(bundle: PyPIRegistryBundle) -> PyPIVersionMetadata:
    info = bundle.document.get("info")
    urls = bundle.document.get("urls")
    if not isinstance(info, dict) or not isinstance(urls, list):
        raise ValueError("PyPI response is missing version metadata")
    name = info.get("name")
    version = info.get("version")
    if not isinstance(name, str) or PackageVersionKey.from_version_key({
        "system": "PYPI", "name": name, "version": str(version or ""),
    }) != bundle.requested:
        raise ValueError("PyPI package identity does not match request")
    artifacts = [item for item in urls if isinstance(item, dict)]
    artifact = next((item for item in artifacts if item.get("packagetype") == "sdist"), None)
    artifact = artifact or (artifacts[0] if artifacts else {})
    artifact_uri = _safe_artifact_uri(artifact.get("url"))
    project_urls = info.get("project_urls")
    hashes = artifact.get("digests")
    return PyPIVersionMetadata(
        key=bundle.requested, registry_key=bundle.registry_key,
        registry_origin=bundle.registry_origin, visibility=bundle.visibility,
        summary=_optional_string(info.get("summary")),
        license=_optional_string(info.get("license")),
        classifiers=_string_tuple(info.get("classifiers")),
        requires_python=_optional_string(info.get("requires_python")),
        requires_dist=_string_tuple(info.get("requires_dist")),
        project_urls={
            str(key): value for key, value in project_urls.items()
            if isinstance(value, str)
        } if isinstance(project_urls, dict) else {},
        home_page=_safe_page_uri(info.get("home_page")),
        author=_optional_string(info.get("author")),
        yanked=artifact.get("yanked") is True,
        yanked_reason=_optional_string(artifact.get("yanked_reason")),
        published_at=_optional_string(artifact.get("upload_time_iso_8601") or artifact.get("upload_time")),
        artifact_uri=artifact_uri,
        artifact_type=_optional_string(artifact.get("packagetype")),
        artifact_size=artifact.get("size") if isinstance(artifact.get("size"), int) else None,
        hashes={
            str(key): value for key, value in hashes.items() if isinstance(value, str)
        } if isinstance(hashes, dict) else {},
        source_revision=bundle.source_revision, observed_at=bundle.observed_at,
        request_uri=bundle.request_uri, evidence_hash=sha256_key({"info": info, "artifact": artifact}),
    )


def _normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment
    ):
        raise ValueError("registry origin must be credential-free HTTPS")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/") + "/", "", ""))


def _assert_same_registry(final_url: str, registry_origin: str) -> None:
    final = urlsplit(final_url)
    registry = urlsplit(registry_origin)
    if (
        final.scheme != registry.scheme or final.netloc.lower() != registry.netloc.lower()
        or not final.path.startswith(registry.path) or final.username or final.password
    ):
        raise ValueError("PyPI registry redirect left the configured origin")


def _safe_artifact_uri(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.fragment
    ):
        raise ValueError("PyPI artifact URI must be credential-free HTTPS")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _safe_page_uri(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None

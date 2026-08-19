from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from stackgraph_data.catalog import canonical_json, sha256_key
from stackgraph_data.depsdev import PackageVersionKey


JsonObject = dict[str, Any]
INSTALL_V1 = "application/vnd.npm.install-v1+json"


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class HttpTransport(Protocol):
    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse: ...


class UrlLibTransport:
    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    response.status,
                    dict(response.headers.items()),
                    response.read(),
                    response.geturl(),
                )
        except HTTPError as error:
            return HttpResponse(
                error.code,
                dict(error.headers.items()) if error.headers else {},
                error.read(),
                error.geturl(),
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            reason = getattr(error, "reason", error)
            raise NpmRegistryTransportError(
                f"npm registry request failed: {reason}"
            ) from error


class NpmRegistryTransportError(RuntimeError):
    pass


class NpmRegistryApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retriable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class NpmRegistryBundle:
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
        target_key = f"registry:{self.registry_key}:{self.requested.purl}"
        envelope: JsonObject = {
            "observation_contract_version": "1.0.0",
            "idempotency_key": sha256_key(
                self.registry_key,
                self.requested.purl,
                self.source_revision,
                "npm-registry/1.0.0",
            ),
            "source": {
                "key": self.registry_key,
                "kind": "PACKAGE_REGISTRY",
                "adapter_version": "1.0.0",
                "schema_version": "npm-install-v1",
            },
            "target_key": target_key,
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
        if self.etag is not None:
            envelope["request"]["etag"] = self.etag
        if tenant_key is not None:
            envelope["tenant_key"] = tenant_key
        return envelope


@dataclass(frozen=True, slots=True)
class NpmVersionMetadata:
    key: PackageVersionKey
    registry_key: str
    registry_origin: str
    visibility: str
    dist_tags: Mapping[str, str]
    deprecated: str | None
    license: object
    engines: Mapping[str, str]
    repository: object
    published_at: str | None
    tarball_uri: str | None
    integrity: str | None
    shasum: str | None
    source_revision: str
    observed_at: str
    request_uri: str
    evidence_hash: str

    @property
    def properties(self) -> JsonObject:
        return {
            "record_kind": "npm_registry_version_metadata",
            "ecosystem": "npm",
            "package_name": self.key.name,
            "version": self.key.version,
            "registry_key": self.registry_key,
            "registry_origin": self.registry_origin,
            "visibility": self.visibility,
            "dist_tags": dict(self.dist_tags),
            "deprecated": self.deprecated,
            "license": self.license,
            "engines": dict(self.engines),
            "repository": self.repository,
            "published_at": self.published_at,
            "dist": {
                "tarball": self.tarball_uri,
                "integrity": self.integrity,
                "shasum": self.shasum,
            },
        }

    @property
    def logical_key(self) -> str:
        return sha256_key(
            self.registry_origin,
            self.key.purl,
            "HAS_PROPERTY",
            "npm-registry-version-metadata",
        )


class NpmRegistryClient:
    def __init__(
        self,
        *,
        registry_key: str = "npm-public",
        registry_origin: str = "https://registry.npmjs.org/",
        visibility: str = "PUBLIC",
        token: str | None = None,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 16 * 1024 * 1024,
        transport: HttpTransport | None = None,
    ) -> None:
        self.registry_origin = _normalize_origin(registry_origin)
        if not registry_key.strip():
            raise ValueError("registry_key must not be empty")
        if visibility not in {"PUBLIC", "PRIVATE", "UNKNOWN"}:
            raise ValueError("registry visibility is invalid")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("npm registry client limits must be positive")
        self.registry_key = registry_key.strip()
        self.visibility = visibility
        self._token = token
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrlLibTransport()

    def fetch(
        self, target: PackageVersionKey, *, etag: str | None = None
    ) -> NpmRegistryBundle | None:
        if target.system != "NPM":
            raise ValueError("npm registry client only accepts npm purls")
        request_uri = f"{self.registry_origin}{quote(target.name, safe='')}"
        headers = {
            "Accept": INSTALL_V1,
            "User-Agent": "StackGraph-npm-registry/1.0",
        }
        if etag:
            headers["If-None-Match"] = etag
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = self.transport.request(
            request_uri, headers, self.timeout_seconds
        )
        _assert_same_registry(response.final_url, self.registry_origin)
        normalized_headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status == 304:
            return None
        if response.status < 200 or response.status >= 300:
            retry_after = _optional_int(normalized_headers.get("retry-after"))
            raise NpmRegistryApiError(
                f"npm registry request failed with status {response.status}",
                status_code=response.status,
                retriable=response.status == 429 or response.status >= 500,
                retry_after_seconds=retry_after,
            )
        if len(response.body) > self.max_response_bytes:
            raise ValueError("npm registry response exceeds max_response_bytes")
        try:
            document = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("npm registry returned invalid JSON") from error
        if not isinstance(document, dict):
            raise ValueError("npm registry returned an unexpected JSON document")
        return NpmRegistryBundle(
            requested=target,
            registry_key=self.registry_key,
            registry_origin=self.registry_origin,
            visibility=self.visibility,
            document=document,
            request_uri=request_uri,
            etag=normalized_headers.get("etag"),
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )


def normalize_version(bundle: NpmRegistryBundle) -> NpmVersionMetadata:
    package_name = bundle.document.get("name")
    if not isinstance(package_name, str) or package_name.lower() != bundle.requested.name:
        raise ValueError("npm registry package identity does not match request")
    versions = bundle.document.get("versions")
    if not isinstance(versions, dict):
        raise ValueError("npm registry packument has no versions")
    raw_version = versions.get(bundle.requested.version)
    if not isinstance(raw_version, dict):
        raise ValueError("npm registry packument does not contain requested version")
    if raw_version.get("name", package_name).lower() != bundle.requested.name:
        raise ValueError("npm registry version package identity does not match request")
    if raw_version.get("version") != bundle.requested.version:
        raise ValueError("npm registry version identity does not match request")
    dist = raw_version.get("dist") if isinstance(raw_version.get("dist"), dict) else {}
    tarball = _safe_artifact_uri(dist.get("tarball"))
    dist_tags = bundle.document.get("dist-tags")
    time = bundle.document.get("time")
    return NpmVersionMetadata(
        key=bundle.requested,
        registry_key=bundle.registry_key,
        registry_origin=bundle.registry_origin,
        visibility=bundle.visibility,
        dist_tags={
            key: value
            for key, value in dist_tags.items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(dist_tags, dict)
        else {},
        deprecated=raw_version.get("deprecated")
        if isinstance(raw_version.get("deprecated"), str)
        else None,
        license=raw_version.get("license"),
        engines={
            key: value
            for key, value in raw_version.get("engines", {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(raw_version.get("engines"), dict)
        else {},
        repository=raw_version.get("repository"),
        published_at=time.get(bundle.requested.version)
        if isinstance(time, dict) and isinstance(time.get(bundle.requested.version), str)
        else None,
        tarball_uri=tarball,
        integrity=dist.get("integrity") if isinstance(dist.get("integrity"), str) else None,
        shasum=dist.get("shasum") if isinstance(dist.get("shasum"), str) else None,
        source_revision=bundle.source_revision,
        observed_at=bundle.observed_at,
        request_uri=bundle.request_uri,
        evidence_hash=sha256_key(raw_version),
    )


def _normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("registry origin must be credential-free HTTPS")
    path = parsed.path.rstrip("/") + "/"
    return urlunsplit(("https", parsed.netloc.lower(), path, "", ""))


def _assert_same_registry(final_url: str, registry_origin: str) -> None:
    final = urlsplit(final_url)
    registry = urlsplit(registry_origin)
    if (
        final.scheme != registry.scheme
        or final.netloc.lower() != registry.netloc.lower()
        or not final.path.startswith(registry.path)
        or final.username
        or final.password
    ):
        raise ValueError("npm registry redirect left the configured origin")


def _safe_artifact_uri(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("npm tarball URI must be credential-free HTTPS")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit


PUBLIC_NPM_ORIGIN = "https://registry.npmjs.org/"
NPM_SCOPE = re.compile(r"^@[a-z0-9._~-]+$")
NPM_UNSCOPED_NAME = re.compile(r"^[a-z0-9._~-]+$")
SECRET_KEY_MARKERS = (
    "_auth",
    "_authtoken",
    "password",
    "username",
    "certfile",
    "keyfile",
)


@dataclass(frozen=True, slots=True)
class NpmConfig:
    default_registry: str
    scoped_registries: Mapping[str, str]
    credential_keys: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NpmDependencyResolution:
    package_name: str
    requested_spec: str
    resolved_version: str
    registry_origin: str
    resolution_source: str
    package_scope: str | None
    config_path: str | None
    custom_registry: bool
    lockfile_behavior: str
    visibility: str
    resolved_uri: str | None
    integrity: str | None

    @property
    def registry_key(self) -> str:
        if self.registry_origin == PUBLIC_NPM_ORIGIN:
            return "npm-public"
        digest = hashlib.sha256(self.registry_origin.encode("utf-8")).hexdigest()[:16]
        return f"npm-{digest}"

    @property
    def package_purl(self) -> str:
        return f"pkg:npm/{quote(self.package_name, safe='/')}"

    @property
    def version_purl(self) -> str:
        version = quote(self.resolved_version, safe=".-_~+")
        return f"{self.package_purl}@{version}"

    @property
    def canonical_key(self) -> str:
        if self.visibility == "PUBLIC" and self.registry_origin == PUBLIC_NPM_ORIGIN:
            return self.version_purl
        return f"registry:{self.registry_key}:{self.version_purl}"

    def fact_properties(
        self, *, dependency_scope: str, direct: bool
    ) -> dict[str, Any]:
        value: dict[str, Any] = {
            "scope": dependency_scope,
            "direct": direct,
            "requested_spec": self.requested_spec,
            "resolved_version": self.resolved_version,
            "registry_resolution": {
                "origin": self.registry_origin,
                "source": self.resolution_source,
                "scope": self.package_scope,
                "config_path": self.config_path,
                "custom_registry": self.custom_registry,
                "lockfile_behavior": self.lockfile_behavior,
                "visibility": self.visibility,
            },
        }
        if self.resolved_uri is not None or self.integrity is not None:
            value["artifact"] = {}
            if self.resolved_uri is not None:
                value["artifact"]["resolved_uri"] = self.resolved_uri
            if self.integrity is not None:
                value["artifact"]["integrity"] = self.integrity
        return value


def parse_npmrc(
    content: str,
    *,
    config_path: str = ".npmrc",
    allow_insecure_localhost: bool = False,
) -> NpmConfig:
    default_registry = PUBLIC_NPM_ORIGIN
    scopes: dict[str, str] = {}
    credential_keys: list[str] = []
    diagnostics: list[str] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            diagnostics.append(f"{config_path}:{line_number}: ignored malformed entry")
            continue
        key = key.strip()
        value = raw_value.strip()
        lowered = key.lower()
        if any(marker in lowered for marker in SECRET_KEY_MARKERS):
            credential_keys.append(key)
            continue
        if "${" in value:
            diagnostics.append(
                f"{config_path}:{line_number}: unresolved environment expression"
            )
            continue
        try:
            if lowered == "registry":
                default_registry = normalize_registry_origin(
                    value, allow_insecure_localhost=allow_insecure_localhost
                )
            elif lowered.endswith(":registry") and lowered.startswith("@"):
                scope = lowered[: -len(":registry")]
                if not NPM_SCOPE.fullmatch(scope):
                    raise ValueError("invalid npm scope")
                scopes[scope] = normalize_registry_origin(
                    value, allow_insecure_localhost=allow_insecure_localhost
                )
        except ValueError as error:
            diagnostics.append(f"{config_path}:{line_number}: {error}")
    return NpmConfig(
        default_registry=default_registry,
        scoped_registries=scopes,
        credential_keys=tuple(sorted(set(credential_keys))),
        diagnostics=tuple(diagnostics),
    )


def resolve_npm_dependency(
    package_name: str,
    *,
    requested_spec: str,
    resolved_version: str,
    npm_config: NpmConfig | None = None,
    config_path: str | None = None,
    resolved_uri: str | None = None,
    integrity: str | None = None,
    known_visibility: Mapping[str, str] | None = None,
) -> NpmDependencyResolution:
    normalized_name, scope = normalize_package_name(package_name)
    if not requested_spec.strip() or not resolved_version.strip():
        raise ValueError("requested_spec and resolved_version are required")
    config = npm_config or NpmConfig(PUBLIC_NPM_ORIGIN, {}, (), ())
    configured_origin = (
        config.scoped_registries.get(scope, config.default_registry)
        if scope is not None
        else config.default_registry
    )
    source = (
        "NPMRC_SCOPE"
        if scope is not None and scope in config.scoped_registries
        else "NPMRC_DEFAULT"
        if config.default_registry != PUBLIC_NPM_ORIGIN
        else "NPM_DEFAULT"
    )
    origin = configured_origin
    lockfile_behavior = "CONFIGURED_DEFAULT"
    sanitized_uri: str | None = None
    if resolved_uri is not None:
        sanitized_uri = normalize_artifact_uri(resolved_uri)
        if _uri_belongs_to_origin(sanitized_uri, configured_origin):
            source = "LOCKFILE"
            lockfile_behavior = (
                "CUSTOM_PINNED"
                if configured_origin != PUBLIC_NPM_ORIGIN
                else "CONFIGURED_DEFAULT"
            )
        elif _uri_belongs_to_origin(sanitized_uri, PUBLIC_NPM_ORIGIN):
            # npm rewrites lockfile URLs produced by the default public registry
            # to the registry selected by the active project configuration.
            lockfile_behavior = "CONFIGURED_DEFAULT"
        elif _is_explicit_uri_spec(requested_spec):
            source = "EXPLICIT_TARBALL"
            lockfile_behavior = "EXPLICIT_TARBALL"
            origin = _artifact_origin(sanitized_uri)
        else:
            # URLs written while a custom registry was active remain pinned even
            # when the current project configuration points somewhere else.
            source = "LOCKFILE"
            lockfile_behavior = "CUSTOM_PINNED"
            origin = _artifact_origin(sanitized_uri)
    visibility_by_origin = known_visibility or {}
    visibility = visibility_by_origin.get(origin)
    if visibility not in {"PUBLIC", "PRIVATE", "UNKNOWN"}:
        visibility = "PUBLIC" if origin == PUBLIC_NPM_ORIGIN else "UNKNOWN"
    return NpmDependencyResolution(
        package_name=normalized_name,
        requested_spec=requested_spec.strip(),
        resolved_version=resolved_version.strip(),
        registry_origin=origin,
        resolution_source=source,
        package_scope=scope,
        config_path=config_path if source.startswith("NPMRC") else None,
        custom_registry=origin != PUBLIC_NPM_ORIGIN,
        lockfile_behavior=lockfile_behavior,
        visibility=visibility,
        resolved_uri=sanitized_uri,
        integrity=integrity.strip() if isinstance(integrity, str) and integrity.strip() else None,
    )


def normalize_registry_origin(
    value: str, *, allow_insecure_localhost: bool = False
) -> str:
    parsed = urlsplit(value.strip())
    localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"https", "http"}
        or (parsed.scheme == "http" and not (allow_insecure_localhost and localhost))
    ):
        raise ValueError("registry origin must be credential-free HTTPS")
    path = parsed.path.rstrip("/") + "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def normalize_artifact_uri(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("resolved artifact URI must be credential-free HTTPS")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def normalize_package_name(value: str) -> tuple[str, str | None]:
    name = value.strip().lower()
    if name.startswith("@"):
        scope, separator, package = name.partition("/")
        if not separator or not NPM_SCOPE.fullmatch(scope) or not NPM_UNSCOPED_NAME.fullmatch(package):
            raise ValueError("scoped npm package must use @scope/name")
        return name, scope
    if not NPM_UNSCOPED_NAME.fullmatch(name):
        raise ValueError("invalid npm package name")
    return name, None


def _uri_belongs_to_origin(uri: str, origin: str) -> bool:
    artifact = urlsplit(uri)
    registry = urlsplit(origin)
    return (
        artifact.scheme == registry.scheme
        and artifact.netloc == registry.netloc
        and artifact.path.startswith(registry.path)
    )


def _artifact_origin(uri: str) -> str:
    parsed = urlsplit(uri)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _is_explicit_uri_spec(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme in {"https", "http"} and parsed.hostname is not None

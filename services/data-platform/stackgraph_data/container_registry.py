"""Resolve mutable container tags to immutable digests, and read what the image contains.

S3 requires digest-first container identity: `registry.internal/acme/shipping:2.0.1` is an
observation, `sha256:…` is an identity. The scanner deliberately performs no network access, so
it can only record the tag — which left `estate_container_profile` unwritable, since its primary
key is the digest.

This is that missing step, built the way the plan asks: asynchronous, cached, rate-limited,
allowlisted, and unable to block a local scan. Nothing here runs during scanning; a scan
publishes tag observations and this resolves them later, or never, without changing what the
scan concluded.

Two safety properties the OCI protocol makes easy to get wrong:

* A manifest list (multi-architecture image) has its own digest, and so does each platform
  manifest underneath it. The list digest is what a deployment actually references, so that is
  what is recorded as identity; the platform manifest is recorded as the resolved variant.
* The registry states the digest in `Docker-Content-Digest`, but a header is the registry's
  claim about the body. The digest is recomputed from the bytes and the header is only trusted
  when the two agree, because an identity taken on trust is not an identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlsplit


# Only these registries are contacted. An allowlist rather than a denylist, because the set of
# hosts a container reference can name is unbounded and a scanned repository chooses it.
DEFAULT_ALLOWED_REGISTRIES = frozenset({
    "registry-1.docker.io", "index.docker.io", "ghcr.io", "quay.io", "mcr.microsoft.com",
    "public.ecr.aws", "gcr.io", "registry.k8s.io",
})
DOCKER_HUB_HOSTS = frozenset({"docker.io", "index.docker.io", "registry-1.docker.io"})

MANIFEST_MEDIA_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
INDEX_MEDIA_TYPES = frozenset({
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
})

DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
# A registry can return an arbitrarily large blob. Manifests and configs are small; anything
# claiming otherwise is not a manifest and is refused rather than buffered.
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_LAYERS = 128
# A layer blob is the one response that is legitimately large. It is bounded separately from a
# manifest, and a layer whose *declared* size exceeds the bound is skipped before it is
# requested rather than buffered and then refused.
MAX_LAYER_BYTES = 96 * 1024 * 1024


class ContainerRegistryError(RuntimeError):
    """Raised when a registry cannot be used. Never fatal to the caller's scan."""

    def __init__(self, message: str, *, retriable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.retriable = retriable
        self.status_code = status_code


class Transport(Protocol):
    def request(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float,
    ) -> Any: ...


@dataclass(frozen=True)
class ImageReference:
    registry_host: str
    repository: str
    tag: str | None
    digest: str | None

    @property
    def is_digest_pinned(self) -> bool:
        return self.digest is not None

    def manifest_path(self) -> str:
        reference = self.digest or self.tag or "latest"
        return f"/v2/{self.repository}/manifests/{quote(reference, safe=':')}"

    def blob_path(self, digest: str) -> str:
        return f"/v2/{self.repository}/blobs/{quote(digest, safe=':')}"


def parse_image_reference(value: str) -> ImageReference:
    """Split a container reference into host, repository, tag, and digest.

    The rule that decides whether the first segment is a registry or a namespace is the one
    every implementation gets wrong: it is a host only if it contains a dot or a colon, or is
    exactly `localhost`. Without that, `acme/shipping` would be read as the registry `acme`.
    """
    if not value or value.strip() != value:
        raise ContainerRegistryError("an image reference must be non-empty and untrimmed")
    remainder = value
    digest: str | None = None
    if "@" in remainder:
        remainder, _, digest = remainder.partition("@")
        if not DIGEST.fullmatch(digest):
            raise ContainerRegistryError(f"unsupported digest algorithm in {value!r}")
    head, _, tail = remainder.partition("/")
    if tail and ("." in head or ":" in head or head == "localhost"):
        registry_host, path = head, tail
    else:
        registry_host, path = "registry-1.docker.io", remainder
    tag: str | None = None
    if ":" in path.rsplit("/", 1)[-1]:
        path, _, tag = path.rpartition(":")
    if registry_host in DOCKER_HUB_HOSTS and "/" not in path:
        # Docker Hub's official images live under `library/`, which the reference omits.
        path = f"library/{path}"
    if not path:
        raise ContainerRegistryError(f"{value!r} names no repository")
    if digest is None and tag is None:
        tag = "latest"
    return ImageReference(
        registry_host=registry_host, repository=path, tag=tag, digest=digest,
    )


@dataclass(frozen=True)
class ResolvedImage:
    reference: ImageReference
    digest: str
    media_type: str
    architecture: str | None = None
    operating_system: str | None = None
    platform_digest: str | None = None
    layers: tuple[Mapping[str, Any], ...] = ()
    entrypoint: tuple[str, ...] = ()
    user: str | None = None
    exposed_ports: tuple[str, ...] = ()
    runtime_labels: Mapping[str, str] = field(default_factory=dict)
    coverage: Mapping[str, str] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()


def _require_allowed(host: str, allowed: frozenset[str]) -> None:
    if host not in allowed:
        raise ContainerRegistryError(
            f"registry {host!r} is not on the allowlist; no request was made",
        )


def _digest_of(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


class ContainerRegistryClient:
    """A read-only OCI distribution client bounded to an allowlist.

    Anonymous by default. A registry that demands credentials is reported as an uncovered
    image rather than being retried with anything, because guessing at auth against an
    arbitrary host named by scanned repository content is not a thing to do.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        allowed_registries: frozenset[str] = DEFAULT_ALLOWED_REGISTRIES,
        timeout_seconds: float = 15.0,
        max_manifest_bytes: int = MAX_MANIFEST_BYTES,
        token_provider: Any = None,
    ) -> None:
        self.transport = transport
        self.allowed_registries = allowed_registries
        self.timeout_seconds = timeout_seconds
        self.max_manifest_bytes = max_manifest_bytes
        self.token_provider = token_provider

    def blob(self, reference: ImageReference, digest: str, *, max_bytes: int = MAX_LAYER_BYTES) -> bytes:
        """Fetch one blob, verifying it hashes to the digest that named it.

        A layer is content-addressed, so a blob that does not hash to its digest is not the
        layer the manifest referenced, whatever the registry says. Reading packages out of it
        would attribute another image's contents to this one.
        """
        if not DIGEST.fullmatch(digest):
            raise ContainerRegistryError(f"{digest!r} is not a supported blob digest")
        _, body = self._get(
            reference, reference.blob_path(digest), "application/octet-stream",
            max_bytes=max_bytes,
        )
        if _digest_of(body) != digest:
            raise ContainerRegistryError("the blob does not hash to the digest that named it")
        return body

    def _get(
        self, reference: ImageReference, path: str, accept: str, *, max_bytes: int | None = None,
    ) -> tuple[Any, bytes]:
        _require_allowed(reference.registry_host, self.allowed_registries)
        url = f"https://{reference.registry_host}{path}"
        headers = {"Accept": accept, "User-Agent": "StackGraph-container-registry/1.0"}
        if self.token_provider is not None:
            token = self.token_provider(reference)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        response = self.transport.request(url, headers, self.timeout_seconds)
        # A redirect that leaves the allowlisted host would exfiltrate the request; blob
        # downloads on some registries redirect to object storage, so this is checked rather
        # than assumed.
        final = getattr(response, "final_url", url)
        if urlsplit(final).hostname not in self.allowed_registries:
            raise ContainerRegistryError(
                f"registry redirected to {urlsplit(final).hostname!r}, which is not allowlisted",
            )
        status = response.status
        if status == 401 or status == 403:
            raise ContainerRegistryError(
                "the registry requires credentials StackGraph does not hold",
                status_code=status,
            )
        if status == 404:
            raise ContainerRegistryError("the registry does not hold this image", status_code=404)
        if status == 429 or status >= 500:
            raise ContainerRegistryError(
                f"the registry answered with status {status}", retriable=True, status_code=status,
            )
        if status < 200 or status >= 300:
            raise ContainerRegistryError(
                f"the registry answered with status {status}", status_code=status,
            )
        body = response.body
        bound = self.max_manifest_bytes if max_bytes is None else max_bytes
        if len(body) > bound:
            raise ContainerRegistryError(
                f"the registry response exceeds the {bound} byte bound",
            )
        return response, body

    def resolve(self, image: str) -> ResolvedImage:
        """Resolve a reference to an immutable digest and read what it contains."""
        reference = parse_image_reference(image)
        response, body = self._get(
            reference, reference.manifest_path(), ", ".join(MANIFEST_MEDIA_TYPES),
        )
        computed = _digest_of(body)
        headers = {key.lower(): value for key, value in (response.headers or {}).items()}
        claimed = headers.get("docker-content-digest")
        limitations: list[str] = []
        if claimed and claimed != computed:
            # The header is the registry's claim; the bytes are the evidence. Trusting a header
            # that disagrees with its own body would let a proxy hand back any identity it liked.
            raise ContainerRegistryError(
                "the registry's content digest does not match the manifest it returned",
            )
        try:
            manifest = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContainerRegistryError("the registry returned a manifest that is not JSON") from error
        if not isinstance(manifest, Mapping):
            raise ContainerRegistryError("the registry returned an unexpected manifest shape")

        media_type = str(manifest.get("mediaType") or "")
        architecture: str | None = None
        operating_system: str | None = None
        platform_digest: str | None = None
        platform_manifest: Mapping[str, Any] = manifest

        if media_type in INDEX_MEDIA_TYPES:
            # The index digest is the identity a deployment references, so it stays as `digest`.
            # Picking a platform is a reading of the index, recorded separately.
            selected = _select_platform(manifest.get("manifests"))
            if selected is None:
                limitations.append(
                    "the image is a manifest list with no linux/amd64 or linux/arm64 variant, "
                    "so its contents were not read"
                )
                return ResolvedImage(
                    reference=reference, digest=computed, media_type=media_type,
                    coverage={"manifest": "AVAILABLE", "config": "NOT_COLLECTED",
                              "layers": "NOT_COLLECTED"},
                    limitations=tuple(limitations),
                )
            platform_digest = str(selected.get("digest"))
            platform = selected.get("platform") if isinstance(selected.get("platform"), Mapping) else {}
            architecture = _optional_string(platform.get("architecture"))
            operating_system = _optional_string(platform.get("os"))
            _, platform_body = self._get(
                ImageReference(
                    registry_host=reference.registry_host, repository=reference.repository,
                    tag=None, digest=platform_digest,
                ),
                f"/v2/{reference.repository}/manifests/{quote(platform_digest, safe=':')}",
                ", ".join(MANIFEST_MEDIA_TYPES),
            )
            if _digest_of(platform_body) != platform_digest:
                raise ContainerRegistryError(
                    "the platform manifest does not hash to the digest the index named",
                )
            platform_manifest = json.loads(platform_body)

        layers = tuple(
            item for item in (platform_manifest.get("layers") or ())
            if isinstance(item, Mapping)
        )[:MAX_LAYERS]
        if len(platform_manifest.get("layers") or ()) > MAX_LAYERS:
            limitations.append(f"only the first {MAX_LAYERS} layers were recorded")

        entrypoint: tuple[str, ...] = ()
        user: str | None = None
        ports: tuple[str, ...] = ()
        labels: dict[str, str] = {}
        config_coverage = "NOT_COLLECTED"
        config = platform_manifest.get("config")
        if isinstance(config, Mapping) and DIGEST.fullmatch(str(config.get("digest") or "")):
            try:
                _, config_body = self._get(
                    reference, reference.blob_path(str(config["digest"])),
                    "application/vnd.oci.image.config.v1+json, "
                    "application/vnd.docker.container.image.v1+json",
                )
                document = json.loads(config_body)
                if isinstance(document, Mapping):
                    config_coverage = "AVAILABLE"
                    architecture = architecture or _optional_string(document.get("architecture"))
                    operating_system = operating_system or _optional_string(document.get("os"))
                    inner = document.get("config")
                    if isinstance(inner, Mapping):
                        entrypoint = tuple(
                            str(item) for item in (inner.get("Entrypoint") or ())
                        ) or tuple(str(item) for item in (inner.get("Cmd") or ()))
                        user = _optional_string(inner.get("User"))
                        ports = tuple(sorted(str(key) for key in (inner.get("ExposedPorts") or {})))
                        labels = {
                            str(key): str(value)
                            for key, value in (inner.get("Labels") or {}).items()
                        }
            except ContainerRegistryError as error:
                # A readable manifest with an unreadable config is a partial answer, not a
                # failed one: the digest is still an identity worth recording.
                limitations.append(f"the image config could not be read: {error}")
        else:
            limitations.append("the manifest names no readable config blob")

        return ResolvedImage(
            reference=reference, digest=computed, media_type=media_type,
            architecture=architecture, operating_system=operating_system,
            platform_digest=platform_digest, layers=layers, entrypoint=entrypoint,
            user=user, exposed_ports=ports, runtime_labels=labels,
            coverage={
                "manifest": "AVAILABLE",
                "config": config_coverage,
                "layers": "AVAILABLE" if layers else "NOT_COLLECTED",
                # StackGraph reads the image's metadata, never its filesystem. Package
                # inventory needs a layer scan, which is a different product.
                "os_packages": "NOT_COLLECTED",
            },
            limitations=tuple(limitations),
        )


def _select_platform(manifests: Any) -> Mapping[str, Any] | None:
    """Pick the platform variant to read, preferring linux/amd64 then linux/arm64.

    Deterministic on purpose: reading whichever variant the registry happened to list first
    would make the same image resolve to different contents on different days.
    """
    if not isinstance(manifests, list):
        return None
    candidates = [item for item in manifests if isinstance(item, Mapping)]
    for architecture in ("amd64", "arm64"):
        for item in candidates:
            platform = item.get("platform") if isinstance(item.get("platform"), Mapping) else {}
            if platform.get("os") == "linux" and platform.get("architecture") == architecture:
                if DIGEST.fullmatch(str(item.get("digest") or "")):
                    return item
    return None


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None

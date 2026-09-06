"""Read the packages installed inside a container image, from the layers themselves.

`estate_container_profile.coverage` has reported `os_packages: NOT_COLLECTED` since the profile
existed, and `estate_container_package` had no writer. That is an honest answer but a thin one:
an image's OS packages are exactly what a CVE lands in, and "we did not look" cannot be acted on.

Reading them means downloading layer blobs and opening them, which is the most expensive and
most dangerous thing StackGraph does over the network. Four bounds make it safe:

* a layer whose *declared* size exceeds the bound is skipped before it is requested, so nothing
  oversized is ever buffered;
* decompression is capped independently of the compressed size, because a gzip bomb's whole
  point is that those two numbers are unrelated;
* only files at known package-database paths are extracted, each under its own size bound, so a
  layer full of large files costs its download and nothing else;
* every bound that trips is reported as a limitation, so a partial read is never presented as a
  complete inventory.

What this deliberately does not do is parse an RPM database. It is a Berkeley DB, an ndb, or a
SQLite file depending on the distribution's age, and a wrong answer about which packages are
installed is worse than no answer. Its presence is detected and reported as uncollected.
"""

from __future__ import annotations

import io
import json
import posixpath
import re
import tarfile
import zlib
from dataclasses import dataclass
from typing import Mapping

from stackgraph_data.container_registry import (
    MAX_LAYER_BYTES,
    ContainerRegistryClient,
    ContainerRegistryError,
    ResolvedImage,
)


METHOD_VERSION = "container-packages/1.0.0"

# Bounds. Each one is a number somebody can argue with; what matters is that tripping one is
# reported rather than silently truncating the inventory.
MAX_LAYERS_READ = 24
MAX_TOTAL_LAYER_BYTES = 320 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TRACKED_FILES = 4000
MAX_PACKAGES = 5000

GZIP_MEDIA_TYPES = frozenset({
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
    "application/vnd.oci.image.layer.nondistributable.v1.tar+gzip",
})
UNCOMPRESSED_MEDIA_TYPES = frozenset({
    "application/vnd.oci.image.layer.v1.tar",
})

DPKG_STATUS = "var/lib/dpkg/status"
APK_INSTALLED = "lib/apk/db/installed"
RPM_DIRECTORY = "var/lib/rpm/"
_DIST_INFO = re.compile(r"(?:^|/)([^/]+)\.dist-info/METADATA$")
_EGG_INFO = re.compile(r"(?:^|/)([^/]+)\.egg-info/PKG-INFO$")
_NODE_PACKAGE = re.compile(r"(?:^|/)node_modules/((?:@[^/]+/)?[^/]+)/package\.json$")


@dataclass(frozen=True)
class ContainerPackageRecord:
    name: str
    version: str | None
    ecosystem: str
    purl: str | None = None


@dataclass
class PackageInventory:
    packages: tuple[ContainerPackageRecord, ...] = ()
    coverage: str = "NOT_COLLECTED"
    limitations: tuple[str, ...] = ()
    layers_read: int = 0
    layers_skipped: int = 0
    sources: tuple[str, ...] = ()


def _tracked(path: str) -> bool:
    return (
        path == DPKG_STATUS
        or path == APK_INSTALLED
        or path.startswith(RPM_DIRECTORY)
        or bool(_DIST_INFO.search(path))
        or bool(_EGG_INFO.search(path))
        or bool(_NODE_PACKAGE.search(path))
    )


def _normalise(name: str) -> str:
    """Normalise a tar member name to a rootfs-absolute path without a leading slash."""
    cleaned = name.lstrip("./")
    return posixpath.normpath(cleaned).lstrip("/") if cleaned else ""


def _gunzip_bounded(body: bytes, limit: int) -> tuple[bytes, bool]:
    """Decompress a gzip member, stopping at `limit` bytes.

    Returns the bytes and whether the limit was reached. A compressed layer says nothing about
    how large it expands to, so this cannot be bounded by the download size.
    """
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    output = bytearray()
    view = memoryview(body)
    chunk = 1024 * 1024
    for start in range(0, len(view), chunk):
        output.extend(decompressor.decompress(bytes(view[start:start + chunk]), limit - len(output)))
        if len(output) >= limit:
            return bytes(output), True
        if decompressor.eof:
            break
    output.extend(decompressor.flush())
    return bytes(output[:limit]), len(output) > limit


def _read_layer(
    body: bytes, files: dict[str, bytes], limitations: list[str],
) -> None:
    """Extract tracked files from one layer tar, honouring whiteouts.

    A later layer replaces what an earlier one wrote, and a `.wh.` entry deletes it. Ignoring
    whiteouts would report packages an image no longer contains, which is worse than reporting
    none: it would be a specific, confident, wrong answer.
    """
    try:
        archive = tarfile.open(fileobj=io.BytesIO(body), mode="r|")
    except tarfile.TarError:
        limitations.append("a layer could not be opened as a tar archive")
        return
    try:
        for member in archive:
            name = _normalise(member.name)
            if not name:
                continue
            base = posixpath.basename(name)
            if base.startswith(".wh."):
                directory = posixpath.dirname(name)
                if base == ".wh..wh..opq":
                    for key in [key for key in files if key.startswith(f"{directory}/")]:
                        del files[key]
                else:
                    files.pop(posixpath.join(directory, base[4:]), None)
                continue
            if not member.isfile() or not _tracked(name):
                continue
            if member.size > MAX_MEMBER_BYTES:
                limitations.append(f"{name} exceeds the per-file bound and was not read")
                continue
            if len(files) >= MAX_TRACKED_FILES and name not in files:
                limitations.append(
                    f"only the first {MAX_TRACKED_FILES} package files in the image were read",
                )
                break
            handle = archive.extractfile(member)
            if handle is None:
                continue
            files[name] = handle.read(MAX_MEMBER_BYTES)
    except tarfile.TarError:
        limitations.append("a layer archive ended unexpectedly and was read only in part")
    finally:
        archive.close()


def parse_dpkg_status(body: bytes) -> list[ContainerPackageRecord]:
    """Parse `/var/lib/dpkg/status`, keeping only packages that are actually installed.

    dpkg keeps stanzas for packages that were removed but whose configuration remains. Counting
    those as installed would report an inventory the image does not have.
    """
    packages: list[ContainerPackageRecord] = []
    for stanza in body.decode("utf-8", errors="replace").split("\n\n"):
        fields: dict[str, str] = {}
        for line in stanza.splitlines():
            if line[:1].isspace() or ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
        name = fields.get("package")
        status = fields.get("status", "")
        if not name or "installed" not in status.split() or status.startswith("deinstall"):
            continue
        version = fields.get("version") or None
        packages.append(ContainerPackageRecord(
            name=name, version=version, ecosystem="deb",
            purl=f"pkg:deb/{name}@{version}" if version else f"pkg:deb/{name}",
        ))
    return packages


def parse_apk_installed(body: bytes) -> list[ContainerPackageRecord]:
    """Parse Alpine's `installed` database, whose records are `K:value` lines."""
    packages: list[ContainerPackageRecord] = []
    name: str | None = None
    version: str | None = None
    for line in body.decode("utf-8", errors="replace").splitlines():
        if line == "":
            if name:
                packages.append(ContainerPackageRecord(
                    name=name, version=version, ecosystem="apk",
                    purl=f"pkg:apk/{name}@{version}" if version else f"pkg:apk/{name}",
                ))
            name, version = None, None
            continue
        if line.startswith("P:"):
            name = line[2:].strip() or None
        elif line.startswith("V:"):
            version = line[2:].strip() or None
    if name:
        packages.append(ContainerPackageRecord(
            name=name, version=version, ecosystem="apk",
            purl=f"pkg:apk/{name}@{version}" if version else f"pkg:apk/{name}",
        ))
    return packages


def _parse_metadata(body: bytes) -> tuple[str | None, str | None]:
    name: str | None = None
    version: str | None = None
    for line in body.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            break
        if line.lower().startswith("name:") and name is None:
            name = line.partition(":")[2].strip() or None
        elif line.lower().startswith("version:") and version is None:
            version = line.partition(":")[2].strip() or None
    return name, version


def collect_packages(files: Mapping[str, bytes], limitations: list[str]) -> list[ContainerPackageRecord]:
    """Turn the extracted package databases into records, one ecosystem at a time."""
    packages: list[ContainerPackageRecord] = []
    sources: set[str] = set()
    for path, body in sorted(files.items()):
        if path == DPKG_STATUS:
            packages.extend(parse_dpkg_status(body))
            sources.add("dpkg")
        elif path == APK_INSTALLED:
            packages.extend(parse_apk_installed(body))
            sources.add("apk")
        elif _DIST_INFO.search(path) or _EGG_INFO.search(path):
            name, version = _parse_metadata(body)
            if name:
                packages.append(ContainerPackageRecord(
                    name=name, version=version, ecosystem="pypi",
                    purl=f"pkg:pypi/{name.lower()}@{version}" if version else None,
                ))
                sources.add("python")
        else:
            match = _NODE_PACKAGE.search(path)
            if match is None:
                continue
            try:
                document = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(document, Mapping) or not isinstance(document.get("name"), str):
                continue
            version = document.get("version")
            packages.append(ContainerPackageRecord(
                name=str(document["name"]),
                version=str(version) if isinstance(version, str) else None,
                ecosystem="npm",
                purl=f"pkg:npm/{document['name']}@{version}" if isinstance(version, str) else None,
            ))
            sources.add("npm")
    if any(path.startswith(RPM_DIRECTORY) for path in files):
        # Detected, deliberately not parsed. See this module's docstring.
        limitations.append(
            "the image carries an RPM database, which StackGraph does not parse; its packages "
            "are not included",
        )
        sources.add("rpm-detected")
    deduped: dict[tuple[str, str, str | None], ContainerPackageRecord] = {}
    for package in packages:
        deduped.setdefault((package.ecosystem, package.name, package.version), package)
    ordered = sorted(deduped.values(), key=lambda item: (item.ecosystem, item.name, item.version or ""))
    if len(ordered) > MAX_PACKAGES:
        limitations.append(
            f"only {MAX_PACKAGES} of {len(ordered)} packages found in the image were recorded",
        )
        ordered = ordered[:MAX_PACKAGES]
    return ordered


def read_package_inventory(
    client: ContainerRegistryClient, resolved: ResolvedImage,
) -> PackageInventory:
    """Download the image's layers and read the package databases inside them."""
    if not resolved.layers:
        return PackageInventory(
            coverage="NOT_COLLECTED",
            limitations=("the manifest names no layers to read",),
        )
    reference = resolved.reference
    files: dict[str, bytes] = {}
    limitations: list[str] = []
    read = 0
    skipped = 0
    total = 0
    for layer in resolved.layers:
        digest = str(layer.get("digest") or "")
        media_type = str(layer.get("mediaType") or "")
        size = layer.get("size") if isinstance(layer.get("size"), int) else None
        if read >= MAX_LAYERS_READ:
            skipped += 1
            continue
        if media_type not in GZIP_MEDIA_TYPES and media_type not in UNCOMPRESSED_MEDIA_TYPES:
            skipped += 1
            limitations.append(
                f"a layer of type {media_type or 'unknown'} was not read; StackGraph reads only "
                "gzip and uncompressed tar layers",
            )
            continue
        if size is not None and size > MAX_LAYER_BYTES:
            skipped += 1
            limitations.append(
                f"a layer of {size} bytes exceeds the {MAX_LAYER_BYTES} byte bound and was not "
                "requested",
            )
            continue
        if size is not None and total + size > MAX_TOTAL_LAYER_BYTES:
            skipped += 1
            limitations.append("the image's remaining layers exceed the total download bound")
            continue
        try:
            body = client.blob(reference, digest)
        except ContainerRegistryError as error:
            skipped += 1
            limitations.append(f"a layer could not be downloaded: {error}")
            continue
        total += len(body)
        if media_type in GZIP_MEDIA_TYPES:
            body, truncated = _gunzip_bounded(body, MAX_DECOMPRESSED_BYTES)
            if truncated:
                limitations.append(
                    "a layer expanded past the decompression bound and was read only in part",
                )
        _read_layer(body, files, limitations)
        read += 1

    packages = collect_packages(files, limitations)
    sources = tuple(sorted({
        "dpkg" if path == DPKG_STATUS else
        "apk" if path == APK_INSTALLED else
        "rpm" if path.startswith(RPM_DIRECTORY) else
        "npm" if _NODE_PACKAGE.search(path) else "python"
        for path in files
    }))
    if read == 0:
        coverage = "NOT_COLLECTED"
    elif skipped or limitations:
        coverage = "PARTIAL"
    elif not packages:
        # Every layer was read and no package database exists. A distroless or scratch image is
        # a real answer, and reporting it as PARTIAL would imply something went unread.
        coverage = "NOT_APPLICABLE"
        limitations.append(
            "the image carries no OS or language package database; distroless and scratch "
            "images have none",
        )
    else:
        coverage = "AVAILABLE"
    return PackageInventory(
        packages=tuple(packages), coverage=coverage,
        limitations=tuple(dict.fromkeys(limitations)), layers_read=read, layers_skipped=skipped,
        sources=sources,
    )

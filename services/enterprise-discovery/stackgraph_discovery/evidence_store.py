from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import urlsplit


URI_SCHEME = "stackgraph-evidence"
URI_HOST = "local"


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    uri: str
    content_hash: str
    size_bytes: int
    media_type: str


class LocalEvidenceStore:
    """Tenant-scoped, content-addressed evidence storage on a durable volume.

    The URI intentionally does not expose the host filesystem path or tenant key.
    A production object-store backend can retain this descriptor contract while
    changing the physical storage implementation.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError("evidence-store root cannot be a symbolic link")

    def put_bytes(
        self,
        tenant_key: str,
        content: bytes,
        *,
        media_type: str,
        expected_hash: str | None = None,
    ) -> StoredEvidence:
        tenant_segment = _tenant_segment(tenant_key)
        if not media_type.strip():
            raise ValueError("evidence media type is required")
        digest = hashlib.sha256(content).hexdigest()
        content_hash = f"sha256:{digest}"
        if expected_hash is not None and expected_hash != content_hash:
            raise ValueError("evidence content does not match the expected hash")

        directory = self._tenant_root(tenant_segment) / "sha256" / digest[:2]
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / digest
        metadata = directory / f"{digest}.json"
        if target.exists():
            _verify_file(target, content_hash, len(content))
        else:
            _atomic_write(target, content)
        descriptor = StoredEvidence(
            uri=f"{URI_SCHEME}://{URI_HOST}/tenants/{tenant_segment}/sha256/{digest}",
            content_hash=content_hash,
            size_bytes=len(content),
            media_type=media_type,
        )
        metadata_bytes = (
            json.dumps(asdict(descriptor), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if metadata.exists():
            if metadata.read_bytes() != metadata_bytes:
                raise ValueError("evidence metadata conflicts with existing content")
        else:
            _atomic_write(metadata, metadata_bytes)
        return descriptor

    def read_bytes(
        self,
        tenant_key: str,
        descriptor: StoredEvidence,
    ) -> bytes:
        tenant_segment = _tenant_segment(tenant_key)
        digest = _digest_from_uri(descriptor.uri, tenant_segment)
        target = self._tenant_root(tenant_segment) / "sha256" / digest[:2] / digest
        content = target.read_bytes()
        actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if actual_hash != descriptor.content_hash or len(content) != descriptor.size_bytes:
            raise ValueError("stored evidence failed checksum or size verification")
        if descriptor.content_hash != f"sha256:{digest}":
            raise ValueError("evidence descriptor hash does not match its URI")
        return content

    def delete_tenant(self, tenant_key: str) -> bool:
        """Delete one tenant prefix; callers must enforce lifecycle authorization."""

        tenant_root = self._tenant_root(_tenant_segment(tenant_key))
        if not tenant_root.exists():
            return False
        if tenant_root.is_symlink() or not tenant_root.is_relative_to(self.root / "tenants"):
            raise ValueError("unsafe tenant evidence-store path")
        shutil.rmtree(tenant_root)
        return True

    def _tenant_root(self, tenant_segment: str) -> Path:
        tenant_root = (self.root / "tenants" / tenant_segment).resolve()
        if not tenant_root.is_relative_to(self.root / "tenants"):
            raise ValueError("tenant evidence-store path escapes the configured root")
        return tenant_root


def deterministic_tar(entries: Mapping[str, bytes]) -> bytes:
    """Build a replayable tar payload whose checksum is stable across runs."""

    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(entries):
            path = PurePosixPath(name)
            if not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError(f"unsafe evidence archive path: {name!r}")
            content = entries[name]
            info = tarfile.TarInfo(path.as_posix())
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, BytesIO(content))
    return output.getvalue()


def _tenant_segment(tenant_key: str) -> str:
    if not tenant_key or not tenant_key.strip():
        raise ValueError("tenant key is required for durable evidence storage")
    return hashlib.sha256(tenant_key.encode("utf-8")).hexdigest()


def _digest_from_uri(uri: str, tenant_segment: str) -> str:
    parsed = urlsplit(uri)
    if parsed.scheme != URI_SCHEME or parsed.netloc != URI_HOST or parsed.query or parsed.fragment:
        raise ValueError("unsupported evidence URI")
    parts = PurePosixPath(parsed.path).parts
    expected_prefix = ("/", "tenants", tenant_segment, "sha256")
    if len(parts) != 5 or parts[:4] != expected_prefix:
        raise ValueError("evidence URI is outside the tenant scope")
    digest = parts[4]
    if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
        raise ValueError("evidence URI contains an invalid SHA-256 digest")
    return digest


def _verify_file(path: Path, expected_hash: str, expected_size: int) -> None:
    content = path.read_bytes()
    actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
    if actual_hash != expected_hash or len(content) != expected_size:
        raise ValueError("existing evidence object is corrupt")


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

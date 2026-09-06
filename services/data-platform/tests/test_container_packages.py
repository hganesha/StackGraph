"""Reading the packages installed inside a container image.

`coverage.os_packages` said NOT_COLLECTED for as long as the container profile existed. These
tests hold the two things that make replacing it with a real answer safe: the bounds that stop a
layer read from being unbounded work in memory, and the distinctions that stop a partial read
from being presented as a complete inventory.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
import unittest
import zlib

from stackgraph_data.container_packages import (
    MAX_DECOMPRESSED_BYTES,
    MAX_LAYERS_READ,
    _gunzip_bounded,
    collect_packages,
    parse_apk_installed,
    parse_dpkg_status,
    read_package_inventory,
)
from stackgraph_data.container_registry import (
    MAX_LAYER_BYTES,
    ContainerRegistryError,
    ImageReference,
    ResolvedImage,
)


GZIP_TAR = "application/vnd.oci.image.layer.v1.tar+gzip"
REFERENCE = ImageReference("ghcr.io", "acme/shipping", "2.0.1", None)

DPKG_STATUS = b"""Package: libc6
Status: install ok installed
Version: 2.36-9+deb12u7
Architecture: amd64

Package: openssl
Status: install ok installed
Version: 3.0.11-1~deb12u2

Package: removed-config
Status: deinstall ok config-files
Version: 1.4.0
"""

APK_INSTALLED = b"""C:Q1abc
P:musl
V:1.2.4-r2
A:x86_64

C:Q1def
P:busybox
V:1.36.1-r5
"""


def tar_layer(files: dict[str, bytes], *, compress: bool = True) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    raw = buffer.getvalue()
    return gzip.compress(raw) if compress else raw


class Client:
    """A registry that hands back prepared blobs and records what was asked for."""

    def __init__(self, blobs: dict[str, bytes], *, failing: set[str] | None = None):
        self.blobs = blobs
        self.failing = failing or set()
        self.requested: list[str] = []

    def blob(self, reference, digest, **_):
        self.requested.append(digest)
        if digest in self.failing:
            raise ContainerRegistryError("the registry does not hold this blob")
        return self.blobs[digest]


def image(*layers: tuple[bytes, str, int | None]) -> tuple[ResolvedImage, Client]:
    blobs: dict[str, bytes] = {}
    descriptors = []
    for body, media_type, size in layers:
        digest = f"sha256:{hashlib.sha256(body).hexdigest()}"
        blobs[digest] = body
        descriptors.append({
            "digest": digest, "mediaType": media_type,
            "size": len(body) if size is None else size,
        })
    resolved = ResolvedImage(
        reference=REFERENCE, digest="sha256:" + "a" * 64, media_type="m",
        layers=tuple(descriptors),
    )
    return resolved, Client(blobs)


class DatabaseParsingTests(unittest.TestCase):
    def test_dpkg_reports_installed_packages_and_not_removed_ones(self) -> None:
        packages = parse_dpkg_status(DPKG_STATUS)

        self.assertEqual({"libc6", "openssl"}, {item.name for item in packages})
        # dpkg keeps a stanza for a package whose configuration survives removal. Counting it
        # would report an inventory the image does not have.
        self.assertNotIn("removed-config", {item.name for item in packages})
        self.assertEqual("pkg:deb/libc6@2.36-9+deb12u7", packages[0].purl)

    def test_apk_reads_the_final_record_without_a_trailing_blank_line(self) -> None:
        packages = parse_apk_installed(APK_INSTALLED)

        self.assertEqual(["musl", "busybox"], [item.name for item in packages])
        self.assertEqual("1.36.1-r5", packages[1].version)

    def test_an_rpm_database_is_reported_rather_than_parsed(self) -> None:
        limitations: list[str] = []
        packages = collect_packages({"var/lib/rpm/rpmdb.sqlite": b"\x00binary"}, limitations)

        self.assertEqual([], packages)
        # A confident wrong answer about what is installed is worse than a stated gap.
        self.assertTrue(any("RPM database" in item for item in limitations))


class LayerReadingTests(unittest.TestCase):
    def test_packages_are_read_from_every_database_the_image_carries(self) -> None:
        resolved, client = image(
            (tar_layer({
                "var/lib/dpkg/status": DPKG_STATUS,
                "usr/lib/python3/site-packages/requests-2.32.3.dist-info/METADATA":
                    b"Name: requests\nVersion: 2.32.3\n",
            }), GZIP_TAR, None),
            (tar_layer({
                "app/node_modules/left-pad/package.json":
                    json.dumps({"name": "left-pad", "version": "1.3.0"}).encode(),
            }), GZIP_TAR, None),
        )

        inventory = read_package_inventory(client, resolved)

        self.assertEqual("AVAILABLE", inventory.coverage)
        self.assertEqual(2, inventory.layers_read)
        self.assertEqual(
            {("deb", "libc6"), ("deb", "openssl"), ("pypi", "requests"), ("npm", "left-pad")},
            {(item.ecosystem, item.name) for item in inventory.packages},
        )
        self.assertEqual(("dpkg", "npm", "python"), inventory.sources)

    def test_a_later_layer_replaces_what_an_earlier_one_wrote(self) -> None:
        resolved, client = image(
            (tar_layer({"var/lib/dpkg/status": DPKG_STATUS}), GZIP_TAR, None),
            (tar_layer({"var/lib/dpkg/status": (
                b"Package: libc6\nStatus: install ok installed\nVersion: 2.37-1\n"
            )}), GZIP_TAR, None),
        )

        inventory = read_package_inventory(client, resolved)

        self.assertEqual(
            [("libc6", "2.37-1")], [(item.name, item.version) for item in inventory.packages],
        )

    def test_a_whiteout_removes_a_database_an_earlier_layer_wrote(self) -> None:
        resolved, client = image(
            (tar_layer({"var/lib/dpkg/status": DPKG_STATUS}), GZIP_TAR, None),
            (tar_layer({"var/lib/dpkg/.wh.status": b""}), GZIP_TAR, None),
        )

        inventory = read_package_inventory(client, resolved)

        # Reporting packages an image no longer contains is worse than reporting none: it is a
        # specific, confident, wrong answer.
        self.assertEqual((), inventory.packages)

    def test_an_oversized_layer_is_skipped_before_it_is_requested(self) -> None:
        body = tar_layer({"var/lib/dpkg/status": DPKG_STATUS})
        resolved, client = image((body, GZIP_TAR, MAX_LAYER_BYTES + 1))

        inventory = read_package_inventory(client, resolved)

        self.assertEqual([], client.requested)
        self.assertEqual(1, inventory.layers_skipped)
        self.assertEqual("NOT_COLLECTED", inventory.coverage)
        self.assertTrue(any("byte bound" in item for item in inventory.limitations))

    def test_a_layer_type_with_no_reader_is_named_rather_than_ignored(self) -> None:
        resolved, client = image(
            (tar_layer({"var/lib/dpkg/status": DPKG_STATUS}),
             "application/vnd.oci.image.layer.v1.tar+zstd", None),
        )

        inventory = read_package_inventory(client, resolved)

        self.assertEqual([], client.requested)
        self.assertTrue(any("zstd" in item for item in inventory.limitations))

    def test_only_a_bounded_number_of_layers_is_read(self) -> None:
        layers = [
            (tar_layer({f"app/node_modules/pkg{index}/package.json":
                        json.dumps({"name": f"pkg{index}", "version": "1.0.0"}).encode()}),
             GZIP_TAR, None)
            for index in range(MAX_LAYERS_READ + 3)
        ]
        resolved, client = image(*layers)

        inventory = read_package_inventory(client, resolved)

        self.assertEqual(MAX_LAYERS_READ, inventory.layers_read)
        self.assertEqual(3, inventory.layers_skipped)
        # A bounded read is PARTIAL, never AVAILABLE: the rest of the image went unexamined.
        self.assertEqual("PARTIAL", inventory.coverage)

    def test_a_failed_layer_download_leaves_the_read_partial_rather_than_empty(self) -> None:
        resolved, client = image(
            (tar_layer({"var/lib/dpkg/status": DPKG_STATUS}), GZIP_TAR, None),
            (tar_layer({"app/node_modules/x/package.json": b"{}"}), GZIP_TAR, None),
        )
        client.failing = {resolved.layers[1]["digest"]}

        inventory = read_package_inventory(client, resolved)

        self.assertEqual("PARTIAL", inventory.coverage)
        self.assertEqual(1, inventory.layers_read)
        self.assertTrue({item.name for item in inventory.packages})

    def test_an_image_with_no_package_database_is_not_applicable_rather_than_empty(self) -> None:
        resolved, client = image((tar_layer({"app/server": b"binary"}), GZIP_TAR, None))

        inventory = read_package_inventory(client, resolved)

        # A distroless image genuinely has no package database. Reporting PARTIAL would imply
        # something went unread, and AVAILABLE with zero packages would read as "none found".
        self.assertEqual("NOT_APPLICABLE", inventory.coverage)
        self.assertTrue(any("distroless" in item for item in inventory.limitations))

    def test_an_image_with_no_layers_reports_nothing_collected(self) -> None:
        resolved = ResolvedImage(
            reference=REFERENCE, digest="sha256:" + "a" * 64, media_type="m", layers=(),
        )

        inventory = read_package_inventory(Client({}), resolved)

        self.assertEqual("NOT_COLLECTED", inventory.coverage)
        self.assertEqual((), inventory.packages)

    def test_an_uncompressed_layer_is_read_without_decompression(self) -> None:
        resolved, client = image(
            (tar_layer({"lib/apk/db/installed": APK_INSTALLED}, compress=False),
             "application/vnd.oci.image.layer.v1.tar", None),
        )

        inventory = read_package_inventory(client, resolved)

        self.assertEqual({"musl", "busybox"}, {item.name for item in inventory.packages})


class DecompressionBoundTests(unittest.TestCase):
    def test_decompression_stops_at_the_bound_however_small_the_input(self) -> None:
        # A gzip bomb's whole point is that compressed size says nothing about expanded size,
        # so the bound cannot be derived from the download.
        compressor = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        payload = compressor.compress(b"\0" * (4 * 1024 * 1024)) + compressor.flush()
        self.assertLess(len(payload), 64 * 1024)

        body, truncated = _gunzip_bounded(payload, 1024)

        self.assertEqual(1024, len(body))
        self.assertTrue(truncated)

    def test_a_normal_layer_decompresses_whole(self) -> None:
        body, truncated = _gunzip_bounded(gzip.compress(b"hello"), MAX_DECOMPRESSED_BYTES)

        self.assertEqual(b"hello", body)
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()

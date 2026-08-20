from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stackgraph_discovery.evidence_store import (
    LocalEvidenceStore,
    StoredEvidence,
    deterministic_tar,
)


class LocalEvidenceStoreTests(unittest.TestCase):
    def test_put_is_tenant_scoped_content_addressed_and_replayable(self) -> None:
        with TemporaryDirectory() as directory:
            store = LocalEvidenceStore(Path(directory))
            first = store.put_bytes(
                "tenant-one",
                b"immutable evidence",
                media_type="application/octet-stream",
            )
            replay = store.put_bytes(
                "tenant-one",
                b"immutable evidence",
                media_type="application/octet-stream",
            )

            self.assertEqual(first, replay)
            self.assertEqual(store.read_bytes("tenant-one", first), b"immutable evidence")
            self.assertRegex(first.content_hash, r"^sha256:[a-f0-9]{64}$")
            self.assertNotIn("tenant-one", first.uri)
            with self.assertRaisesRegex(ValueError, "tenant scope"):
                store.read_bytes("tenant-two", first)

    def test_descriptor_and_existing_object_corruption_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            store = LocalEvidenceStore(Path(directory))
            stored = store.put_bytes(
                "tenant-one",
                b"evidence",
                media_type="application/octet-stream",
            )
            wrong = StoredEvidence(
                uri=stored.uri,
                content_hash=f"sha256:{'0' * 64}",
                size_bytes=stored.size_bytes,
                media_type=stored.media_type,
            )
            with self.assertRaisesRegex(ValueError, "checksum"):
                store.read_bytes("tenant-one", wrong)
            with self.assertRaisesRegex(ValueError, "expected hash"):
                store.put_bytes(
                    "tenant-one",
                    b"evidence",
                    media_type="application/octet-stream",
                    expected_hash=f"sha256:{'0' * 64}",
                )

    def test_delete_tenant_removes_only_that_tenant_prefix(self) -> None:
        with TemporaryDirectory() as directory:
            store = LocalEvidenceStore(Path(directory))
            first = store.put_bytes("one", b"first", media_type="text/plain")
            second = store.put_bytes("two", b"second", media_type="text/plain")

            self.assertTrue(store.delete_tenant("one"))
            self.assertFalse(store.delete_tenant("one"))
            self.assertEqual(store.read_bytes("two", second), b"second")
            with self.assertRaises(FileNotFoundError):
                store.read_bytes("one", first)

    def test_deterministic_tar_is_stable_and_rejects_unsafe_paths(self) -> None:
        first = deterministic_tar({"b.txt": b"b", "nested/a.txt": b"a"})
        second = deterministic_tar({"nested/a.txt": b"a", "b.txt": b"b"})
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            deterministic_tar({"../escape": b"no"})


if __name__ == "__main__":
    unittest.main()

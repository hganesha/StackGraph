from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from stackgraph_discovery.evidence_store import (
    LocalEvidenceStore,
    S3EvidenceStore,
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


class S3EvidenceStoreTests(unittest.TestCase):
    def test_put_read_encryption_retention_and_authorized_deletion(self) -> None:
        client = _FakeS3Client()
        store = S3EvidenceStore(
            "evidence",
            kms_key_id="alias/stackgraph-evidence",
            retention_days=45,
            legal_hold=True,
            allow_delete=True,
            client=client,
        )
        descriptor = store.put_bytes(
            "tenant-a", b"immutable input", media_type="application/octet-stream",
        )
        request = client.puts[0]
        self.assertEqual(request["ServerSideEncryption"], "aws:kms")
        self.assertEqual(request["SSEKMSKeyId"], "alias/stackgraph-evidence")
        self.assertEqual(request["ObjectLockMode"], "GOVERNANCE")
        self.assertEqual(request["ObjectLockLegalHoldStatus"], "ON")
        self.assertEqual(store.read_bytes("tenant-a", descriptor), b"immutable input")
        self.assertTrue(store.delete_tenant("tenant-a"))
        self.assertTrue(client.bypassed_governance)

    def test_tenant_isolation_and_deletion_policy_are_enforced(self) -> None:
        client = _FakeS3Client()
        store = S3EvidenceStore("evidence", client=client)
        descriptor = store.put_bytes("tenant-a", b"a", media_type="text/plain")
        with self.assertRaises(ValueError):
            store.read_bytes("tenant-b", descriptor)
        with self.assertRaises(PermissionError):
            store.delete_tenant("tenant-a")


class _NotFound(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, object]] = {}
        self.puts: list[dict[str, object]] = []
        self.bypassed_governance = False

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if Key not in self.objects:
            raise _NotFound()
        item = self.objects[Key]
        return {
            "ContentLength": len(item["Body"]),
            "ContentType": item["ContentType"],
            "Metadata": item["Metadata"],
        }

    def put_object(self, **request: object) -> None:
        self.puts.append(request)
        self.objects[str(request["Key"])] = request

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        return {"Body": _Body(self.objects[Key]["Body"])}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **_: object) -> dict[str, object]:
        return {
            "Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)],
            "IsTruncated": False,
        }

    def delete_objects(
        self,
        *,
        Bucket: str,
        Delete: dict[str, object],
        BypassGovernanceRetention: bool,
    ) -> None:
        self.bypassed_governance = BypassGovernanceRetention
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)


if __name__ == "__main__":
    unittest.main()

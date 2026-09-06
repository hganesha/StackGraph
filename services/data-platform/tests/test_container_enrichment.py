"""Tests for writing resolved container images into the typed estate profile.

The value of this step is that `estate_container_profile` finally has a writer. The risks are
that it runs when it should not, claims coverage it does not have, or overwrites what production
ran with what a moved tag now points at.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from stackgraph_data.container_enrichment import (
    _image_reference,
    persist_resolution,
    run_enrichment,
)
from stackgraph_data.container_registry import (
    ContainerRegistryError,
    ImageReference,
    ResolvedImage,
)


TENANT_ID = UUID("00000000-0000-4000-8000-00000011a001")
IMAGE_ID = UUID("00000000-0000-4000-8000-00000011a002")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-00000011a003")
PROFILE_ID = UUID("00000000-0000-4000-8000-00000011a0f0")
DIGEST = "sha256:" + "a" * 64
OBSERVED_AT = datetime(2026, 8, 19, 14, tzinfo=UTC)


def resolved(**overrides):
    values = {
        "reference": ImageReference("ghcr.io", "acme/shipping", "2.0.1", None),
        "digest": DIGEST,
        "media_type": "application/vnd.oci.image.manifest.v1+json",
        "architecture": "amd64",
        "operating_system": "linux",
        "layers": ({"digest": "sha256:" + "b" * 64, "size": 128},),
        "entrypoint": ("node", "src/server.js"),
        "user": "node",
        "exposed_ports": ("8080/tcp",),
        "coverage": {"manifest": "AVAILABLE", "config": "AVAILABLE",
                     "layers": "AVAILABLE", "os_packages": "NOT_COLLECTED"},
        "limitations": (),
    }
    values.update(overrides)
    return ResolvedImage(**values)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, *, enabled=True, images=None):
        self.enabled = enabled
        self.images = images or []
        self.tag_resolutions: list[tuple] = []
        self.profiles: list[tuple] = []
        self.layers: list[tuple] = []
        self.supersedes: list[tuple] = []

    def execute(self, query, params=()):
        if "set_config" in query:
            return Result([])
        if "FROM phase2_feature_flag" in query:
            return Result([{"enabled": self.enabled}])
        if "FROM entity image" in query:
            return Result(self.images)
        if "INSERT INTO container_tag_resolution" in query:
            self.tag_resolutions.append(params)
            return Result([])
        if "INSERT INTO estate_container_profile" in query:
            self.profiles.append(params)
            return Result([{"id": PROFILE_ID}])
        if "UPDATE estate_container_profile" in query:
            self.supersedes.append(params)
            return Result([])
        if "INSERT INTO estate_container_layer" in query:
            self.layers.append(params)
            return Result([])
        raise AssertionError(f"unexpected query: {query.strip()[:80]}")


class Registry:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[str] = []

    def resolve(self, image):
        self.calls.append(image)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def image_row(canonical_key="container-image:ghcr.io/acme/shipping:2.0.1"):
    return {
        "image_entity_id": IMAGE_ID, "canonical_key": canonical_key, "name": "shipping",
        "repository_entity_id": REPOSITORY_ID, "source_revision": "b" * 40,
        "observed_at": OBSERVED_AT,
    }


class ReferenceRecoveryTests(unittest.TestCase):
    def test_a_registry_reference_is_recovered_from_the_canonical_key(self) -> None:
        self.assertEqual(
            "ghcr.io/acme/shipping:2.0.1",
            _image_reference("container-image:ghcr.io/acme/shipping:2.0.1"),
        )

    def test_a_local_build_placeholder_is_never_requested_from_a_registry(self) -> None:
        # `container-build:` names something produced by a Dockerfile in this repository. No
        # registry has heard of it, and asking would be a request for a name we invented.
        with self.assertRaises(ContainerRegistryError):
            _image_reference("container-build:github:repo:1:Dockerfile")


class PersistenceTests(unittest.TestCase):
    def persist(self, outcome=None):
        connection = FakeConnection()
        persist_resolution(
            connection, tenant_id=TENANT_ID, image_entity_id=IMAGE_ID,
            repository_entity_id=REPOSITORY_ID, source_revision="b" * 40,
            observed_at=OBSERVED_AT, resolved=outcome or resolved(),
        )
        return connection

    def test_the_digest_becomes_the_profile_identity_and_the_tag_an_observation(self) -> None:
        connection = self.persist()
        profile = connection.profiles[0]
        self.assertEqual(DIGEST, profile[3])
        self.assertEqual(["2.0.1"], profile[4])
        # The tag history is a separate record, so a tag that moves later does not overwrite it.
        self.assertEqual(1, len(connection.tag_resolutions))
        self.assertEqual("2.0.1", connection.tag_resolutions[0][3])

    def test_runtime_configuration_is_recorded_as_build_metadata(self) -> None:
        build = self.persist().profiles[0][8].obj
        self.assertEqual(["node", "src/server.js"], build["entrypoint"])
        self.assertEqual("node", build["user"])
        self.assertEqual(["8080/tcp"], build["exposed_ports"])

    def test_package_coverage_is_carried_through_as_not_collected(self) -> None:
        coverage = self.persist().profiles[0][10].obj
        # A vulnerability question must not be answerable from an inventory never taken.
        self.assertEqual("NOT_COLLECTED", coverage["os_packages"])

    def test_layers_are_written_in_order(self) -> None:
        connection = self.persist(resolved(layers=(
            {"digest": "sha256:" + "b" * 64, "size": 128},
            {"digest": "sha256:" + "c" * 64, "size": 256},
        )))
        self.assertEqual([0, 1], [params[2] for params in connection.layers])

    def test_an_older_profile_is_superseded_rather_than_accumulated(self) -> None:
        connection = self.persist()
        self.assertEqual([(TENANT_ID, IMAGE_ID, PROFILE_ID)], connection.supersedes)

    def test_a_digest_pinned_image_records_no_tag_observation(self) -> None:
        connection = self.persist(resolved(
            reference=ImageReference("ghcr.io", "acme/shipping", None, DIGEST),
        ))
        # There is no tag to observe: the reference was already an identity.
        self.assertEqual([], connection.tag_resolutions)
        self.assertEqual([], connection.profiles[0][4])


class EnrichmentRunTests(unittest.TestCase):
    def test_nothing_is_fetched_while_the_flag_is_off(self) -> None:
        registry = Registry(resolved())
        connection = FakeConnection(enabled=False, images=[image_row()])
        counts = run_enrichment(connection, tenant_id=TENANT_ID, registry=registry)
        # Reaching an external registry is an operator's decision, so the default is no request.
        self.assertEqual(1, counts["skipped_disabled"])
        self.assertEqual([], registry.calls)
        self.assertEqual([], connection.profiles)

    def test_an_observed_image_is_resolved_and_written(self) -> None:
        registry = Registry(resolved())
        connection = FakeConnection(images=[image_row()])
        counts = run_enrichment(connection, tenant_id=TENANT_ID, registry=registry)
        self.assertEqual(1, counts["resolved"])
        self.assertEqual(["ghcr.io/acme/shipping:2.0.1"], registry.calls)
        self.assertEqual(1, len(connection.profiles))

    def test_an_unresolvable_image_leaves_the_estate_unchanged(self) -> None:
        registry = Registry(ContainerRegistryError("the registry requires credentials"))
        connection = FakeConnection(images=[image_row()])
        counts = run_enrichment(connection, tenant_id=TENANT_ID, registry=registry)
        # The read surface already reports an unresolved tag as INFERRED, which stays true.
        self.assertEqual(1, counts["unresolvable"])
        self.assertEqual(0, counts["resolved"])
        self.assertEqual([], connection.profiles)

    def test_a_local_build_is_counted_as_unresolvable_without_a_request(self) -> None:
        registry = Registry(resolved())
        connection = FakeConnection(
            images=[image_row("container-build:github:repo:1:Dockerfile")],
        )
        counts = run_enrichment(connection, tenant_id=TENANT_ID, registry=registry)
        self.assertEqual(1, counts["unresolvable"])
        self.assertEqual([], registry.calls)


if __name__ == "__main__":
    unittest.main()

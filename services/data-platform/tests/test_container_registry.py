"""Tests for resolving container tags to immutable digests.

S3's rule is that a tag is an observation and a digest is an identity. These tests hold the
places where that distinction is easy to lose: a registry claiming a digest its own bytes do not
support, a manifest list whose index digest is what deployments reference, a redirect off the
allowlist, and a reference whose first segment only looks like a registry.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from stackgraph_data.container_registry import (
    DEFAULT_ALLOWED_REGISTRIES,
    ContainerRegistryClient,
    ContainerRegistryError,
    parse_image_reference,
)


def digest_of(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


CONFIG = {
    "architecture": "amd64",
    "os": "linux",
    "config": {
        "Entrypoint": ["node", "src/server.js"],
        "User": "node",
        "ExposedPorts": {"8080/tcp": {}},
        "Labels": {"org.opencontainers.image.version": "2.0.1"},
    },
}
CONFIG_BODY = json.dumps(CONFIG).encode()
CONFIG_DIGEST = digest_of(CONFIG_BODY)

MANIFEST = {
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "config": {"digest": CONFIG_DIGEST, "mediaType": "application/vnd.oci.image.config.v1+json"},
    "layers": [
        {"digest": digest_of(b"layer-1"), "size": 128},
        {"digest": digest_of(b"layer-2"), "size": 256},
    ],
}
MANIFEST_BODY = json.dumps(MANIFEST).encode()
MANIFEST_DIGEST = digest_of(MANIFEST_BODY)

PLATFORM_BODY = MANIFEST_BODY
PLATFORM_DIGEST = MANIFEST_DIGEST
INDEX = {
    "mediaType": "application/vnd.oci.image.index.v1+json",
    "manifests": [
        {"digest": digest_of(b"windows"), "platform": {"os": "windows", "architecture": "amd64"}},
        {"digest": PLATFORM_DIGEST, "platform": {"os": "linux", "architecture": "amd64"}},
    ],
}
INDEX_BODY = json.dumps(INDEX).encode()
INDEX_DIGEST = digest_of(INDEX_BODY)


class Response:
    def __init__(self, status, body, headers=None, final_url=None):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.final_url = final_url or "https://ghcr.io/v2/acme/shipping/manifests/2.0.1"


class Transport:
    def __init__(self, routes):
        self.routes = routes
        self.requests: list[str] = []

    def request(self, url, headers, timeout_seconds):
        self.requests.append(url)
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        raise AssertionError(f"unrouted request: {url}")


def client(routes, **overrides):
    return ContainerRegistryClient(Transport(routes), **overrides)


class ReferenceParsingTests(unittest.TestCase):
    def test_a_bare_name_resolves_to_docker_hub_library(self) -> None:
        reference = parse_image_reference("node:20.11-alpine")
        self.assertEqual("registry-1.docker.io", reference.registry_host)
        self.assertEqual("library/node", reference.repository)
        self.assertEqual("20.11-alpine", reference.tag)

    def test_a_namespaced_name_is_not_mistaken_for_a_registry(self) -> None:
        # `acme` has no dot or colon, so it is a Docker Hub namespace, not a host.
        reference = parse_image_reference("acme/shipping:2.0.1")
        self.assertEqual("registry-1.docker.io", reference.registry_host)
        self.assertEqual("acme/shipping", reference.repository)

    def test_a_host_is_recognised_by_its_dot_or_port(self) -> None:
        self.assertEqual(
            "registry.internal", parse_image_reference("registry.internal/acme/x:1").registry_host,
        )
        self.assertEqual(
            "localhost:5000", parse_image_reference("localhost:5000/acme/x:1").registry_host,
        )

    def test_a_digest_pinned_reference_is_already_an_identity(self) -> None:
        reference = parse_image_reference(f"ghcr.io/acme/shipping@{MANIFEST_DIGEST}")
        self.assertTrue(reference.is_digest_pinned)
        self.assertEqual(MANIFEST_DIGEST, reference.digest)
        self.assertIsNone(reference.tag)

    def test_an_omitted_tag_means_latest(self) -> None:
        self.assertEqual("latest", parse_image_reference("ghcr.io/acme/shipping").tag)

    def test_an_unsupported_digest_algorithm_is_refused(self) -> None:
        with self.assertRaises(ContainerRegistryError):
            parse_image_reference("ghcr.io/acme/x@md5:abc")


class ResolutionTests(unittest.TestCase):
    def routes(self, **overrides):
        routes = {
            "/manifests/2.0.1": Response(
                200, MANIFEST_BODY, {"Docker-Content-Digest": MANIFEST_DIGEST},
            ),
            f"/blobs/{CONFIG_DIGEST}": Response(200, CONFIG_BODY),
        }
        routes.update(overrides)
        return routes

    def test_a_tag_resolves_to_the_digest_of_the_bytes_returned(self) -> None:
        resolved = client(self.routes()).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertEqual(MANIFEST_DIGEST, resolved.digest)
        self.assertEqual("2.0.1", resolved.reference.tag)

    def test_image_configuration_is_read_into_runtime_facts(self) -> None:
        resolved = client(self.routes()).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertEqual("amd64", resolved.architecture)
        self.assertEqual("linux", resolved.operating_system)
        self.assertEqual(("node", "src/server.js"), resolved.entrypoint)
        self.assertEqual("node", resolved.user)
        self.assertEqual(("8080/tcp",), resolved.exposed_ports)
        self.assertEqual(2, len(resolved.layers))

    def test_a_registry_whose_header_disagrees_with_its_body_is_refused(self) -> None:
        routes = self.routes(**{
            "/manifests/2.0.1": Response(
                200, MANIFEST_BODY, {"Docker-Content-Digest": digest_of(b"something else")},
            ),
        })
        # A header is the registry's claim; the bytes are the evidence. Trusting the claim would
        # let a proxy hand back any identity it liked.
        with self.assertRaises(ContainerRegistryError) as raised:
            client(routes).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertIn("does not match", str(raised.exception))

    def test_os_package_inventory_is_reported_as_not_collected(self) -> None:
        resolved = client(self.routes()).resolve("ghcr.io/acme/shipping:2.0.1")
        # Reading metadata is not reading a filesystem. Claiming coverage here would let a
        # vulnerability question be answered from an inventory that was never taken.
        self.assertEqual("NOT_COLLECTED", resolved.coverage["os_packages"])
        self.assertEqual("AVAILABLE", resolved.coverage["manifest"])

    def test_an_unreadable_config_still_yields_the_digest_as_a_partial_answer(self) -> None:
        routes = self.routes(**{f"/blobs/{CONFIG_DIGEST}": Response(404, b"")})
        resolved = client(routes).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertEqual(MANIFEST_DIGEST, resolved.digest)
        self.assertEqual("NOT_COLLECTED", resolved.coverage["config"])
        self.assertTrue(any("config could not be read" in item for item in resolved.limitations))


class ManifestListTests(unittest.TestCase):
    def routes(self):
        return {
            "/manifests/2.0.1": Response(
                200, INDEX_BODY, {"Docker-Content-Digest": INDEX_DIGEST},
            ),
            f"/manifests/{PLATFORM_DIGEST}": Response(200, PLATFORM_BODY),
            f"/blobs/{CONFIG_DIGEST}": Response(200, CONFIG_BODY),
        }

    def test_the_index_digest_is_the_identity_and_the_platform_is_recorded_separately(self) -> None:
        resolved = client(self.routes()).resolve("ghcr.io/acme/shipping:2.0.1")
        # A deployment references the list, not a platform underneath it.
        self.assertEqual(INDEX_DIGEST, resolved.digest)
        self.assertEqual(PLATFORM_DIGEST, resolved.platform_digest)

    def test_platform_selection_is_deterministic_rather_than_first_listed(self) -> None:
        resolved = client(self.routes()).resolve("ghcr.io/acme/shipping:2.0.1")
        # The windows variant is listed first; reading whichever came first would make the same
        # image resolve to different contents on different days.
        self.assertEqual("linux", resolved.operating_system)
        self.assertEqual("amd64", resolved.architecture)

    def test_an_index_with_no_supported_platform_says_so_and_keeps_the_digest(self) -> None:
        index = {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {"digest": digest_of(b"w"), "platform": {"os": "windows", "architecture": "amd64"}},
            ],
        }
        body = json.dumps(index).encode()
        resolved = client({
            "/manifests/2.0.1": Response(200, body, {"Docker-Content-Digest": digest_of(body)}),
        }).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertEqual(digest_of(body), resolved.digest)
        self.assertEqual("NOT_COLLECTED", resolved.coverage["layers"])
        self.assertTrue(any("manifest list" in item for item in resolved.limitations))


class SafetyTests(unittest.TestCase):
    def test_a_registry_off_the_allowlist_is_never_contacted(self) -> None:
        transport = Transport({})
        registry = ContainerRegistryClient(transport)
        with self.assertRaises(ContainerRegistryError) as raised:
            registry.resolve("evil.example.com/acme/x:1")
        self.assertIn("allowlist", str(raised.exception))
        # The point is that no request happened, not that one failed.
        self.assertEqual([], transport.requests)

    def test_a_redirect_off_the_allowlist_is_refused(self) -> None:
        routes = {
            "/manifests/2.0.1": Response(
                200, MANIFEST_BODY, {"Docker-Content-Digest": MANIFEST_DIGEST},
                final_url="https://exfiltrate.example.com/v2/acme/shipping/manifests/2.0.1",
            ),
        }
        with self.assertRaises(ContainerRegistryError) as raised:
            client(routes).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertIn("not allowlisted", str(raised.exception))

    def test_credentials_are_never_guessed_at(self) -> None:
        routes = {"/manifests/2.0.1": Response(401, b"")}
        with self.assertRaises(ContainerRegistryError) as raised:
            client(routes).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertIn("credentials StackGraph does not hold", str(raised.exception))
        self.assertEqual(401, raised.exception.status_code)

    def test_rate_limiting_and_server_errors_are_retriable_but_a_404_is_not(self) -> None:
        with self.assertRaises(ContainerRegistryError) as throttled:
            client({"/manifests/2.0.1": Response(429, b"")}).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertTrue(throttled.exception.retriable)
        with self.assertRaises(ContainerRegistryError) as missing:
            client({"/manifests/2.0.1": Response(404, b"")}).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertFalse(missing.exception.retriable)

    def test_an_oversized_response_is_refused_rather_than_buffered(self) -> None:
        routes = {"/manifests/2.0.1": Response(200, b"x" * 4096)}
        with self.assertRaises(ContainerRegistryError) as raised:
            client(routes, max_manifest_bytes=1024).resolve("ghcr.io/acme/shipping:2.0.1")
        self.assertIn("byte bound", str(raised.exception))

    def test_the_default_allowlist_holds_no_wildcard(self) -> None:
        self.assertTrue(all("*" not in host for host in DEFAULT_ALLOWED_REGISTRIES))


if __name__ == "__main__":
    unittest.main()

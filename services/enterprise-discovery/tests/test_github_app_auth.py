from __future__ import annotations

import base64
import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from stackgraph_discovery.github_app_auth import (
    GitHubAppTokenBroker,
    create_app_jwt,
    resolve_runtime_credential,
)
from stackgraph_discovery.github_client import HttpResponse


class _TokenTransport:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.requests: list[tuple[str, dict[str, str], bytes]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.requests.append((url, dict(headers), body))
        token_number = len(self.requests)
        return HttpResponse(
            status=201,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "token": f"ghs_short_lived_{token_number}",
                "expires_at": (self.now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            }).encode("utf-8"),
        )


class GitHubAppAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    def test_app_jwt_has_required_rs256_claims(self) -> None:
        token = create_app_jwt(
            "12345", self.private_key, issued_at=1_700_000_000, expires_at=1_700_000_540,
        )
        header, payload, signature = token.split(".")
        self.assertEqual(_decode_segment(header), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(
            _decode_segment(payload),
            {"exp": 1_700_000_540, "iat": 1_700_000_000, "iss": "12345"},
        )
        self.assertTrue(signature)

    def test_broker_mints_and_caches_installation_token(self) -> None:
        now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
        transport = _TokenTransport(now)
        clock = [now.timestamp()]
        broker = GitHubAppTokenBroker(
            base_url="https://api.github.test",
            transport=transport,
            clock=lambda: clock[0],
        )

        first = broker.token("9876", app_id="12345", private_key_pem=self.private_key)
        second = broker.token("9876", app_id="12345", private_key_pem=self.private_key)

        self.assertEqual(first, "ghs_short_lived_1")
        self.assertEqual(second, first)
        self.assertEqual(len(transport.requests), 1)
        url, headers, body = transport.requests[0]
        self.assertEqual(url, "https://api.github.test/app/installations/9876/access_tokens")
        self.assertEqual(body, b"{}")
        self.assertTrue(headers["Authorization"].startswith("Bearer ey"))
        self.assertNotIn(first, repr(transport.requests))

        clock[0] += 56 * 60
        refreshed = broker.token("9876", app_id="12345", private_key_pem=self.private_key)
        self.assertEqual(refreshed, "ghs_short_lived_2")
        self.assertEqual(len(transport.requests), 2)

    def test_runtime_resolver_checks_reference_and_supports_escaped_pem(self) -> None:
        now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
        broker = GitHubAppTokenBroker(
            base_url="https://api.github.test",
            transport=_TokenTransport(now),
            clock=lambda: now.timestamp(),
        )
        value = resolve_runtime_credential(
            "github-app://installation/9876",
            installation_id="9876",
            environment={
                "GITHUB_APP_ID": "12345",
                "GITHUB_APP_PRIVATE_KEY": self.private_key.replace("\n", "\\n"),
            },
            broker=broker,
        )
        self.assertEqual(value, "ghs_short_lived_1")
        with self.assertRaisesRegex(ValueError, "does not match"):
            resolve_runtime_credential(
                "github-app://installation/1111",
                installation_id="9876",
                environment={
                    "GITHUB_APP_ID": "12345",
                    "GITHUB_APP_PRIVATE_KEY": self.private_key,
                },
                broker=broker,
            )

    def test_runtime_resolver_supports_encrypted_tenant_token_reference(self) -> None:
        tenant_id = UUID("00000000-0000-4000-8000-000000000123")
        with patch(
            "stackgraph_discovery.github_installation_store.resolve_tenant_secret_credential",
            return_value="github-token-from-database",
        ) as resolve:
            value = resolve_runtime_credential(
                "tenant-secret://github-token",
                database_url="postgresql://database/stackgraph",
                tenant_id=tenant_id,
                credential_encryption_key="encryption-key-with-at-least-32-chars",
            )

        self.assertEqual(value, "github-token-from-database")
        resolve.assert_called_once_with(
            "tenant-secret://github-token",
            database_url="postgresql://database/stackgraph",
            tenant_id=tenant_id,
            encryption_key="encryption-key-with-at-least-32-chars",
        )


def _decode_segment(value: str) -> dict[str, object]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import hmac
import json
import unittest

from stackgraph_discovery.github_webhook import verify_github_webhook


SECRET = "webhook-secret"


def headers(body: bytes, *, delivery_id: str = "delivery-123", event: str = "push") -> dict:
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Hookshot/example",
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": f"sha256={digest}",
    }


class GitHubWebhookVerificationTests(unittest.TestCase):
    def test_verifies_before_parsing_and_retains_only_safe_headers(self) -> None:
        body = json.dumps({
            "installation": {"id": 9876},
            "ref": "refs/heads/main",
            "after": "a" * 40,
        }).encode()

        webhook = verify_github_webhook(headers(body), body, secret=SECRET)

        self.assertEqual(webhook.installation_id, "9876")
        self.assertEqual(webhook.event_type, "push")
        self.assertEqual(webhook.delivery_id, "delivery-123")
        self.assertRegex(webhook.body_hash, r"^sha256:[a-f0-9]{64}$")
        self.assertNotIn("x-hub-signature-256", webhook.safe_headers)
        self.assertEqual(webhook.safe_headers["x-github-event"], "push")

    def test_rejects_bad_signature_and_malformed_delivery_identity(self) -> None:
        body = json.dumps({"installation": {"id": 9876}}).encode()
        invalid = headers(body)
        invalid["X-Hub-Signature-256"] = "sha256=" + "0" * 64
        with self.assertRaises(PermissionError):
            verify_github_webhook(invalid, body, secret=SECRET)

        invalid_delivery = headers(body, delivery_id="bad delivery")
        with self.assertRaisesRegex(ValueError, "delivery ID"):
            verify_github_webhook(invalid_delivery, body, secret=SECRET)

    def test_accepts_signed_ping_without_tenant_installation(self) -> None:
        body = json.dumps({"zen": "Design for failure."}).encode()
        webhook = verify_github_webhook(
            headers(body, event="ping"), body, secret=SECRET,
        )
        self.assertEqual(webhook.event_type, "ping")
        self.assertIsNone(webhook.installation_id)


if __name__ == "__main__":
    unittest.main()

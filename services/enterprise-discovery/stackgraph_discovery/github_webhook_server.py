from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .evidence_store import EvidenceStore, evidence_store_from_environment
from .github_webhook import MAX_WEBHOOK_BYTES, verify_github_webhook
from .github_webhook_store import process_github_webhook


LOGGER = logging.getLogger(__name__)


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value:
        raise ValueError(f"{name} is required")
    return value


def handler(
    *,
    database_url: str,
    webhook_secret: str,
    evidence_store: EvidenceStore,
) -> type[BaseHTTPRequestHandler]:
    class GitHubWebhookHandler(BaseHTTPRequestHandler):
        server_version = "StackGraphGitHubWebhook/1.0"

        def do_GET(self) -> None:
            if self.path == "/health/live":
                self._write(200, {"status": "ok"})
            else:
                self._write(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/webhooks/github":
                self._write(404, {"error": "not found"})
                return
            length_value = self.headers.get("Content-Length")
            try:
                length = int(length_value or "")
            except ValueError:
                self._write(411, {"error": "a valid content length is required"})
                return
            if length < 0 or length > MAX_WEBHOOK_BYTES:
                self._write(413, {"error": "webhook body is too large"})
                return
            body = self.rfile.read(length)
            try:
                webhook = verify_github_webhook(
                    dict(self.headers.items()), body, secret=webhook_secret,
                )
                if webhook.event_type == "ping":
                    self._write(
                        202,
                        {
                            "delivery_id": webhook.delivery_id,
                            "status": "IGNORED",
                            "replayed": False,
                        },
                    )
                    return
                result = process_github_webhook(
                    database_url, webhook, evidence_store=evidence_store,
                )
            except PermissionError:
                self._write(401, {"error": "signature verification failed"})
                return
            except ValueError as error:
                status = 404 if "not registered" in str(error) else 400
                self._write(status, {"error": str(error)})
                return
            except Exception:
                LOGGER.exception("GitHub webhook processing failed")
                self._write(500, {"error": "webhook processing failed"})
                return
            self._write(
                202,
                {
                    "delivery_id": result.delivery_id,
                    "status": result.status,
                    "replayed": result.replayed,
                },
            )

        def _write(self, status: int, value: dict[str, Any]) -> None:
            content = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            # Avoid the default user-agent/referrer logging surface. The delivery
            # record contains the safe operational headers needed for diagnosis.
            return

    return GitHubWebhookHandler


def main() -> None:
    database_url = _required_environment("STACKGRAPH_DATABASE_URL")
    webhook_secret = _required_environment("GITHUB_WEBHOOK_SECRET")
    host = os.environ.get("STACKGRAPH_GITHUB_WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("STACKGRAPH_GITHUB_WEBHOOK_PORT", "8090"))
    if port < 1 or port > 65535:
        raise ValueError("STACKGRAPH_GITHUB_WEBHOOK_PORT must be a valid TCP port")
    server = ThreadingHTTPServer(
        (host, port),
        handler(
            database_url=database_url,
            webhook_secret=webhook_secret,
            evidence_store=evidence_store_from_environment(),
        ),
    )
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()

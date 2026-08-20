from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .github_installation import validate_installation_id


DELIVERY_ID = re.compile(r"^[A-Za-z0-9-]{1,128}$")
EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SIGNATURE = re.compile(r"^sha256=([a-f0-9]{64})$")
MAX_WEBHOOK_BYTES = 10 * 1024 * 1024
SAFE_HEADER_NAMES = {"content-type", "user-agent", "x-github-delivery", "x-github-event"}


@dataclass(frozen=True, slots=True)
class VerifiedGitHubWebhook:
    delivery_id: str
    event_type: str
    event_action: str | None
    installation_id: str | None
    body_hash: str
    safe_headers: Mapping[str, str]
    payload: Mapping[str, Any]
    raw_body: bytes


def verify_github_webhook(
    headers: Mapping[str, str],
    body: bytes,
    *,
    secret: str,
) -> VerifiedGitHubWebhook:
    if not secret:
        raise ValueError("GitHub webhook secret is not configured")
    if len(body) > MAX_WEBHOOK_BYTES:
        raise ValueError("GitHub webhook body exceeds the configured limit")
    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    signature = normalized.get("x-hub-signature-256", "")
    match = SIGNATURE.fullmatch(signature)
    if match is None:
        raise PermissionError("GitHub webhook signature is missing or malformed")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, match.group(1)):
        raise PermissionError("GitHub webhook signature verification failed")
    delivery_id = normalized.get("x-github-delivery", "")
    event_type = normalized.get("x-github-event", "")
    if not DELIVERY_ID.fullmatch(delivery_id):
        raise ValueError("GitHub webhook delivery ID is invalid")
    if not EVENT_TYPE.fullmatch(event_type):
        raise ValueError("GitHub webhook event type is invalid")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GitHub webhook body is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError("GitHub webhook body must be a JSON object")
    installation = payload.get("installation")
    if event_type == "ping" and installation is None:
        installation_id = None
    elif not isinstance(installation, Mapping):
        raise ValueError("GitHub webhook has no installation identity")
    else:
        installation_id = str(installation.get("id") or "")
        validate_installation_id(installation_id)
    action = payload.get("action")
    if action is not None and not isinstance(action, str):
        raise ValueError("GitHub webhook action must be a string")
    return VerifiedGitHubWebhook(
        delivery_id=delivery_id,
        event_type=event_type,
        event_action=action,
        installation_id=installation_id,
        body_hash=f"sha256:{hashlib.sha256(body).hexdigest()}",
        safe_headers={key: value for key, value in normalized.items() if key in SAFE_HEADER_NAMES},
        payload=payload,
        raw_body=body,
    )

"""Render API responses into tool output that stays inside an agent's context budget."""

from __future__ import annotations

import json
from typing import Any

import httpx

TRUNCATION_NOTE = (
    "\n\n[truncated after {shown} of {total} characters. Narrow the result: pass 'limit'/'cursor' "
    "where the operation supports paging, or filter with the parameters listed by "
    "stackgraph_describe_operation.]"
)


def truncate(text: str, max_chars: int) -> str:
    """Cap ``text`` at ``max_chars``, appending a note that says how to ask for less.

    Args:
        text: The rendered response.
        max_chars: Maximum characters of payload to keep.

    Returns:
        str: ``text`` unchanged when it fits, otherwise a truncated copy with a note.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + TRUNCATION_NOTE.format(shown=max_chars, total=len(text))


def render_response(response: httpx.Response, *, max_chars: int) -> str:
    """Render a successful API response as tool output.

    Args:
        response: A 2xx response from the StackGraph API.
        max_chars: Truncation budget for the rendered payload.

    Returns:
        str: Pretty-printed JSON, the raw body when it is not JSON, or a short status
        line for empty responses such as 204 No Content.
    """
    if response.status_code == 204 or not response.content:
        return f"OK ({response.status_code}). The operation returned no content."

    try:
        payload: Any = response.json()
    except (json.JSONDecodeError, ValueError):
        return truncate(response.text, max_chars)

    return truncate(json.dumps(payload, indent=2, ensure_ascii=False), max_chars)


def render_json(payload: Any, *, max_chars: int) -> str:
    """Pretty-print a locally built payload under the same truncation budget."""
    return truncate(json.dumps(payload, indent=2, ensure_ascii=False), max_chars)

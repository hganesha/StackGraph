from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib import error, request


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/+:-]*", re.IGNORECASE)


@dataclass(frozen=True)
class EmbeddingResult:
    values: list[float]
    token_count: int
    latency_ms: int
    usage: dict[str, Any]
    request_id: str | None = None


class EmbeddingFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        retry_after_seconds: float | None = None,
        failure_kind: str = "EMBEDDING_FAILURE",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.failure_kind = failure_kind


class EmbeddingAdapter(Protocol):
    def embed(self, content: str, *, dimensions: int, model: str) -> EmbeddingResult: ...


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _features(content: str) -> Iterable[tuple[str, float]]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(content)]
    for token in tokens:
        yield "word:" + token, 1.0
        padded = f"^{token}$"
        for index in range(max(0, len(padded) - 2)):
            yield "tri:" + padded[index:index + 3], 0.25
    for left, right in zip(tokens, tokens[1:]):
        yield f"pair:{left}:{right}", 0.5


def local_hash_embedding(content: str, dimensions: int) -> list[float]:
    if dimensions < 8:
        raise ValueError("embedding dimensions must be at least 8")
    values = [0.0] * dimensions
    for feature, weight in _features(content):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        values[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class LocalHashEmbeddingAdapter:
    def embed(self, content: str, *, dimensions: int, model: str) -> EmbeddingResult:
        started = time.perf_counter()
        values = local_hash_embedding(content, dimensions)
        return EmbeddingResult(
            values=values,
            token_count=len(TOKEN_PATTERN.findall(content)),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            usage={"adapter": "LOCAL", "model": model},
        )


class OpenAICompatibleEmbeddingAdapter:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def embed(self, content: str, *, dimensions: int, model: str) -> EmbeddingResult:
        body = canonical_json({"input": content, "model": model, "dimensions": dimensions}).encode("utf-8")
        outbound = request.Request(
            f"{self.base_url}/embeddings",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                values = [float(value) for value in payload["data"][0]["embedding"]]
                if len(values) != dimensions:
                    raise EmbeddingFailure("provider returned unexpected dimensions", retryable=False)
                usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
                return EmbeddingResult(
                    values=values,
                    token_count=int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0),
                    latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
                    usage=usage,
                    request_id=response.headers.get("x-request-id"),
                )
        except error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            retry_after_seconds = float(retry_after) if retry_after and retry_after.isdigit() else None
            retryable = exc.code in {408, 409, 425, 429} or exc.code >= 500
            raise EmbeddingFailure(
                f"embedding provider returned HTTP {exc.code}",
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
                failure_kind=("EMBEDDING_RATE_LIMIT" if exc.code == 429 else "EMBEDDING_PROVIDER_HTTP"),
            ) from exc
        except (error.URLError, TimeoutError) as exc:
            raise EmbeddingFailure(
                "embedding provider is unavailable",
                retryable=True,
                failure_kind="EMBEDDING_PROVIDER_UNAVAILABLE",
            ) from exc


def render_entity_document(
    entity: Mapping[str, Any],
    relationships: Iterable[Mapping[str, Any]],
    *,
    template_version: str,
) -> tuple[str, list[str]]:
    properties = entity.get("properties") if isinstance(entity.get("properties"), Mapping) else {}
    sections: list[str] = [
        f"entity type: {entity.get('entity_type', '')}",
        f"name: {entity.get('name', '')}",
    ]
    for key in ("purpose", "description", "definition", "summary", "lifecycle_state", "owner"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(f"{key.replace('_', ' ')}: {value.strip()}")
    fact_ids: list[str] = []
    relationship_rows = sorted(
        relationships,
        key=lambda row: (str(row.get("predicate") or ""), str(row.get("object_name") or ""), str(row.get("fact_id") or "")),
    )
    for row in relationship_rows:
        fact_ids.append(str(row["fact_id"]))
        target = row.get("object_name") or row.get("object_text")
        if target:
            sections.append(f"{str(row.get('predicate') or '').lower().replace('_', ' ')}: {target}")
    content = f"template: {template_version}\n" + "\n".join(sections)
    return content, fact_ids


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in values) + "]"

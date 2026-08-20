from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any
from uuid import UUID

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                parsed_length = int(raw_length)
                if parsed_length < 0 or parsed_length > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return
        if scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        buffered: list[Message] = []
        received = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if buffered:
                return buffered.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"code":"REQUEST_TOO_LARGE","message":"The request body exceeds the configured limit."}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


class RateLimiter:
    def __init__(self, database: Any | None = None) -> None:
        self.database = database if hasattr(database, "fetch_one") else None
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def check(
        self,
        *,
        tenant_id: UUID | None,
        actor_key: str,
        bucket: str,
        limit: int,
    ) -> tuple[bool, int]:
        window = int(time.time() // 60)
        if self.database is not None and tenant_id is not None:
            row = await self.database.fetch_one(
                """
                WITH expired AS (
                  DELETE FROM api_rate_limit_window
                  WHERE window_started_at < now()-interval '2 minutes'
                )
                INSERT INTO api_rate_limit_window(
                  tenant_id,actor_key,route_bucket,window_started_at,request_count
                )
                SELECT %s,%s,%s,date_trunc('minute',now()),1
                WHERE EXISTS (SELECT 1 FROM tenant WHERE id=%s)
                ON CONFLICT (tenant_id,actor_key,route_bucket,window_started_at)
                DO UPDATE SET request_count=api_rate_limit_window.request_count+1
                RETURNING request_count
                """,
                (tenant_id, actor_key, bucket, tenant_id),
                tenant_id=tenant_id,
            )
            if row is not None:
                count = int(row["request_count"])
                return count <= limit, max(0, limit - count)

        # An unknown tenant must still reach normal authorization handling. Keep
        # its abuse counter process-local instead of allowing limiter persistence
        # to turn a tenant-scoped 404 into a foreign-key 500.
        key = (str(tenant_id or "global"), actor_key, bucket, window)
        async with self._lock:
            self._counts[key] += 1
            count = self._counts[key]
            for old_key in list(self._counts):
                if old_key[2] == bucket and old_key[3] < window - 1:
                    del self._counts[old_key]
        return count <= limit, max(0, limit - count)

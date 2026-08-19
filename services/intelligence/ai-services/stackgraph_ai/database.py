from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row


class PostgresDatabase:
    """Small async database adapter shared by prompt catalogs and audit recording."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self.database_url = database_url

    @asynccontextmanager
    async def session(
        self,
        tenant_id: UUID | None = None,
    ) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
        connection = await AsyncConnection.connect(
            self.database_url,
            row_factory=dict_row,
        )
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(tenant_id) if tenant_id else "",),
                )
                yield connection
        finally:
            await connection.close()

    async def fetch_one(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
        *,
        tenant_id: UUID | None = None,
    ) -> Mapping[str, Any] | None:
        async with self.session(tenant_id) as connection:
            cursor = await connection.execute(query, params)
            return await cursor.fetchone()

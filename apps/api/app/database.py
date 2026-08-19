from dataclasses import asdict, dataclass

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import Settings


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    connected: bool
    database: str | None = None
    postgres_version: str | None = None
    age_installed: bool = False
    schema_installed: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, bool | str | None]:
        return asdict(self)


class Database:
    def __init__(self, settings: Settings) -> None:
        self._pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

    async def open(self) -> None:
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    async def check_readiness(self) -> DatabaseReadiness:
        try:
            async with self._pool.connection(timeout=3) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT
                            current_database() AS database,
                            current_setting('server_version') AS postgres_version,
                            EXISTS (
                                SELECT 1 FROM pg_extension WHERE extname = 'age'
                            ) AS age_installed,
                            to_regclass('public.entity') IS NOT NULL AS schema_installed
                        """
                    )
                    row = await cursor.fetchone()
        except Exception as error:  # readiness must report failures without crashing the API
            return DatabaseReadiness(connected=False, error=type(error).__name__)

        if row is None:
            return DatabaseReadiness(connected=False, error="EmptyReadinessResult")

        return DatabaseReadiness(
            connected=True,
            database=row["database"],
            postgres_version=row["postgres_version"],
            age_installed=row["age_installed"],
            schema_installed=row["schema_installed"],
        )

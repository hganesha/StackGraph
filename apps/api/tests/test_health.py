import asyncio

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.config import Settings
from app.database import DatabaseReadiness
from app.main import create_app


class StubDatabase:
    def __init__(self, readiness: DatabaseReadiness) -> None:
        self.readiness = readiness

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def check_readiness(self) -> DatabaseReadiness:
        return self.readiness


async def get(app: FastAPI, path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


def test_liveness_does_not_depend_on_database() -> None:
    app = create_app(
        settings=Settings(environment="test"),
        database=StubDatabase(DatabaseReadiness(connected=False, error="offline")),
    )

    response = asyncio.run(get(app, "/health/live"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "stackgraph-api",
        "environment": "test",
    }


def test_readiness_reports_initialized_database() -> None:
    app = create_app(
        settings=Settings(environment="test"),
        database=StubDatabase(
            DatabaseReadiness(
                connected=True,
                database="stackgraph",
                postgres_version="16.10",
                age_installed=True,
                schema_installed=True,
            )
        ),
    )

    response = asyncio.run(get(app, "/health/ready"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    app = create_app(
        settings=Settings(environment="test"),
        database=StubDatabase(DatabaseReadiness(connected=False, error="PoolTimeout")),
    )

    response = asyncio.run(get(app, "/health/ready"))

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"

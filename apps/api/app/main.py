from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.database import Database, DatabaseReadiness


class DatabaseProtocol(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def check_readiness(self) -> DatabaseReadiness: ...


def create_app(
    *,
    settings: Settings | None = None,
    database: DatabaseProtocol | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app_database = database or Database(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await app_database.open()
        try:
            yield
        finally:
            await app_database.close()

    application = FastAPI(
        title="StackGraph API",
        version="0.1.0",
        description="Evidence-backed software estate intelligence API.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = app_database

    @application.get("/health/live", tags=["operations"])
    async def live(request: Request) -> dict[str, str]:
        current_settings: Settings = request.app.state.settings
        return {
            "status": "ok",
            "service": current_settings.service_name,
            "environment": current_settings.environment,
        }

    @application.get(
        "/health/ready",
        tags=["operations"],
        response_model=None,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database is not ready"}},
    )
    async def ready(request: Request, response: Response) -> dict[str, object] | JSONResponse:
        current_database: DatabaseProtocol = request.app.state.database
        readiness = await current_database.check_readiness()
        payload = {
            "status": "ok" if readiness.connected and readiness.age_installed and readiness.schema_installed else "not_ready",
            "database": readiness.as_dict(),
        }
        if payload["status"] == "not_ready":
            return JSONResponse(payload, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        response.status_code = status.HTTP_200_OK
        return payload

    return application


app = create_app()

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import Authenticator
from app.config import Settings, get_settings
from app.database import Database, DatabaseReadiness
from app.errors import APIError
from app.read_models import ReadModelStore
from app.routes import ReadModelsProtocol, router


logger = logging.getLogger(__name__)


class DatabaseProtocol(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def check_readiness(self) -> DatabaseReadiness: ...


def create_app(
    *,
    settings: Settings | None = None,
    database: DatabaseProtocol | None = None,
    read_models: ReadModelsProtocol | None = None,
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
        version="1.0.0",
        description="Evidence-backed software estate intelligence API.",
        servers=[{"url": "/api/v1"}],
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = app_database
    application.state.read_models = read_models or ReadModelStore(  # type: ignore[arg-type]
        app_database,
        graph_read_mode=app_settings.graph_read_mode,
        graph_discovery_limit=app_settings.graph_discovery_limit,
    )
    application.state.authenticator = Authenticator(app_settings)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def error_payload(request: Request, code: str, message: str, details: dict | None = None) -> dict:
        payload: dict = {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", str(uuid4())),
        }
        if details is not None:
            payload["details"] = details
        return payload

    @application.exception_handler(APIError)
    async def handle_api_error(request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(
            error_payload(request, error.code, error.message, error.details),
            status_code=error.status_code,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            error_payload(request, "VALIDATION_ERROR", "The request is invalid.", {"errors": error.errors()}),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(error_payload(request, code, str(error.detail)), status_code=error.status_code)

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=error)
        return JSONResponse(
            error_payload(request, "INTERNAL_ERROR", "The server could not complete the request."),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

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

    application.include_router(router)
    application.include_router(router, prefix="/api/v1", include_in_schema=False)

    return application


app = create_app()

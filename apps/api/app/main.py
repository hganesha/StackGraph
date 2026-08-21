import logging
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import Authenticator, DatabaseTokenRevocationStore, NullTokenRevocationStore
from app.auth_routes import OIDCClient, router as auth_router
from app.abuse import RateLimiter, RequestBodyLimitMiddleware
from app.config import Settings, get_settings
from app.database import Database, DatabaseReadiness
from app.errors import APIError
from app.observability import configure_logging
from app.operations import QUERY as OPERATIONS_QUERY, normalize_metrics, prometheus_text
from app.read_models import ReadModelStore
from app.routes import AskServiceProtocol, ReadModelsProtocol, router


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
    ask_service: AskServiceProtocol | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    if app_settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=app_settings.sentry_dsn,
            environment=app_settings.environment,
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    app_database = database or Database(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await app_database.open()
        try:
            # Development auth intentionally has no external tenant directory. A migrate-only
            # local startup must still produce a writable Admin workspace, so provision the
            # configured tenant id without loading demo/seed estate data.
            if (
                app_settings.environment.strip().lower() in {"development", "dev"}
                and app_settings.auth_mode == "development"
                and app_settings.default_tenant_id is not None
            ):
                async with app_database.session(  # type: ignore[attr-defined]
                    app_settings.default_tenant_id,
                ) as connection:
                    await connection.execute(
                        """
                        INSERT INTO tenant(id,tenant_key,name,status)
                        VALUES (%s,%s,'Local workspace','ACTIVE')
                        ON CONFLICT(id) DO NOTHING
                        """,
                        (
                            app_settings.default_tenant_id,
                            f"local-{app_settings.default_tenant_id.hex[:12]}",
                        ),
                    )
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
        graph_age_timeout_seconds=app_settings.graph_age_timeout_seconds,
        credential_encryption_key=app_settings.credential_encryption_key,
    )
    environment_ask_service = None
    if ask_service is None and read_models is None and app_settings.ai_ask_enabled:
        from app.ai_ask import AIAskOrchestrator
        from stackgraph_ai import AISettings, build_ai_service

        ai_service = build_ai_service(AISettings.from_env(), database=app_database)  # type: ignore[arg-type]
        ai_service.routes.get(app_settings.ai_ask_route)
        environment_ask_service = AIAskOrchestrator(
            deterministic=application.state.read_models,
            ai=ai_service,
            route=app_settings.ai_ask_route,
            fallback_enabled=app_settings.ai_ask_fallback_enabled,
            max_evidence_chars=app_settings.ai_ask_max_evidence_chars,
        )
    if ask_service is not None:
        application.state.ask_service = ask_service
    elif read_models is not None:
        # Unit/contract tests can supply a self-contained read-model stub.
        application.state.ask_service = application.state.read_models
    else:
        from app.ai_ask import TenantConfiguredAIAskService

        application.state.ask_service = TenantConfiguredAIAskService(
            database=app_database,
            deterministic=application.state.read_models,
            encryption_key=app_settings.credential_encryption_key,
            environment_fallback=environment_ask_service,
            fallback_enabled=app_settings.ai_ask_fallback_enabled,
            max_evidence_chars=app_settings.ai_ask_max_evidence_chars,
        )
    revocations = (
        DatabaseTokenRevocationStore(app_database)
        if hasattr(app_database, "fetch_one")
        else NullTokenRevocationStore()
    )
    application.state.authenticator = Authenticator(app_settings, revocations)
    application.state.oidc_client = OIDCClient(app_settings)
    application.state.rate_limiter = RateLimiter(app_database)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=app_settings.request_body_max_bytes,
    )

    def error_payload(request: Request, code: str, message: str, details: dict | None = None) -> dict:
        payload: dict = {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", str(uuid4())),
        }
        if details is not None:
            payload["details"] = details
        return payload

    @application.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        started_at = time.perf_counter()
        inbound_request_id = request.headers.get("X-Request-ID", "")
        request_id = inbound_request_id[:128] if inbound_request_id.isprintable() else ""
        request_id = request_id or str(uuid4())
        request.state.request_id = request_id
        path = request.url.path
        public_path = (
            path.startswith("/health/")
            or path == "/metrics"
            or path.startswith("/auth/")
            or path.startswith("/api/v1/auth/")
        )
        remaining: int | None = None
        if not public_path and request.method != "OPTIONS":
            try:
                principal = await application.state.authenticator.authenticate(
                    request.headers.get("Authorization"),
                    request.cookies.get("stackgraph_session"),
                )
                request.state.principal = principal
                bucket = "ask" if path.endswith("/ask") else "general"
                limit = (
                    app_settings.rate_limit_ask_per_minute
                    if bucket == "ask"
                    else app_settings.rate_limit_requests_per_minute
                )
                allowed, remaining = await application.state.rate_limiter.check(
                    tenant_id=principal.tenant_id,
                    actor_key=principal.actor_key,
                    bucket=bucket,
                    limit=limit,
                )
                if not allowed:
                    response = JSONResponse(
                        error_payload(
                            request,
                            "RATE_LIMITED",
                            "The per-tenant request limit has been exceeded.",
                            {"bucket": bucket, "retry_after_seconds": 60},
                        ),
                        status_code=429,
                        headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
                    )
                    response.headers["X-Request-ID"] = request_id
                    return response
            except APIError as error:
                response = JSONResponse(
                    error_payload(request, error.code, error.message, error.details),
                    status_code=error.status_code,
                )
                response.headers["X-Request-ID"] = request_id
                return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        principal = getattr(request.state, "principal", None)
        logger.info(
            "request.complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "tenant_id": getattr(principal, "tenant_id", None),
                "actor_key": getattr(principal, "actor_key", None),
            },
        )
        return response

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

    @application.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
    async def metrics(request: Request) -> PlainTextResponse:
        configured_token = app_settings.metrics_bearer_token
        authorization = request.headers.get("Authorization", "")
        supplied_token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
        if not configured_token or not secrets.compare_digest(configured_token, supplied_token):
            raise APIError(401, "METRICS_AUTH_REQUIRED", "A valid metrics bearer token is required.")
        if not hasattr(app_database, "fetch_one"):
            raise APIError(503, "METRICS_UNAVAILABLE", "Operational metrics require a database connection.")
        row = await app_database.fetch_one(  # type: ignore[attr-defined]
            OPERATIONS_QUERY,
            tenant_id=app_settings.default_tenant_id,
        )
        if row is None:
            raise APIError(503, "METRICS_UNAVAILABLE", "Operational metrics could not be collected.")
        return PlainTextResponse(
            prometheus_text(normalize_metrics(row)),
            media_type="text/plain; version=0.0.4; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    application.include_router(router)
    application.include_router(router, prefix="/api/v1", include_in_schema=False)
    application.include_router(auth_router)
    application.include_router(auth_router, prefix="/api/v1", include_in_schema=False)

    return application


app = create_app()

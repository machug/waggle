"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from waggle.auth import create_api_key_dependency, install_auth_error_handler
from waggle.database import create_engine_from_url, init_db


def _error_response(status_code: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def create_app(
    *,
    db_url: str = "",
    api_key: str = "",
    is_worker: bool = False,
) -> FastAPI:

    engine = create_engine_from_url(db_url, is_worker=is_worker) if db_url else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if engine:
            await init_db(engine)
            app.state.engine = engine
        yield
        if engine:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.engine = engine
    app.state.api_key = api_key
    verify_key = create_api_key_dependency(api_key)

    # Install auth error handler from auth module
    install_auth_error_handler(app)

    # Error handlers
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code_map = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHORIZED",
            404: "NOT_FOUND",
            409: "CONFLICT",
            429: "RATE_LIMITED",
            503: "DB_BUSY",
        }
        code = code_map.get(exc.status_code, "INTERNAL")
        detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        # If detail is already our error dict, pass it through
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return _error_response(exc.status_code, code, detail_msg)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _error_response(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            {"errors": exc.errors()},
        )

    # Register routers (imported here to avoid circular imports)
    from waggle.routers import alerts, hives, readings, status, traffic

    app.include_router(hives.create_router(verify_key), prefix="/api")
    app.include_router(readings.create_router(verify_key), prefix="/api")
    app.include_router(alerts.create_router(verify_key), prefix="/api")
    app.include_router(status.create_router(), prefix="/api")
    app.include_router(traffic.create_router(verify_key), prefix="/api")

    return app

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from time import perf_counter
from uuid import uuid4

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging_config import configure_logging
from app.core.metrics import record_http_request
from app.core.request_context import request_id_var, actor_id_var
from app.core.metrics import snapshot_metrics
from app.services.rate_limiter import InMemoryLimiter, RedisSlidingWindowLimiter
import asyncio
from sqlalchemy import text
from app.db.session import engine
from redis.asyncio import from_url as redis_from_url


@asynccontextmanager
async def app_lifespan(application: FastAPI):
    yield
    if application.state.limiter_redis is not None:
        await application.state.limiter_redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Omni CRM API. Authentication uses Bearer tokens. Meta webhooks require signature "
            "verification before persistence. Rate limits and quotas are enforced per tenant and actor."
        ),
        openapi_tags=[
            {"name": "auth", "description": "Registration, sessions and Bearer authentication."},
            {"name": "webhooks", "description": "Signed Meta webhook ingress and verification."},
            {"name": "system", "description": "Health and operational endpoints."},
        ],
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
        lifespan=app_lifespan,
    )
    application.include_router(api_router, prefix="/api/v1")
    if settings.app_env == "production":
        limiter_redis = redis_from_url(settings.redis_url)
        application.state.limiter_redis = limiter_redis
        application.state.limiter = RedisSlidingWindowLimiter(limiter_redis)
    else:
        application.state.limiter_redis = None
        application.state.limiter = InMemoryLimiter()

    @application.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        snapshot = snapshot_metrics()
        lines = []
        for key, value in snapshot["http_requests_total"].items():
            route, status = key.rsplit("|", 1)
            lines.append(f'http_requests_total{{route="{route}",status="{status}"}} {value}')
        for key, value in snapshot["worker_outcomes"].items():
            job, status = key.split("|", 1)
            lines.append(f'worker_outcomes_total{{job="{job}",status="{status}"}} {value}')
        for key, value in snapshot["delivery_outcomes"].items():
            channel, status = key.split("|", 1)
            lines.append(f'delivery_outcomes_total{{channel="{channel}",status="{status}"}} {value}')
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
    configure_logging()

    @application.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request_token = request_id_var.set(request_id)
        actor_token = actor_id_var.set(None)
        started = perf_counter()
        if request.url.path not in {"/health", "/api/v1/health", "/readiness"} and not request.url.path.startswith("/api/v1/webhooks"):
            path_limit = 10 if request.url.path.startswith("/api/v1/auth") else 120
            client_ip = request.client.host if request.client else "unknown"
            limit_result = await application.state.limiter.check_limit(f"ip:{client_ip}:{request.url.path}", path_limit, 60)
            if not limit_result.allowed:
                request_id_var.reset(request_token)
                actor_id_var.reset(actor_token)
                return JSONResponse(
                    status_code=429, content={"detail": {"code": "RATE_LIMITED"}},
                    headers={"Retry-After": str(limit_result.retry_after), "X-Request-ID": request_id},
                )
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            route = getattr(request.scope.get("route"), "path", request.url.path)
            recorded_response = locals().get("response")
            record_http_request(route, recorded_response.status_code if recorded_response is not None else 500, elapsed_ms)
            request_id_var.reset(request_token)
            actor_id_var.reset(actor_token)
        response.headers["X-Request-ID"] = request_id
        return response

    def custom_openapi():
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title, version=application.version,
            description=application.description, routes=application.routes,
            tags=application.openapi_tags,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        }
        for path, operations in schema.get("paths", {}).items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                operation.setdefault("summary", f"{method.upper()} {path}")
                operation.setdefault("description", operation["summary"])
                operation.setdefault("tags", ["api"])
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]

    @application.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readiness", include_in_schema=False)
    async def readiness() -> JSONResponse:
        failing: list[str] = []
        try:
            async def check_postgres():
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            await asyncio.wait_for(check_postgres(), timeout=2)
        except Exception:
            failing.append("postgres")
        try:
            async def check_redis():
                client = redis_from_url(get_settings().redis_url)
                try:
                    await client.ping()
                finally:
                    await client.aclose()
            await asyncio.wait_for(check_redis(), timeout=2)
        except Exception:
            failing.append("redis")
        if failing:
            return JSONResponse(status_code=503, content={"status": "degraded", "failing": failing})
        return JSONResponse(status_code=200, content={"status": "ready"})

    @application.exception_handler(AppError)
    async def application_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "https://api.omni.local/errors/application",
                "title": exc.title, "status": exc.status_code, "code": exc.code,
                "detail": exc.detail, "instance": str(request.url),
            },
            media_type="application/problem+json",
        )
    return application


app = create_app()

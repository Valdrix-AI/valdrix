import asyncio
import hashlib
import inspect
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Callable, TypeVar, cast

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.shared.core.app_routes import register_api_routers, register_lifecycle_routes
from app.shared.core.app_runtime import (
    _api_documentation_allowed,
    _is_test_mode,
    _runtime_data_dir,
    _stop_emissions_tracker,
    EmissionsTracker,
)
from app.shared.core.config import get_settings, reload_settings_from_environment
from app.shared.core.cors_policy import (
    InvalidCorsConfiguration,
    resolve_cors_allowed_origins,
)
from app.shared.core.logging import setup_logging
from app.shared.core.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TrustedProxyHeadersMiddleware,
)
from app.shared.core.security_metrics import CSRF_ERRORS, RATE_LIMIT_EXCEEDED
from app.shared.core.ops_metrics import API_ERRORS_TOTAL
from app.shared.core.docs_assets import render_redoc_ui_html, render_swagger_ui_html
from app.shared.core.sentry import init_sentry
from app.shared.core.runtime_dependencies import validate_runtime_dependencies
from app.shared.core.validation_errors import sanitize_validation_errors

# SchedulerService imported lazily in lifespan() to avoid Celery blocking on startup
from app.shared.core.timeout import TimeoutMiddleware
from app.shared.core.tracing import setup_tracing
from app.shared.db.session import async_session_maker, get_engine
from app.shared.core.exceptions import ValdricsException
from app.shared.core.rate_limit import (
    setup_rate_limiting,
)

# Ensure all models are registered with SQLAlchemy

from app.modules.governance.api.v1.scim import (
    ScimError,
    scim_error_response,
)

# Configure logging and Sentry
setup_logging()
settings = get_settings()

class CsrfSettings(BaseModel):
    """Configuration for CSRF protection (Finding #5)."""
    secret_key: str
    cookie_samesite: str = "lax"

# fastapi-csrf-protect uses a decorator with a dynamic callable signature.
# Cast once to keep runtime behavior while avoiding type-ignore noise.
F = TypeVar("F", bound=Callable[..., Any])
_csrf_load_config = cast(Callable[[F], F], CsrfProtect.load_config)

def _resolve_csrf_settings() -> CsrfSettings:
    """
    Lazy initialization of CSRF settings to avoid module-load race conditions
    with environment configuration (Finding #5).
    """
    if settings.CSRF_SECRET_KEY:
        return CsrfSettings(secret_key=settings.CSRF_SECRET_KEY)
    if settings.TESTING:
        # Tests may provide an explicit key; otherwise derive an ephemeral key so
        # no hardcoded fallback secret can leak across environments.
        explicit_test_key_raw = getattr(settings, "CSRF_TEST_SECRET_KEY", None)
        if not isinstance(explicit_test_key_raw, str):
            explicit_test_key_raw = os.getenv("CSRF_TEST_SECRET_KEY", "")
        explicit_test_key = explicit_test_key_raw.strip()
        if explicit_test_key:
            return CsrfSettings(secret_key=explicit_test_key)
        pytest_current_test = getattr(settings, "PYTEST_CURRENT_TEST", None)
        if not isinstance(pytest_current_test, str):
            pytest_current_test = os.getenv("PYTEST_CURRENT_TEST")
        test_seed = f"{pytest_current_test or 'pytest'}:{os.getpid()}"
        derived_key = hashlib.sha256(test_seed.encode("utf-8")).hexdigest()
        return CsrfSettings(secret_key=f"test_csrf_{derived_key}")
    raise ValueError("CSRF_SECRET_KEY must be configured")

@_csrf_load_config
def get_csrf_config() -> CsrfSettings:
    return _resolve_csrf_settings()

logger = structlog.get_logger()
INTERNAL_METRICS_PATH = "/_internal/metrics"
API_DOCUMENTATION_PATHS = frozenset({"/openapi.json", "/docs", "/redoc"})

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global settings
    settings = reload_settings_from_environment()
    validate_runtime_dependencies(settings)
    init_sentry()

    # Setup: Initialize scheduler and emissions tracker
    logger.info("app_starting", app_name=settings.APP_NAME)

    runtime_data_dir = _runtime_data_dir()
    os.makedirs(runtime_data_dir, exist_ok=True)

    # Track app's own carbon footprint (GreenOps)
    tracker = None
    if EmissionsTracker and not _is_test_mode():
        tracker = EmissionsTracker(
            project_name=settings.APP_NAME,
            measure_power_secs=300,
            save_to_file=True,
            output_dir=runtime_data_dir,
            allow_multiple_runs=True,
        )
        tracker.start()
    else:
        logger.info(
            "emissions_tracker_skipped",
            reason="testing" if _is_test_mode() else "unavailable",
        )
    app.state.emissions_tracker = tracker

    # Pass shared session factory to scheduler (DI pattern)
    # Lazy import to avoid Celery blocking on module load
    from app.modules.governance.domain.scheduler import SchedulerService

    scheduler = SchedulerService(session_maker=async_session_maker)
    if settings.TESTING:
        logger.info("scheduler_skipped_in_testing")
    elif not settings.ENABLE_SCHEDULER:
        logger.warning("scheduler_disabled_via_config")
    elif settings.REDIS_URL:
        scheduler.start()
        logger.info("scheduler_started")
    else:
        logger.warning(
            "scheduler_skipped_no_redis", msg="Set REDIS_URL to enable background job"
        )
    app.state.scheduler = scheduler

    # Refresh LLM pricing from DB on startup (non-fatal but important for correctness).
    if settings.TESTING:
        logger.info("llm_pricing_refresh_skipped_testing")
    else:
        from app.shared.llm.pricing_data import (
            LLM_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS,
            refresh_llm_pricing,
        )
        from app.shared.core.cloud_pricing_data import (
            CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS,
            refresh_cloud_resource_pricing,
        )

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                await refresh_llm_pricing()
                logger.info("llm_pricing_refreshed", attempt=attempt)
                last_error = None
                break
            except LLM_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS as exc:
                last_error = exc
                logger.warning(
                    "llm_pricing_refresh_failed_startup",
                    attempt=attempt,
                    error=str(exc),
                    exc_info=True,
                )
                await asyncio.sleep(0.2 * attempt)
        if last_error is not None:
            # 2026 PRODUCTION STANDARD: Keep the app running to allow diagnostics,
            # but surface the risk loudly via structured logging (Finding #C3).
            # Ops should alert on 'llm_pricing_refresh_failed_startup_final'.
            logger.error(
                "llm_pricing_refresh_failed_startup_final",
                error=str(last_error),
                exc_info=True,
                remediation="Ensure database connectivity and check LLM_PROVIDER_PRICING table. "
                "Analysis functionality may use stale pricing until manual refresh.",
            )

        cloud_last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                await refresh_cloud_resource_pricing()
                logger.info("cloud_pricing_refreshed", attempt=attempt)
                cloud_last_error = None
                break
            except CLOUD_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS as exc:
                cloud_last_error = exc
                logger.warning(
                    "cloud_pricing_refresh_failed_startup",
                    attempt=attempt,
                    error=str(exc),
                    exc_info=True,
                )
                await asyncio.sleep(0.2 * attempt)
        if cloud_last_error is not None:
            logger.error(
                "cloud_pricing_refresh_failed_startup_final",
                error=str(cloud_last_error),
                exc_info=True,
                remediation="Ensure cloud_resource_pricing seeding completed. "
                "Optimization estimates may use stale or missing pricing until refresh succeeds.",
            )

    from app.shared.core.http import init_http_client, close_http_client

    # Initialize Singleton HTTP Client (2026 Pooling Standard)
    await init_http_client()

    yield

    # Teardown: Stop all services gracefully
    logger.info("Shutting down...")

    # Close HTTP pool first (prevents new requests while shutting down)
    try:
        await close_http_client()
    except RuntimeError as exc:
        logger.warning("http_client_close_skipped_loop_closed", error=str(exc))

    scheduler.stop()
    _stop_emissions_tracker(tracker)

    # Final DB Cleanup
    try:
        await get_engine().dispose()
        logger.info("db_engine_disposed")
    except RuntimeError as exc:
        logger.warning("db_engine_dispose_skipped_loop_closed", error=str(exc))

# Application instance
valdrics_app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# Justification (Finding #C1): Uvicorn requires 'app' name by default in start parameters.
# Standard pattern to resolve FastAPI type collision with module-level common variable.
app: FastAPI = valdrics_app  # noqa: A001  # type: ignore[no-redef]
router = valdrics_app

__all__ = ["app", "valdrics_app", "lifespan"]

# Initialize Tracing
setup_tracing(valdrics_app)

@valdrics_app.exception_handler(ValdricsException)
async def valdrics_exception_handler(
    request: Request, exc: ValdricsException
) -> JSONResponse:
    """Handle custom application exceptions."""
    from app.shared.core.error_governance import handle_exception
    return handle_exception(request, exc)

@valdrics_app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(
    request: Request, exc: CsrfProtectError
) -> JSONResponse:
    """Handle CSRF protection exceptions."""
    CSRF_ERRORS.labels(path=request.url.path, method=request.method).inc()
    from app.shared.core.error_governance import handle_exception
    return handle_exception(request, exc)

@valdrics_app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions with standardized format."""
    is_prod = settings.ENVIRONMENT.lower() in {"production", "staging"}
    detail_text = str(exc.detail) if isinstance(exc.detail, str) else "Request failed"
    if is_prod and exc.status_code >= 500:
        error_text = "Internal Server Error"
        message_text = "An unexpected internal error occurred"
    else:
        error_text = detail_text if isinstance(exc.detail, str) else "Error"
        message_text = detail_text

    API_ERRORS_TOTAL.labels(
        path=request.url.path, method=request.method, status_code=exc.status_code
    ).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error_text,
            "code": "HTTP_ERROR",
            "message": message_text,
        },
    )

@valdrics_app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""

    API_ERRORS_TOTAL.labels(
        path=request.url.path, method=request.method, status_code=422
    ).inc()
    return JSONResponse(
        status_code=422,
        content={
            "error": "Unprocessable Entity",
            "code": "VALIDATION_ERROR",
            "message": "The request body or parameters are invalid.",
            "details": sanitize_validation_errors(exc.errors()),
        },
    )

@valdrics_app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle business logic ValueErrors via central governance."""
    from app.shared.core.error_governance import handle_exception
    return handle_exception(request, exc)

@valdrics_app.exception_handler(ScimError)
async def scim_error_handler(_request: Request, exc: ScimError) -> JSONResponse:
    """Return SCIM-compliant error responses for /scim/v2 endpoints."""
    return scim_error_response(exc)

# Setup rate limiting early for test visibility
setup_rate_limiting(valdrics_app)

# Serve static files for local Swagger UI
valdrics_app.mount("/static", StaticFiles(directory="app/static"), name="static")

@valdrics_app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> Any:
    if not _api_documentation_allowed():
        raise HTTPException(status_code=404, detail="Not Found")
    return await render_swagger_ui_html(valdrics_app, logger=logger)

@valdrics_app.get("/redoc", include_in_schema=False)
async def redoc_html() -> Any:
    if not _api_documentation_allowed():
        raise HTTPException(status_code=404, detail="Not Found")
    return await render_redoc_ui_html(valdrics_app, logger=logger)


@valdrics_app.get("/openapi.json", include_in_schema=False)
async def openapi_schema() -> JSONResponse:
    if not _api_documentation_allowed():
        raise HTTPException(status_code=404, detail="Not Found")
    return JSONResponse(valdrics_app.openapi())

# Override handler to include metrics (SEC-03)
# MyPy: 'exception_handlers' is dynamic on FastAPI instance
original_handler = valdrics_app.exception_handlers.get(
    RateLimitExceeded, _rate_limit_exceeded_handler
)

async def custom_rate_limit_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    RATE_LIMIT_EXCEEDED.labels(
        path=request.url.path,
        method=request.method,
        tier=getattr(request.state, "tier", "unknown"),
    ).inc()
    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=getattr(exc, "status_code", 429),
    ).inc()
    res = original_handler(request, exc)
    if inspect.isawaitable(res):
        return await res
    return res

valdrics_app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

@valdrics_app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unhandled exceptions with standardized 2026 Error Governance.
    Ensures OTel trace correlation and sanitized responses.
    """
    from app.shared.core.error_governance import handle_exception

    return handle_exception(request, exc)

# Keep app entrypoint lean by registering lifecycle/health routes in a focused module.
register_lifecycle_routes(
    valdrics_app,
    app_name=settings.APP_NAME,
    version=settings.VERSION,
)

# Initialize Prometheus Metrics
Instrumentator().instrument(valdrics_app).expose(
    valdrics_app,
    endpoint=INTERNAL_METRICS_PATH,
    include_in_schema=False,
)

# IMPORTANT: Middleware order matters in FastAPI!
# Middleware is processed in REVERSE order of addition.
# CORS must be added LAST so it processes FIRST for incoming requests.

# Add timeout middleware (5 minutes for long zombie scans)
valdrics_app.add_middleware(TimeoutMiddleware, timeout_seconds=300)

# Compress larger JSON responses to reduce bandwidth/latency on dashboard-heavy endpoints
valdrics_app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers and request ID
valdrics_app.add_middleware(SecurityHeadersMiddleware)
valdrics_app.add_middleware(RequestIDMiddleware)
valdrics_app.add_middleware(TrustedProxyHeadersMiddleware)

# CORS - added LAST so it processes FIRST
# This ensures OPTIONS preflight requests are handled before other middleware
try:
    cors_allowed_origins = resolve_cors_allowed_origins(
        settings.CORS_ORIGINS,
        allow_credentials=True,
    )
except InvalidCorsConfiguration as exc:
    logger.critical(
        "insecure_cors_config_detected",
        msg=str(exc),
        configured_origins=settings.CORS_ORIGINS,
    )
    raise RuntimeError(str(exc)) from exc

valdrics_app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
)

# CSRF Protection Middleware - processes after CORS but before auth
@valdrics_app.middleware("http")
async def csrf_protect_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
        # Skip CSRF for health checks and in testing mode
        if settings.TESTING:
            return await call_next(request)

        # Public lead-gen endpoints are unauthenticated and intended for third-party forms.
        if request.url.path.startswith("/api/v1/public"):
            return await call_next(request)

        # CSRF only protects cookie-authenticated browser requests.
        # If there's no Cookie header, there's nothing to protect against.
        cookie_header = request.headers.get("cookie")
        if not cookie_header:
            return await call_next(request)

        # If the caller authenticates via an Authorization header (bearer token),
        # CSRF protection is unnecessary: browsers don't attach Authorization
        # headers implicitly like cookies. Keep CSRF for cookie/session flows.
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.strip().lower().startswith("bearer "):
            return await call_next(request)

        csrf = CsrfProtect()
        try:
            await csrf.validate_csrf(request)
        except CsrfProtectError as e:
            # Log and block
            logger.warning(
                "csrf_validation_failed",
                path=request.url.path,
                method=request.method,
            )
            return await csrf_protect_exception_handler(request, e)

    return await call_next(request)

# Register API routers in a dedicated registry module for maintainability.
register_api_routers(valdrics_app)

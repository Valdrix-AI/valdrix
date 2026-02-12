import structlog
import json
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Any, Callable, Awaitable, cast, AsyncGenerator, List, Sequence
from fastapi import FastAPI, Depends, Request, HTTPException, Response
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Gauge

from app.shared.core.config import get_settings
from app.shared.core.logging import setup_logging
from app.shared.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.shared.core.security_metrics import CSRF_ERRORS, RATE_LIMIT_EXCEEDED
from app.shared.core.ops_metrics import API_ERRORS_TOTAL
from app.shared.core.sentry import init_sentry
# SchedulerService imported lazily in lifespan() to avoid Celery blocking on startup
from app.shared.core.timeout import TimeoutMiddleware
from app.shared.core.tracing import setup_tracing
from app.shared.db.session import get_db, async_session_maker, engine
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.exceptions import ValdrixException
from app.shared.core.rate_limit import setup_rate_limiting, RateLimitExceeded, _rate_limit_exceeded_handler

# Ensure all models are registered with SQLAlchemy
import app.models.tenant
import app.models.aws_connection
import app.models.azure_connection
import app.models.gcp_connection
import app.models.saas_connection
import app.models.license_connection
import app.models.llm
import app.models.notification_settings
import app.models.remediation
import app.models.remediation_settings
import app.models.background_job
import app.models.attribution
import app.models.carbon_settings
import app.models.cost_audit
import app.models.discovered_account
import app.models.pricing
import app.models.security
import app.models.anomaly_marker
import app.models.optimization
import app.models.unit_economics_settings
import app.modules.governance.domain.security.audit_log


from app.modules.governance.api.v1.settings.onboard import router as onboard_router
from app.modules.governance.api.v1.settings.connections import router as connections_router
from app.modules.governance.api.v1.settings import router as settings_router
from app.modules.reporting.api.v1.leaderboards import router as leaderboards_router
from app.modules.reporting.api.v1.costs import router as costs_router
from app.modules.reporting.api.v1.attribution import router as attribution_router
from app.modules.reporting.api.v1.carbon import router as carbon_router
from app.modules.optimization.api.v1.zombies import router as zombies_router
from app.modules.optimization.api.v1.strategies import router as strategies_router
from app.modules.governance.api.v1.admin import router as admin_router
from app.modules.billing.api.v1.billing import router as billing_router
from app.modules.governance.api.v1.audit import router as audit_router
from app.modules.governance.api.v1.jobs import router as jobs_router
from app.modules.governance.api.v1.health_dashboard import router as health_dashboard_router
from app.modules.reporting.api.v1.usage import router as usage_router
from app.modules.governance.api.oidc import router as oidc_router
from app.modules.governance.api.v1.public import router as public_router
from app.modules.reporting.api.v1.currency import router as currency_router

# Configure logging and Sentry
setup_logging()
init_sentry()
settings = get_settings()

class CsrfSettings(BaseModel):
    """Configuration for CSRF protection."""
    secret_key: str = settings.CSRF_SECRET_KEY
    cookie_samesite: str = "lax"

@CsrfProtect.load_config # type: ignore[arg-type]
def get_csrf_config() -> CsrfSettings:
    return CsrfSettings()

logger = structlog.get_logger()

def _is_test_mode() -> bool:
    return settings.TESTING or os.getenv("PYTEST_CURRENT_TEST") is not None

def _load_emissions_tracker() -> Any:
    if _is_test_mode():
        return None
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The pynvml package is deprecated.*",
                category=FutureWarning
            )
            from codecarbon import EmissionsTracker as Tracker
        return Tracker
    except Exception as exc:
        logger.warning("emissions_tracker_unavailable", error=str(exc))
        return None

EmissionsTracker = _load_emissions_tracker()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Setup: Initialize scheduler and emissions tracker
    logger.info("app_starting", app_name=settings.APP_NAME)

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Track app's own carbon footprint (GreenOps)
    tracker = None
    if EmissionsTracker and not _is_test_mode():
        tracker = EmissionsTracker(
            project_name=settings.APP_NAME,
            measure_power_secs=300,
            save_to_file=True,
            output_dir="data",
            allow_multiple_runs=True,
        )
        tracker.start()
    else:
        logger.info("emissions_tracker_skipped", reason="testing" if _is_test_mode() else "unavailable")
    app.state.emissions_tracker = tracker

    # Pass shared session factory to scheduler (DI pattern)
    # Lazy import to avoid Celery blocking on module load
    from app.modules.governance.domain.scheduler import SchedulerService
    scheduler = SchedulerService(session_maker=async_session_maker)
    if not settings.TESTING and settings.REDIS_URL:
        scheduler.start()
        logger.info("scheduler_started")
    elif settings.TESTING:
        logger.info("scheduler_skipped_in_testing")
    else:
        logger.warning("scheduler_skipped_no_redis", msg="Set REDIS_URL to enable background job")
    app.state.scheduler = scheduler

    # Refresh LLM pricing from DB on startup (non-fatal)
    try:
        if not settings.TESTING:
            from app.shared.llm.pricing_data import refresh_llm_pricing
            await refresh_llm_pricing()
            logger.info("llm_pricing_refreshed")
        else:
            logger.info("llm_pricing_refresh_skipped_testing")
    except Exception as e:
        logger.warning("llm_pricing_refresh_failed_startup", error=str(e))

    yield

    # Teardown: Stop scheduler and tracker
    logger.info("Shutting down...")
    scheduler.stop()
    if tracker:
        tracker.stop()

    # Item 18: Async Database Engine Cleanup
    await engine.dispose()
    logger.info("db_engine_disposed")


# Application instance
valdrix_app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)
# MyPy: 'app' shadows the package name, ignore the assignment error
app = valdrix_app # type: ignore[assignment]
router = valdrix_app

# Initialize Tracing
setup_tracing(valdrix_app)

@valdrix_app.exception_handler(ValdrixException)
async def valdrix_exception_handler(request: Request, exc: ValdrixException) -> JSONResponse:
    """Handle custom application exceptions."""
    API_ERRORS_TOTAL.labels(
        path=request.url.path, 
        method=request.method, 
        status_code=exc.status_code
    ).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.message,
            "code": exc.code,
            "details": exc.details
        },
    )

@valdrix_app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError) -> JSONResponse:
    """Handle CSRF protection exceptions."""
    CSRF_ERRORS.labels(path=request.url.path, method=request.method).inc()
    API_ERRORS_TOTAL.labels(
        path=request.url.path, 
        method=request.method, 
        status_code=exc.status_code
    ).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.message,
            "code": "csrf_error"
        },
    )

@valdrix_app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions with standardized format."""
    API_ERRORS_TOTAL.labels(
        path=request.url.path, 
        method=request.method, 
        status_code=exc.status_code
    ).inc()
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else "Error",
            "code": "HTTP_ERROR",
            "message": str(exc.detail) if isinstance(exc.detail, str) else "Request failed"
        }
    )

@valdrix_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors."""
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Exception):
            return str(value)
        try:
            json.dumps(value)
            return value
        except Exception:
            return str(value)

    def _sanitize_errors(errors: Sequence[Any]) -> List[Dict[str, Any]]:
        sanitized = []
        for err in errors:
            clean = dict(err)
            if "ctx" in clean and isinstance(clean["ctx"], dict):
                clean["ctx"] = {k: _json_safe(v) for k, v in clean["ctx"].items()}
            if "input" in clean:
                clean["input"] = _json_safe(clean["input"])
            sanitized.append(clean)
        return sanitized

    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=422
    ).inc()
    return JSONResponse(
        status_code=422,
        content={
            "error": "Unprocessable Entity",
            "code": "VALIDATION_ERROR",
            "message": "The request body or parameters are invalid.",
            "details": _sanitize_errors(exc.errors())
        }
    )

@valdrix_app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle business logic ValueErrors."""
    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=400
    ).inc()
    return JSONResponse(
        status_code=400,
        content={
            "error": "Bad Request",
            "code": "VALUE_ERROR",
            "message": str(exc)
        }
    )

# Setup rate limiting early for test visibility
setup_rate_limiting(valdrix_app)

# Serve static files for local Swagger UI
valdrix_app.mount("/static", StaticFiles(directory="app/static"), name="static")

@valdrix_app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> Any:
    return get_swagger_ui_html(
        openapi_url=valdrix_app.openapi_url, # type: ignore
        title=valdrix_app.title + " - Swagger UI",
        oauth2_redirect_url=valdrix_app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        swagger_favicon_url="/static/favicon.png",
    )

@valdrix_app.get("/redoc", include_in_schema=False)
async def redoc_html() -> Any:
    return get_redoc_html(
        openapi_url=valdrix_app.openapi_url, # type: ignore
        title=valdrix_app.title + " - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js", # Redoc still remote for now
        redoc_favicon_url="/static/favicon.png",
    )

# Override handler to include metrics (SEC-03)
# MyPy: 'exception_handlers' is dynamic on FastAPI instance
original_handler = valdrix_app.exception_handlers.get(RateLimitExceeded, _rate_limit_exceeded_handler)

async def custom_rate_limit_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    RATE_LIMIT_EXCEEDED.labels(
        path=request.url.path, 
        method=request.method,
        tier=getattr(request.state, "tier", "unknown")
    ).inc()
    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=getattr(exc, "status_code", 429)
    ).inc()
    res = original_handler(request, exc)
    if asyncio.iscoroutine(res):
        return await res # type: ignore
    return cast(Response, res)

valdrix_app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

@valdrix_app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unhandled exceptions with a standardized response.
    Item 4 & 10: Prevents leaking stack traces and provides machine-readable error codes.
    Ensures NO internal variables (env or local) are leaked in the response.
    """
    from uuid import uuid4
    error_id = str(uuid4())
    
    # Log the full exception internally (Sentry or local logs)
    logger.exception("unhandled_exception", 
                     path=request.url.path, 
                     method=request.method,
                     error_id=error_id)
    API_ERRORS_TOTAL.labels(
        path=request.url.path,
        method=request.method,
        status_code=500
    ).inc()
    
    # Standardized response for end users
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please contact support with the error ID.",
            "error_id": error_id
        }
    )



# Prometheus Gauge for System Health
SYSTEM_HEALTH = Gauge("valdrix_system_health", "System health status (1=healthy, 0.5=degraded, 0=unhealthy)")

@valdrix_app.get("/", tags=["Lifecycle"])
async def root() -> Dict[str, str]:
    """Root endpoint for basic reachability."""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION}

@valdrix_app.get("/health/live", tags=["Lifecycle"])
async def liveness_check() -> Dict[str, str]:
    """Fast liveness check without dependencies."""
    return {"status": "healthy"}

@valdrix_app.get("/health", tags=["Lifecycle"])
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Any:
    """
    Enhanced health check for load balancers.
    Checks DB, Redis, and AWS STS reachability.
    """
    from app.shared.core.health import HealthService

    service = HealthService(db)
    health = await service.check_all()
    
    # Update Prometheus metrics
    status_map = {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}
    SYSTEM_HEALTH.set(status_map.get(health["status"], 0.0))
    
    # Critical dependency: Database
    if health["database"]["status"] == "down":
        return JSONResponse(
            status_code=503,
            content=health
        )
    
    return health

# Initialize Prometheus Metrics
Instrumentator().instrument(valdrix_app).expose(valdrix_app)

# IMPORTANT: Middleware order matters in FastAPI!
# Middleware is processed in REVERSE order of addition.
# CORS must be added LAST so it processes FIRST for incoming requests.

# Add timeout middleware (5 minutes for long zombie scans)
valdrix_app.add_middleware(TimeoutMiddleware, timeout_seconds=300)

# Security headers and request ID
valdrix_app.add_middleware(SecurityHeadersMiddleware)
valdrix_app.add_middleware(RequestIDMiddleware)

# CORS - added LAST so it processes FIRST
# This ensures OPTIONS preflight requests are handled before other middleware
valdrix_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
)

# CSRF Protection Middleware - processes after CORS but before auth
@valdrix_app.middleware("http")
async def csrf_protect_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
        # Skip CSRF for health checks and in testing mode
        if settings.TESTING:
            return await call_next(request)

        # Public lead-gen endpoints are unauthenticated and intended for third-party forms.
        if request.url.path.startswith("/api/v1/public"):
            return await call_next(request)

        if request.url.path.startswith("/api/v1"):
            csrf = CsrfProtect()
            try:
                await csrf.validate_csrf(request)
            except CsrfProtectError as e:
                # Log and block
                logger.warning("csrf_validation_failed", path=request.url.path, method=request.method)
                return await csrf_protect_exception_handler(request, e)

    return await call_next(request)

# Register Routers
valdrix_app.include_router(onboard_router, prefix="/api/v1/settings/onboard")
valdrix_app.include_router(connections_router, prefix="/api/v1/settings/connections")
valdrix_app.include_router(settings_router, prefix="/api/v1/settings")
valdrix_app.include_router(leaderboards_router, prefix="/api/v1/leaderboards")
valdrix_app.include_router(costs_router, prefix="/api/v1/costs")
valdrix_app.include_router(attribution_router, prefix="/api/v1/attribution")
valdrix_app.include_router(carbon_router, prefix="/api/v1/carbon")
valdrix_app.include_router(zombies_router, prefix="/api/v1/zombies")
valdrix_app.include_router(strategies_router, prefix="/api/v1/strategies")
valdrix_app.include_router(admin_router, prefix="/api/v1/admin")
valdrix_app.include_router(billing_router, prefix="/api/v1/billing")
valdrix_app.include_router(audit_router, prefix="/api/v1/audit")
valdrix_app.include_router(jobs_router, prefix="/api/v1/jobs")
valdrix_app.include_router(health_dashboard_router, prefix="/api/v1/admin/health-dashboard")
valdrix_app.include_router(usage_router, prefix="/api/v1/usage")
valdrix_app.include_router(currency_router, prefix="/api/v1/currency")
valdrix_app.include_router(oidc_router)
valdrix_app.include_router(public_router, prefix="/api/v1/public")

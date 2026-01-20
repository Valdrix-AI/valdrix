import structlog
import os
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.security_metrics import CSRF_ERRORS, RATE_LIMIT_EXCEEDED
from app.core.ops_metrics import API_ERRORS_TOTAL
from app.core.sentry import init_sentry
from app.services.scheduler import SchedulerService
from app.core.timeout import TimeoutMiddleware
from app.core.tracing import setup_tracing
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure all models are registered with SQLAlchemy
import app.models.tenant
import app.models.aws_connection
import app.models.llm
import app.models.notification_settings
import app.models.remediation
import app.models.background_job
import app.models.azure_connection
import app.models.gcp_connection
import app.services.security.audit_log


from codecarbon import EmissionsTracker
from app.api.v1.settings.onboard import router as onboard_router
from app.api.v1.settings.connections import router as connections_router
from app.api.v1.settings import router as settings_router
from app.api.v1.leaderboards import router as leaderboards_router
from app.api.v1.costs import router as costs_router
from app.api.v1.carbon import router as carbon_router
from app.api.v1.zombies import router as zombies_router
from app.api.v1.admin import router as admin_router
from app.api.v1.billing import router as billing_router
from app.api.v1.audit import router as audit_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.health_dashboard import router as health_dashboard_router
from app.api.v1.usage import router as usage_router
from app.api.oidc import router as oidc_router
from app.api.v1.public import router as public_router

# Configure logging and Sentry
setup_logging()
init_sentry()
settings = get_settings()

class CsrfSettings(BaseModel):
    """Configuration for CSRF protection."""
    secret_key: str = settings.CSRF_SECRET_KEY
    cookie_samesite: str = "lax"

@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup: Initialize scheduler and emissions tracker
    settings = get_settings()
    logger.info(f"Starting {settings.APP_NAME}...")

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Track app's own carbon footprint (GreenOps)
    tracker = EmissionsTracker(
        project_name=settings.APP_NAME,
        measure_power_secs=300,
        save_to_file=True,
        output_dir="data",
        allow_multiple_runs=True,
    )
    if not settings.TESTING:
        tracker.start()
    app.state.emissions_tracker = tracker

    # Pass shared session factory to scheduler (DI pattern)
    from app.db.session import async_session_maker
    scheduler = SchedulerService(session_maker=async_session_maker)
    if not settings.TESTING:
        scheduler.start()
        logger.info("scheduler_started")
    else:
        logger.info("scheduler_skipped_in_testing")
    app.state.scheduler = scheduler

    yield

    # Teardown: Stop scheduler and tracker
    logger.info("Shutting down...")
    scheduler.stop()
    tracker.stop()

    # Item 18: Async Database Engine Cleanup
    from app.db.session import engine
    await engine.dispose()
    logger.info("db_engine_disposed")

from fastapi.responses import JSONResponse
from app.core.exceptions import ValdrixException

# Application instance
settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Initialize Tracing
setup_tracing(app)

@app.exception_handler(ValdrixException)
async def valdrix_exception_handler(request: Request, exc: ValdrixException):
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

@app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
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

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Unprocessable Entity",
            "code": "VALIDATION_ERROR",
            "message": "The request body or parameters are invalid.",
            "details": exc.errors()
        }
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle business logic ValueErrors."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "Bad Request",
            "code": "VALUE_ERROR",
            "message": str(exc)
        }
    )

# Setup rate limiting early for test visibility
from app.core.rate_limit import setup_rate_limiting, RateLimitExceeded, _rate_limit_exceeded_handler
setup_rate_limiting(app)

# Override handler to include metrics (SEC-03)
original_handler = app.exception_handlers.get(RateLimitExceeded, _rate_limit_exceeded_handler)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    RATE_LIMIT_EXCEEDED.labels(
        path=request.url.path, 
        method=request.method,
        tier=getattr(request.state, "tier", "unknown")
    ).inc()
    return await original_handler(request, exc)

app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
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
from prometheus_client import Gauge
SYSTEM_HEALTH = Gauge("valdrix_system_health", "System health status (1=healthy, 0.5=degraded, 0=unhealthy)")

@app.get("/", tags=["Lifecycle"])
async def root():
    """Root endpoint for basic reachability."""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION}

@app.get("/health/live", tags=["Lifecycle"])
async def liveness_check():
    """Fast liveness check without dependencies."""
    return {"status": "healthy"}

@app.get("/health", tags=["Lifecycle"])
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Enhanced health check for load balancers.
    Checks DB, Redis, and AWS STS reachability.
    """
    from app.services.health import HealthService
    from fastapi import Response

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
Instrumentator().instrument(app).expose(app)

# IMPORTANT: Middleware order matters in FastAPI!
# Middleware is processed in REVERSE order of addition.
# CORS must be added LAST so it processes FIRST for incoming requests.

# Add timeout middleware (5 minutes for long zombie scans)
app.add_middleware(TimeoutMiddleware, timeout_seconds=300)

# Security headers and request ID
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS - added LAST so it processes FIRST
# This ensures OPTIONS preflight requests are handled before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# CSRF Protection Middleware - processes after CORS but before auth
@app.middleware("http")
async def csrf_protect_middleware(request: Request, call_next):
    """
    Global CSRF protection middleware.
    Blocks unsafe methods (POST, PUT, DELETE, PATCH) if CSRF token is missing/invalid.
    Allows safe methods (GET, HEAD, OPTIONS, TRACE).
    """
    if request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
        # Skip CSRF for health checks and in testing mode
        if settings.TESTING:
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
app.include_router(onboard_router, prefix="/api/v1/settings/onboard")
app.include_router(connections_router, prefix="/api/v1/settings/connections")
app.include_router(settings_router, prefix="/api/v1/settings")
app.include_router(leaderboards_router, prefix="/api/v1/leaderboards")
app.include_router(costs_router, prefix="/api/v1/costs")
app.include_router(carbon_router, prefix="/api/v1/carbon")
app.include_router(zombies_router, prefix="/api/v1/zombies")
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(billing_router, prefix="/api/v1/billing")
app.include_router(audit_router, prefix="/api/v1/audit")
app.include_router(jobs_router, prefix="/api/v1/jobs")
app.include_router(health_dashboard_router, prefix="/api/v1/admin/health-dashboard")
app.include_router(usage_router, prefix="/api/v1/usage")
app.include_router(oidc_router)
app.include_router(public_router, prefix="/api/v1/public")

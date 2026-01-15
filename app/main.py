import structlog
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.sentry import init_sentry
from app.services.scheduler import SchedulerService
from app.core.timeout import TimeoutMiddleware
from app.core.tracing import setup_tracing

# Ensure all models are registered with SQLAlchemy
import app.models.tenant
import app.models.aws_connection
import app.models.llm
import app.models.notification_settings
import app.models.remediation
import app.models.background_job
import app.models.azure_connection
import app.models.gcp_connection


from codecarbon import EmissionsTracker
from app.api.v1.onboard import router as onboard_router
from app.api.v1.connections import router as connections_router
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

# Configure logging and Sentry
setup_logging()
init_sentry()
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
    )
    tracker.start()
    app.state.emissions_tracker = tracker

    # Pass shared session factory to scheduler (DI pattern)
    from app.db.session import async_session_maker
    scheduler = SchedulerService(session_maker=async_session_maker)
    scheduler.start()
    app.state.scheduler = scheduler

    # Setup rate limiting
    from app.core.rate_limit import setup_rate_limiting
    setup_rate_limiting(app)

    yield

    # Teardown: Stop scheduler and tracker
    logger.info("Shutting down...")
    scheduler.stop()
    tracker.stop()

from fastapi import FastAPI, Request
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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.message,
            "code": exc.code,
            "details": exc.details
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An unexpected error occurred. Please try again later.",
            "code": "internal_server_error"
        },
    )

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

# Root/Health check (legacy support or moved)
@app.get("/health", tags=["Infrastructure"])
async def health_check():
    """Heartbeat endpoint."""
    scheduler_status = app.state.scheduler.get_status()
    return {
        "status": "active",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "scheduler": scheduler_status,
    }

# Register Routers
app.include_router(onboard_router)
app.include_router(connections_router)
app.include_router(settings_router)
app.include_router(leaderboards_router)
app.include_router(costs_router)
app.include_router(carbon_router)
app.include_router(zombies_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(audit_router)
app.include_router(jobs_router)
app.include_router(health_dashboard_router)
app.include_router(usage_router)
app.include_router(oidc_router)

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.db.session import get_system_db

SYSTEM_HEALTH = Gauge(
    "valdrics_system_health",
    "System health status (1=healthy, 0.5=degraded, 0=unhealthy)",
)

_REQUIRED_API_PREFIXES = {
    "/api/v1/admin",
    "/api/v1/admin/health-dashboard",
    "/api/v1/audit",
    "/api/v1/attribution",
    "/api/v1/billing",
    "/api/v1/carbon",
    "/api/v1/costs",
    "/api/v1/currency",
    "/api/v1/enforcement",
    "/api/v1/jobs",
    "/api/v1/leaderboards",
    "/api/v1/leadership",
    "/api/v1/public",
    "/api/v1/savings",
    "/api/v1/settings",
    "/api/v1/settings/connections",
    "/api/v1/settings/onboard",
    "/api/v1/strategies",
    "/api/v1/usage",
    "/api/v1/zombies",
    "/scim/v2",
}


def _validate_router_registry(routes: list[tuple[Any, str | None]]) -> None:
    seen_prefixes: set[str] = set()
    for router, prefix in routes:
        route_list = getattr(router, "routes", None)
        if not isinstance(route_list, list) or not route_list:
            raise RuntimeError("Router registry includes an empty router definition")
        if prefix is None:
            continue
        normalized_prefix = prefix.strip()
        if not normalized_prefix.startswith("/"):
            raise RuntimeError(f"Router prefix must start with '/': {prefix!r}")
        if normalized_prefix in seen_prefixes:
            raise RuntimeError(f"Duplicate router prefix registered: {normalized_prefix}")
        seen_prefixes.add(normalized_prefix)

    missing_prefixes = sorted(_REQUIRED_API_PREFIXES - seen_prefixes)
    if missing_prefixes:
        raise RuntimeError(
            "Router registry is missing required API prefixes: "
            + ", ".join(missing_prefixes)
        )

    unexpected_prefixes = sorted(seen_prefixes - _REQUIRED_API_PREFIXES)
    if unexpected_prefixes:
        raise RuntimeError(
            "Router registry includes unexpected API prefixes: "
            + ", ".join(unexpected_prefixes)
        )


def register_lifecycle_routes(
    app: FastAPI,
    *,
    app_name: str,
    version: str,
) -> None:
    """Register lifecycle and health endpoints."""

    @app.get("/", tags=["Lifecycle"])
    async def root() -> dict[str, str]:
        """Root endpoint for basic reachability."""
        return {"status": "ok", "app": app_name, "version": version}

    @app.get("/health/live", tags=["Lifecycle"])
    async def liveness_check() -> dict[str, str]:
        """Fast liveness check without dependencies."""
        return {"status": "healthy"}

    @app.get("/health", tags=["Lifecycle"])
    async def health_check(db: Annotated[AsyncSession, Depends(get_system_db)]) -> Any:
        """
        Enhanced health check for load balancers.
        Checks DB, Redis, and AWS STS reachability.
        """
        from app.shared.core.health import HealthService

        service = HealthService(db)
        health = await service.check_all()

        status_map = {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}
        SYSTEM_HEALTH.set(status_map.get(health["status"], 0.0))

        if health["database"]["status"] == "down":
            return JSONResponse(status_code=503, content=health)

        return health


def register_api_routers(app: FastAPI) -> None:
    """Register API route modules in one place to keep app entrypoint focused."""
    from app.modules.billing.api.v1.billing import router as billing_router
    from app.modules.enforcement.api.v1.enforcement import router as enforcement_router
    from app.modules.governance.api.oidc import router as oidc_router
    from app.modules.governance.api.v1.admin import router as admin_router
    from app.modules.governance.api.v1.audit import router as audit_router
    from app.modules.governance.api.v1.health_dashboard import (
        router as health_dashboard_router,
    )
    from app.modules.governance.api.v1.jobs import router as jobs_router
    from app.modules.governance.api.v1.public import router as public_router
    from app.modules.governance.api.v1.scim import router as scim_router
    from app.modules.governance.api.v1.settings import router as settings_router
    from app.modules.governance.api.v1.settings.connections import (
        router as connections_router,
    )
    from app.modules.governance.api.v1.settings.onboard import (
        router as onboard_router,
    )
    from app.modules.optimization.api.v1.strategies import router as strategies_router
    from app.modules.optimization.api.v1.zombies import router as zombies_router
    from app.modules.reporting.api.v1.attribution import router as attribution_router
    from app.modules.reporting.api.v1.carbon import router as carbon_router
    from app.modules.reporting.api.v1.costs import router as costs_router
    from app.modules.reporting.api.v1.currency import router as currency_router
    from app.modules.reporting.api.v1.leadership import router as leadership_router
    from app.modules.reporting.api.v1.leaderboards import router as leaderboards_router
    from app.modules.reporting.api.v1.savings import router as savings_router
    from app.modules.reporting.api.v1.usage import router as usage_router

    routes: list[tuple[Any, str | None]] = [
        (onboard_router, "/api/v1/settings/onboard"),
        (connections_router, "/api/v1/settings/connections"),
        (settings_router, "/api/v1/settings"),
        (leaderboards_router, "/api/v1/leaderboards"),
        (costs_router, "/api/v1/costs"),
        (savings_router, "/api/v1/savings"),
        (leadership_router, "/api/v1/leadership"),
        (attribution_router, "/api/v1/attribution"),
        (carbon_router, "/api/v1/carbon"),
        (zombies_router, "/api/v1/zombies"),
        (strategies_router, "/api/v1/strategies"),
        (admin_router, "/api/v1/admin"),
        (billing_router, "/api/v1/billing"),
        (enforcement_router, "/api/v1/enforcement"),
        (audit_router, "/api/v1/audit"),
        (jobs_router, "/api/v1/jobs"),
        (health_dashboard_router, "/api/v1/admin/health-dashboard"),
        (usage_router, "/api/v1/usage"),
        (currency_router, "/api/v1/currency"),
        (oidc_router, None),
        (public_router, "/api/v1/public"),
        (scim_router, "/scim/v2"),
    ]

    _validate_router_registry(routes)

    for router, prefix in routes:
        if prefix is None:
            app.include_router(router)
        else:
            app.include_router(router, prefix=prefix)

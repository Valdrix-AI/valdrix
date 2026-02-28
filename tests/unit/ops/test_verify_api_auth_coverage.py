from __future__ import annotations

from fastapi import APIRouter, FastAPI

from scripts.verify_api_auth_coverage import (
    collect_auth_coverage_violations,
    load_app_for_audit,
)


def test_collect_auth_coverage_detects_unprotected_private_route() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/private")
    async def private_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router, prefix="/api/v1/demo")

    violations = collect_auth_coverage_violations(app)
    assert len(violations) == 1
    assert violations[0].method == "GET"
    assert violations[0].path == "/api/v1/demo/private"


def test_collect_auth_coverage_exempts_public_prefix_routes() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/status")
    async def public_status() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router, prefix="/api/v1/public")

    violations = collect_auth_coverage_violations(app)
    assert violations == []


def test_collect_auth_coverage_passes_current_application_routes() -> None:
    app = load_app_for_audit()
    violations = collect_auth_coverage_violations(app)
    assert violations == []

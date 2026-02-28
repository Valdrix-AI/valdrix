from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.shared.core.app_routes import (
    _REQUIRED_API_PREFIXES,
    _validate_router_registry,
    register_api_routers,
)


def _fake_router() -> SimpleNamespace:
    return SimpleNamespace(routes=[object()])


def test_validate_router_registry_accepts_complete_registry() -> None:
    routes = [(_fake_router(), prefix) for prefix in sorted(_REQUIRED_API_PREFIXES)]
    routes.append((_fake_router(), None))
    _validate_router_registry(routes)


def test_validate_router_registry_rejects_missing_prefix() -> None:
    routes = [(_fake_router(), "/api/v1/billing"), (_fake_router(), None)]
    with pytest.raises(RuntimeError, match="missing required API prefixes"):
        _validate_router_registry(routes)


def test_validate_router_registry_rejects_duplicate_prefix() -> None:
    routes = [
        (_fake_router(), "/api/v1/billing"),
        (_fake_router(), "/api/v1/billing"),
    ]
    with pytest.raises(RuntimeError, match="Duplicate router prefix"):
        _validate_router_registry(routes)


def test_validate_router_registry_rejects_prefix_without_leading_slash() -> None:
    routes = [(_fake_router(), "api/v1/billing")]
    with pytest.raises(RuntimeError, match="must start with '/'"):
        _validate_router_registry(routes)


def test_validate_router_registry_rejects_unexpected_prefix() -> None:
    routes = [(_fake_router(), prefix) for prefix in sorted(_REQUIRED_API_PREFIXES)]
    routes.append((_fake_router(), "/api/v1/unexpected"))
    with pytest.raises(RuntimeError, match="unexpected API prefixes"):
        _validate_router_registry(routes)


def test_validate_router_registry_rejects_empty_router_definition() -> None:
    routes = [(SimpleNamespace(routes=[]), "/api/v1/billing")]
    with pytest.raises(RuntimeError, match="empty router definition"):
        _validate_router_registry(routes)


def test_register_api_routers_exposes_required_prefixes() -> None:
    app = FastAPI()
    register_api_routers(app)

    registered_paths = {
        route.path
        for route in app.router.routes
        if isinstance(getattr(route, "path", None), str)
    }
    for prefix in sorted(_REQUIRED_API_PREFIXES):
        assert any(path.startswith(prefix) for path in registered_paths), prefix

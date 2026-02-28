#!/usr/bin/env python3
"""
Verify API auth coverage across registered routes.

Purpose:
- Enforce a machine-checkable guard for VAL-SEC-002.
- Ensure non-public API routes use an explicit authentication dependency.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi.routing import APIRoute

# Dependency call names that satisfy route-level authentication coverage.
AUTH_DEPENDENCY_CALL_NAMES = {
    "get_current_user",
    "get_current_user_from_jwt",
    "get_current_user_with_db_context",
    "get_scim_context",
    "validate_admin_key",
    "require_internal_job_secret",
}

# Intentionally unauthenticated endpoints.
PUBLIC_ROUTE_ALLOWLIST: set[tuple[str, str]] = {
    ("GET", "/.well-known/jwks.json"),
    ("GET", "/.well-known/openid-configuration"),
    ("GET", "/api/v1/billing/plans"),
    ("POST", "/api/v1/billing/webhook"),
    ("POST", "/api/v1/settings/connections/aws/setup"),
    ("GET", "/scim/v2/ServiceProviderConfig"),
    ("GET", "/scim/v2/Schemas"),
    ("GET", "/scim/v2/Schemas/{schema_id:path}"),
    ("GET", "/scim/v2/ResourceTypes"),
}

PUBLIC_PREFIX_ALLOWLIST = ("/api/v1/public",)
MONITORED_PREFIXES = ("/api/v1", "/scim/v2", "/.well-known")


@dataclass(frozen=True)
class AuthCoverageViolation:
    method: str
    path: str
    dependency_calls: tuple[str, ...]


def _route_dependency_call_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def _walk(dep: object) -> None:
        deps = getattr(dep, "dependencies", None)
        if not isinstance(deps, list):
            return
        for child in deps:
            call = getattr(child, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", repr(call)))
            _walk(child)

    _walk(route.dependant)
    return names


def _is_monitored_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in MONITORED_PREFIXES)


def _is_public_exempt(method: str, path: str) -> bool:
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIX_ALLOWLIST):
        return True
    return (method, path) in PUBLIC_ROUTE_ALLOWLIST


def collect_auth_coverage_violations(app: object) -> list[AuthCoverageViolation]:
    violations: list[AuthCoverageViolation] = []
    routes = getattr(app, "routes", [])
    if not isinstance(routes, list):
        return violations

    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if not _is_monitored_path(path):
            continue

        call_names = _route_dependency_call_names(route)
        methods = {
            method.upper()
            for method in route.methods
            if method.upper() not in {"HEAD", "OPTIONS"}
        }
        for method in sorted(methods):
            if _is_public_exempt(method, path):
                continue
            if not any(name in AUTH_DEPENDENCY_CALL_NAMES for name in call_names):
                violations.append(
                    AuthCoverageViolation(
                        method=method,
                        path=path,
                        dependency_calls=tuple(sorted(call_names)),
                    )
                )

    return sorted(violations, key=lambda item: (item.path, item.method))


def load_app_for_audit() -> object:
    # Keep config deterministic and test-safe for script execution.
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("DEBUG", "false")
    from app.main import app

    return app


def main(argv: Iterable[str] | None = None) -> int:
    _ = argv
    app = load_app_for_audit()
    violations = collect_auth_coverage_violations(app)
    if not violations:
        print("Auth coverage check passed.")
        return 0

    print("Auth coverage violations detected:")
    for item in violations:
        print(
            f"- {item.method} {item.path} "
            f"(dependency_calls={list(item.dependency_calls)})"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

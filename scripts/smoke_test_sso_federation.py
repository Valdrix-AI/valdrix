#!/usr/bin/env python3
"""
SSO federation smoke test + evidence payload generator.

This script:
- Calls public tenant discovery (no auth): POST /api/v1/public/sso/discovery
- Calls admin validation (auth): GET /api/v1/settings/identity/sso/validation
- Emits an audit-safe evidence payload (no secrets).
- Optionally publishes the evidence: POST /api/v1/audit/identity/sso-federation/evidence

Usage:
  export VALDRICS_API_URL="http://127.0.0.1:8000"
  export VALDRICS_TOKEN="<bearer jwt>"
  uv run python scripts/smoke_test_sso_federation.py --email admin@example.com --out reports/acceptance/sso.json
  uv run python scripts/smoke_test_sso_federation.py --email admin@example.com --publish
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urljoin, urlparse

import httpx

from app.shared.core.evidence_capture import redact_secrets, sanitize_bearer_token


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_url(base: str, path: str) -> str:
    base_norm = base if base.endswith("/") else base + "/"
    path_norm = path[1:] if path.startswith("/") else path
    return urljoin(base_norm, path_norm)


def _normalize_base_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return value
    if lowered.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
        return f"http://{value}"
    return f"https://{value}"


def _require_valid_base_url(raw: str) -> str:
    normalized = _normalize_base_url(raw)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(
            f"Invalid --url '{raw}'. Provide a full http(s) URL like 'http://127.0.0.1:8000'."
        )
    return normalized


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    status_code: int | None = None
    detail: str | None = None
    duration_ms: float | None = None


def _exit_with_connectivity_error(base_url: str, exc: httpx.RequestError) -> NoReturn:
    request_url = str(exc.request.url) if exc.request is not None else base_url
    raise SystemExit(
        "Connection failed while calling "
        f"{request_url}. Ensure the API is running and --url/VALDRICS_API_URL is correct "
        f"(current base URL: {base_url}). Underlying error: {exc.__class__.__name__}: {exc}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test SSO federation discovery + validation."
    )
    parser.add_argument(
        "--url", default=os.environ.get("VALDRICS_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("VALDRICS_TOKEN"))
    parser.add_argument(
        "--email",
        required=True,
        help="Email to use for tenant discovery (domain routing).",
    )
    parser.add_argument(
        "--out", default=None, help="Optional path to write evidence JSON."
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish evidence into audit logs (admin only).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds for each request (default: 30).",
    )
    args = parser.parse_args()

    raw_url = str(args.url or "").strip()
    if not raw_url:
        fallback = (
            os.environ.get("VALDRICS_API_URL", "").strip() or "http://127.0.0.1:8000"
        )
        print(f"[sso-smoke] warning: empty --url; defaulting to {fallback}")
        raw_url = fallback
    base_url = _require_valid_base_url(raw_url)
    token = str(args.token or "").strip()
    email = str(args.email).strip()
    timeout_seconds = float(args.timeout)
    if timeout_seconds <= 0:
        raise SystemExit("--timeout must be > 0")
    if not email:
        raise SystemExit("--email is required")

    if token:
        try:
            token = sanitize_bearer_token(token)
        except ValueError as exc:
            raise SystemExit(
                "Invalid token (VALDRICS_TOKEN/--token). "
                "Ensure it's a single JWT string. "
                f"Details: {exc}"
            ) from None

    started_at = _utc_now()
    checks: list[Check] = []
    discovery_payload: dict[str, Any] | None = None
    validation_payload: dict[str, Any] | None = None
    discovery_ok = False
    validation_ok = False

    timeout = httpx.Timeout(timeout_seconds)
    public_client = httpx.Client(timeout=timeout)
    admin_client = httpx.Client(
        timeout=timeout, headers={"Authorization": f"Bearer {token}"} if token else None
    )

    try:
        # Preflight connectivity check for clearer operator feedback.
        try:
            public_client.get(_build_url(base_url, "/api/v1/public/csrf"))
        except httpx.RequestError as exc:
            _exit_with_connectivity_error(base_url, exc)

        # 1) Public discovery (no auth)
        t0 = time.perf_counter()
        try:
            resp = public_client.post(
                _build_url(base_url, "/api/v1/public/sso/discovery"), json={"email": email}
            )
        except httpx.RequestError as exc:
            _exit_with_connectivity_error(base_url, exc)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        ok = resp.status_code == 200
        discovery_ok = bool(ok)
        detail = None
        try:
            discovery_payload = resp.json() if ok else {"error": resp.text}
        except Exception:  # noqa: BLE001
            discovery_payload = {"error": resp.text}
        checks.append(
            Check(
                name="public.sso_discovery",
                passed=ok,
                status_code=resp.status_code,
                detail=detail,
                duration_ms=round(dt_ms, 3),
            )
        )

        # 2) Admin validation
        if not token:
            validation_ok = False
            checks.append(
                Check(
                    name="admin.sso_validation",
                    passed=False,
                    status_code=None,
                    detail="Missing token. Set VALDRICS_TOKEN or pass --token.",
                )
            )
        else:
            t0 = time.perf_counter()
            try:
                resp2 = admin_client.get(
                    _build_url(base_url, "/api/v1/settings/identity/sso/validation")
                )
            except httpx.RequestError as exc:
                _exit_with_connectivity_error(base_url, exc)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            ok2 = resp2.status_code == 200
            validation_ok = bool(ok2)
            try:
                validation_payload = resp2.json() if ok2 else {"error": resp2.text}
            except Exception:  # noqa: BLE001
                validation_payload = {"error": resp2.text}
            checks.append(
                Check(
                    name="admin.sso_validation",
                    passed=ok2,
                    status_code=resp2.status_code,
                    detail=None,
                    duration_ms=round(dt_ms, 3),
                )
            )

        # Determine overall pass condition.
        passed = bool(discovery_ok and validation_ok)
        if validation_payload and isinstance(validation_payload, dict):
            if validation_payload.get("passed") is False:
                passed = False
            federation_enabled = bool(validation_payload.get("federation_enabled"))
        else:
            federation_enabled = False

        if federation_enabled:
            passed = passed and bool((discovery_payload or {}).get("available") is True)
            checks.append(
                Check(
                    name="public.sso_discovery_available_when_federation_enabled",
                    passed=bool((discovery_payload or {}).get("available") is True),
                    status_code=200,
                    detail="Discovery must return available=true for the configured domain when federation is enabled.",
                )
            )
        else:
            checks.append(
                Check(
                    name="public.sso_discovery_available_when_federation_disabled",
                    passed=True,
                    status_code=200,
                    detail="Federation is disabled; discovery availability is not required.",
                )
            )

        completed_at = _utc_now()
        duration_seconds = max(
            0.0,
            (
                datetime.fromisoformat(completed_at)
                - datetime.fromisoformat(started_at)
            ).total_seconds(),
        )

        evidence_payload: dict[str, Any] = {
            "runner": "scripts/smoke_test_sso_federation.py",
            "passed": bool(passed),
            "federation_mode": (validation_payload or {}).get("federation_mode")
            if isinstance(validation_payload, dict)
            else None,
            "frontend_url": (validation_payload or {}).get("frontend_url")
            if isinstance(validation_payload, dict)
            else None,
            "expected_redirect_url": (validation_payload or {}).get(
                "expected_redirect_url"
            )
            if isinstance(validation_payload, dict)
            else None,
            "discovery_endpoint": (validation_payload or {}).get("discovery_endpoint")
            if isinstance(validation_payload, dict)
            else None,
            "checks": [
                {
                    "name": c.name,
                    "passed": bool(c.passed),
                    "status_code": c.status_code,
                    "detail": c.detail,
                    "duration_ms": c.duration_ms,
                }
                for c in checks
            ],
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": float(duration_seconds),
            "notes": {
                "email_domain": email.split("@")[-1].lower().strip()
                if "@" in email
                else None,
                "discovery": redact_secrets(discovery_payload)
                if discovery_payload is not None
                else None,
                "validation": redact_secrets(validation_payload)
                if validation_payload is not None
                else None,
            },
        }

        if args.out:
            _write_json(Path(str(args.out)), evidence_payload)

        if args.publish:
            if not token:
                raise SystemExit("Missing token. Set VALDRICS_TOKEN or pass --token.")
            publish_url = _build_url(
                base_url, "/api/v1/audit/identity/sso-federation/evidence"
            )
            # CSRF: best-effort bootstrap (some deployments enforce CSRF even for bearer-auth).
            publish_headers = {}
            try:
                csrf_resp = admin_client.get(
                    _build_url(base_url, "/api/v1/public/csrf")
                )
                if csrf_resp.is_success:
                    csrf_token = (csrf_resp.json() or {}).get("csrf_token")
                    if csrf_token:
                        publish_headers["X-CSRF-Token"] = str(csrf_token)
            except Exception:
                pass

            try:
                resp3 = admin_client.post(
                    publish_url, json=evidence_payload, headers=publish_headers or None
                )
            except httpx.RequestError as exc:
                _exit_with_connectivity_error(base_url, exc)
            if not resp3.is_success:
                raise SystemExit(
                    f"Publish failed: HTTP {resp3.status_code}: {resp3.text}"
                )

        print(json.dumps(evidence_payload, indent=2, sort_keys=True))
        return 0 if passed else 2
    finally:
        public_client.close()
        admin_client.close()


if __name__ == "__main__":
    raise SystemExit(main())

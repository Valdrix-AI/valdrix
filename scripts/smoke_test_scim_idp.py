#!/usr/bin/env python3
"""
SCIM IdP Smoke Test Runner (Operator).

This script validates SCIM interoperability against a running Valdrix environment.

Modes:
- Read-only (default): validates discovery endpoints only.
- Write-mode (--write): creates a test user + group, verifies membership, then cleans up.

Publishing:
- If --publish is set, posts an evidence payload to:
  POST /api/v1/audit/identity/idp-smoke/evidence
  This requires VALDRIX_TOKEN (admin) and does NOT transmit the SCIM token.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urljoin

import httpx

from app.shared.core.evidence_capture import sanitize_bearer_token


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a SCIM IdP smoke test against Valdrix."
    )
    parser.add_argument(
        "--scim-base-url",
        dest="scim_base_url",
        default=os.getenv("VALDRIX_SCIM_BASE_URL", "").strip(),
        help="SCIM base URL, e.g. https://host/scim/v2 (or set VALDRIX_SCIM_BASE_URL)",
    )
    parser.add_argument(
        "--scim-token",
        dest="scim_token",
        default=os.getenv("VALDRIX_SCIM_TOKEN", "").strip(),
        help="Tenant SCIM bearer token (or set VALDRIX_SCIM_TOKEN)",
    )
    parser.add_argument(
        "--idp",
        dest="idp",
        default=os.getenv("VALDRIX_IDP_VENDOR", "").strip(),
        help="IdP vendor label for evidence (okta/entra/etc). Optional.",
    )
    parser.add_argument(
        "--write",
        dest="write_mode",
        action="store_true",
        help="Enable write-mode: create user+group and validate membership (recommended on staging).",
    )
    parser.add_argument(
        "--no-cleanup",
        dest="no_cleanup",
        action="store_true",
        help="Do not delete created resources (debugging only).",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--out",
        dest="out",
        default="",
        help="Write JSON results to this path (optional)",
    )
    parser.add_argument(
        "--publish",
        dest="publish",
        action="store_true",
        help="Publish evidence to /api/v1/audit/identity/idp-smoke/evidence (requires VALDRIX_TOKEN).",
    )
    parser.add_argument(
        "--api-url",
        dest="api_url",
        default=os.getenv("VALDRIX_API_URL", "http://127.0.0.1:8000").strip(),
        help="API base URL used for --publish (defaults to VALDRIX_API_URL)",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_url(value: str, *, name: str) -> str:
    url = str(value or "").strip()
    if not url:
        raise SystemExit(f"{name} is required.")
    return url.rstrip("/")


def _auth_headers(token: str) -> dict[str, str]:
    token = str(token or "").strip()
    if not token:
        raise SystemExit("VALDRIX_SCIM_TOKEN/--scim-token is required.")
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class _Check:
    name: str
    passed: bool
    status_code: int | None = None
    detail: str | None = None
    duration_ms: float | None = None


def _extract_scim_error_detail(payload: Any) -> str:
    if not payload or not isinstance(payload, dict):
        return ""
    for key in ("detail", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def _scim_url(base: str, path: str) -> str:
    # Ensure urljoin keeps /scim/v2 root.
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _check(
    checks: list[_Check],
    *,
    name: str,
    resp: httpx.Response | None,
    started: float,
    ok: bool,
    detail: str | None = None,
) -> None:
    duration_ms = (time.time() - started) * 1000.0
    status_code = resp.status_code if resp is not None else None
    checks.append(
        _Check(
            name=name,
            passed=bool(ok),
            status_code=status_code,
            detail=detail,
            duration_ms=round(duration_ms, 2),
        )
    )


def _require_success(resp: httpx.Response) -> tuple[bool, str | None]:
    if resp.is_success:
        return True, None
    payload = _safe_json(resp)
    detail = _extract_scim_error_detail(payload) or resp.text
    return False, detail.strip() if isinstance(detail, str) else None


def _build_user_payload(email: str) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": email,
        "active": True,
        "emails": [{"value": email, "primary": True}],
    }


def _build_group_payload(display_name: str) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "displayName": display_name,
        "members": [],
    }


def _build_group_add_member_patch(user_id: str) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {
                "op": "add",
                "path": "members",
                "value": [{"value": user_id}],
            }
        ],
    }


def _write_out(path: str, payload: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def main() -> int:
    args = _parse_args()

    started_at = _now_iso()
    start_time = time.time()

    scim_base_url = _ensure_url(
        args.scim_base_url,
        name="SCIM base URL (--scim-base-url or VALDRIX_SCIM_BASE_URL)",
    )
    scim_headers = _auth_headers(args.scim_token)
    idp = str(args.idp or "").strip() or None

    checks: list[_Check] = []
    created_user_id: str | None = None
    created_group_id: str | None = None

    # Test identifiers: deterministic, unique, and obviously “smoke”.
    nonce = uuid4().hex[:10]
    user_email = f"valdrix-smoke-{nonce}@example.com"
    group_name = f"Valdrix Smoke Group {nonce}"

    timeout = httpx.Timeout(float(args.timeout))
    with httpx.Client(timeout=timeout, headers=scim_headers) as client:
        # 1) Discovery: ServiceProviderConfig
        t0 = time.time()
        resp = None
        try:
            resp = client.get(_scim_url(scim_base_url, "/ServiceProviderConfig"))
            ok, detail = _require_success(resp)
            _check(
                checks,
                name="scim.service_provider_config",
                resp=resp,
                started=t0,
                ok=ok,
                detail=detail,
            )
        except Exception as exc:
            _check(
                checks,
                name="scim.service_provider_config",
                resp=resp,
                started=t0,
                ok=False,
                detail=str(exc),
            )

        # 2) Discovery: Schemas
        t0 = time.time()
        resp = None
        try:
            resp = client.get(_scim_url(scim_base_url, "/Schemas"))
            ok, detail = _require_success(resp)
            _check(
                checks, name="scim.schemas", resp=resp, started=t0, ok=ok, detail=detail
            )
        except Exception as exc:
            _check(
                checks,
                name="scim.schemas",
                resp=resp,
                started=t0,
                ok=False,
                detail=str(exc),
            )

        # 3) Discovery: ResourceTypes
        t0 = time.time()
        resp = None
        try:
            resp = client.get(_scim_url(scim_base_url, "/ResourceTypes"))
            ok, detail = _require_success(resp)
            _check(
                checks,
                name="scim.resource_types",
                resp=resp,
                started=t0,
                ok=ok,
                detail=detail,
            )
        except Exception as exc:
            _check(
                checks,
                name="scim.resource_types",
                resp=resp,
                started=t0,
                ok=False,
                detail=str(exc),
            )

        if args.write_mode:
            # 4) Create User
            t0 = time.time()
            resp = None
            try:
                resp = client.post(
                    _scim_url(scim_base_url, "/Users"),
                    json=_build_user_payload(user_email),
                )
                ok, detail = _require_success(resp)
                payload = _safe_json(resp)
                if (
                    ok
                    and isinstance(payload, dict)
                    and isinstance(payload.get("id"), str)
                ):
                    created_user_id = payload["id"]
                _check(
                    checks,
                    name="scim.user_create",
                    resp=resp,
                    started=t0,
                    ok=ok,
                    detail=detail,
                )
            except Exception as exc:
                _check(
                    checks,
                    name="scim.user_create",
                    resp=resp,
                    started=t0,
                    ok=False,
                    detail=str(exc),
                )

            # 5) Create Group
            t0 = time.time()
            resp = None
            try:
                resp = client.post(
                    _scim_url(scim_base_url, "/Groups"),
                    json=_build_group_payload(group_name),
                )
                ok, detail = _require_success(resp)
                payload = _safe_json(resp)
                if (
                    ok
                    and isinstance(payload, dict)
                    and isinstance(payload.get("id"), str)
                ):
                    created_group_id = payload["id"]
                _check(
                    checks,
                    name="scim.group_create",
                    resp=resp,
                    started=t0,
                    ok=ok,
                    detail=detail,
                )
            except Exception as exc:
                _check(
                    checks,
                    name="scim.group_create",
                    resp=resp,
                    started=t0,
                    ok=False,
                    detail=str(exc),
                )

            # 6) Add Member
            if created_group_id and created_user_id:
                t0 = time.time()
                resp = None
                try:
                    resp = client.patch(
                        _scim_url(scim_base_url, f"/Groups/{created_group_id}"),
                        json=_build_group_add_member_patch(created_user_id),
                    )
                    ok, detail = _require_success(resp)
                    _check(
                        checks,
                        name="scim.group_add_member",
                        resp=resp,
                        started=t0,
                        ok=ok,
                        detail=detail,
                    )
                except Exception as exc:
                    _check(
                        checks,
                        name="scim.group_add_member",
                        resp=resp,
                        started=t0,
                        ok=False,
                        detail=str(exc),
                    )
            else:
                checks.append(
                    _Check(
                        name="scim.group_add_member",
                        passed=False,
                        status_code=None,
                        detail="skipped: missing created_user_id or created_group_id",
                        duration_ms=None,
                    )
                )

            # Cleanup (default on, opt-out via --no-cleanup)
            if not args.no_cleanup:
                if created_group_id:
                    t0 = time.time()
                    resp = None
                    try:
                        resp = client.delete(
                            _scim_url(scim_base_url, f"/Groups/{created_group_id}")
                        )
                        ok, detail = _require_success(resp)
                        _check(
                            checks,
                            name="scim.group_delete",
                            resp=resp,
                            started=t0,
                            ok=ok,
                            detail=detail,
                        )
                    except Exception as exc:
                        _check(
                            checks,
                            name="scim.group_delete",
                            resp=resp,
                            started=t0,
                            ok=False,
                            detail=str(exc),
                        )
                if created_user_id:
                    t0 = time.time()
                    resp = None
                    try:
                        resp = client.delete(
                            _scim_url(scim_base_url, f"/Users/{created_user_id}")
                        )
                        ok, detail = _require_success(resp)
                        _check(
                            checks,
                            name="scim.user_delete",
                            resp=resp,
                            started=t0,
                            ok=ok,
                            detail=detail,
                        )
                    except Exception as exc:
                        _check(
                            checks,
                            name="scim.user_delete",
                            resp=resp,
                            started=t0,
                            ok=False,
                            detail=str(exc),
                        )

    passed = all(c.passed for c in checks)
    completed_at = _now_iso()
    duration_seconds = round(time.time() - start_time, 3)

    evidence_payload: dict[str, Any] = {
        "runner": "scripts/smoke_test_scim_idp.py",
        "idp": idp,
        "scim_base_url": scim_base_url,
        "write_mode": bool(args.write_mode),
        "passed": bool(passed),
        "checks": [asdict(c) for c in checks],
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "notes": {
            "created_user_id": created_user_id,
            "created_group_id": created_group_id,
            "cleanup": (not args.no_cleanup),
        },
    }

    print(json.dumps(evidence_payload, indent=2, sort_keys=True))
    _write_out(str(args.out or ""), evidence_payload)

    if args.publish:
        api_url = _ensure_url(
            args.api_url, name="API URL (--api-url or VALDRIX_API_URL)"
        )
        raw_token = os.getenv("VALDRIX_TOKEN", "").strip()
        try:
            token = sanitize_bearer_token(raw_token)
        except ValueError as exc:
            raise SystemExit(
                "Invalid VALDRIX_TOKEN. Ensure it's a single JWT string. "
                f"Details: {exc}"
            ) from None
        if not token:
            raise SystemExit(
                "VALDRIX_TOKEN is required for --publish (admin bearer JWT)."
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        publish_url = urljoin(
            api_url.rstrip("/") + "/", "api/v1/audit/identity/idp-smoke/evidence"
        )
        with httpx.Client(timeout=httpx.Timeout(30.0), headers=headers) as client:
            resp = client.post(publish_url, json=evidence_payload)
        if resp.status_code >= 400:
            raise SystemExit(f"Publish failed ({resp.status_code}): {resp.text}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
Tenant isolation verification runner (operator-friendly).

Runs focused tenant isolation regression tests and (optionally) publishes the
result as audit-grade evidence for procurement/security reviews.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.shared.core.evidence_capture import sanitize_bearer_token


DEFAULT_TESTS = [
    "tests/security/test_tenant_isolation_regression.py",
]

DEFAULT_CHECKS = [
    "connections_list_is_tenant_scoped",
    "notification_settings_get_is_tenant_scoped",
    "audit_logs_endpoint_is_tenant_scoped",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 4000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _git_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and sha else None


def run_pytest(tests: list[str]) -> dict[str, Any]:
    cmd = ["uv", "run", "pytest", "--no-cov", "-q", *tests]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        cmd = ["python", "-m", "pytest", "--no-cov", "-q", *tests]
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    duration = time.perf_counter() - start

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    summary = ""
    for line in reversed(stdout.splitlines()):
        if "passed" in line or "failed" in line:
            summary = line.strip()
            break

    return {
        "passed": proc.returncode == 0,
        "pytest_exit_code": proc.returncode,
        "duration_seconds": round(duration, 4),
        "stdout_snippet": _truncate(stdout),
        "stderr_snippet": _truncate(stderr),
        "summary": summary,
        "command": " ".join(cmd),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify tenant isolation and optionally publish evidence."
    )
    parser.add_argument(
        "--publish", action="store_true", help="Publish evidence to the API endpoint."
    )
    parser.add_argument(
        "--url", default=os.environ.get("VALDRICS_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("VALDRICS_TOKEN"))
    parser.add_argument("--notes", default=None)
    parser.add_argument("--tests", nargs="*", default=DEFAULT_TESTS)
    args = parser.parse_args()

    tests = [str(t).strip() for t in (args.tests or []) if str(t).strip()]
    if not tests:
        raise SystemExit("No tests provided")

    result = run_pytest(tests)
    payload = {
        "runner": "scripts/verify_tenant_isolation.py",
        "checks": DEFAULT_CHECKS,
        "passed": bool(result["passed"]),
        "pytest_exit_code": int(result["pytest_exit_code"]),
        "duration_seconds": float(result["duration_seconds"]),
        "git_sha": _git_sha(),
        "captured_at": _utc_now_iso(),
        "notes": str(args.notes) if args.notes else None,
        "stdout_snippet": result.get("stdout_snippet"),
        "stderr_snippet": result.get("stderr_snippet"),
    }

    print("[tenancy] tenant isolation verification")
    print(f"[tenancy] passed: {payload['passed']}")
    if result.get("summary"):
        print(f"[tenancy] summary: {result['summary']}")

    if not args.publish:
        return 0 if payload["passed"] else 1

    token = str(args.token or "").strip()
    try:
        token = sanitize_bearer_token(token)
    except ValueError as exc:
        raise SystemExit(
            "Invalid token (VALDRICS_TOKEN/--token). "
            "Ensure it's a single JWT string. "
            f"Details: {exc}"
        ) from None
    if not token:
        raise SystemExit("Missing token. Set VALDRICS_TOKEN or pass --token.")

    url = str(args.url).rstrip("/")
    endpoint = f"{url}/api/v1/audit/tenancy/isolation/evidence"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        resp = client.post(endpoint, json=payload)
    if not resp.is_success:
        raise SystemExit(
            f"Publish failed: HTTP {resp.status_code} -> {resp.text[:300]}"
        )

    body = resp.json()
    print(
        f"[tenancy] published: event_id={body.get('event_id')} run_id={body.get('run_id')}"
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

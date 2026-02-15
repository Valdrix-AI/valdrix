#!/usr/bin/env python3
"""
Live smoke test for remediation pending_approval workflow.

Flow:
1) Fetch CSRF token/cookie.
2) Find a pending remediation request whose policy preview decision is "escalate"
   (or use --request-id).
3) If request is pending, approve once (admin/owner) so execution is allowed.
4) Execute request and verify it moves to pending_approval.
5) Optionally approve escalated request and (optionally) execute post-approval.

Usage:
  export VALDRIX_TOKEN="<bearer_jwt>"
  .venv/bin/python scripts/verify_pending_approval_flow.py --approve --execute-after-approve
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

from app.shared.core.evidence_capture import sanitize_bearer_token


def _must_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _fail(resp: httpx.Response, prefix: str) -> None:
    payload = _safe_json(resp)
    raise SystemExit(f"{prefix}: HTTP {resp.status_code} -> {payload}")


def _api_get(client: httpx.Client, url: str, headers: dict[str, str]) -> Any:
    resp = client.get(url, headers=headers, timeout=30)
    if resp.status_code >= 400:
        _fail(resp, f"GET {url} failed")
    return _safe_json(resp)


def _api_post(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
) -> Any:
    resp = client.post(url, headers=headers, json=json_body, timeout=30)
    if resp.status_code >= 400:
        _fail(resp, f"POST {url} failed")
    return _safe_json(resp)


def _find_escalation_candidate(
    client: httpx.Client, base_url: str, headers: dict[str, str]
) -> dict[str, Any]:
    pending = _api_get(client, f"{base_url}/api/v1/zombies/pending?limit=100", headers)
    requests = pending.get("requests", [])
    if not requests:
        raise SystemExit("No pending remediation requests found.")

    for request in requests:
        request_id = request["id"]
        preview = _api_get(
            client, f"{base_url}/api/v1/zombies/policy-preview/{request_id}", headers
        )
        if preview.get("decision") == "escalate":
            print(f"Selected escalation candidate request: {request_id}")
            return request

    raise SystemExit(
        "No pending request currently previews to 'escalate'. "
        "Create one (for example GPU-related terminate/resize action) and retry."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify pending_approval remediation flow against live API."
    )
    parser.add_argument(
        "--base-url", default=os.getenv("VALDRIX_BASE_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument(
        "--request-id", default=None, help="Optional remediation request ID to test."
    )
    parser.add_argument(
        "--approve", action="store_true", help="Approve request after escalation."
    )
    parser.add_argument(
        "--execute-after-approve",
        action="store_true",
        help="Execute again after approval (requires --approve).",
    )
    args = parser.parse_args()

    token = _must_env("VALDRIX_TOKEN")
    try:
        token = sanitize_bearer_token(token)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid VALDRIX_TOKEN. Ensure it's a single JWT string. Details: {exc}"
        ) from None
    if args.execute_after_approve and not args.approve:
        raise SystemExit("--execute-after-approve requires --approve")

    with httpx.Client(follow_redirects=True) as client:
        csrf_resp = client.get(f"{args.base_url}/api/v1/public/csrf", timeout=30)
        if csrf_resp.status_code >= 400:
            _fail(csrf_resp, "Fetching CSRF token failed")
        csrf_payload = _safe_json(csrf_resp)
        csrf_token = str(csrf_payload.get("csrf_token", "")).strip()
        if not csrf_token:
            raise SystemExit(f"CSRF endpoint did not return csrf_token: {csrf_payload}")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_token,
        }

        if args.request_id:
            pending = _api_get(
                client, f"{args.base_url}/api/v1/zombies/pending?limit=100", headers
            )
            request = next(
                (
                    r
                    for r in pending.get("requests", [])
                    if r.get("id") == args.request_id
                ),
                None,
            )
            if request is None:
                request = {"id": args.request_id}
        else:
            request = _find_escalation_candidate(client, args.base_url, headers)
        request_id = request["id"]

        request_status = request.get("status")
        if request_status == "pending":
            print(f"Pre-approving pending request {request_id} before execution...")
            preapprove_payload = _api_post(
                client,
                f"{args.base_url}/api/v1/zombies/approve/{request_id}",
                headers,
                {"notes": "Smoke test pre-approval"},
            )
            print(f"Pre-approve response: {preapprove_payload}")

        if request_status != "pending_approval":
            print(f"Executing request {request_id} to trigger escalation...")
            execute_payload = _api_post(
                client,
                f"{args.base_url}/api/v1/zombies/execute/{request_id}?bypass_grace_period=true",
                headers,
            )
            status = execute_payload.get("status")
            print(f"Execute response status: {status}")
            if status != "pending_approval":
                raise SystemExit(
                    f"Expected execute status 'pending_approval', got '{status}'. Payload: {execute_payload}"
                )
        else:
            print(
                f"Request {request_id} is already pending_approval; skipping initial execute step."
            )

        pending = _api_get(
            client, f"{args.base_url}/api/v1/zombies/pending?limit=100", headers
        )
        updated = next(
            (r for r in pending.get("requests", []) if r.get("id") == request_id), None
        )
        if not updated:
            raise SystemExit("Request not found in pending queue after escalation.")
        if updated.get("status") != "pending_approval":
            raise SystemExit(
                f"Expected queue status pending_approval, got {updated.get('status')}: {updated}"
            )
        if not updated.get("escalation_required", False):
            raise SystemExit(
                f"Expected escalation_required=true after escalation: {updated}"
            )
        print("Verified pending_approval state in queue.")

        if args.approve:
            print("Approving escalated request...")
            approve_payload = _api_post(
                client,
                f"{args.base_url}/api/v1/zombies/approve/{request_id}",
                headers,
                {"notes": "Smoke test owner approval"},
            )
            print(f"Approve response: {approve_payload}")

            if args.execute_after_approve:
                print("Executing approved request...")
                post_approve_execute = _api_post(
                    client,
                    f"{args.base_url}/api/v1/zombies/execute/{request_id}?bypass_grace_period=true",
                    headers,
                )
                print(f"Post-approval execute response: {post_approve_execute}")

    print("✅ pending_approval smoke flow completed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

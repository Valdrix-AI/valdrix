"""
Capture carbon assurance evidence (methodology + factor versions) into audit logs.
"""

from __future__ import annotations

import argparse
import os

import httpx

from app.shared.core.evidence_capture import sanitize_bearer_token


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture carbon assurance evidence into audit logs."
    )
    parser.add_argument(
        "--url", default=os.environ.get("VALDRIX_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("VALDRIX_TOKEN"))
    parser.add_argument(
        "--runner", default="scripts/capture_carbon_assurance_evidence.py"
    )
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    raw_token = str(args.token or "").strip()
    try:
        token = sanitize_bearer_token(raw_token)
    except ValueError as exc:
        raise SystemExit(
            "Invalid token (VALDRIX_TOKEN/--token). "
            "Ensure it's a single JWT string. "
            f"Details: {exc}"
        ) from None
    if not token:
        raise SystemExit("Missing token. Set VALDRIX_TOKEN or pass --token.")

    url = str(args.url).rstrip("/")
    endpoint = f"{url}/api/v1/audit/carbon/assurance/evidence"
    payload = {
        "runner": str(args.runner),
        "notes": (str(args.notes) if args.notes else None),
    }
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        resp = client.post(endpoint, json=payload)
    if not resp.is_success:
        raise SystemExit(
            f"Capture failed: HTTP {resp.status_code} -> {resp.text[:300]}"
        )

    body = resp.json()
    print(
        f"[carbon] captured: event_id={body.get('event_id')} run_id={body.get('run_id')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

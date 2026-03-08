#!/usr/bin/env python3
"""Execute a repeatable repository-managed disaster recovery drill against a running API."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx

from app.shared.core.auth import create_access_token


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a DR drill against a rebuilt application instance."
    )
    parser.add_argument("--url", required=True, help="Base URL for the API under test.")
    parser.add_argument(
        "--out",
        default="",
        help="Optional path for a JSON evidence report.",
    )
    return parser.parse_args()


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, object] | None = None,
) -> tuple[int, object]:
    response = await client.request(method, url, headers=headers, json=json_body)
    try:
        payload: object = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = response.text
    return int(response.status_code), payload


async def main() -> None:
    args = _parse_args()
    base_url = str(args.url).rstrip("/")
    user_id = str(uuid4())
    email = f"dr-drill-{user_id[:8]}@valdrics.local"
    token = create_access_token(
        {"sub": user_id, "email": email},
        timedelta(hours=2),
    )
    headers = {"Authorization": f"Bearer {token}"}
    today = date.today()
    start_date = (today - timedelta(days=30)).isoformat()
    end_date = today.isoformat()

    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        live_status, live_payload = await _request_json(
            client,
            "GET",
            f"{base_url}/health/live",
        )
        health_status, health_payload = await _request_json(
            client,
            "GET",
            f"{base_url}/health",
        )
        onboard_status, onboard_payload = await _request_json(
            client,
            "POST",
            f"{base_url}/api/v1/settings/onboard",
            headers=headers,
            json_body={
                "tenant_name": "Disaster Recovery Drill Tenant",
                "admin_email": email,
            },
        )
        costs_status, costs_payload = await _request_json(
            client,
            "GET",
            f"{base_url}/api/v1/costs?start_date={start_date}&end_date={end_date}",
            headers=headers,
        )

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target_url": base_url,
        "steps": {
            "health_live": {"status_code": live_status, "payload": live_payload},
            "health_deep": {"status_code": health_status, "payload": health_payload},
            "tenant_onboard": {
                "status_code": onboard_status,
                "payload": onboard_payload,
            },
            "costs_query": {"status_code": costs_status, "payload": costs_payload},
        },
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)

    print(json.dumps(evidence, indent=2, sort_keys=True))

    failing = {
        name: step["status_code"]
        for name, step in evidence["steps"].items()
        if int(step["status_code"]) >= 400
    }
    if failing:
        raise SystemExit(f"Disaster recovery drill failed: {failing}")


if __name__ == "__main__":
    asyncio.run(main())


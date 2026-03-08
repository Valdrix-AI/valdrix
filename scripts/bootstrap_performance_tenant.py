#!/usr/bin/env python3
"""Bootstrap a local authenticated tenant for performance smoke runs."""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx

from app.shared.core.auth import create_access_token


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a signed bearer token and onboard a tenant for load-test runs."
    )
    parser.add_argument("--url", required=True, help="Base URL for the running API.")
    parser.add_argument(
        "--tenant-name",
        default="Performance Validation Tenant",
        help="Tenant name to onboard.",
    )
    parser.add_argument(
        "--email",
        default="performance.owner@valdrics.local",
        help="Owner email used for the bootstrap token and onboarding.",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=2.0,
        help="Bearer token TTL in hours.",
    )
    return parser.parse_args()


async def _onboard_tenant(*, base_url: str, token: str, tenant_name: str, email: str) -> None:
    payload = {"tenant_name": tenant_name, "admin_email": email}
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/v1/settings/onboard",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code == 200:
        return
    if response.status_code == 400 and "Already onboarded" in response.text:
        return
    raise SystemExit(
        f"Tenant bootstrap failed ({response.status_code}): {response.text}"
    )


async def main() -> None:
    args = _parse_args()
    user_id = str(uuid4())
    token = create_access_token(
        {"sub": user_id, "email": str(args.email).strip()},
        timedelta(hours=float(args.hours)),
    )
    await _onboard_tenant(
        base_url=str(args.url),
        token=token,
        tenant_name=str(args.tenant_name).strip(),
        email=str(args.email).strip(),
    )
    print(token)


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Generate a short-lived bearer JWT for local dev/testing.

This is useful for scripted API smoke tests (curl) without needing to copy a JWT
from the browser. The token is signed with `SUPABASE_JWT_SECRET` (same as the API).

Examples:
  uv run python scripts/dev_bearer_token.py --user-id 00000000-0000-0000-0000-000000000000
  uv run python scripts/dev_bearer_token.py --email owner@valdrix.io --hours 2
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from datetime import timedelta

# Ensure any library logs go to stderr so we keep stdout clean for the JWT.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
from uuid import UUID  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local dev bearer JWT.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--user-id", dest="user_id", type=str, help="User UUID")
    group.add_argument("--email", dest="email", type=str, help="User email")
    parser.add_argument(
        "--hours", dest="hours", type=float, default=2.0, help="Token TTL in hours"
    )
    return parser.parse_args()


async def _resolve_user(args: argparse.Namespace) -> tuple[str, str]:
    # Import inside the function so operator scripts can capture stdout safely.
    # Some modules emit structured logs at import time (DB SSL mode warnings, etc).
    from app.shared.core.security import generate_blind_index
    from app.shared.db.session import async_session_maker

    # Ensure relationship targets are registered before ORM usage.
    import app.models.aws_connection  # noqa: F401
    import app.models.background_job  # noqa: F401
    import app.models.license_connection  # noqa: F401
    import app.models.llm  # noqa: F401
    import app.models.notification_settings  # noqa: F401
    import app.models.saas_connection  # noqa: F401
    from app.models.tenant import User

    async with async_session_maker() as db:
        if args.user_id:
            uid = UUID(args.user_id)
            row = (
                await db.execute(select(User.id, User.email).where(User.id == uid))
            ).first()
        elif args.email:
            email_bidx = generate_blind_index(args.email)
            row = (
                await db.execute(
                    select(User.id, User.email).where(User.email_bidx == email_bidx)
                )
            ).first()
        else:
            row = (await db.execute(select(User.id, User.email).limit(1))).first()

        if not row:
            raise SystemExit(
                "No matching user found in DB. Complete onboarding/seed a user first."
            )

        uid, email = row
        return str(uid), str(email)


async def main() -> None:
    args = _parse_args()
    # IMPORTANT: keep stdout clean so operators can safely do:
    #   export VALDRIX_TOKEN="$(python scripts/dev_bearer_token.py ...)"
    with contextlib.redirect_stdout(sys.stderr):
        uid, email = await _resolve_user(args)
        from app.shared.core.auth import create_access_token

        token = create_access_token(
            {"sub": uid, "email": email}, timedelta(hours=float(args.hours))
        )

    print(token)


if __name__ == "__main__":
    asyncio.run(main())

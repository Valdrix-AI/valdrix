#!/usr/bin/env python3
"""
Debug helper: isolate SQLite `Base.metadata.create_all()` hangs by creating tables
one-by-one and printing progress.

Usage:
  timeout 60s .venv/bin/python scripts/debug_sqlite_create_all.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


def _set_test_env() -> None:
    # Force a safe, deterministic environment (no network DB).
    os.environ["TESTING"] = "true"
    os.environ["DB_SSL_MODE"] = "disable"
    os.environ["SUPABASE_JWT_SECRET"] = "test-jwt-secret-for-testing-at-least-32-bytes"
    os.environ["ENCRYPTION_KEY"] = "32-byte-long-test-encryption-key"
    os.environ["CSRF_SECRET_KEY"] = "test-csrf-secret-key-at-least-32-bytes"
    os.environ["KDF_SALT"] = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s="

    sqlite_path = Path("/tmp/valdrix_debug_create_all.sqlite")
    try:
        sqlite_path.unlink(missing_ok=True)
    except Exception:
        pass
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{sqlite_path}"


async def main() -> None:
    _set_test_env()

    print("[debug] importing Base/engine...", flush=True)
    from app.shared.db.base import Base
    from app.shared.db.session import engine as async_engine

    print(f"[debug] engine url: {async_engine.url}", flush=True)

    # Import a representative set of models (same set used by acceptance evidence in-process mode).
    print("[debug] importing models...", flush=True)
    import app.models.cloud  # noqa: F401
    import app.models.tenant  # noqa: F401
    import app.models.tenant_identity_settings  # noqa: F401
    import app.models.notification_settings  # noqa: F401
    import app.models.remediation_settings  # noqa: F401
    import app.models.background_job  # noqa: F401
    import app.models.llm  # noqa: F401

    print("[debug] imports done; connecting...", flush=True)

    async with async_engine.begin() as conn:

        def _create_tables(sync_conn) -> None:
            tables = list(Base.metadata.sorted_tables)
            print(f"[debug] creating {len(tables)} tables...", flush=True)
            for table in tables:
                print(f"[debug] creating table: {table.name}", flush=True)
                table.create(bind=sync_conn, checkfirst=True)
                print(f"[debug] created table: {table.name}", flush=True)

        await conn.run_sync(_create_tables)

    print("[debug] done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

import argparse
import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

from scripts.safety_guardrails import (
    current_environment,
    ensure_environment_confirmation,
    ensure_force_and_phrase,
    ensure_interactive_confirmation,
    ensure_protected_environment_bypass,
)

load_dotenv()

CONFIRM_PHRASE = "WIPE_VALDRICS_DATA"
PROD_WIPE_BYPASS = "I_UNDERSTAND_THIS_WILL_DESTROY_DATA"
NONINTERACTIVE_BYPASS_ENV = "VALDRICS_ALLOW_NONINTERACTIVE_WIPE"


def _validate_wipe_request(
    *,
    force: bool,
    phrase: str,
    confirm_environment: str,
    no_prompt: bool,
) -> None:
    environment = current_environment()
    ensure_protected_environment_bypass(
        environment=environment,
        bypass_env_var="VALDRICS_ALLOW_PROD_WIPE",
        bypass_phrase=PROD_WIPE_BYPASS,
        operation_label="wipe",
    )
    ensure_force_and_phrase(force=force, phrase=phrase, expected_phrase=CONFIRM_PHRASE)
    ensure_environment_confirmation(
        confirm_environment=confirm_environment, environment=environment
    )
    ensure_interactive_confirmation(
        token=f"WIPE:{environment.upper()}",
        no_prompt=no_prompt,
        noninteractive_env_var=NONINTERACTIVE_BYPASS_ENV,
    )


async def wipe_database() -> None:
    """Drop all tables, views, and types in the public schema."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not found in environment.")

    print("Connecting to database to perform wipe...")
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    conn = await asyncpg.connect(db_url)
    try:
        print("Dropping all tables in public schema...")
        await conn.execute(
            """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
            """
        )

        print("Dropping all custom types in public schema...")
        await conn.execute(
            """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT typname
                    FROM pg_type t
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE n.nspname = 'public' AND t.typtype = 'e'
                ) LOOP
                    EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
                END LOOP;
            END $$;
            """
        )

        print("Dropping all functions in public schema...")
        await conn.execute(
            """
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (
                    SELECT routine_name
                    FROM information_schema.routines
                    WHERE routine_schema = 'public'
                ) LOOP
                    EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_name) || ' CASCADE';
                END LOOP;
            END $$;
            """
        )

        print("✅ Database wipe complete. Public schema is now empty.")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error during wipe: {exc}", file=sys.stderr)
        raise
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dangerous: wipe database objects in public schema."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Acknowledge destructive operation.",
    )
    parser.add_argument(
        "--confirm-phrase",
        default="",
        help=f"Must equal {CONFIRM_PHRASE!r} to execute.",
    )
    parser.add_argument(
        "--confirm-environment",
        default="",
        help="Must match current ENVIRONMENT exactly (normalized to lowercase).",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help=(
            "Skip interactive typed confirmation. Requires "
            f"{NONINTERACTIVE_BYPASS_ENV}=true."
        ),
    )
    args = parser.parse_args()

    try:
        _validate_wipe_request(
            force=bool(args.force),
            phrase=str(args.confirm_phrase),
            confirm_environment=str(args.confirm_environment),
            no_prompt=bool(args.no_prompt),
        )
        asyncio.run(wipe_database())
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

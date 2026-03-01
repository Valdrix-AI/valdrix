
import argparse
import asyncio
import sys

from sqlalchemy import text

from app.shared.db.session import async_session_maker
from scripts.safety_guardrails import (
    current_environment,
    ensure_environment_confirmation,
    ensure_force_and_phrase,
    ensure_interactive_confirmation,
    ensure_protected_environment_bypass,
)

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


async def force_wipe() -> None:
    print("Forcing wipe by dropping public schema using app engine...")
    async with async_session_maker() as session:
        try:
            await session.execute(text("DROP SCHEMA public CASCADE"))
            await session.execute(text("CREATE SCHEMA public"))
            await session.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
            await session.execute(text("GRANT ALL ON SCHEMA public TO public"))
            await session.commit()
            print("✅ Database wiped (schema-level)")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error: {exc}", file=sys.stderr)
            await session.rollback()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Dangerous: wipe the entire public schema.")
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
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    asyncio.run(force_wipe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

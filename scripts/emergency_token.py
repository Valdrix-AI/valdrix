import argparse
import asyncio
import os
import sys
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy import select

from scripts.safety_guardrails import (
    current_environment,
    ensure_environment_confirmation,
    ensure_force_and_phrase,
    ensure_interactive_confirmation,
    ensure_protected_environment_bypass,
)

CONFIRM_PHRASE = "VALDRICS_BREAK_GLASS"
INTERACTIVE_CONFIRM_TOKEN = "ISSUE_VALDRICS_EMERGENCY_TOKEN"
DEFAULT_TTL_HOURS = 1
MAX_TTL_HOURS = 4
MIN_REASON_LENGTH = 16
PROD_EMERGENCY_BYPASS = "I_UNDERSTAND_EMERGENCY_TOKEN_RISK"
NONINTERACTIVE_BYPASS_ENV = "VALDRICS_ALLOW_NONINTERACTIVE_EMERGENCY_TOKEN"


def _validate_request(
    *,
    email: str,
    force: bool,
    phrase: str,
    ttl_hours: int,
    operator: str,
    reason: str,
    confirm_environment: str,
    no_prompt: bool,
) -> None:
    environment = current_environment()
    ensure_protected_environment_bypass(
        environment=environment,
        bypass_env_var="VALDRICS_ALLOW_PROD_EMERGENCY_TOKEN",
        bypass_phrase=PROD_EMERGENCY_BYPASS,
        operation_label="emergency token issuance",
    )
    ensure_force_and_phrase(force=force, phrase=phrase, expected_phrase=CONFIRM_PHRASE)
    ensure_environment_confirmation(
        confirm_environment=confirm_environment, environment=environment
    )
    ensure_interactive_confirmation(
        token=INTERACTIVE_CONFIRM_TOKEN,
        no_prompt=no_prompt,
        noninteractive_env_var=NONINTERACTIVE_BYPASS_ENV,
    )

    if os.getenv("VALDRICS_EMERGENCY_TOKEN_ENABLED", "").strip().lower() != "true":
        raise RuntimeError(
            "Emergency token generation is disabled. "
            "Set VALDRICS_EMERGENCY_TOKEN_ENABLED=true for an explicit, temporary break-glass flow."
        )
    if not email.strip():
        raise RuntimeError("--email is required.")
    if not operator.strip():
        raise RuntimeError("--operator is required for accountability.")
    if len(reason.strip()) < MIN_REASON_LENGTH:
        raise RuntimeError(
            f"--reason must be at least {MIN_REASON_LENGTH} characters."
        )
    if ttl_hours < 1 or ttl_hours > MAX_TTL_HOURS:
        raise RuntimeError(
            f"--ttl-hours must be between 1 and {MAX_TTL_HOURS}."
        )


def _validate_target_role(role: str) -> None:
    normalized = str(role or "").strip().lower()
    if normalized not in {"owner", "admin"}:
        raise RuntimeError(
            "Emergency token can only be issued for owner/admin accounts."
        )


async def generate_token(
    *, email: str, ttl_hours: int, operator: str, reason: str
) -> str:
    load_dotenv()

    from app.models.tenant import User
    from app.shared.core.auth import create_access_token
    from app.shared.core.security import decrypt_string
    from app.shared.core.security import generate_blind_index
    from app.shared.db.session import async_session_maker

    email_bidx = generate_blind_index(email.strip())

    async with async_session_maker() as db:
        row = (
            await db.execute(
                select(User.id, User.email, User.role, User.tenant_id)
                .where(User.email_bidx == email_bidx)
                .limit(1)
            )
        ).first()
        if not row:
            raise RuntimeError("No user found for the supplied email.")

        user_id, encrypted_email, role, tenant_id = row
        _validate_target_role(str(role))
        email_plain = decrypt_string(str(encrypted_email), context="pii")
        token = create_access_token(
            {
                "sub": str(user_id),
                "email": email_plain,
                "emergency": True,
                "emergency_operator": operator.strip(),
                "emergency_reason": reason.strip(),
            },
            expires_delta=timedelta(hours=ttl_hours),
        )

        from app.modules.governance.domain.security.audit_log import (
            AuditEventType,
            AuditLogger,
        )

        audit = AuditLogger(
            db=db,
            tenant_id=tenant_id,
            correlation_id=f"emergency-token:{user_id}",
        )
        await audit.log(
            event_type=AuditEventType.SECURITY_EMERGENCY_TOKEN_ISSUED,
            actor_id=user_id,
            actor_email=email_plain,
            resource_type="user",
            resource_id=str(user_id),
            details={
                "operator": operator.strip(),
                "reason": reason.strip(),
                "ttl_hours": int(ttl_hours),
            },
            success=True,
        )
        await db.commit()
        return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a short-lived emergency token.")
    parser.add_argument("--email", default="", help="Target user email.")
    parser.add_argument("--operator", default="", help="Operator identifier (email or handle).")
    parser.add_argument(
        "--reason",
        default="",
        help="Break-glass reason (minimum 16 characters).",
    )
    parser.add_argument(
        "--ttl-hours",
        type=int,
        default=DEFAULT_TTL_HOURS,
        help=f"Token lifetime in hours (1-{MAX_TTL_HOURS}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Acknowledge break-glass operation.",
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
        _validate_request(
            email=str(args.email),
            force=bool(args.force),
            phrase=str(args.confirm_phrase),
            ttl_hours=int(args.ttl_hours),
            operator=str(args.operator),
            reason=str(args.reason),
            confirm_environment=str(args.confirm_environment),
            no_prompt=bool(args.no_prompt),
        )
        token = asyncio.run(
            generate_token(
                email=str(args.email),
                ttl_hours=int(args.ttl_hours),
                operator=str(args.operator),
                reason=str(args.reason),
            )
        )
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error: {exc}", file=sys.stderr)
        return 1

    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

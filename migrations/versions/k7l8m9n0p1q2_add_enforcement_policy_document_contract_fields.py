"""add enforcement policy document contract fields

Revision ID: k7l8m9n0p1q2
Revises: j6k7l8m9n0p1
Create Date: 2026-02-25 05:05:00.000000
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "k7l8m9n0p1q2"
down_revision: Union[str, Sequence[str], None] = "j6k7l8m9n0p1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_POLICY_SCHEMA_VERSION = "valdrics.enforcement.policy.v1"
_EMPTY_SHA256 = "0" * 64


def _decimal_to_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return str(parsed.quantize(Decimal("0.0001")))


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json_value(inner)
            for key, inner in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _policy_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column(
        "enforcement_policies",
        sa.Column("policy_document_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("policy_document_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("policy_document", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                terraform_mode,
                terraform_mode_prod,
                terraform_mode_nonprod,
                k8s_admission_mode,
                k8s_admission_mode_prod,
                k8s_admission_mode_nonprod,
                require_approval_for_prod,
                require_approval_for_nonprod,
                enforce_prod_requester_reviewer_separation,
                enforce_nonprod_requester_reviewer_separation,
                approval_routing_rules,
                plan_monthly_ceiling_usd,
                enterprise_monthly_ceiling_usd,
                auto_approve_below_monthly_usd,
                hard_deny_above_monthly_usd,
                default_ttl_seconds
            FROM enforcement_policies
            """
        )
    ).mappings()

    policy_table = sa.table(
        "enforcement_policies",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("policy_document_schema_version", sa.String(length=64)),
        sa.column("policy_document_sha256", sa.String(length=64)),
        sa.column("policy_document", postgresql.JSONB(astext_type=sa.Text())),
    )

    for row in rows:
        routing_rules_raw = row.get("approval_routing_rules")
        routing_rules = routing_rules_raw if isinstance(routing_rules_raw, list) else []
        ttl_seconds_raw = row.get("default_ttl_seconds")
        ttl_seconds = int(ttl_seconds_raw) if ttl_seconds_raw is not None else 900
        ttl_seconds = max(60, min(ttl_seconds, 86400))

        policy_document = _normalize_json_value(
            {
                "schema_version": _POLICY_SCHEMA_VERSION,
                "mode_matrix": {
                    "terraform_default": str(row.get("terraform_mode") or "soft"),
                    "terraform_prod": str(row.get("terraform_mode_prod") or "soft"),
                    "terraform_nonprod": str(row.get("terraform_mode_nonprod") or "soft"),
                    "k8s_admission_default": str(row.get("k8s_admission_mode") or "soft"),
                    "k8s_admission_prod": str(
                        row.get("k8s_admission_mode_prod") or "soft"
                    ),
                    "k8s_admission_nonprod": str(
                        row.get("k8s_admission_mode_nonprod") or "soft"
                    ),
                },
                "approval": {
                    "require_approval_prod": bool(
                        row.get("require_approval_for_prod", True)
                    ),
                    "require_approval_nonprod": bool(
                        row.get("require_approval_for_nonprod", False)
                    ),
                    "enforce_prod_requester_reviewer_separation": bool(
                        row.get("enforce_prod_requester_reviewer_separation", True)
                    ),
                    "enforce_nonprod_requester_reviewer_separation": bool(
                        row.get("enforce_nonprod_requester_reviewer_separation", False)
                    ),
                    "routing_rules": routing_rules,
                },
                "entitlements": {
                    "plan_monthly_ceiling_usd": _decimal_to_str(
                        row.get("plan_monthly_ceiling_usd")
                    ),
                    "enterprise_monthly_ceiling_usd": _decimal_to_str(
                        row.get("enterprise_monthly_ceiling_usd")
                    ),
                    "auto_approve_below_monthly_usd": _decimal_to_str(
                        row.get("auto_approve_below_monthly_usd") or Decimal("25")
                    ),
                    "hard_deny_above_monthly_usd": _decimal_to_str(
                        row.get("hard_deny_above_monthly_usd") or Decimal("5000")
                    ),
                },
                "execution": {"default_ttl_seconds": ttl_seconds},
            }
        )
        if not isinstance(policy_document, dict):
            policy_document = {"schema_version": _POLICY_SCHEMA_VERSION}

        bind.execute(
            policy_table.update()
            .where(policy_table.c.id == row["id"])
            .values(
                policy_document_schema_version=_POLICY_SCHEMA_VERSION,
                policy_document_sha256=_policy_hash(policy_document),
                policy_document=policy_document,
            )
        )

    op.alter_column(
        "enforcement_policies",
        "policy_document_schema_version",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=_POLICY_SCHEMA_VERSION,
    )
    op.alter_column(
        "enforcement_policies",
        "policy_document_sha256",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default=_EMPTY_SHA256,
    )
    op.alter_column(
        "enforcement_policies",
        "policy_document",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.drop_column("enforcement_policies", "policy_document")
    op.drop_column("enforcement_policies", "policy_document_sha256")
    op.drop_column("enforcement_policies", "policy_document_schema_version")

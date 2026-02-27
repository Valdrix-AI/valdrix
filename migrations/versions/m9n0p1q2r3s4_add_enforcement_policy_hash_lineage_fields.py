"""add enforcement decision and ledger policy hash lineage fields

Revision ID: m9n0p1q2r3s4
Revises: l8m9n0p1q2r3
Create Date: 2026-02-25 12:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m9n0p1q2r3s4"
down_revision: Union[str, Sequence[str], None] = "l8m9n0p1q2r3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_POLICY_SCHEMA_VERSION = "valdrix.enforcement.policy.v1"
_EMPTY_POLICY_HASH = "0" * 64


def upgrade() -> None:
    op.add_column(
        "enforcement_decisions",
        sa.Column(
            "policy_document_schema_version",
            sa.String(length=64),
            nullable=False,
            server_default=_POLICY_SCHEMA_VERSION,
        ),
    )
    op.add_column(
        "enforcement_decisions",
        sa.Column(
            "policy_document_sha256",
            sa.String(length=64),
            nullable=False,
            server_default=_EMPTY_POLICY_HASH,
        ),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column(
            "policy_document_schema_version",
            sa.String(length=64),
            nullable=False,
            server_default=_POLICY_SCHEMA_VERSION,
        ),
    )
    op.add_column(
        "enforcement_decision_ledger",
        sa.Column(
            "policy_document_sha256",
            sa.String(length=64),
            nullable=False,
            server_default=_EMPTY_POLICY_HASH,
        ),
    )


def downgrade() -> None:
    op.drop_column("enforcement_decision_ledger", "policy_document_sha256")
    op.drop_column("enforcement_decision_ledger", "policy_document_schema_version")
    op.drop_column("enforcement_decisions", "policy_document_sha256")
    op.drop_column("enforcement_decisions", "policy_document_schema_version")

"""add enforcement per-environment mode matrix fields

Revision ID: g2h3i4j5k6l7
Revises: f3c4d5e6a7b8
Create Date: 2026-02-24 23:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, Sequence[str], None] = "f3c4d5e6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enforcement_mode_enum() -> sa.Enum:
    return sa.Enum("shadow", "soft", "hard", name="enforcement_mode", native_enum=False)


def upgrade() -> None:
    op.add_column(
        "enforcement_policies",
        sa.Column("terraform_mode_prod", _enforcement_mode_enum(), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("terraform_mode_nonprod", _enforcement_mode_enum(), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("k8s_admission_mode_prod", _enforcement_mode_enum(), nullable=True),
    )
    op.add_column(
        "enforcement_policies",
        sa.Column("k8s_admission_mode_nonprod", _enforcement_mode_enum(), nullable=True),
    )

    op.execute(
        """
        UPDATE enforcement_policies
        SET
            terraform_mode_prod = terraform_mode,
            terraform_mode_nonprod = terraform_mode,
            k8s_admission_mode_prod = k8s_admission_mode,
            k8s_admission_mode_nonprod = k8s_admission_mode
        """
    )

    op.alter_column("enforcement_policies", "terraform_mode_prod", nullable=False)
    op.alter_column("enforcement_policies", "terraform_mode_nonprod", nullable=False)
    op.alter_column("enforcement_policies", "k8s_admission_mode_prod", nullable=False)
    op.alter_column("enforcement_policies", "k8s_admission_mode_nonprod", nullable=False)


def downgrade() -> None:
    op.drop_column("enforcement_policies", "k8s_admission_mode_nonprod")
    op.drop_column("enforcement_policies", "k8s_admission_mode_prod")
    op.drop_column("enforcement_policies", "terraform_mode_nonprod")
    op.drop_column("enforcement_policies", "terraform_mode_prod")

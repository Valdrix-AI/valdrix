"""add llm usage user_id for per-user quotas

Revision ID: f2b9c0d4e8aa
Revises: 84a6f82e9a14
Create Date: 2026-02-22 23:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b9c0d4e8aa"
down_revision: Union[str, Sequence[str], None] = "84a6f82e9a14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_usage", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_llm_usage_user_id"), "llm_usage", ["user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_llm_usage_user_id_users"),
        "llm_usage",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_llm_usage_user_id_users"), "llm_usage", type_="foreignkey")
    op.drop_index(op.f("ix_llm_usage_user_id"), table_name="llm_usage")
    op.drop_column("llm_usage", "user_id")

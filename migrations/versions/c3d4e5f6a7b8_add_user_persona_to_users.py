"""add_user_persona_to_users

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-13

Adds a user-scoped persona preference used for persona-specific default UX.
This is NOT a permission boundary (RBAC + tier gating remain the security controls).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("persona", sa.String(length=32), nullable=True))
    op.execute("UPDATE users SET persona = 'engineering' WHERE persona IS NULL")
    op.alter_column(
        "users",
        "persona",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'engineering'"),
    )
    op.create_check_constraint(
        "ck_users_persona_valid",
        "users",
        "persona IN ('engineering','finance','platform','leadership')",
    )
    op.create_index(op.f("ix_users_persona"), "users", ["persona"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_persona"), table_name="users")
    op.drop_constraint("ck_users_persona_valid", "users", type_="check")
    op.drop_column("users", "persona")


"""add_blind_indexes

Revision ID: ab12cd34ef56
Revises: 1234567890ab
Create Date: 2026-01-14 23:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.shared.core.security import generate_blind_index

# revision identifiers, used by Alembic.
revision = 'ab12cd34ef56'
down_revision = '1234567890ab'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add columns
    op.add_column('tenants', sa.Column('name_bidx', sa.String(64), nullable=True))
    op.create_index('ix_tenants_name_bidx', 'tenants', ['name_bidx'], unique=False)
    
    op.add_column('users', sa.Column('email_bidx', sa.String(64), nullable=True))
    op.create_index('ix_users_email_bidx', 'users', ['email_bidx'], unique=False)

    # 2. Data Migration: Populate blind indexes for existing data
    # Use raw SQL to avoid dependencies on future model columns (like trial_started_at)
    conn = op.get_bind()
    
    # Populate Tenants
    res = conn.execute(sa.text("SELECT id, name FROM tenants WHERE name IS NOT NULL"))
    for row in res:
        tid, name = row
        bidx = generate_blind_index(name)
        conn.execute(
            sa.text("UPDATE tenants SET name_bidx = :bidx WHERE id = :id"),
            {"bidx": bidx, "id": tid}
        )
    
    # Populate Users
    res = conn.execute(sa.text("SELECT id, email FROM users WHERE email IS NOT NULL"))
    for row in res:
        uid, email = row
        bidx = generate_blind_index(email)
        conn.execute(
            sa.text("UPDATE users SET email_bidx = :bidx WHERE id = :id"),
            {"bidx": bidx, "id": uid}
        )

def downgrade() -> None:
    op.drop_index('ix_users_email_bidx', table_name='users')
    op.drop_column('users', 'email_bidx')
    op.drop_index('ix_tenants_name_bidx', table_name='tenants')
    op.drop_column('tenants', 'name_bidx')

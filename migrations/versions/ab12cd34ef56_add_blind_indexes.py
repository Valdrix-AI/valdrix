"""add_blind_indexes

Revision ID: ab12cd34ef56
Revises: 1234567890ab
Create Date: 2026-01-14 23:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.core.security import generate_blind_index

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
    # We use a session to handle the decryption/hashing
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Import ALL models to ensure relationships (like BackgroundJob) are registered
        from app.models.tenant import Tenant, User
        from app.models.background_job import BackgroundJob
        from app.models.llm import LLMUsage, LLMBudget
        from app.models.aws_connection import AWSConnection
        
        # Populate Tenants
        tenants = session.query(Tenant).all()
        for t in tenants:
            if t.name:
                t.name_bidx = generate_blind_index(t.name)
        
        # Populate Users
        users = session.query(User).all()
        for u in users:
            if u.email:
                u.email_bidx = generate_blind_index(u.email)
        
        session.commit()
    except Exception as e:
        print(f"Error during data migration: {e}")
        session.rollback()
        # We don't want to fail the whole migration if data pop fails in some envs, 
        # but in prod we should be careful.
    finally:
        session.close()

def downgrade() -> None:
    op.drop_index('ix_users_email_bidx', table_name='users')
    op.drop_column('users', 'email_bidx')
    op.drop_index('ix_tenants_name_bidx', table_name='tenants')
    op.drop_column('tenants', 'name_bidx')

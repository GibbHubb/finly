"""add currency fields to users and transactions

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('base_currency', sa.String(3), nullable=False, server_default='EUR'),
    )
    op.add_column(
        'transactions',
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),
    )


def downgrade() -> None:
    op.drop_column('transactions', 'currency')
    op.drop_column('users', 'base_currency')

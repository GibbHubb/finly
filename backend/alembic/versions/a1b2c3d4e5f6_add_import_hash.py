"""add import_hash to transactions

Revision ID: a1b2c3d4e5f6
Revises: d54e5cc41632
Create Date: 2026-04-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'd54e5cc41632'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('import_hash', sa.Text(), nullable=True),
    )
    op.create_index(
        op.f('ix_transactions_import_hash'),
        'transactions',
        ['import_hash'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_import_hash'), table_name='transactions')
    op.drop_column('transactions', 'import_hash')

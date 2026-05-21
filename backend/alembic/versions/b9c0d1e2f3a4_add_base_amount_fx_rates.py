"""add base_amount to transactions + fx_rates table

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-04-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b9c0d1e2f3a4'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('base_amount', sa.Numeric(12, 2), nullable=True),
    )
    op.create_table(
        'fx_rates',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rate_date', sa.Date(), nullable=False, index=True),
        sa.Column('currency', sa.String(3), nullable=False),
        # Rate is the amount of {currency} per 1 EUR (ECB-style).
        sa.Column('rate_vs_eur', sa.Numeric(18, 8), nullable=False),
        sa.UniqueConstraint('rate_date', 'currency', name='uq_fx_rates_date_currency'),
    )


def downgrade() -> None:
    op.drop_table('fx_rates')
    op.drop_column('transactions', 'base_amount')

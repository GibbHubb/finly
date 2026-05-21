"""add categorisation rules table + transactions.categorised_by_rule_id

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-04-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'categorisation_rules',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('match_type', sa.String(20), nullable=False),
        sa.Column('match_value', sa.String(255), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.add_column(
        'transactions',
        sa.Column('categorised_by_rule_id', sa.Integer(), sa.ForeignKey('categorisation_rules.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('transactions', 'categorised_by_rule_id')
    op.drop_table('categorisation_rules')

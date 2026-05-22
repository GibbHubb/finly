"""add parent_transaction_id self-FK on transactions (F25 — split tx)

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-05-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable self-FK; the parent stays as the bank-truth record and
    # children carry the category breakdown. ON DELETE CASCADE so deleting
    # the parent cleans up its children automatically.
    with op.batch_alter_table('transactions') as batch:
        batch.add_column(
            sa.Column('parent_transaction_id', sa.Integer(), nullable=True),
        )
        batch.create_foreign_key(
            'fk_transactions_parent_transaction_id',
            referent_table='transactions',
            local_cols=['parent_transaction_id'],
            remote_cols=['id'],
            ondelete='CASCADE',
        )
        batch.create_index(
            'ix_transactions_parent_transaction_id',
            ['parent_transaction_id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('transactions') as batch:
        batch.drop_index('ix_transactions_parent_transaction_id')
        batch.drop_constraint('fk_transactions_parent_transaction_id', type_='foreignkey')
        batch.drop_column('parent_transaction_id')

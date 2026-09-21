"""F44: index transactions(user_id, transaction_date)

Every list, summary, trend and report filters transactions by user_id and orders or bounds by
transaction_date. The baseline created indexes on id, import_hash and parent_transaction_id only,
so each of those is a sequential scan of the whole table.

Revision ID: f44a1b2c3d4e
Revises: 577651163975
"""
from alembic import op

revision = "f44a1b2c3d4e"
down_revision = "577651163975"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "transaction_date"])


def downgrade() -> None:
    op.drop_index("ix_transactions_user_date", table_name="transactions")

"""F45: one budget per (user, category, month, year); refresh_tokens.created_at NOT NULL

`services/budgets.create_budget` enforced the budget rule with SELECT-then-INSERT, which two
concurrent POSTs both pass. The constraint is what makes it true.

`refresh_tokens.created_at` is NOT NULL in the model (`Mapped[datetime]`) but F42's migration
created it nullable. `alembic check` found the drift the first time it ran against Postgres.

Revision ID: f45b0d9e7c1a
Revises: 9c2f7a1e8b4d
"""
import sqlalchemy as sa
from alembic import op

revision = "f45b0d9e7c1a"
down_revision = "9c2f7a1e8b4d"
branch_labels = None
depends_on = None

_UQ = "uq_budgets_user_category_period"


def upgrade() -> None:
    # Never delete a user's budget to make a migration pass. If the race already happened,
    # stop and say how many groups need a human decision.
    dupes = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT 1 FROM budgets "
        "GROUP BY user_id, category, month, year HAVING COUNT(*) > 1) d"
    )).scalar()
    if dupes:
        raise RuntimeError(
            f"F45: {dupes} (user, category, month, year) group(s) in `budgets` already hold "
            "more than one row. Resolve them by hand before this migration can add "
            f"{_UQ}; nothing was changed."
        )

    with op.batch_alter_table("budgets") as batch:
        batch.create_unique_constraint(_UQ, ["user_id", "category", "month", "year"])

    with op.batch_alter_table("refresh_tokens") as batch:
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(), nullable=False,
            existing_server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(), nullable=True,
            existing_server_default=sa.func.now(),
        )

    with op.batch_alter_table("budgets") as batch:
        batch.drop_constraint(_UQ, type_="unique")

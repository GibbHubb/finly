"""F64: one account per email, whatever its case (unique index on lower(email))

Login and registration now match users on lower(email) (services/auth.py). This index is
what makes "at most one row matches" true in the database, including for two registrations
racing each other. Existing rows are NOT rewritten: a legacy mixed-case email keeps working
because the lookup is on lower(email), not on a lowercased column.

Note on the collision check: it groups on lower(email) only, NOT trim, matching the index.
The app also strips whitespace (normalise_email), but a stored email with surrounding
spaces is not counted as colliding here (prod had none on 2026-11-21). And Python's
str.lower() (what the app writes) and Postgres lower() (what the index and lookup use,
locale-dependent) agree on ASCII but can differ for some non-ASCII characters.

Revision ID: f64c1e5a9b2d
Revises: f45b0d9e7c1a
"""
import sqlalchemy as sa
from alembic import op

revision = "f64c1e5a9b2d"
down_revision = "f45b0d9e7c1a"
branch_labels = None
depends_on = None

_IX = "ix_users_email_lower"


def upgrade() -> None:
    # Never merge or delete an account to make a migration pass. Two users whose emails
    # differ only by case are two people's data (or one person's two accounts): a human
    # decides which survives. Stop, say how many, change nothing.
    collisions = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT 1 FROM users "
        "GROUP BY lower(email) HAVING COUNT(*) > 1) d"
    )).scalar()
    if collisions:
        raise RuntimeError(
            f"F64: {collisions} email(s) in `users` are held by more than one account when "
            "case is ignored (e.g. `Bob@x.com` and `bob@x.com`). Find them with "
            "`SELECT lower(email), COUNT(*) FROM users GROUP BY lower(email) HAVING COUNT(*) > 1`, "
            f"resolve them by hand, then re-run; {_IX} was not created and nothing was changed."
        )

    op.create_index(_IX, "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index(_IX, table_name="users")

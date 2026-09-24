"""F42: refresh_tokens + login_attempts

refresh_tokens is the server-side revocation record for a session `jti`
(shared by the access and refresh JWTs minted together); login_attempts
backs the DB-based login lockout counter (see app/models/refresh_token.py
and app/models/login_attempt.py for the full rationale).

Revision ID: 9c2f7a1e8b4d
Revises: f44a1b2c3d4e
"""
import sqlalchemy as sa
from alembic import op

revision = "9c2f7a1e8b4d"
down_revision = "f44a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("jti", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(length=255), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("refresh_tokens")

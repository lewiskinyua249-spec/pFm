"""Add hashed email verification codes.

Revision ID: 51c8bfae04d3
Revises: a47c91ef320b
Create Date: 2026-11-26 09:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "51c8bfae04d3"
down_revision = "a47c91ef320b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("email_verification_code_hash", sa.String(length=64))
    )
    op.add_column(
        "users",
        sa.Column("email_verification_code_expires_at", sa.DateTime())
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verification_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0"
        )
    )


def downgrade():
    op.drop_column("users", "email_verification_attempts")
    op.drop_column("users", "email_verification_code_expires_at")
    op.drop_column("users", "email_verification_code_hash")

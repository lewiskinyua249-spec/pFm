"""Add user email verification state.

Revision ID: a47c91ef320b
Revises: c4a28f2d109e
Create Date: 2026-11-25 12:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a47c91ef320b"
down_revision = "c4a28f2d109e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true()
        )
    )
    op.add_column(
        "users",
        sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True)
    )


def downgrade():
    op.drop_column("users", "email_verification_sent_at")
    op.drop_column("users", "email_verified")

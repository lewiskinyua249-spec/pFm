"""Add recurring income and expense reminders

Revision ID: 91f4b24c8a10
Revises: f0ade68a0b13
Create Date: 2026-11-20 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "91f4b24c8a10"
down_revision = "f0ade68a0b13"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recurring_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_recurring_item_positive_amount"
        ),
        sa.CheckConstraint(
            "type IN ('income', 'expense')",
            name="ck_recurring_item_valid_type"
        ),
        sa.CheckConstraint(
            "frequency IN ('weekly', 'monthly')",
            name="ck_recurring_item_valid_frequency"
        ),
        sa.CheckConstraint(
            "(frequency = 'weekly' AND day_of_month IS NULL) OR "
            "(frequency = 'monthly' AND day_of_month BETWEEN 1 AND 31)",
            name="ck_recurring_item_schedule_anchor"
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(
        op.f("ix_recurring_items_category_id"),
        "recurring_items",
        ["category_id"],
        unique=False
    )
    op.create_index(
        op.f("ix_recurring_items_next_due_date"),
        "recurring_items",
        ["next_due_date"],
        unique=False
    )
    op.create_index(
        op.f("ix_recurring_items_user_id"),
        "recurring_items",
        ["user_id"],
        unique=False
    )


def downgrade():
    op.drop_index(
        op.f("ix_recurring_items_user_id"),
        table_name="recurring_items"
    )
    op.drop_index(
        op.f("ix_recurring_items_next_due_date"),
        table_name="recurring_items"
    )
    op.drop_index(
        op.f("ix_recurring_items_category_id"),
        table_name="recurring_items"
    )
    op.drop_table("recurring_items")

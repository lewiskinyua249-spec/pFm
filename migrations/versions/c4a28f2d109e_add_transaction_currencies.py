"""Add original currency amounts and historical exchange rates.

Revision ID: c4a28f2d109e
Revises: 91f4b24c8a10
Create Date: 2026-11-23 11:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c4a28f2d109e"
down_revision = "91f4b24c8a10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transactions",
        sa.Column("original_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "transactions",
        sa.Column("currency", sa.String(length=3), nullable=True)
    )
    op.add_column(
        "transactions",
        sa.Column("exchange_rate", sa.Numeric(20, 10), nullable=True)
    )
    op.add_column(
        "transactions",
        sa.Column("exchange_rate_date", sa.Date(), nullable=True)
    )

    op.execute(
        "UPDATE transactions "
        "SET original_amount = amount, "
        "currency = 'KES', "
        "exchange_rate = 1, "
        "exchange_rate_date = date"
    )

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column(
            "original_amount",
            existing_type=sa.Numeric(12, 2),
            nullable=False
        )
        batch_op.alter_column(
            "currency",
            existing_type=sa.String(length=3),
            nullable=False
        )
        batch_op.alter_column(
            "exchange_rate",
            existing_type=sa.Numeric(20, 10),
            nullable=False
        )
        batch_op.alter_column(
            "exchange_rate_date",
            existing_type=sa.Date(),
            nullable=False
        )
        batch_op.create_check_constraint(
            "ck_transaction_positive_original_amount",
            "original_amount > 0"
        )
        batch_op.create_check_constraint(
            "ck_transaction_positive_exchange_rate",
            "exchange_rate > 0"
        )


def downgrade():
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_constraint(
            "ck_transaction_positive_exchange_rate",
            type_="check"
        )
        batch_op.drop_constraint(
            "ck_transaction_positive_original_amount",
            type_="check"
        )
        batch_op.drop_column("exchange_rate_date")
        batch_op.drop_column("exchange_rate")
        batch_op.drop_column("currency")
        batch_op.drop_column("original_amount")

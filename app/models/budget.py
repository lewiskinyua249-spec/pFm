
from datetime import datetime

from sqlalchemy import CheckConstraint, UniqueConstraint

from app import db


class Budget(db.Model):

    __tablename__ = "budgets"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_budget_positive_amount"
        ),
        CheckConstraint(
            "month BETWEEN 1 AND 12",
            name="ck_budget_valid_month"
        ),
        CheckConstraint(
            "year >= 2000",
            name="ck_budget_valid_year"
        ),
        UniqueConstraint(
            "user_id",
            "category_id",
            "month",
            "year",
            name="uq_budget_user_category_period"
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    month = db.Column(
        db.Integer,
        nullable=False
    )

    year = db.Column(
        db.Integer,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        nullable=True,
        index=True
    )

    category = db.relationship(
        "Category",
        backref="budgets"
    )

    def __repr__(self):
        return (
            f"<Budget {self.amount} "
            f"for {self.month}/{self.year}>"
        )

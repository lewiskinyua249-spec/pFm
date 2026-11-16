
from datetime import datetime

from sqlalchemy import CheckConstraint

from app import db


class Transaction(db.Model):

    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_transaction_positive_amount"
        ),
        CheckConstraint(
            "type IN ('income', 'expense')",
            name="ck_transaction_valid_type"
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

    type = db.Column(
        db.String(20),
        nullable=False
    )

    description = db.Column(
        db.String(255),
        nullable=True
    )

    date = db.Column(
        db.Date,
        nullable=False,
        default=lambda: datetime.utcnow().date(),
        index=True
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
        backref="transactions"
    )

    def __repr__(self):
        return (
            f"<Transaction {self.type}: "
            f"{self.amount}>"
        )

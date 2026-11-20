from datetime import datetime

from sqlalchemy import CheckConstraint

from app import db


class RecurringItem(db.Model):

    __tablename__ = "recurring_items"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_recurring_item_positive_amount"
        ),
        CheckConstraint(
            "type IN ('income', 'expense')",
            name="ck_recurring_item_valid_type"
        ),
        CheckConstraint(
            "frequency IN ('weekly', 'monthly')",
            name="ck_recurring_item_valid_frequency"
        ),
        CheckConstraint(
            "(frequency = 'weekly' AND day_of_month IS NULL) OR "
            "(frequency = 'monthly' AND day_of_month BETWEEN 1 AND 31)",
            name="ck_recurring_item_schedule_anchor"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)
    next_due_date = db.Column(db.Date, nullable=False, index=True)
    day_of_month = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
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
        backref="recurring_items"
    )

    def __repr__(self):
        return f"<RecurringItem {self.name}: {self.frequency}>"

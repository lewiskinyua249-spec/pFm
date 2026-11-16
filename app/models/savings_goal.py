
from datetime import datetime

from sqlalchemy import CheckConstraint

from app import db


class SavingsGoal(db.Model):

    __tablename__ = "savings_goals"

    __table_args__ = (
        CheckConstraint(
            "target_amount > 0",
            name="ck_savings_goal_positive_target"
        ),
        CheckConstraint(
            "current_amount >= 0",
            name="ck_savings_goal_nonnegative_current"
        ),
        CheckConstraint(
            "current_amount <= target_amount",
            name="ck_savings_goal_current_within_target"
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    target_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    current_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=0
    )

    deadline = db.Column(
        db.Date,
        nullable=True
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

    def __repr__(self):
        return (
            f"<SavingsGoal {self.name}: "
            f"{self.current_amount}/"
            f"{self.target_amount}>"
        )

    @property
    def progress_percentage(self):
        """Calculate savings progress as a percentage."""

        if self.target_amount <= 0:
            return 0

        progress = (
            self.current_amount / self.target_amount
        ) * 100

        return min(float(progress), 100.0)

    @property
    def remaining_amount(self):
        """Calculate the remaining amount needed."""

        remaining = self.target_amount - self.current_amount

        return max(remaining, 0)

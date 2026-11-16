
from datetime import datetime

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from flask_login import UserMixin

from app import db


class User(UserMixin, db.Model):

    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # User's financial transactions
    transactions = db.relationship(
        "Transaction",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    # User's income and expense categories
    categories = db.relationship(
        "Category",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    # User's budgets
    budgets = db.relationship(
        "Budget",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    # User's savings goals
    savings_goals = db.relationship(
        "SavingsGoal",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(
            password,
            method="scrypt"
        )

    def check_password(self, password):
        """Verify a password against its stored hash."""
        return check_password_hash(
            self.password_hash,
            password
        )

    def __repr__(self):
        return f"<User {self.username}>"

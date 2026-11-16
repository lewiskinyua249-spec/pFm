
from sqlalchemy import UniqueConstraint

from app import db


class Category(db.Model):

    __tablename__ = "categories"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "name",
            "type",
            name="uq_category_user_name_type"
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(80),
        nullable=False
    )

    type = db.Column(
        db.String(20),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    def __repr__(self):
        return (
            f"<Category {self.name} "
            f"({self.type})>"
        )

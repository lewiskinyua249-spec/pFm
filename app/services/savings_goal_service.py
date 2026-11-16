
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import SavingsGoal


MAX_AMOUNT = Decimal("9999999999.99")


def validate_money_amount(value, field_name):

    try:
        amount = Decimal(str(value))

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            f"Enter a valid {field_name}."
        )

    if not amount.is_finite() or amount <= 0:
        raise ValueError(
            f"{field_name.capitalize()} must be greater than zero."
        )

    if amount > MAX_AMOUNT:
        raise ValueError(
            f"{field_name.capitalize()} is too large."
        )

    try:
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(
                "Amount cannot have more than two decimal places."
            )

    except InvalidOperation:
        raise ValueError(
            f"Enter a valid {field_name}."
        )

    return amount


def validate_goal_name(name):

    name = (name or "").strip()

    if not name:
        raise ValueError("Goal name is required.")

    if len(name) > 100:
        raise ValueError(
            "Goal name cannot exceed 100 characters."
        )

    return name


def validate_deadline(deadline):

    if deadline in (None, ""):
        return None

    if isinstance(deadline, datetime):
        deadline = deadline.date()

    elif not isinstance(deadline, date):

        try:
            deadline = date.fromisoformat(str(deadline))

        except (ValueError, TypeError):
            raise ValueError("Enter a valid deadline.")

    if deadline < date.today():
        raise ValueError("Deadline cannot be in the past.")

    return deadline


def create_savings_goal(
    user_id,
    name,
    target_amount,
    deadline=None
):

    name = validate_goal_name(name)

    target_amount = validate_money_amount(
        target_amount,
        "target amount"
    )

    deadline = validate_deadline(deadline)

    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        current_amount=Decimal("0.00"),
        deadline=deadline
    )

    try:
        db.session.add(goal)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        raise ValueError(
            "Could not create this savings goal."
        )

    except Exception:
        db.session.rollback()
        raise

    return goal


def get_user_savings_goals(user_id):

    return SavingsGoal.query.filter_by(
        user_id=user_id
    ).order_by(
        SavingsGoal.created_at.desc()
    ).all()


def get_savings_goal_by_id(goal_id, user_id):

    return SavingsGoal.query.filter_by(
        id=goal_id,
        user_id=user_id
    ).first()


def update_savings_progress(goal_id, user_id, amount):

    goal = get_savings_goal_by_id(
        goal_id,
        user_id
    )

    if not goal:
        raise ValueError("Savings goal not found.")

    amount = validate_money_amount(
        amount,
        "savings amount"
    )

    if goal.current_amount >= goal.target_amount:
        raise ValueError("This savings goal is already complete.")

    new_total = goal.current_amount + amount

    if new_total > goal.target_amount:
        raise ValueError(
            "Savings cannot exceed the target amount."
        )

    goal.current_amount = new_total

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return goal


def delete_savings_goal(goal_id, user_id):

    goal = get_savings_goal_by_id(
        goal_id,
        user_id
    )

    if not goal:
        raise ValueError("Savings goal not found.")

    try:
        db.session.delete(goal)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return True

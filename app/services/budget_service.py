
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Budget, Category, Transaction


MAX_AMOUNT = Decimal("9999999999.99")


def validate_budget_amount(value):

    try:
        amount = Decimal(str(value))

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid budget amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError(
            "Budget amount must be greater than zero."
        )

    if amount > MAX_AMOUNT:
        raise ValueError("Budget amount is too large.")

    try:
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(
                "Budget cannot have more than two decimal places."
            )

    except InvalidOperation:
        raise ValueError("Enter a valid budget amount.")

    return amount


def validate_month_year(month, year):

    try:
        month_text = str(month).strip()
        year_text = str(year).strip()

        if not month_text.isdigit() or not year_text.isdigit():
            raise ValueError()

        month = int(month_text)
        year = int(year_text)

    except (ValueError, TypeError):
        raise ValueError("Enter a valid month and year.")

    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12.")

    if year < 2000:
        raise ValueError("Year must be 2000 or later.")

    return month, year


def validate_budget_category(user_id, category_id):

    if category_id in (None, ""):
        return None

    try:
        category_id = int(category_id)

    except (ValueError, TypeError):
        raise ValueError("Select a valid expense category.")

    category = Category.query.filter_by(
        id=category_id,
        user_id=user_id,
        type="expense"
    ).first()

    if not category:
        raise ValueError(
            "Select a valid expense category belonging to your account."
        )

    return category_id


def create_budget(user_id, amount, month, year, category_id=None):

    amount = validate_budget_amount(amount)

    month, year = validate_month_year(month, year)

    category_id = validate_budget_category(
        user_id,
        category_id
    )

    existing_query = Budget.query.filter_by(
        user_id=user_id,
        month=month,
        year=year
    )

    if category_id is None:
        existing_query = existing_query.filter(
            Budget.category_id.is_(None)
        )

    else:
        existing_query = existing_query.filter_by(
            category_id=category_id
        )

    if existing_query.first():
        raise ValueError(
            "A budget already exists for this category and month."
        )

    budget = Budget(
        user_id=user_id,
        amount=amount,
        month=month,
        year=year,
        category_id=category_id
    )

    try:
        db.session.add(budget)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        raise ValueError("This budget already exists.")

    except Exception:
        db.session.rollback()
        raise

    return budget


def get_user_budgets(user_id, month=None, year=None):

    query = Budget.query.filter_by(
        user_id=user_id
    )

    if month is not None:
        month, _ = validate_month_year(month, 2000)
        query = query.filter_by(month=month)

    if year is not None:
        _, year = validate_month_year(1, year)
        query = query.filter_by(year=year)

    return query.order_by(
        Budget.year.desc(),
        Budget.month.desc()
    ).all()


def get_budget_by_id(budget_id, user_id):

    return Budget.query.filter_by(
        id=budget_id,
        user_id=user_id
    ).first()


def update_budget(
    budget_id,
    user_id,
    amount,
    month,
    year,
    category_id=None
):

    budget = get_budget_by_id(budget_id, user_id)

    if not budget:
        raise ValueError("Budget not found.")

    amount = validate_budget_amount(amount)
    month, year = validate_month_year(month, year)
    category_id = validate_budget_category(user_id, category_id)

    existing_query = Budget.query.filter(
        Budget.user_id == user_id,
        Budget.month == month,
        Budget.year == year,
        Budget.id != budget.id
    )

    if category_id is None:
        existing_query = existing_query.filter(
            Budget.category_id.is_(None)
        )
    else:
        existing_query = existing_query.filter_by(
            category_id=category_id
        )

    if existing_query.first():
        raise ValueError(
            "A budget already exists for this category and month."
        )

    budget.amount = amount
    budget.month = month
    budget.year = year
    budget.category_id = category_id

    try:
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        raise ValueError("This budget already exists.")

    except Exception:
        db.session.rollback()
        raise

    return budget


def delete_budget(budget_id, user_id):

    budget = get_budget_by_id(budget_id, user_id)

    if not budget:
        raise ValueError("Budget not found.")

    try:
        db.session.delete(budget)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return True


def calculate_budget_spending(budget):

    start_date = date(
        budget.year,
        budget.month,
        1
    )

    if budget.month == 12:
        end_date = date(
            budget.year + 1,
            1,
            1
        )

    else:
        end_date = date(
            budget.year,
            budget.month + 1,
            1
        )

    query = db.session.query(
        func.coalesce(
            func.sum(Transaction.amount),
            0
        )
    ).filter(
        Transaction.user_id == budget.user_id,
        Transaction.type == "expense",
        Transaction.date >= start_date,
        Transaction.date < end_date
    )

    if budget.category_id is not None:
        query = query.filter(
            Transaction.category_id == budget.category_id
        )

    spent = Decimal(str(query.scalar()))

    remaining = budget.amount - spent

    percentage = (
        (spent / budget.amount) * 100
        if budget.amount > 0
        else Decimal("0")
    )

    return {
        "budget": budget.amount,
        "spent": spent,
        "remaining": remaining,
        "percentage": float(percentage),
        "exceeded": spent > budget.amount
    }

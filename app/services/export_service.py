
import csv
import io

from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import (
    Transaction,
    Category,
    Budget,
    SavingsGoal,
    RecurringItem
)


def money_to_string(value):
    """Convert a financial value into a precise string."""

    return str(Decimal(str(value or 0)))


def date_to_string(value):
    """Convert dates and datetimes into ISO format."""

    if value is None:
        return None

    return value.isoformat()


def validate_export_dates(start_date=None, end_date=None):
    """Validate optional export date filters."""

    if isinstance(start_date, datetime):
        start_date = start_date.date()

    if isinstance(end_date, datetime):
        end_date = end_date.date()

    if start_date is not None and not isinstance(start_date, date):
        raise ValueError("Enter a valid export start date.")

    if end_date is not None and not isinstance(end_date, date):
        raise ValueError("Enter a valid export end date.")

    if start_date and end_date and start_date > end_date:
        raise ValueError(
            "Start date cannot be after end date."
        )

    return start_date, end_date


def get_transactions_for_export(
    user_id,
    start_date=None,
    end_date=None
):
    """Retrieve only the specified user's transactions."""

    start_date, end_date = validate_export_dates(
        start_date,
        end_date
    )

    query = Transaction.query.filter_by(
        user_id=user_id
    )

    if start_date:
        query = query.filter(
            Transaction.date >= start_date
        )

    if end_date:
        query = query.filter(
            Transaction.date <= end_date
        )

    return query.order_by(
        Transaction.date.desc(),
        Transaction.id.desc()
    ).all()


def generate_transactions_csv(
    user_id,
    start_date=None,
    end_date=None
):
    """Generate a CSV file containing the user's transactions."""

    transactions = get_transactions_for_export(
        user_id,
        start_date,
        end_date
    )

    # Fetch the user's categories once instead of querying
    # the database separately for every transaction.
    categories = {
        category.id: category.name
        for category in Category.query.filter_by(
            user_id=user_id
        ).all()
    }

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Type",
        "Category",
        "Description",
        "Amount",
        "Currency",
        "Amount (KES)",
        "Exchange Rate",
        "Exchange Rate Date"
    ])

    for transaction in transactions:

        category_name = categories.get(
            transaction.category_id,
            "Uncategorized"
        )

        writer.writerow([
            date_to_string(transaction.date),
            transaction.type,
            category_name,
            transaction.description or "",
            money_to_string(transaction.original_amount),
            transaction.currency,
            money_to_string(transaction.amount),
            money_to_string(transaction.exchange_rate),
            date_to_string(transaction.exchange_rate_date)
        ])

    return output.getvalue()


def generate_personal_backup(user_id):
    """
    Generate a versioned JSON-compatible backup
    containing only the specified user's records.
    """

    transactions = Transaction.query.filter_by(
        user_id=user_id
    ).order_by(
        Transaction.id.asc()
    ).all()

    categories = Category.query.filter_by(
        user_id=user_id
    ).order_by(
        Category.id.asc()
    ).all()

    budgets = Budget.query.filter_by(
        user_id=user_id
    ).order_by(
        Budget.id.asc()
    ).all()

    savings_goals = SavingsGoal.query.filter_by(
        user_id=user_id
    ).order_by(
        SavingsGoal.id.asc()
    ).all()

    recurring_items = RecurringItem.query.filter_by(
        user_id=user_id
    ).order_by(
        RecurringItem.id.asc()
    ).all()

    backup = {

        "application": "Personal Finance Manager",

        "backup_version": 3,

        "backup_date": datetime.now(
            timezone.utc
        ).isoformat(),

        "user_id": user_id,

        "transactions": [
            {
                "id": item.id,
                "amount": money_to_string(item.amount),
                "original_amount": money_to_string(item.original_amount),
                "currency": item.currency,
                "exchange_rate": money_to_string(item.exchange_rate),
                "exchange_rate_date": date_to_string(
                    item.exchange_rate_date
                ),
                "type": item.type,
                "description": item.description,
                "date": date_to_string(item.date),
                "category_id": item.category_id
            }
            for item in transactions
        ],

        "categories": [
            {
                "id": item.id,
                "name": item.name,
                "type": item.type
            }
            for item in categories
        ],

        "budgets": [
            {
                "id": item.id,
                "amount": money_to_string(item.amount),
                "month": item.month,
                "year": item.year,
                "category_id": item.category_id
            }
            for item in budgets
        ],

        "savings_goals": [
            {
                "id": item.id,
                "name": item.name,
                "target_amount": money_to_string(
                    item.target_amount
                ),
                "current_amount": money_to_string(
                    item.current_amount
                ),
                "deadline": date_to_string(item.deadline)
            }
            for item in savings_goals
        ],

        "recurring_items": [
            {
                "id": item.id,
                "name": item.name,
                "amount": money_to_string(item.amount),
                "type": item.type,
                "frequency": item.frequency,
                "next_due_date": date_to_string(item.next_due_date),
                "day_of_month": item.day_of_month,
                "is_active": item.is_active,
                "category_id": item.category_id
            }
            for item in recurring_items
        ]
    }

    return backup


from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from app.models import Transaction, Category


def validate_report_dates(start_date, end_date):

    if isinstance(start_date, datetime):
        start_date = start_date.date()

    if isinstance(end_date, datetime):
        end_date = end_date.date()

    if not isinstance(start_date, date):
        raise ValueError("Enter a valid report start date.")

    if not isinstance(end_date, date):
        raise ValueError("Enter a valid report end date.")

    if start_date > end_date:
        raise ValueError(
            "Start date cannot be after end date."
        )

    return start_date, end_date


def get_financial_report(user_id, start_date, end_date):

    start_date, end_date = validate_report_dates(
        start_date,
        end_date
    )

    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).order_by(
        Transaction.date.asc(),
        Transaction.id.asc()
    ).all()

    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")

    category_totals = defaultdict(
        lambda: Decimal("0.00")
    )

    monthly_totals = defaultdict(
        lambda: {
            "income": Decimal("0.00"),
            "expenses": Decimal("0.00")
        }
    )

    for transaction in transactions:

        month_key = transaction.date.strftime("%Y-%m")

        if transaction.type == "income":

            total_income += transaction.amount

            monthly_totals[month_key]["income"] += (
                transaction.amount
            )

        elif transaction.type == "expense":

            total_expenses += transaction.amount

            monthly_totals[month_key]["expenses"] += (
                transaction.amount
            )

            category_name = "Uncategorized"

            if transaction.category_id is not None:

                category = Category.query.filter_by(
                    id=transaction.category_id,
                    user_id=user_id,
                    type="expense"
                ).first()

                if category:
                    category_name = category.name

            category_totals[category_name] += (
                transaction.amount
            )

    net_balance = total_income - total_expenses

    category_breakdown = []

    for name, amount in sorted(
        category_totals.items(),
        key=lambda item: item[1],
        reverse=True
    ):

        percentage = (
            float((amount / total_expenses) * 100)
            if total_expenses > 0
            else 0.0
        )

        category_breakdown.append({
            "name": name,
            "amount": amount,
            "percentage": percentage
        })

    monthly_data = []

    for month, values in sorted(monthly_totals.items()):

        income = values["income"]
        expenses = values["expenses"]

        monthly_data.append({
            "month": month,
            "income": income,
            "expenses": expenses,
            "net_balance": income - expenses
        })

    largest_month = max(
        (
            max(item["income"], item["expenses"])
            for item in monthly_data
        ),
        default=Decimal("0.00")
    )

    for item in monthly_data:

        if largest_month > 0:

            item["income_width"] = float(
                item["income"] / largest_month * 100
            )

            item["expense_width"] = float(
                item["expenses"] / largest_month * 100
            )

        else:

            item["income_width"] = 0.0
            item["expense_width"] = 0.0

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_balance": net_balance,
        "transaction_count": len(transactions),
        "category_breakdown": category_breakdown,
        "monthly_data": monthly_data
    }

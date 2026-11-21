from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import and_, func

from app import db
from app.models import Category, Transaction


MIN_ABSOLUTE_CHANGE = Decimal("100.00")
MIN_PERCENT_CHANGE = Decimal("20")
MAX_EXPENSE_MIX_CATEGORIES = 5
EXPENSE_MIX_COLORS = (
    "#226b4d",
    "#d0a251",
    "#6086b1",
    "#c3665f",
    "#8a73ad"
)


def _expense_totals_by_category(user_id, start_date, end_date):
    results = db.session.query(
        Category.id,
        Category.name,
        func.sum(Transaction.amount).label("total")
    ).outerjoin(
        Category,
        and_(
            Category.id == Transaction.category_id,
            Category.user_id == user_id,
            Category.type == "expense"
        )
    ).filter(
        Transaction.user_id == user_id,
        Transaction.type == "expense",
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).group_by(
        Category.id,
        Category.name
    ).all()

    return {
        result.id: {
            "name": result.name or "Uncategorized",
            "amount": Decimal(str(result.total))
        }
        for result in results
    }


def _build_expense_mix(category_totals, expense_total):
    if expense_total == 0:
        return []

    totals_by_name = defaultdict(lambda: Decimal("0.00"))
    for item in category_totals.values():
        totals_by_name[item["name"]] += item["amount"]

    ranked_categories = sorted(
        totals_by_name.items(),
        key=lambda item: (-item[1], item[0].casefold())
    )

    if len(ranked_categories) > MAX_EXPENSE_MIX_CATEGORIES:
        top_categories = ranked_categories[:MAX_EXPENSE_MIX_CATEGORIES - 1]
        other_total = sum(
            (amount for _, amount in ranked_categories[MAX_EXPENSE_MIX_CATEGORIES - 1:]),
            Decimal("0.00")
        )
        ranked_categories = top_categories + [("Other", other_total)]

    expense_mix = []
    accumulated_percent = Decimal("0.00")

    for index, (category_name, amount) in enumerate(ranked_categories):
        exact_percent = amount / expense_total * Decimal("100")
        is_last = index == len(ranked_categories) - 1
        chart_percent = (
            Decimal("100.00") - accumulated_percent
            if is_last
            else exact_percent.quantize(
                Decimal("0.01"),
                rounding=ROUND_DOWN
            )
        )
        dash_offset = -accumulated_percent
        accumulated_percent += chart_percent

        expense_mix.append({
            "name": category_name,
            "amount": amount,
            "percentage": exact_percent.quantize(Decimal("1")),
            "color": EXPENSE_MIX_COLORS[index],
            "dasharray": (
                f"{chart_percent} "
                f"{Decimal('100.00') - chart_percent}"
            ),
            "dashoffset": dash_offset
        })

    return expense_mix


def get_spending_insights(user_id, start_date, end_date):
    if start_date > end_date:
        raise ValueError("Start date cannot be after end date.")

    period_days = (end_date - start_date).days + 1
    comparison_end = start_date - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=period_days - 1)

    current_totals = _expense_totals_by_category(
        user_id,
        start_date,
        end_date
    )
    comparison_totals = _expense_totals_by_category(
        user_id,
        comparison_start,
        comparison_end
    )

    insights = []
    current_expenses = sum(
        (item["amount"] for item in current_totals.values()),
        Decimal("0.00")
    )
    expense_mix = _build_expense_mix(
        current_totals,
        current_expenses
    )

    if current_totals:
        top_category = max(
            current_totals.values(),
            key=lambda item: (item["amount"], item["name"].casefold())
        )
        insights.append({
            "kind": "top_category",
            "category": top_category["name"],
            "amount": top_category["amount"],
            "share_percent": (
                top_category["amount"] / current_expenses * Decimal("100")
            ).quantize(Decimal("1"))
        })

    changes = []
    category_ids = set(current_totals) | set(comparison_totals)

    for category_id in category_ids:
        current = current_totals.get(category_id, {})
        previous = comparison_totals.get(category_id, {})
        current_amount = current.get("amount", Decimal("0.00"))
        previous_amount = previous.get("amount", Decimal("0.00"))

        if previous_amount == 0:
            continue

        difference = current_amount - previous_amount
        absolute_difference = abs(difference)
        percent_change = (
            absolute_difference / previous_amount * Decimal("100")
        )

        if (
            absolute_difference < MIN_ABSOLUTE_CHANGE
            or percent_change < MIN_PERCENT_CHANGE
        ):
            continue

        changes.append({
            "kind": "increase" if difference > 0 else "decrease",
            "category": current.get(
                "name",
                previous.get("name", "Uncategorized")
            ),
            "current_amount": current_amount,
            "previous_amount": previous_amount,
            "difference": absolute_difference,
            "percent_change": percent_change.quantize(Decimal("1"))
        })

    if changes:
        changes.sort(
            key=lambda item: (
                -item["difference"],
                item["category"].casefold()
            )
        )
        insights.append(changes[0])

    return {
        "items": insights,
        "expense_total": current_expenses,
        "expense_mix": expense_mix,
        "comparison_start": comparison_start,
        "comparison_end": comparison_end
    }

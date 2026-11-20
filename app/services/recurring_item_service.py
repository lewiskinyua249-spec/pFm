import calendar
from datetime import date, timedelta

from app import db
from app.models import RecurringItem, Transaction
from app.services.transaction_service import (
    validate_amount,
    validate_category,
    validate_description,
    validate_transaction_date,
    validate_transaction_type
)


FREQUENCIES = {"weekly", "monthly"}


def validate_recurring_name(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Recurring item name is required.")
    if len(name) > 100:
        raise ValueError("Name cannot exceed 100 characters.")
    return name


def validate_frequency(frequency):
    frequency = str(frequency or "").strip().lower()
    if frequency not in FREQUENCIES:
        raise ValueError("Choose a weekly or monthly schedule.")
    return frequency


def _validate_recurring_fields(
    user_id,
    name,
    amount,
    item_type,
    frequency,
    next_due_date,
    category_id
):
    name = validate_recurring_name(name)
    amount = validate_amount(amount)
    item_type = validate_transaction_type(item_type)
    frequency = validate_frequency(frequency)
    if next_due_date in (None, ""):
        raise ValueError("Choose the next due date.")
    next_due_date = validate_transaction_date(next_due_date)
    category_id = validate_category(user_id, category_id, item_type)
    return name, amount, item_type, frequency, next_due_date, category_id


def create_recurring_item(
    user_id,
    name,
    amount,
    item_type,
    frequency,
    next_due_date,
    category_id=None
):
    fields = _validate_recurring_fields(
        user_id,
        name,
        amount,
        item_type,
        frequency,
        next_due_date,
        category_id
    )
    name, amount, item_type, frequency, next_due_date, category_id = fields
    item = RecurringItem(
        user_id=user_id,
        name=name,
        amount=amount,
        type=item_type,
        frequency=frequency,
        next_due_date=next_due_date,
        day_of_month=(
            next_due_date.day if frequency == "monthly" else None
        ),
        category_id=category_id
    )
    try:
        db.session.add(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return item


def get_recurring_item(item_id, user_id):
    return RecurringItem.query.filter_by(
        id=item_id,
        user_id=user_id
    ).first()


def get_user_recurring_items(user_id, active_only=False):
    query = RecurringItem.query.filter_by(user_id=user_id)
    if active_only:
        query = query.filter_by(is_active=True)
    return query.order_by(
        RecurringItem.next_due_date.asc(),
        RecurringItem.id.asc()
    ).all()


def get_upcoming_recurring_items(user_id, as_of=None, days=30, limit=5):
    as_of = as_of or date.today()
    through_date = as_of + timedelta(days=days)
    return RecurringItem.query.filter(
        RecurringItem.user_id == user_id,
        RecurringItem.is_active.is_(True),
        RecurringItem.next_due_date <= through_date
    ).order_by(
        RecurringItem.next_due_date.asc(),
        RecurringItem.id.asc()
    ).limit(max(1, min(int(limit), 50))).all()


def update_recurring_item(
    item_id,
    user_id,
    name,
    amount,
    item_type,
    frequency,
    next_due_date,
    category_id=None
):
    item = get_recurring_item(item_id, user_id)
    if item is None:
        raise ValueError("Recurring item not found.")

    fields = _validate_recurring_fields(
        user_id,
        name,
        amount,
        item_type,
        frequency,
        next_due_date,
        category_id
    )
    name, amount, item_type, frequency, next_due_date, category_id = fields
    item.name = name
    item.amount = amount
    item.type = item_type
    item.frequency = frequency
    item.next_due_date = next_due_date
    item.day_of_month = (
        next_due_date.day if frequency == "monthly" else None
    )
    item.category_id = category_id
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return item


def _next_occurrence(item):
    due_date = item.next_due_date
    if item.frequency == "weekly":
        return due_date + timedelta(days=7)

    month_index = due_date.year * 12 + due_date.month
    next_year, zero_based_month = divmod(month_index, 12)
    next_month = zero_based_month + 1
    day = min(
        item.day_of_month or due_date.day,
        calendar.monthrange(next_year, next_month)[1]
    )
    return date(next_year, next_month, day)


def handle_recurring_item(item_id, user_id, action, handled_date=None):
    item = get_recurring_item(item_id, user_id)
    if item is None:
        raise ValueError("Recurring item not found.")
    if not item.is_active:
        raise ValueError("This recurring item is paused.")
    if action not in {"record", "skip"}:
        raise ValueError("Choose whether to record or skip this occurrence.")
    handled_date = validate_transaction_date(
        handled_date or date.today()
    )
    if item.next_due_date > handled_date:
        raise ValueError("This recurring item is not due yet.")

    transaction = None
    if action == "record":
        category_id = validate_category(
            user_id,
            item.category_id,
            item.type
        )
        transaction = Transaction(
            user_id=user_id,
            date=handled_date,
            type=validate_transaction_type(item.type),
            amount=validate_amount(item.amount),
            description=validate_description(item.name),
            category_id=category_id
        )
        db.session.add(transaction)

    item.next_due_date = _next_occurrence(item)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return transaction


def set_recurring_item_active(item_id, user_id, is_active):
    item = get_recurring_item(item_id, user_id)
    if item is None:
        raise ValueError("Recurring item not found.")
    item.is_active = bool(is_active)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return item


def delete_recurring_item(item_id, user_id):
    item = get_recurring_item(item_id, user_id)
    if item is None:
        raise ValueError("Recurring item not found.")
    try:
        db.session.delete(item)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True

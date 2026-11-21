
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, case

from app import db
from app.models import Transaction, Category
from app.services.category_service import validate_category_name


MAX_AMOUNT = Decimal("9999999999.99")
MAX_DESCRIPTION_LENGTH = 255
MAX_SEARCH_LENGTH = 255
MAX_PER_PAGE = 100


def validate_amount(value):

    try:
        amount = Decimal(str(value))

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Enter a valid transaction amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if amount > MAX_AMOUNT:
        raise ValueError("Amount is too large.")

    try:
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(
                "Amount cannot have more than two decimal places."
            )

    except InvalidOperation:
        raise ValueError("Enter a valid transaction amount.")

    return amount


def validate_transaction_type(transaction_type):

    transaction_type = str(transaction_type).strip().lower()

    if transaction_type not in ("income", "expense"):
        raise ValueError(
            "Transaction type must be income or expense."
        )

    return transaction_type


def validate_description(description):

    description = (description or "").strip()

    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            "Description cannot exceed 255 characters."
        )

    return description


def validate_transaction_date(transaction_date):

    if transaction_date is None or transaction_date == "":
        return date.today()

    if isinstance(transaction_date, datetime):
        return transaction_date.date()

    if isinstance(transaction_date, date):
        return transaction_date

    try:
        return date.fromisoformat(str(transaction_date))

    except (ValueError, TypeError):
        raise ValueError("Enter a valid transaction date.")


def validate_category(user_id, category_id, transaction_type):

    if category_id in (None, ""):
        return None

    try:
        category_id = int(category_id)

    except (ValueError, TypeError):
        raise ValueError("Select a valid category.")

    category = Category.query.filter_by(
        id=category_id,
        user_id=user_id,
        type=transaction_type
    ).first()

    if not category:
        raise ValueError(
            "Select a valid category belonging to your account."
        )

    return category_id


def create_transaction(
    user_id,
    amount,
    transaction_type,
    description="",
    category_id=None,
    transaction_date=None
):

    amount = validate_amount(amount)

    transaction_type = validate_transaction_type(
        transaction_type
    )

    description = validate_description(description)

    category_id = validate_category(
        user_id,
        category_id,
        transaction_type
    )

    transaction_date = validate_transaction_date(
        transaction_date
    )

    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        type=transaction_type,
        description=description,
        category_id=category_id,
        date=transaction_date
    )

    try:
        db.session.add(transaction)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return transaction


def create_transaction_with_new_category(
    user_id,
    amount,
    transaction_type,
    description,
    category_name,
    transaction_date=None
):

    amount = validate_amount(amount)
    transaction_type = validate_transaction_type(transaction_type)
    description = validate_description(description)
    transaction_date = validate_transaction_date(transaction_date)
    category_name = validate_category_name(category_name)

    category = Category.query.filter(
        Category.user_id == user_id,
        func.lower(Category.name) == category_name.lower(),
        Category.type == transaction_type
    ).first()

    if category:
        return create_transaction(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            category_id=category.id,
            transaction_date=transaction_date
        )

    category = Category(
        user_id=user_id,
        name=category_name,
        type=transaction_type
    )

    try:
        db.session.add(category)
        db.session.flush()

        return create_transaction(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            category_id=category.id,
            transaction_date=transaction_date
        )

    except Exception:
        db.session.rollback()
        raise


def get_user_transactions(
    user_id,
    limit=None,
    start_date=None,
    end_date=None
):

    query = (
        Transaction.query
        .filter_by(user_id=user_id)
    )

    if start_date is not None:
        query = query.filter(Transaction.date >= start_date)

    if end_date is not None:
        query = query.filter(Transaction.date <= end_date)

    query = query.order_by(
        Transaction.date.desc(),
        Transaction.created_at.desc(),
        Transaction.id.desc()
    )

    if limit is not None:
        limit = max(1, min(int(limit), 100))
        query = query.limit(limit)

    return query.all()


def get_transaction_by_id(transaction_id, user_id):

    return Transaction.query.filter_by(
        id=transaction_id,
        user_id=user_id
    ).first()


def update_transaction(
    transaction_id,
    user_id,
    amount,
    transaction_type,
    description="",
    category_id=None,
    transaction_date=None
):

    transaction = get_transaction_by_id(
        transaction_id,
        user_id
    )

    if not transaction:
        raise ValueError("Transaction not found.")

    amount = validate_amount(amount)

    transaction_type = validate_transaction_type(
        transaction_type
    )

    description = validate_description(description)

    category_id = validate_category(
        user_id,
        category_id,
        transaction_type
    )

    transaction_date = validate_transaction_date(
        transaction_date
    )

    transaction.amount = amount
    transaction.type = transaction_type
    transaction.description = description
    transaction.category_id = category_id
    transaction.date = transaction_date

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return transaction


def delete_transaction(transaction_id, user_id):

    transaction = get_transaction_by_id(
        transaction_id,
        user_id
    )

    if not transaction:
        raise ValueError("Transaction not found.")

    try:
        db.session.delete(transaction)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return True


def get_filtered_transactions(
    user_id,
    search=None,
    transaction_type=None,
    category_id=None,
    start_date=None,
    end_date=None,
    page=1,
    per_page=10
):

    query = Transaction.query.filter_by(
        user_id=user_id
    )

    if search:
        search = str(search).strip()

        if len(search) > MAX_SEARCH_LENGTH:
            raise ValueError("Search text is too long.")

        query = query.filter(
            Transaction.description.ilike(
                f"%{search}%"
            )
        )

    if transaction_type:
        transaction_type = validate_transaction_type(
            transaction_type
        )

        query = query.filter(
            Transaction.type == transaction_type
        )

    if category_id is not None:

        category_id = int(category_id)

        category = Category.query.filter_by(
            id=category_id,
            user_id=user_id
        ).first()

        if not category:
            raise ValueError("Invalid category filter.")

        query = query.filter(
            Transaction.category_id == category_id
        )

    if start_date is not None:
        start_date = validate_transaction_date(start_date)

        query = query.filter(
            Transaction.date >= start_date
        )

    if end_date is not None:
        end_date = validate_transaction_date(end_date)

        query = query.filter(
            Transaction.date <= end_date
        )

    if start_date and end_date and start_date > end_date:
        raise ValueError(
            "Start date cannot be after end date."
        )

    page = max(1, int(page))
    per_page = max(1, min(int(per_page), MAX_PER_PAGE))

    query = query.order_by(
        Transaction.date.desc(),
        Transaction.created_at.desc(),
        Transaction.id.desc()
    )

    return query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )


def calculate_balance(user_id, start_date=None, end_date=None):

    query = db.session.query(
        func.coalesce(
            func.sum(
                case(
                    (Transaction.type == "income", Transaction.amount),
                    else_=0
                )
            ),
            0
        ).label("income"),

        func.coalesce(
            func.sum(
                case(
                    (Transaction.type == "expense", Transaction.amount),
                    else_=0
                )
            ),
            0
        ).label("expenses")

    ).filter(Transaction.user_id == user_id)

    if start_date is not None:
        query = query.filter(Transaction.date >= start_date)

    if end_date is not None:
        query = query.filter(Transaction.date <= end_date)

    results = query.one()

    total_income = Decimal(str(results.income))
    total_expenses = Decimal(str(results.expenses))

    return {
        "income": total_income,
        "expenses": total_expenses,
        "balance": total_income - total_expenses
    }

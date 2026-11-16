
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Budget, Category, Transaction


def validate_category_name(name):

    name = (name or "").strip()

    if not name:
        raise ValueError("Category name cannot be empty.")

    if len(name) > 80:
        raise ValueError(
            "Category name cannot exceed 80 characters."
        )

    return name


def validate_category_type(category_type):

    category_type = str(category_type).strip().lower()

    if category_type not in ("income", "expense"):
        raise ValueError("Invalid category type.")

    return category_type


def create_category(user_id, name, category_type):

    name = validate_category_name(name)

    category_type = validate_category_type(
        category_type
    )

    existing_category = Category.query.filter(
        Category.user_id == user_id,
        func.lower(Category.name) == name.lower(),
        Category.type == category_type
    ).first()

    if existing_category:
        raise ValueError("This category already exists.")

    category = Category(
        user_id=user_id,
        name=name,
        type=category_type
    )

    try:
        db.session.add(category)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        raise ValueError("This category already exists.")

    except Exception:
        db.session.rollback()
        raise

    return category


def get_user_categories(user_id, category_type=None):

    query = Category.query.filter_by(
        user_id=user_id
    )

    if category_type is not None:

        category_type = validate_category_type(
            category_type
        )

        query = query.filter_by(
            type=category_type
        )

    return query.order_by(
        Category.name.asc()
    ).all()


def get_category_by_id(category_id, user_id):

    try:
        category_id = int(category_id)

    except (ValueError, TypeError):
        return None

    return Category.query.filter_by(
        id=category_id,
        user_id=user_id
    ).first()


def update_category(category_id, user_id, name, category_type):

    category = get_category_by_id(category_id, user_id)

    if not category:
        raise ValueError("Category not found.")

    name = validate_category_name(name)
    category_type = validate_category_type(category_type)

    existing_category = Category.query.filter(
        Category.user_id == user_id,
        func.lower(Category.name) == name.lower(),
        Category.type == category_type,
        Category.id != category.id
    ).first()

    if existing_category:
        raise ValueError("This category already exists.")

    if category_type != category.type:
        is_referenced = (
            Transaction.query.filter_by(category_id=category.id).first()
            or Budget.query.filter_by(category_id=category.id).first()
        )
        if is_referenced:
            raise ValueError(
                "A category used by transactions or budgets cannot change type."
            )

    category.name = name
    category.type = category_type

    try:
        db.session.commit()

    except IntegrityError:
        db.session.rollback()
        raise ValueError("This category already exists.")

    except Exception:
        db.session.rollback()
        raise

    return category


def delete_category(category_id, user_id):

    category = get_category_by_id(category_id, user_id)

    if not category:
        raise ValueError("Category not found.")

    is_referenced = (
        Transaction.query.filter_by(category_id=category.id).first()
        or Budget.query.filter_by(category_id=category.id).first()
    )
    if is_referenced:
        raise ValueError(
            "This category is used by a transaction or budget. "
            "Remove those references before deleting it."
        )

    try:
        db.session.delete(category)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return True

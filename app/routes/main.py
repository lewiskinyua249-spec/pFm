
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import io
import json

from datetime import date, datetime

from flask import send_file

from flask import (
    Blueprint,
    current_app,
    render_template,
    redirect,
    url_for,
    flash,
    request
)

from app.services.export_service import (
    generate_transactions_csv,
    generate_personal_backup
)

from flask_login import login_required, current_user

from app.services.transaction_service import (
    create_transaction,
    create_transaction_with_new_category,
    get_user_transactions,
    calculate_balance,
    get_filtered_transactions,
    get_transaction_by_id,
    update_transaction,
    delete_transaction
)
from app.services.transaction_import_service import (
    MAX_IMPORT_BYTES,
    delete_staged_transaction_import,
    get_staged_transaction_import,
    import_staged_transactions,
    preview_transaction_csv,
    stage_transaction_import
)
from app.services.recurring_item_service import (
    create_recurring_item,
    delete_recurring_item,
    get_recurring_item,
    get_upcoming_recurring_items,
    get_user_recurring_items,
    handle_recurring_item,
    set_recurring_item_active,
    update_recurring_item
)

from app.services.category_service import (
    create_category,
    get_user_categories,
    get_category_by_id,
    update_category,
    delete_category
)

from app.services.budget_service import (
    create_budget,
    get_user_budgets,
    calculate_budget_spending,
    calculate_budget_pacing,
    get_budget_by_id,
    update_budget,
    delete_budget
)

from app.services.savings_goal_service import (
    create_savings_goal,
    get_user_savings_goals,
    update_savings_progress,
    delete_savings_goal

)
from app.services.report_service import (
    get_financial_report
)
from app.services.spending_insight_service import (
    get_spending_insights
)
from app.services.exchange_rate_service import SUPPORTED_CURRENCIES

main = Blueprint("main", __name__)


@main.route("/")
@login_required
def dashboard():

    today = date.today()
    default_start = today - timedelta(days=today.weekday())
    start_date_value = request.args.get(
        "start_date",
        default_start.isoformat()
    )
    end_date_value = request.args.get(
        "end_date",
        today.isoformat()
    )

    try:
        start_date = date.fromisoformat(start_date_value)
        end_date = date.fromisoformat(end_date_value)

        if start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

        if end_date > today:
            raise ValueError("End date cannot be in the future.")

    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("main.dashboard"))

    summary = calculate_balance(
        current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    spending_insights = get_spending_insights(
        current_user.id,
        start_date,
        end_date
    )

    transactions = get_user_transactions(
        current_user.id,
        limit=10,
        start_date=start_date,
        end_date=end_date
    )

    current_budgets = get_user_budgets(
        current_user.id,
        month=today.month,
        year=today.year
    )
    budget_pacing = [
        {
            "budget": budget,
            "pacing": calculate_budget_pacing(budget, as_of=today)
        }
        for budget in current_budgets
    ]
    upcoming_items = get_upcoming_recurring_items(
        current_user.id,
        as_of=today,
        days=30,
        limit=5
    )

    return render_template(
        "dashboard.html",
        user=current_user,
        summary=summary,
        spending_insights=spending_insights,
        transactions=transactions,
        budget_pacing=budget_pacing,
        upcoming_items=upcoming_items,
        today=today,
        is_weekly_check_in=(
            start_date == default_start and end_date == today
        ),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat()
    )


@main.route("/recurring", methods=["GET", "POST"])
@login_required
def recurring_items():
    today = date.today()
    form_data = {
        "name": request.form.get("name", "").strip(),
        "amount": request.form.get("amount", "").strip(),
        "type": request.form.get("type", "expense").strip(),
        "frequency": request.form.get("frequency", "monthly").strip(),
        "next_due_date": request.form.get(
            "next_due_date",
            today.isoformat() if request.method == "GET" else ""
        ).strip(),
        "category_id": request.form.get("category_id", "").strip()
    }

    if request.method == "POST":
        try:
            create_recurring_item(
                user_id=current_user.id,
                name=form_data["name"],
                amount=form_data["amount"],
                item_type=form_data["type"],
                frequency=form_data["frequency"],
                next_due_date=form_data["next_due_date"],
                category_id=form_data["category_id"] or None
            )
            flash("Recurring reminder created.", "success")
            return redirect(url_for("main.recurring_items"))
        except ValueError as error:
            flash(str(error), "error")
        except Exception:
            current_app.logger.exception(
                "Could not create recurring item for user %s",
                current_user.id
            )
            flash("The recurring reminder could not be saved.", "error")

    return render_template(
        "recurring_items.html",
        items=get_user_recurring_items(current_user.id),
        categories=get_user_categories(current_user.id),
        form_data=form_data,
        editing_item=None,
        today=today
    )


@main.route("/recurring/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_recurring_item(item_id):
    item = get_recurring_item(item_id, current_user.id)
    if item is None:
        flash("Recurring reminder not found.", "error")
        return redirect(url_for("main.recurring_items"))

    form_data = {
        "name": request.form.get("name", item.name).strip(),
        "amount": request.form.get("amount", str(item.amount)).strip(),
        "type": request.form.get("type", item.type).strip(),
        "frequency": request.form.get(
            "frequency",
            item.frequency
        ).strip(),
        "next_due_date": request.form.get(
            "next_due_date",
            item.next_due_date.isoformat()
        ).strip(),
        "category_id": request.form.get(
            "category_id",
            str(item.category_id or "")
        ).strip()
    }
    if request.method == "POST":
        try:
            update_recurring_item(
                item_id=item.id,
                user_id=current_user.id,
                name=form_data["name"],
                amount=form_data["amount"],
                item_type=form_data["type"],
                frequency=form_data["frequency"],
                next_due_date=form_data["next_due_date"],
                category_id=form_data["category_id"] or None
            )
            flash("Recurring reminder updated.", "success")
            return redirect(url_for("main.recurring_items"))
        except ValueError as error:
            flash(str(error), "error")
        except Exception:
            current_app.logger.exception(
                "Could not update recurring item %s for user %s",
                item.id,
                current_user.id
            )
            flash("The recurring reminder could not be updated.", "error")

    return render_template(
        "recurring_items.html",
        items=get_user_recurring_items(current_user.id),
        categories=get_user_categories(current_user.id),
        form_data=form_data,
        editing_item=item,
        today=date.today()
    )


@main.route("/recurring/<int:item_id>/handle", methods=["POST"])
@login_required
def handle_recurring_item_route(item_id):
    action = request.form.get("action", "")
    try:
        transaction = handle_recurring_item(
            item_id=item_id,
            user_id=current_user.id,
            action=action,
            handled_date=date.today()
        )
        if transaction is not None:
            flash(
                "Transaction recorded and the next reminder scheduled.",
                "success"
            )
        else:
            flash("Occurrence skipped and the next reminder scheduled.", "success")
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        current_app.logger.exception(
            "Could not handle recurring item %s for user %s",
            item_id,
            current_user.id
        )
        flash("The recurring reminder could not be updated.", "error")
    if request.form.get("return_to") == "dashboard":
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.recurring_items"))


@main.route("/recurring/<int:item_id>/status", methods=["POST"])
@login_required
def set_recurring_item_status(item_id):
    action = request.form.get("action", "")
    if action not in {"pause", "resume"}:
        flash("Invalid recurring reminder action.", "error")
        return redirect(url_for("main.recurring_items"))
    try:
        set_recurring_item_active(
            item_id,
            current_user.id,
            is_active=(action == "resume")
        )
        flash(
            "Recurring reminder " + ("resumed." if action == "resume" else "paused."),
            "success"
        )
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        current_app.logger.exception(
            "Could not change status for recurring item %s and user %s",
            item_id,
            current_user.id
        )
        flash("The recurring reminder status could not be changed.", "error")
    return redirect(url_for("main.recurring_items"))


@main.route("/recurring/<int:item_id>/delete", methods=["POST"])
@login_required
def remove_recurring_item(item_id):
    try:
        delete_recurring_item(item_id, current_user.id)
        flash("Recurring reminder deleted.", "success")
    except ValueError as error:
        flash(str(error), "error")
    except Exception:
        current_app.logger.exception(
            "Could not delete recurring item %s for user %s",
            item_id,
            current_user.id
        )
        flash("The recurring reminder could not be deleted.", "error")
    return redirect(url_for("main.recurring_items"))


@main.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():

    categories = get_user_categories(current_user.id)

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        transaction_type = request.form.get("type", "").strip()
        description = request.form.get("description", "").strip()
        currency = request.form.get("currency", "KES").strip().upper()
        transaction_date = request.form.get("date", "").strip()
        category_id = request.form.get("category_id", "").strip()
        new_category_name = request.form.get(
            "new_category_name",
            ""
        ).strip()

        if not amount or not transaction_type:
            flash("Amount and transaction type are required.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories,
                currencies=SUPPORTED_CURRENCIES
            )

        try:
            amount = Decimal(amount)

            if not amount.is_finite() or amount <= 0:
                raise ValueError()

        except (InvalidOperation, ValueError):
            flash("Enter a valid positive amount.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories,
                currencies=SUPPORTED_CURRENCIES
            )

        if transaction_type not in ["income", "expense"]:
            flash("Invalid transaction type.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories,
                currencies=SUPPORTED_CURRENCIES
            )

        create_new_category = category_id == "new"

        if category_id and not create_new_category:
            try:
                category_id = int(category_id)
            except ValueError:
                flash("Invalid category selected.", "error")

                return render_template(
                    "add_transaction.html",
                    categories=categories,
                    currencies=SUPPORTED_CURRENCIES
                )
        elif not create_new_category:
            category_id = None

        if category_id is not None and not create_new_category:
            from app.models import Category

            category = Category.query.filter_by(
                id=category_id,
                user_id=current_user.id,
                type=transaction_type
            ).first()

            if not category:
                flash("Invalid category selected.", "error")

                return render_template(
                    "add_transaction.html",
                    categories=categories,
                    currencies=SUPPORTED_CURRENCIES
                )

        try:
            if create_new_category:
                create_transaction_with_new_category(
                    user_id=current_user.id,
                    amount=amount,
                    transaction_type=transaction_type,
                    description=description,
                    category_name=new_category_name,
                    transaction_date=transaction_date,
                    currency=currency
                )
            else:
                create_transaction(
                    user_id=current_user.id,
                    amount=amount,
                    transaction_type=transaction_type,
                    description=description,
                    category_id=category_id,
                    transaction_date=transaction_date,
                    currency=currency
                )

            flash("Transaction added successfully.", "success")

            return redirect(url_for("main.dashboard"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            current_app.logger.exception(
                "Failed to add transaction for user %s",
                current_user.id
            )
            flash("An unexpected error occurred.", "error")

    return render_template(
        "add_transaction.html",
        categories=categories,
        currencies=SUPPORTED_CURRENCIES
    )


@main.route("/transactions/import", methods=["GET", "POST"])
@login_required
def import_transactions():
    if request.method == "GET":
        return render_template(
            "import_transactions.html",
            preview=None,
            preview_token=None
        )

    action = request.form.get("action", "")
    token = request.form.get("preview_token", "")

    if action == "cancel":
        if get_staged_transaction_import(current_user.id, token):
            delete_staged_transaction_import(token)
        flash("Transaction import cancelled.", "success")
        return redirect(url_for("main.transactions"))

    if action == "confirm":
        preview = get_staged_transaction_import(current_user.id, token)
        if preview is None:
            flash("That import preview expired. Please upload the CSV again.", "error")
            return redirect(url_for("main.import_transactions"))

        try:
            imported_count, duplicate_count = import_staged_transactions(
                current_user.id,
                preview["rows"]
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("main.import_transactions"))
        except Exception:
            current_app.logger.exception(
                "Transaction CSV import failed for user %s",
                current_user.id
            )
            flash("The transactions could not be imported. No rows were saved.", "error")
            return redirect(url_for("main.import_transactions"))

        delete_staged_transaction_import(token)
        flash(
            f"Imported {imported_count} transaction(s); skipped "
            f"{duplicate_count} duplicate(s).",
            "success"
        )
        return redirect(url_for("main.transactions"))

    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a CSV file to upload.", "error")
        return redirect(url_for("main.import_transactions"))
    if not uploaded_file.filename.lower().endswith(".csv"):
        flash("Choose a file with the .csv extension.", "error")
        return redirect(url_for("main.import_transactions"))

    content = uploaded_file.stream.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        flash("CSV file must be 2 MB or smaller.", "error")
        return redirect(url_for("main.import_transactions"))

    try:
        preview = preview_transaction_csv(current_user.id, content)
        preview["filename"] = uploaded_file.filename[:255]
        preview_token = stage_transaction_import(
            current_user.id,
            preview
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("main.import_transactions"))
    except Exception:
        current_app.logger.exception(
            "Transaction CSV preview failed for user %s",
            current_user.id
        )
        flash("The CSV could not be prepared for import.", "error")
        return redirect(url_for("main.import_transactions"))

    return render_template(
        "import_transactions.html",
        preview=preview,
        preview_token=preview_token
    )


@main.route("/categories", methods=["GET", "POST"])
@login_required
def categories():

    form_data = {
        "name": request.form.get("name", "").strip(),
        "type": request.form.get("type", "").strip()
    }

    if request.method == "POST":
        try:
            create_category(
                user_id=current_user.id,
                name=form_data["name"],
                category_type=form_data["type"]
            )

            flash("Category created successfully.", "success")

            return redirect(url_for("main.categories"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    categories_list = get_user_categories(current_user.id)

    income_categories = [
        category for category in categories_list
        if category.type == "income"
    ]

    expense_categories = [
        category for category in categories_list
        if category.type == "expense"
    ]

    return render_template(
        "categories.html",
        income_categories=income_categories,
        expense_categories=expense_categories,
        form_data=form_data
    )


@main.route(
    "/categories/<int:category_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_category(category_id):

    category = get_category_by_id(category_id, current_user.id)

    if not category:
        flash("Category not found.", "error")
        return redirect(url_for("main.categories"))

    form_data = {
        "name": request.form.get("name", category.name).strip(),
        "type": request.form.get("type", category.type).strip()
    }

    if request.method == "POST":
        try:
            update_category(
                category_id=category.id,
                user_id=current_user.id,
                name=form_data["name"],
                category_type=form_data["type"]
            )
            flash("Category updated successfully.", "success")
            return redirect(url_for("main.categories"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    return render_template(
        "edit_category.html",
        category=category,
        form_data=form_data
    )


@main.route(
    "/categories/<int:category_id>/delete",
    methods=["POST"]
)
@login_required
def remove_category(category_id):

    try:
        delete_category(category_id, current_user.id)
        flash("Category deleted successfully.", "success")

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        flash("An unexpected error occurred.", "error")

    return redirect(url_for("main.categories"))


@main.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():

    today = date.today()
    form_data = {
        "amount": request.form.get("amount", "").strip(),
        "month": request.form.get("month", str(today.month)).strip(),
        "year": request.form.get("year", str(today.year)).strip(),
        "category_id": request.form.get("category_id", "").strip()
    }

    if request.method == "POST":
        try:
            create_budget(
                user_id=current_user.id,
                amount=form_data["amount"],
                month=form_data["month"],
                year=form_data["year"],
                category_id=form_data["category_id"]
            )

            flash("Budget created successfully.", "success")

            return redirect(url_for("main.budgets"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    budget_records = get_user_budgets(current_user.id)

    budget_data = []

    for budget in budget_records:

        spending = calculate_budget_spending(budget)

        budget_data.append({
            "budget": budget,
            "spending": spending
        })

    expense_categories = [
        category for category in get_user_categories(current_user.id)
        if category.type == "expense"
    ]

    return render_template(
        "budgets.html",
        budget_data=budget_data,
        categories=expense_categories,
        current_month=today.month,
        current_year=today.year,
        form_data=form_data
    )


@main.route(
    "/budgets/<int:budget_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_budget(budget_id):

    budget = get_budget_by_id(budget_id, current_user.id)

    if not budget:
        flash("Budget not found.", "error")
        return redirect(url_for("main.budgets"))

    form_data = {
        "amount": request.form.get("amount", str(budget.amount)).strip(),
        "month": request.form.get("month", str(budget.month)).strip(),
        "year": request.form.get("year", str(budget.year)).strip(),
        "category_id": request.form.get(
            "category_id",
            str(budget.category_id or "")
        ).strip()
    }

    if request.method == "POST":
        try:
            update_budget(
                budget_id=budget.id,
                user_id=current_user.id,
                amount=form_data["amount"],
                month=form_data["month"],
                year=form_data["year"],
                category_id=form_data["category_id"]
            )
            flash("Budget updated successfully.", "success")
            return redirect(url_for("main.budgets"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    expense_categories = [
        category for category in get_user_categories(current_user.id)
        if category.type == "expense"
    ]

    return render_template(
        "edit_budget.html",
        budget=budget,
        categories=expense_categories,
        current_month=date.today().month,
        current_year=date.today().year,
        form_data=form_data
    )


@main.route(
    "/budgets/<int:budget_id>/delete",
    methods=["POST"]
)
@login_required
def remove_budget(budget_id):

    try:
        delete_budget(budget_id, current_user.id)
        flash("Budget deleted successfully.", "success")

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        flash("An unexpected error occurred.", "error")

    return redirect(url_for("main.budgets"))


@main.route("/savings-goals", methods=["GET", "POST"])
@login_required
def savings_goals():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        target_amount = request.form.get(
            "target_amount", ""
        ).strip()
        deadline = request.form.get("deadline", "").strip()

        try:
            create_savings_goal(
                user_id=current_user.id,
                name=name,
                target_amount=target_amount,
                deadline=deadline or None
            )

            flash("Savings goal created successfully.", "success")

            return redirect(url_for("main.savings_goals"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    goals = get_user_savings_goals(current_user.id)

    return render_template(
        "savings_goals.html",
        goals=goals,
        today=date.today()
    )


@main.route(
    "/savings-goals/<int:goal_id>/add",
    methods=["POST"]
)
@login_required
def add_savings_progress(goal_id):

    amount = request.form.get("amount", "").strip()

    try:
        update_savings_progress(
            goal_id=goal_id,
            user_id=current_user.id,
            amount=amount
        )

        flash("Savings progress updated successfully.", "success")

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        flash("An unexpected error occurred.", "error")

    return redirect(url_for("main.savings_goals"))


@main.route(
    "/savings-goals/<int:goal_id>/delete",
    methods=["POST"]
)
@login_required
def remove_savings_goal(goal_id):

    try:
        delete_savings_goal(
            goal_id=goal_id,
            user_id=current_user.id
        )

        flash("Savings goal deleted successfully.", "success")

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        flash("An unexpected error occurred.", "error")

    return redirect(url_for("main.savings_goals"))


@main.route("/transactions")
@login_required
def transactions():

    search = request.args.get("q", "").strip()
    transaction_type = request.args.get("type", "").strip()
    category_id = request.args.get("category_id", "").strip()
    start_date_value = request.args.get("start_date", "").strip()
    end_date_value = request.args.get("end_date", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        if category_id:
            category_id = int(category_id)
        else:
            category_id = None

        if category_id is not None:
            from app.models import Category

            category = Category.query.filter_by(
                id=category_id,
                user_id=current_user.id
            ).first()

            if not category:
                raise ValueError("Invalid category filter.")

        start_date = (
            date.fromisoformat(start_date_value)
            if start_date_value else None
        )

        end_date = (
            date.fromisoformat(end_date_value)
            if end_date_value else None
        )

        if start_date and end_date and start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

    except (ValueError, TypeError):
        flash("Please check your transaction filters.", "error")
        return redirect(url_for("main.transactions"))

    pagination = get_filtered_transactions(
        user_id=current_user.id,
        search=search,
        transaction_type=transaction_type,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=10
    )

    categories_list = get_user_categories(current_user.id)

    return render_template(
        "transactions.html",
        pagination=pagination,
        categories=categories_list,
        filters={
            "q": search,
            "type": transaction_type,
            "category_id": category_id,
            "start_date": start_date_value,
            "end_date": end_date_value
        }
    )


@main.route(
    "/transactions/<int:transaction_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_transaction(transaction_id):

    transaction = get_transaction_by_id(
        transaction_id,
        current_user.id
    )

    if not transaction:
        flash("Transaction not found.", "error")
        return redirect(url_for("main.transactions"))

    categories = get_user_categories(current_user.id)

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        transaction_type = request.form.get("type", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id", "").strip()
        transaction_date = request.form.get("date", "").strip()
        currency = request.form.get("currency", "KES").strip().upper()

        try:
            update_transaction(
                transaction_id=transaction_id,
                user_id=current_user.id,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                category_id=category_id or None,
                transaction_date=transaction_date,
                currency=currency
            )

            flash("Transaction updated successfully.", "success")
            return redirect(url_for("main.transactions"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    return render_template(
        "edit_transaction.html",
        transaction=transaction,
        categories=categories,
        currencies=SUPPORTED_CURRENCIES
    )


@main.route(
    "/transactions/<int:transaction_id>/delete",
    methods=["POST"]
)
@login_required
def remove_transaction(transaction_id):

    try:
        delete_transaction(
            transaction_id=transaction_id,
            user_id=current_user.id
        )

        flash("Transaction deleted successfully.", "success")

    except ValueError as error:
        flash(str(error), "error")

    except Exception:
        flash("An unexpected error occurred.", "error")

    return redirect(url_for("main.transactions"))


@main.route("/reports")
@login_required
def reports():

    today = date.today()

    default_start = today.replace(day=1)

    start_date_value = request.args.get(
        "start_date",
        default_start.isoformat()
    )

    end_date_value = request.args.get(
        "end_date",
        today.isoformat()
    )

    try:

        start_date = date.fromisoformat(start_date_value)
        end_date = date.fromisoformat(end_date_value)

        if start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

        if end_date > today:
            raise ValueError("End date cannot be in the future.")

    except ValueError as error:

        flash(str(error), "error")

        return redirect(url_for("main.reports"))

    report = get_financial_report(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )

    return render_template(
        "reports.html",
        report=report,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat()
    )

@main.route("/export/transactions")
@login_required
def export_transactions():

    start_date_text = request.args.get("start_date", "").strip()
    end_date_text = request.args.get("end_date", "").strip()

    try:
        start_date = (
            date.fromisoformat(start_date_text)
            if start_date_text
            else None
        )

        end_date = (
            date.fromisoformat(end_date_text)
            if end_date_text
            else None
        )

    except ValueError:
        flash("Please provide valid export dates.", "error")
        return redirect(url_for("main.reports"))

    if start_date and end_date and start_date > end_date:
        flash("The start date cannot be after the end date.", "error")
        return redirect(url_for("main.reports"))

    csv_data = generate_transactions_csv(
        current_user.id,
        start_date,
        end_date
    )

    file_data = io.BytesIO(
        ("\ufeff" + csv_data).encode("utf-8")
    )

    filename = (
        f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    return send_file(
        file_data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )


@main.route("/export/backup")
@login_required
def download_personal_backup():

    backup_data = generate_personal_backup(
        current_user.id
    )

    file_data = io.BytesIO(
        json.dumps(
            backup_data,
            indent=4,
            ensure_ascii=False
        ).encode("utf-8")
    )

    filename = (
        f"finance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    return send_file(
        file_data,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename
    )
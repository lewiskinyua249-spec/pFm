
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import json

from datetime import date, datetime

from flask import send_file

from flask import (
    Blueprint,
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
    get_user_transactions,
    calculate_balance,
    get_filtered_transactions,
    get_transaction_by_id,
    update_transaction,
    delete_transaction
)

from app.services.category_service import (
    create_category,
    get_user_categories
)

from app.services.budget_service import (
    create_budget,
    get_user_budgets,
    calculate_budget_spending
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

main = Blueprint("main", __name__)


@main.route("/")
@login_required
def dashboard():

    summary = calculate_balance(current_user.id)

    transactions = get_user_transactions(
        current_user.id,
        limit=10
    )

    return render_template(
        "dashboard.html",
        user=current_user,
        summary=summary,
        transactions=transactions
    )


@main.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():

    categories = get_user_categories(current_user.id)

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        transaction_type = request.form.get("type", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id", "").strip()

        if not amount or not transaction_type:
            flash("Amount and transaction type are required.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories
            )

        try:
            amount = Decimal(amount)

            if not amount.is_finite() or amount <= 0:
                raise ValueError()

        except (InvalidOperation, ValueError):
            flash("Enter a valid positive amount.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories
            )

        if transaction_type not in ["income", "expense"]:
            flash("Invalid transaction type.", "error")

            return render_template(
                "add_transaction.html",
                categories=categories
            )

        if category_id:
            try:
                category_id = int(category_id)
            except ValueError:
                flash("Invalid category selected.", "error")

                return render_template(
                    "add_transaction.html",
                    categories=categories
                )
        else:
            category_id = None

        if category_id is not None:
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
                    categories=categories
                )

        try:
            create_transaction(
                user_id=current_user.id,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                category_id=category_id
            )

            flash("Transaction added successfully.", "success")

            return redirect(url_for("main.dashboard"))

        except ValueError as error:
            flash(str(error), "error")

        except Exception:
            flash("An unexpected error occurred.", "error")

    return render_template(
        "add_transaction.html",
        categories=categories
    )


@main.route("/categories", methods=["GET", "POST"])
@login_required
def categories():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category_type = request.form.get("type", "").strip()

        try:
            create_category(
                user_id=current_user.id,
                name=name,
                category_type=category_type
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
        expense_categories=expense_categories
    )


@main.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():

    today = date.today()

    if request.method == "POST":

        amount = request.form.get("amount", "").strip()
        month = request.form.get("month", "").strip()
        year = request.form.get("year", "").strip()
        category_id = request.form.get("category_id", "").strip()

        if category_id:
            try:
                category_id = int(category_id)
            except ValueError:
                flash("Invalid category selected.", "error")
                return redirect(url_for("main.budgets"))
        else:
            category_id = None

        try:
            create_budget(
                user_id=current_user.id,
                amount=amount,
                month=month,
                year=year,
                category_id=category_id
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
        current_year=today.year
    )


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

        try:
            update_transaction(
                transaction_id=transaction_id,
                user_id=current_user.id,
                amount=amount,
                transaction_type=transaction_type,
                description=description,
                category_id=category_id or None,
                transaction_date=transaction_date
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
        categories=categories
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
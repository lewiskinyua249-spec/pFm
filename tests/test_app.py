
import csv
import io
import json
import re
import calendar
from decimal import Decimal

import pytest

from app import create_app, db
from app.models import User, SavingsGoal, Transaction, RecurringItem
from app.services import (
    exchange_rate_service,
    transaction_import_service,
    transaction_service
)

from app.services.transaction_service import (
    create_transaction,
    get_user_transactions,
    get_transaction_by_id,
    calculate_balance
)
from app.services.spending_insight_service import get_spending_insights
from app.services.transaction_import_service import (
    get_staged_transaction_import,
    import_staged_transactions,
    preview_transaction_csv,
    stage_transaction_import
)
from app.services.recurring_item_service import (
    create_recurring_item,
    delete_recurring_item,
    get_recurring_item,
    get_user_recurring_items,
    get_upcoming_recurring_items,
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
    get_savings_goal_by_id,
    update_savings_progress,
    delete_savings_goal
)

from datetime import date, timedelta

from app.services.report_service import get_financial_report

from app.services.export_service import (
    generate_transactions_csv,
    generate_personal_backup
)

@pytest.fixture
def app():
    """Create a separate application for testing."""

    test_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key"
    })

    with test_app.app_context():
        db.create_all()

        yield test_app

        db.session.remove()
        db.drop_all()


def test_app_fixture_uses_in_memory_database(app):
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"

    with app.app_context():
        assert db.engine.url.database is None


@pytest.fixture
def client(app):
    """Provide a test client."""

    return app.test_client()


@pytest.fixture
def registered_user(app):
    """Create a test user."""

    with app.app_context():

        user = User(
            username="testuser",
            email="test@example.com"
        )

        user.set_password("TestPassword123")

        db.session.add(user)
        db.session.commit()

        return {
            "id": user.id,
            "email": user.email,
            "password": "TestPassword123"
        }

@pytest.fixture
def another_user(app):
    with app.app_context():
        user = User(
            username="anotheruser",
            email="another@example.com"
        )
        user.set_password("AnotherPassword123")

        db.session.add(user)
        db.session.commit()

        return {
            "id": user.id,
            "email": user.email,
            "password": "AnotherPassword123"
        }

def test_home_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.location


def test_auth_pages_include_theme_toggle(client):
    for path in ("/login", "/register"):
        response = client.get(path)

        assert response.status_code == 200
        assert b'data-theme-toggle' in response.data
        assert b'js/theme.js' in response.data


def test_settings_page_requires_login(client):
    response = client.get("/settings")

    assert response.status_code == 302
    assert "/login" in response.location


def test_settings_page_shows_existing_account_and_preferences(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/settings")

    assert response.status_code == 200
    assert b"Settings" in response.data
    assert registered_user["email"].encode() in response.data
    assert b"Profile editing is not currently available" in response.data
    assert b"KES" in response.data
    assert b"data-theme-toggle" in response.data
    assert b"/export/transactions" in response.data
    assert b"/export/backup" in response.data
    assert b"Password changes and session management are not currently supported" in response.data
    assert b"Scheduled Transactions" in response.data
    assert b"Reports &amp; Insights" in response.data
    assert b'data-mobile-nav-toggle' in response.data
    assert b'aria-controls="primary-nav"' in response.data
    assert b'href="/transactions"' in response.data
    assert b'href="/recurring"' in response.data
    assert b'href="/categories"' in response.data
    assert b'href="/budgets"' in response.data
    assert b'href="/savings-goals"' in response.data
    assert b'href="/reports"' in response.data
    assert b'href="/settings"' in response.data
    assert b'js/mobile-nav.js' in response.data


def test_user_can_register(client):
    response = client.post(
        "/register",
        data={
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPassword123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Registration successful" in response.data


def test_registration_rejects_duplicate_email(
    client,
    registered_user
):
    response = client.post(
        "/register",
        data={
            "username": "anotheruser",
            "email": registered_user["email"],
            "password": "StrongPassword123"
        },
        follow_redirects=True
    )

    assert b"already registered" in response.data


def test_user_can_login(client, registered_user):
    response = client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Dashboard" in response.data
    assert b'data-theme-toggle' in response.data


def test_dashboard_filters_summary_by_requested_dates(
    app,
    client,
    registered_user
):

    with app.app_context():
        today = date.today()
        yesterday = today - timedelta(days=1)
        create_transaction(
            user_id=registered_user["id"],
            amount="250.00",
            transaction_type="income",
            transaction_date=today
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="40.00",
            transaction_type="expense",
            transaction_date=yesterday
        )

    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    response = client.get(
        f"/?start_date={today.isoformat()}&end_date={today.isoformat()}"
    )

    assert response.status_code == 200
    assert b"KES 250.00" in response.data
    assert b"KES 0.00" in response.data
    assert today.isoformat().encode() in response.data


def test_dashboard_defaults_to_month_to_date_and_shows_current_budget(
    app,
    client,
    registered_user
):
    with app.app_context():
        today = date.today()
        month_start = today.replace(day=1)
        category = create_category(
            user_id=registered_user["id"],
            name="Groceries",
            category_type="expense"
        )
        budget = create_budget(
            user_id=registered_user["id"],
            amount="1000.00",
            month=today.month,
            year=today.year,
            category_id=category.id
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="100.00",
            transaction_type="expense",
            description="Weekly groceries",
            category_id=category.id,
            transaction_date=today
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="900.00",
            transaction_type="expense",
            description="Previous month expense",
            category_id=category.id,
            transaction_date=month_start - timedelta(days=1)
        )
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )
    response = client.get("/")

    assert response.status_code == 200
    assert f'value="{month_start.isoformat()}"'.encode() in response.data
    assert b"Monthly check-in" in response.data
    assert b"Weekly check-in" not in response.data
    assert b"Budget pace" in response.data
    assert b'dashboard-activity-list' in response.data
    assert b"Weekly groceries" in response.data
    assert b"Previous month expense" not in response.data
    assert b"KES 100.00" in response.data
    assert b"Groceries" in response.data
    assert b"Month-end estimate" in response.data


def test_dashboard_compares_spending_by_category_with_previous_period(
    app,
    client,
    registered_user
):
    with app.app_context():
        today = date.today()
        start_date = today - timedelta(days=5)
        comparison_end = start_date - timedelta(days=1)
        comparison_start = comparison_end - timedelta(days=5)
        groceries = create_category(
            user_id=registered_user["id"],
            name="Groceries",
            category_type="expense"
        )
        dining = create_category(
            user_id=registered_user["id"],
            name="Dining",
            category_type="expense"
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="100.00",
            transaction_type="expense",
            category_id=groceries.id,
            transaction_date=comparison_start
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="200.00",
            transaction_type="expense",
            category_id=groceries.id,
            transaction_date=today
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="50.00",
            transaction_type="expense",
            category_id=dining.id,
            transaction_date=today
        )

    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )
    response = client.get(
        f"/?start_date={start_date.isoformat()}&end_date={today.isoformat()}"
    )

    assert response.status_code == 200
    assert b"Smart spending insights" in response.data
    assert comparison_start.isoformat().encode() in response.data
    assert comparison_end.isoformat().encode() in response.data
    assert b"Largest expense category" in response.data
    assert b"Expense mix" in response.data
    assert b"KES 250.00" in response.data
    assert b"expense-donut" in response.data
    assert b"Groceries" in response.data
    assert b"Dining" in response.data
    assert b"80%" in response.data
    assert b"20%" in response.data
    assert b"100%" in response.data
    assert b"KES 200.00" in response.data


def test_spending_insights_group_smaller_categories_as_other(
    app,
    registered_user
):
    with app.app_context():
        today = date.today()
        amounts = ("600.00", "500.00", "400.00", "300.00", "200.00", "100.00")
        for index, amount in enumerate(amounts):
            category = create_category(
                user_id=registered_user["id"],
                name=f"Category {index + 1}",
                category_type="expense"
            )
            create_transaction(
                user_id=registered_user["id"],
                amount=amount,
                transaction_type="expense",
                category_id=category.id,
                transaction_date=today
            )

        insights = get_spending_insights(
            registered_user["id"],
            today,
            today
        )

    expense_mix = insights["expense_mix"]
    assert [category["name"] for category in expense_mix] == [
        "Category 1",
        "Category 2",
        "Category 3",
        "Category 4",
        "Other"
    ]
    assert expense_mix[-1]["amount"] == Decimal("300.00")
    assert sum(
        (Decimal(category["dasharray"].split()[0]) for category in expense_mix),
        Decimal("0.00")
    ) == Decimal("100.00")


def test_dashboard_does_not_create_spending_insights_from_income_only(
    app,
    client,
    registered_user
):
    with app.app_context():
        create_transaction(
            user_id=registered_user["id"],
            amount="500.00",
            transaction_type="income",
            transaction_date=date.today()
        )

    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )
    response = client.get("/")

    assert response.status_code == 200
    assert b"No spending insights yet" in response.data


def test_budget_pacing_uses_month_to_date_spending_only(
    app,
    registered_user
):
    with app.app_context():
        today = date.today()
        budget = create_budget(
            user_id=registered_user["id"],
            amount="1000.00",
            month=today.month,
            year=today.year
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="100.00",
            transaction_type="expense",
            transaction_date=today
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="900.00",
            transaction_type="expense",
            transaction_date=today + timedelta(days=1)
        )

        result = calculate_budget_pacing(budget, as_of=today)

        assert result["spent"] == Decimal("100.00")
        assert result["projected_spending"] == (
            Decimal("100.00") * result["days_in_month"] / today.day
        ).quantize(Decimal("0.01"))
        assert result["projected_over_budget"] is (
            result["projected_spending"] > budget.amount
        )


def test_monthly_recurring_item_keeps_its_anchor_day_when_skipped(
    app,
    registered_user
):
    with app.app_context():
        item = create_recurring_item(
            user_id=registered_user["id"],
            name="Rent",
            amount="25000.00",
            item_type="expense",
            frequency="monthly",
            next_due_date=date(2025, 1, 31)
        )

        handle_recurring_item(item.id, registered_user["id"], "skip")
        assert get_recurring_item(
            item.id,
            registered_user["id"]
        ).next_due_date == date(2025, 2, 28)

        handle_recurring_item(item.id, registered_user["id"], "skip")
        assert get_recurring_item(
            item.id,
            registered_user["id"]
        ).next_due_date == date(2025, 3, 31)


def test_recording_recurring_item_creates_transaction_and_advances_schedule(
    app,
    registered_user
):
    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Utilities",
            category_type="expense"
        )
        item = create_recurring_item(
            user_id=registered_user["id"],
            name="Electricity",
            amount="1800.00",
            item_type="expense",
            frequency="weekly",
            next_due_date=date.today(),
            category_id=category.id
        )

        transaction = handle_recurring_item(
            item.id,
            registered_user["id"],
            "record",
            handled_date=date.today()
        )

        assert transaction is not None
        assert transaction.description == "Electricity"
        assert transaction.amount == Decimal("1800.00")
        assert transaction.category_id == category.id
        assert transaction.date == date.today()
        assert get_recurring_item(
            item.id,
            registered_user["id"]
        ).next_due_date == date.today() + timedelta(days=7)


def test_recurring_item_can_be_updated_and_deleted_by_owner(
    app,
    registered_user,
    another_user
):
    with app.app_context():
        item = create_recurring_item(
            registered_user["id"],
            "Old bill",
            "100",
            "expense",
            "weekly",
            date.today()
        )

        with pytest.raises(ValueError, match="not found"):
            update_recurring_item(
                item.id,
                another_user["id"],
                "Changed",
                "200",
                "expense",
                "weekly",
                date.today()
            )
        with pytest.raises(ValueError, match="not found"):
            delete_recurring_item(item.id, another_user["id"])

        updated = update_recurring_item(
            item.id,
            registered_user["id"],
            "Updated bill",
            "200.00",
            "income",
            "monthly",
            date(2026, 1, 31)
        )
        assert updated.name == "Updated bill"
        assert updated.amount == Decimal("200.00")
        assert updated.type == "income"
        assert updated.frequency == "monthly"
        assert updated.day_of_month == 31

        assert delete_recurring_item(item.id, registered_user["id"])
        assert get_user_recurring_items(registered_user["id"]) == []


def test_upcoming_recurring_items_are_user_scoped_and_exclude_paused_items(
    app,
    registered_user,
    another_user
):
    with app.app_context():
        due_soon = create_recurring_item(
            registered_user["id"],
            "Internet",
            "2500",
            "expense",
            "monthly",
            date.today() + timedelta(days=3)
        )
        create_recurring_item(
            another_user["id"],
            "Other user's rent",
            "10000",
            "expense",
            "monthly",
            date.today() + timedelta(days=2)
        )
        paused = create_recurring_item(
            registered_user["id"],
            "Paused subscription",
            "500",
            "expense",
            "weekly",
            date.today() + timedelta(days=1)
        )
        set_recurring_item_active(
            paused.id,
            registered_user["id"],
            False
        )

        upcoming = get_upcoming_recurring_items(
            registered_user["id"],
            as_of=date.today()
        )

        assert [item.id for item in upcoming] == [due_soon.id]
        with pytest.raises(ValueError, match="not due yet"):
            handle_recurring_item(
                due_soon.id,
                registered_user["id"],
                "record",
                handled_date=date.today()
            )


def test_category_used_by_recurring_item_cannot_be_deleted_or_retyped(
    app,
    registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "Rent",
            "expense"
        )
        create_recurring_item(
            registered_user["id"],
            "Monthly rent",
            "25000",
            "expense",
            "monthly",
            date.today(),
            category_id=category.id
        )

        with pytest.raises(ValueError, match="recurring items"):
            update_category(
                category.id,
                registered_user["id"],
                "Rent",
                "income"
            )
        with pytest.raises(ValueError, match="recurring item"):
            delete_category(category.id, registered_user["id"])


def test_recurring_reminder_routes_create_record_and_skip(
    app,
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)
    today = date.today()
    response = client.post(
        "/recurring",
        data={
            "name": "Payday",
            "amount": "45000.00",
            "type": "income",
            "frequency": "monthly",
            "next_due_date": today.isoformat(),
            "category_id": ""
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Payday" in response.data
    with app.app_context():
        item = RecurringItem.query.filter_by(
            user_id=registered_user["id"],
            name="Payday"
        ).one()
        item_id = item.id
        assert Transaction.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 0

    response = client.post(
        f"/recurring/{item_id}/handle",
        data={"action": "record"},
        follow_redirects=True
    )
    assert b"Transaction recorded" in response.data
    with app.app_context():
        transaction = Transaction.query.filter_by(
            user_id=registered_user["id"],
            description="Payday"
        ).one()
        item = db.session.get(RecurringItem, item_id)
        next_month_index = today.year * 12 + today.month
        next_year, zero_based_month = divmod(next_month_index, 12)
        next_month = zero_based_month + 1
        expected_day = min(
            today.day,
            calendar.monthrange(next_year, next_month)[1]
        )
        assert transaction.type == "income"
        assert transaction.amount == Decimal("45000.00")
        assert item.next_due_date == date(
            next_year,
            next_month,
            expected_day
        )

    with app.app_context():
        skip_item = create_recurring_item(
            registered_user["id"],
            "Weekly subscription",
            "500.00",
            "expense",
            "weekly",
            today
        )
        skip_item_id = skip_item.id

    response = client.post(
        f"/recurring/{skip_item_id}/handle",
        data={"action": "skip"},
        follow_redirects=True
    )
    assert b"Occurrence skipped" in response.data
    with app.app_context():
        assert Transaction.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 1


def test_dashboard_displays_upcoming_recurring_reminder(
    app,
    client,
    registered_user
):
    with app.app_context():
        create_recurring_item(
            registered_user["id"],
            "Water bill",
            "1200.00",
            "expense",
            "monthly",
            date.today() + timedelta(days=4)
        )
    _login_route_test_user(client, registered_user)

    response = client.get("/")

    assert response.status_code == 200
    assert b"Upcoming bills and income" in response.data
    assert b"Water bill" in response.data
    assert b'value="record">Record</button>' not in response.data


def test_budget_and_category_management_routes(
    app,
    client,
    registered_user
):

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Dining",
            category_type="expense"
        )
        budget = create_budget(
            user_id=registered_user["id"],
            amount="500.00",
            month=11,
            year=2026
        )
        category_id = category.id
        budget_id = budget.id

    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    categories_response = client.get("/categories")
    budgets_response = client.get("/budgets")

    assert categories_response.status_code == 200
    assert b"Edit" in categories_response.data
    assert budgets_response.status_code == 200
    assert b"Edit Budget" in budgets_response.data

    category_response = client.post(
        f"/categories/{category_id}/edit",
        data={"name": "Restaurants", "type": "expense"},
        follow_redirects=True
    )
    budget_response = client.post(
        f"/budgets/{budget_id}/edit",
        data={
            "amount": "750.00",
            "month": "11",
            "year": "2026",
            "category_id": ""
        },
        follow_redirects=True
    )

    assert category_response.status_code == 200
    assert b"Restaurants" in category_response.data
    assert budget_response.status_code == 200
    assert b"KES 750.00" in budget_response.data

    category_delete_response = client.post(
        f"/categories/{category_id}/delete",
        follow_redirects=True
    )
    budget_delete_response = client.post(
        f"/budgets/{budget_id}/delete",
        follow_redirects=True
    )

    assert category_delete_response.status_code == 200
    assert b"Restaurants" not in category_delete_response.data
    assert budget_delete_response.status_code == 200
    assert b"You haven't created any budgets yet." in budget_delete_response.data


def test_login_rejects_wrong_password(
    client,
    registered_user
):
    response = client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": "WrongPassword123"
        },
        follow_redirects=True
    )

    assert b"Invalid email or password" in response.data


def test_user_can_create_transaction(app, registered_user):

    with app.app_context():

        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="1000.00",
            transaction_type="income",
            description="Test salary"
        )

        assert transaction.id is not None
        assert transaction.amount == Decimal("1000.00")
        assert transaction.type == "income"


def test_transaction_appears_in_user_history(
    app,
    registered_user
):

    with app.app_context():

        create_transaction(
            user_id=registered_user["id"],
            amount="1000.00",
            transaction_type="income",
            description="Test salary"
        )

        transactions = get_user_transactions(
            registered_user["id"]
        )

        assert len(transactions) == 1
        assert transactions[0].description == "Test salary"


def test_user_cannot_access_another_users_transaction(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="500.00",
            transaction_type="expense",
            description="Private transaction"
        )

        result = get_transaction_by_id(
            transaction.id,
            another_user["id"]
        )

        assert result is None


def test_balance_is_calculated_correctly(
    app,
    registered_user
):

    with app.app_context():

        create_transaction(
            user_id=registered_user["id"],
            amount="10000.00",
            transaction_type="income"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="2500.00",
            transaction_type="expense"
        )

        balance = calculate_balance(
            registered_user["id"]
        )

        assert balance["income"] == Decimal("10000.00")
        assert balance["expenses"] == Decimal("2500.00")
        assert balance["balance"] == Decimal("7500.00")


def test_balance_can_be_calculated_for_a_date_range(
    app,
    registered_user
):

    with app.app_context():
        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        create_transaction(
            user_id=registered_user["id"],
            amount="1000.00",
            transaction_type="income",
            transaction_date=two_days_ago
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="200.00",
            transaction_type="expense",
            transaction_date=yesterday
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="50.00",
            transaction_type="expense",
            transaction_date=today
        )

        balance = calculate_balance(
            registered_user["id"],
            start_date=yesterday,
            end_date=today
        )

        assert balance == {
            "income": Decimal("0.00"),
            "expenses": Decimal("250.00"),
            "balance": Decimal("-250.00")
        }


def test_user_can_create_category(app, registered_user):

    with app.app_context():

        category = create_category(
            user_id=registered_user["id"],
            name="Food",
            category_type="expense"
        )

        assert category.id is not None
        assert category.name == "Food"
        assert category.type == "expense"


def test_duplicate_category_is_rejected(app, registered_user):

    with app.app_context():

        create_category(
            user_id=registered_user["id"],
            name="Food",
            category_type="expense"
        )

        with pytest.raises(ValueError):
            create_category(
                user_id=registered_user["id"],
                name="Food",
                category_type="expense"
            )


def test_user_cannot_access_another_users_category(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        category = create_category(
            user_id=registered_user["id"],
            name="Food",
            category_type="expense"
        )

        result = get_category_by_id(
            category.id,
            another_user["id"]
        )

        assert result is None


def test_user_categories_are_isolated(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        create_category(
            user_id=registered_user["id"],
            name="Food",
            category_type="expense"
        )

        categories = get_user_categories(
            another_user["id"]
        )

        assert len(categories) == 0


def test_user_can_update_category(app, registered_user):

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Old Name",
            category_type="expense"
        )

        updated = update_category(
            category.id,
            registered_user["id"],
            "New Name",
            "expense"
        )

        assert updated.name == "New Name"
        assert updated.type == "expense"


def test_category_type_cannot_change_when_referenced(
    app,
    registered_user
):

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Salary",
            category_type="income"
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="1000.00",
            transaction_type="income",
            category_id=category.id
        )

        with pytest.raises(ValueError, match="cannot change type"):
            update_category(
                category.id,
                registered_user["id"],
                "Salary",
                "expense"
            )

        assert category.type == "income"


def test_category_in_use_cannot_be_deleted(app, registered_user):

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Food",
            category_type="expense"
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="100.00",
            transaction_type="expense",
            category_id=category.id
        )

        with pytest.raises(ValueError, match="used by a transaction"):
            delete_category(category.id, registered_user["id"])

        assert get_category_by_id(
            category.id,
            registered_user["id"]
        ) is not None


def test_user_can_delete_unused_category(app, registered_user):

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Unused",
            category_type="expense"
        )

        assert delete_category(category.id, registered_user["id"]) is True
        assert get_category_by_id(
            category.id,
            registered_user["id"]
        ) is None


def test_user_can_create_budget(app, registered_user):

    with app.app_context():

        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        assert budget.id is not None
        assert budget.amount == Decimal("5000.00")
        assert budget.month == 11
        assert budget.year == 2026


def test_duplicate_budget_is_rejected(app, registered_user):

    with app.app_context():

        create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        with pytest.raises(ValueError):
            create_budget(
                user_id=registered_user["id"],
                amount="6000.00",
                month=11,
                year=2026
            )


def test_user_can_update_budget(app, registered_user):

    with app.app_context():
        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        updated = update_budget(
            budget.id,
            registered_user["id"],
            amount="6500.00",
            month=12,
            year=2026
        )

        assert updated.amount == Decimal("6500.00")
        assert updated.month == 12
        assert updated.year == 2026


def test_budget_update_rejects_duplicate_period(
    app,
    registered_user
):

    with app.app_context():
        first = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )
        second = create_budget(
            user_id=registered_user["id"],
            amount="4000.00",
            month=12,
            year=2026
        )

        with pytest.raises(ValueError, match="already exists"):
            update_budget(
                second.id,
                registered_user["id"],
                amount="4000.00",
                month=11,
                year=2026
            )

        assert get_budget_by_id(
            second.id,
            registered_user["id"]
        ).month == 12
        assert get_budget_by_id(
            first.id,
            registered_user["id"]
        ) is not None


def test_user_can_delete_budget(app, registered_user):

    with app.app_context():
        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        assert delete_budget(budget.id, registered_user["id"]) is True
        assert get_budget_by_id(
            budget.id,
            registered_user["id"]
        ) is None


def test_user_cannot_update_another_users_budget(
    app,
    registered_user,
    another_user
):

    with app.app_context():
        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        with pytest.raises(ValueError, match="not found"):
            update_budget(
                budget.id,
                another_user["id"],
                amount="6500.00",
                month=12,
                year=2026
            )


def test_budget_spending_is_calculated_correctly(
    app,
    registered_user
):

    with app.app_context():

        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="1500.00",
            transaction_type="expense"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="500.00",
            transaction_type="income"
        )

        result = calculate_budget_spending(budget)

        assert result["budget"] == Decimal("5000.00")
        assert result["spent"] == Decimal("1500.00")
        assert result["remaining"] == Decimal("3500.00")
        assert result["percentage"] == 30.0
        assert result["exceeded"] is False


def test_budget_spending_does_not_include_another_users_expenses(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        budget = create_budget(
            user_id=registered_user["id"],
            amount="5000.00",
            month=11,
            year=2026
        )

        create_transaction(
            user_id=another_user["id"],
            amount="3000.00",
            transaction_type="expense"
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("0")
        assert result["remaining"] == Decimal("5000.00")


def test_user_can_create_savings_goal(app, registered_user):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="New Laptop",
            target_amount="50000.00"
        )

        assert goal.id is not None
        assert goal.name == "New Laptop"
        assert goal.target_amount == Decimal("50000.00")
        assert goal.current_amount == Decimal("0.00")


def test_user_can_add_savings_progress(app, registered_user):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="Emergency Fund",
            target_amount="20000.00"
        )

        updated_goal = update_savings_progress(
            goal.id,
            registered_user["id"],
            "5000.00"
        )

        assert updated_goal.current_amount == Decimal("5000.00")


def test_savings_cannot_exceed_target(app, registered_user):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="Holiday Fund",
            target_amount="10000.00"
        )

        with pytest.raises(ValueError):
            update_savings_progress(
                goal.id,
                registered_user["id"],
                "12000.00"
            )

        assert goal.current_amount == Decimal("0.00")


def test_invalid_savings_amount_is_rejected(app, registered_user):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="New Phone",
            target_amount="30000.00"
        )

        with pytest.raises(ValueError):
            update_savings_progress(
                goal.id,
                registered_user["id"],
                "0"
            )

        assert goal.current_amount == Decimal("0.00")


def test_user_cannot_access_another_users_savings_goal(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="Private Goal",
            target_amount="15000.00"
        )

        result = get_savings_goal_by_id(
            goal.id,
            another_user["id"]
        )

        assert result is None


def test_savings_goals_are_isolated(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        create_savings_goal(
            user_id=registered_user["id"],
            name="Private Goal",
            target_amount="15000.00"
        )

        goals = get_user_savings_goals(
            another_user["id"]
        )

        assert len(goals) == 0


def test_user_can_delete_savings_goal(app, registered_user):

    with app.app_context():

        goal = create_savings_goal(
            user_id=registered_user["id"],
            name="Old Goal",
            target_amount="10000.00"
        )

        result = delete_savings_goal(
            goal.id,
            registered_user["id"]
        )

        assert result is True

        deleted_goal = get_savings_goal_by_id(
            goal.id,
            registered_user["id"]
        )

        assert deleted_goal is None


def test_financial_report_calculates_totals(
    app,
    registered_user
):

    with app.app_context():

        today = date.today()

        create_transaction(
            user_id=registered_user["id"],
            amount="10000.00",
            transaction_type="income",
            description="Salary"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="2500.00",
            transaction_type="expense",
            description="Shopping"
        )

        report = get_financial_report(
            registered_user["id"],
            today,
            today
        )

        assert report["total_income"] == Decimal("10000.00")
        assert report["total_expenses"] == Decimal("2500.00")
        assert report["net_balance"] == Decimal("7500.00")
        assert report["transaction_count"] == 2


def test_financial_report_excludes_other_users(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        today = date.today()

        create_transaction(
            user_id=another_user["id"],
            amount="9000.00",
            transaction_type="income"
        )

        report = get_financial_report(
            registered_user["id"],
            today,
            today
        )

        assert report["total_income"] == Decimal("0")
        assert report["total_expenses"] == Decimal("0")
        assert report["transaction_count"] == 0


def test_csv_export_contains_user_transactions(
    app,
    registered_user
):

    with app.app_context():

        create_transaction(
            user_id=registered_user["id"],
            amount="1500.00",
            transaction_type="expense",
            description="Groceries"
        )

        csv_data = generate_transactions_csv(
            registered_user["id"]
        )

        assert "Date" in csv_data
        assert "Type" in csv_data
        assert "Category" in csv_data
        assert "Groceries" in csv_data
        assert "1500.00" in csv_data


def test_json_backup_contains_only_users_records(
    app,
    registered_user,
    another_user
):

    with app.app_context():

        create_transaction(
            user_id=registered_user["id"],
            amount="1000.00",
            transaction_type="income",
            description="My income"
        )

        create_transaction(
            user_id=another_user["id"],
            amount="9000.00",
            transaction_type="income",
            description="Other user's income"
        )

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert backup["application"] == "Personal Finance Manager"
        assert backup["backup_version"] == 3

        assert len(backup["transactions"]) == 1

        assert (
            backup["transactions"][0]["description"]
            == "My income"
        )

        assert (
            backup["transactions"][0]["amount"]
            == "1000.00"
        )

        assert all(
            item["description"] != "Other user's income"
            for item in backup["transactions"]
        )

def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_dashboard_requires_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_logged_in_user_can_open_dashboard(client, registered_user):
    login_response = client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        },
        follow_redirects=True
    )

    assert login_response.status_code == 200

    response = client.get("/")

    assert response.status_code == 200


@pytest.mark.parametrize("page", [
    "/categories",
    "/budgets",
    "/savings-goals",
    "/transactions",
    "/reports"
])
def test_feature_pages_require_authenticated_access(
    client, registered_user, page
):
    # Log in first.
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        },
        follow_redirects=True
    )

    # Request the feature page.
    response = client.get(page)

    assert response.status_code == 200


def test_auth_register_creates_user(app, client):
    response = client.post(
        "/register",
        data={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "NewPassword123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    with app.app_context():
        user = User.query.filter_by(
            email="newuser@example.com"
        ).first()

        assert user is not None
        assert user.username == "newuser"
        assert user.check_password("NewPassword123")
        assert user.password_hash != "NewPassword123"


def test_auth_register_rejects_missing_fields(client):
    response = client.post(
        "/register",
        data={
            "username": "",
            "email": "missing@example.com",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"All fields are required." in response.data


def test_auth_register_rejects_long_username(client):
    response = client.post(
        "/register",
        data={
            "username": "u" * 81,
            "email": "longuser@example.com",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Username cannot exceed 80 characters." in response.data


def test_auth_register_rejects_invalid_email(client):
    response = client.post(
        "/register",
        data={
            "username": "invalidemail",
            "email": "not-an-email",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Enter a valid email address." in response.data


def test_auth_register_rejects_long_email(client):
    response = client.post(
        "/register",
        data={
            "username": "longemail",
            "email": ("a" * 111) + "@example.com",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Enter a valid email address." in response.data


def test_auth_register_rejects_short_password(client):
    response = client.post(
        "/register",
        data={
            "username": "shortpassword",
            "email": "short@example.com",
            "password": "1234567"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Password must be at least 8 characters." in response.data


def test_auth_register_rejects_duplicate_username(
    client,
    registered_user
):
    response = client.post(
        "/register",
        data={
            "username": "testuser",
            "email": "different@example.com",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Username already exists." in response.data


def test_auth_register_rejects_duplicate_email(
    client,
    registered_user
):
    response = client.post(
        "/register",
        data={
            "username": "differentuser",
            "email": registered_user["email"],
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Email already registered." in response.data


def test_auth_register_normalizes_email(app, client):
    client.post(
        "/register",
        data={
            "username": "uppercaseemail",
            "email": "  UPPERCASE@EXAMPLE.COM  ",
            "password": "Password123"
        }
    )

    with app.app_context():
        user = User.query.filter_by(
            email="uppercase@example.com"
        ).first()

        assert user is not None


def test_auth_login_rejects_unknown_email(client):
    response = client.post(
        "/login",
        data={
            "email": "unknown@example.com",
            "password": "Password123"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data


def test_auth_login_normalizes_email(client, registered_user):
    response = client.post(
        "/login",
        data={
            "email": registered_user["email"].upper(),
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.location == "/"


def test_auth_login_rejects_external_next_url(
    client,
    registered_user
):
    response = client.post(
        "/login?next=https://example.com",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.location == "/"


def test_auth_login_allows_safe_internal_next_url(
    client,
    registered_user
):
    response = client.post(
        "/login?next=/transactions",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.location == "/transactions"


def test_auth_login_rejects_protocol_relative_next_url(
    client,
    registered_user
):
    response = client.post(
        "/login?next=//example.com",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.location == "/"


def test_auth_authenticated_user_cannot_open_register(
    client,
    registered_user
):
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    response = client.get("/register")

    assert response.status_code == 302
    assert response.location == "/"


def test_auth_authenticated_user_cannot_open_login(
    client,
    registered_user
):
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    response = client.get("/login")

    assert response.status_code == 302
    assert response.location == "/"


def test_auth_logout_requires_login(client):
    response = client.post("/logout")

    assert response.status_code == 302
    assert "/login" in response.location


def test_auth_logout_rejects_get_request(
    client,
    registered_user
):
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    response = client.get("/logout")

    assert response.status_code == 405


def test_auth_logout_ends_session(client, registered_user):
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    logout_response = client.post(
        "/logout",
        follow_redirects=True
    )

    assert logout_response.status_code == 200

    dashboard_response = client.get(
        "/",
        follow_redirects=False
    )

    assert dashboard_response.status_code == 302
    assert "/login" in dashboard_response.location

 
def _login_route_test_user(client, user):
    return client.post(
        "/login",
        data={
            "email": user["email"],
            "password": user["password"]
        }
    )


def test_add_transaction_page_requires_login(client):
    response = client.get("/transactions/add")

    assert response.status_code == 302
    assert "/login" in response.location


def test_add_transaction_page_opens_for_logged_in_user(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/transactions/add")

    assert response.status_code == 200
    assert b"Create a new category..." in response.data
    assert b'id="new_category_name"' in response.data


def test_add_transaction_page_offers_multiple_currencies(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/transactions/add")

    assert response.status_code == 200
    assert b"USD" in response.data
    assert b"US Dollar" in response.data
    assert b"historical reference rates" in response.data


def test_add_foreign_currency_transaction_shows_kes_equivalent(
    app,
    client,
    registered_user,
    monkeypatch
):
    _login_route_test_user(client, registered_user)
    observed_date = date(2026, 11, 20)
    monkeypatch.setattr(
        transaction_service,
        "get_exchange_rate",
        lambda source, target, requested_date: (
            Decimal("130.00"),
            observed_date
        )
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "12.50",
            "currency": "USD",
            "date": "2026-11-22",
            "type": "expense",
            "description": "Foreign purchase",
            "category_id": ""
        }
    )

    assert response.status_code == 302
    with app.app_context():
        transaction = get_user_transactions(registered_user["id"])[0]
        assert transaction.original_amount == Decimal("12.50")
        assert transaction.currency == "USD"
        assert transaction.amount == Decimal("1625.00")
        assert transaction.exchange_rate_date == observed_date

    list_response = client.get("/transactions")
    assert b"USD 12.50" in list_response.data
    assert b"KES 1,625.00" in list_response.data


def test_add_transaction_shows_exchange_rate_error_without_losing_form(
    app,
    client,
    registered_user,
    monkeypatch
):
    _login_route_test_user(client, registered_user)

    def unavailable_rate(*args):
        raise ValueError(
            "Exchange rates are temporarily unavailable. Please try again."
        )

    monkeypatch.setattr(
        transaction_service,
        "get_exchange_rate",
        unavailable_rate
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "12.50",
            "currency": "USD",
            "date": "2026-11-22",
            "type": "expense",
            "description": "Foreign purchase",
            "category_id": ""
        }
    )

    assert response.status_code == 200
    assert b"Exchange rates are temporarily unavailable" in response.data
    assert b'value="12.50"' in response.data
    assert b'value="2026-11-22"' in response.data
    assert b"Foreign purchase</textarea>" in response.data
    with app.app_context():
        assert get_user_transactions(registered_user["id"]) == []


def test_dashboard_displays_user_transaction(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    create_transaction(
        user_id=registered_user["id"],
        amount="2500.00",
        transaction_type="expense",
        description="Dashboard test purchase"
    )

    response = client.get("/")

    assert response.status_code == 200
    assert b"Dashboard test purchase" in response.data


@pytest.mark.parametrize(
    "transaction_type, amount, description",
    [
        ("income", "10000.00", "Route test income"),
        ("expense", "2500.00", "Route test expense")
    ]
)
def test_add_transaction_success(
    client,
    registered_user,
    transaction_type,
    amount,
    description
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": amount,
            "type": transaction_type,
            "description": description,
            "category_id": ""
        }
    )

    assert response.status_code == 302
    assert response.location == "/"

    transactions = get_user_transactions(
        registered_user["id"]
    )

    saved_transaction = next(
        (
            transaction for transaction in transactions
            if transaction.description == description
        ),
        None
    )

    assert saved_transaction is not None
    assert saved_transaction.type == transaction_type
    assert saved_transaction.amount == Decimal(amount)


def test_add_transaction_with_valid_category(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    category = create_category(
        user_id=registered_user["id"],
        name="Route Test Food",
        category_type="expense"
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1200.00",
            "type": "expense",
            "description": "Food purchase",
            "category_id": str(category.id)
        }
    )

    assert response.status_code == 302

    transactions = get_user_transactions(
        registered_user["id"]
    )

    saved_transaction = next(
        (
            transaction for transaction in transactions
            if transaction.description == "Food purchase"
        ),
        None
    )

    assert saved_transaction is not None
    assert saved_transaction.category_id == category.id


def test_add_transaction_creates_a_new_category_inline(
    app,
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "450.00",
            "type": "expense",
            "description": "Taxi fare",
            "category_id": "new",
            "new_category_name": "Transport"
        }
    )

    assert response.status_code == 302

    with app.app_context():
        category = Category.query.filter_by(
            user_id=registered_user["id"],
            name="Transport",
            type="expense"
        ).one()
        transaction = Transaction.query.filter_by(
            user_id=registered_user["id"],
            description="Taxi fare"
        ).one()

        assert transaction.category_id == category.id


def test_add_transaction_reuses_matching_inline_category(
    app,
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)
    category = create_category(
        user_id=registered_user["id"],
        name="Transport",
        category_type="expense"
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "450.00",
            "type": "expense",
            "description": "Taxi fare",
            "category_id": "new",
            "new_category_name": " transport "
        }
    )

    assert response.status_code == 302

    with app.app_context():
        assert Category.query.filter_by(
            user_id=registered_user["id"],
            type="expense"
        ).count() == 1
        transaction = Transaction.query.filter_by(
            user_id=registered_user["id"],
            description="Taxi fare"
        ).one()

        assert transaction.category_id == category.id


def test_add_transaction_requires_name_for_new_category(
    app,
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "450.00",
            "type": "expense",
            "description": "Taxi fare",
            "category_id": "new",
            "new_category_name": ""
        }
    )

    assert response.status_code == 200
    assert b"Category name cannot be empty." in response.data

    with app.app_context():
        assert not Category.query.filter_by(
            user_id=registered_user["id"],
            name="Transport"
        ).first()
        assert not Transaction.query.filter_by(
            user_id=registered_user["id"],
            description="Taxi fare"
        ).first()


def test_add_transaction_rejects_missing_fields(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "",
            "type": "expense"
        }
    )

    assert response.status_code == 200
    assert b"Amount and transaction type are required." in response.data


@pytest.mark.parametrize(
    "amount",
    [
        "not-a-number",
        "0",
        "-25"
    ]
)
def test_add_transaction_rejects_invalid_amount(
    client,
    registered_user,
    amount
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": amount,
            "type": "expense",
            "description": "Invalid amount test"
        }
    )

    assert response.status_code == 200
    assert b"Enter a valid positive amount." in response.data

    transactions = get_user_transactions(
        registered_user["id"]
    )

    assert not any(
        transaction.description == "Invalid amount test"
        for transaction in transactions
    )


def test_add_transaction_rejects_invalid_type(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1000",
            "type": "transfer",
            "description": "Invalid type test"
        }
    )

    assert response.status_code == 200
    assert b"Invalid transaction type." in response.data


def test_add_transaction_rejects_non_numeric_category_id(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1000",
            "type": "expense",
            "description": "Invalid category test",
            "category_id": "abc"
        }
    )

    assert response.status_code == 200
    assert b"Invalid category selected." in response.data


def test_add_transaction_rejects_another_users_category(
    client,
    registered_user,
    another_user
):
    _login_route_test_user(client, registered_user)

    category = create_category(
        user_id=another_user["id"],
        name="Other User Category",
        category_type="expense"
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1000",
            "type": "expense",
            "description": "Foreign category test",
            "category_id": str(category.id)
        }
    )

    assert response.status_code == 200
    assert b"Invalid category selected." in response.data


def test_add_transaction_rejects_wrong_category_type(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    category = create_category(
        user_id=registered_user["id"],
        name="Income Only Category",
        category_type="income"
    )

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1000",
            "type": "expense",
            "description": "Wrong category type test",
            "category_id": str(category.id)
        }
    )

    assert response.status_code == 200
    assert b"Invalid category selected." in response.data


def test_categories_page_requires_login(client):
    response = client.get("/categories")

    assert response.status_code == 302
    assert "/login" in response.location


def test_categories_page_opens_for_logged_in_user(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/categories")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "category_type, category_name",
    [
        ("income", "Salary Route Test"),
        ("expense", "Food Route Test")
    ]
)
def test_create_category_success(
    client,
    registered_user,
    category_type,
    category_name
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/categories",
        data={
            "name": category_name,
            "type": category_type
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Category created successfully." in response.data

    categories = get_user_categories(
        registered_user["id"]
    )

    saved_category = next(
        (
            category for category in categories
            if category.name == category_name
        ),
        None
    )

    assert saved_category is not None
    assert saved_category.type == category_type


def test_create_category_rejects_empty_name(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/categories",
        data={
            "name": "   ",
            "type": "expense"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Category name cannot be empty." in response.data


def test_create_category_rejects_invalid_type(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/categories",
        data={
            "name": "Invalid Category",
            "type": "transfer"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Invalid category type." in response.data


def test_create_category_rejects_duplicate(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    create_category(
        user_id=registered_user["id"],
        name="Existing Category",
        category_type="expense"
    )

    response = client.post(
        "/categories",
        data={
            "name": "Existing Category",
            "type": "expense"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"This category already exists." in response.data


def test_categories_page_loads_with_existing_categories(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    create_category(
        user_id=registered_user["id"],
        name="Monthly Salary",
        category_type="income"
    )

    create_category(
        user_id=registered_user["id"],
        name="Transport",
        category_type="expense"
    )

    response = client.get("/categories")

    assert response.status_code == 200

    categories = get_user_categories(
        registered_user["id"]
    )

    assert any(
        category.name == "Monthly Salary"
        and category.type == "income"
        for category in categories
    )

    assert any(
        category.name == "Transport"
        and category.type == "expense"
        for category in categories
    )


def test_categories_page_does_not_show_other_users_categories(
    client,
    registered_user,
    another_user
):
    _login_route_test_user(client, registered_user)

    create_category(
        user_id=another_user["id"],
        name="Private Other Category",
        category_type="expense"
    )

    response = client.get("/categories")

    assert response.status_code == 200
    assert b"Private Other Category" not in response.data


def test_category_creation_isolated_between_users(
    client,
    registered_user,
    another_user
):
    _login_route_test_user(client, registered_user)

    client.post(
        "/categories",
        data={
            "name": "My Private Category",
            "type": "expense"
        }
    )

    other_users_categories = get_user_categories(
        another_user["id"]
    )

    assert not any(
        category.name == "My Private Category"
        for category in other_users_categories
    )


def test_category_name_cannot_exceed_80_characters(
    client,
    registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/categories",
        data={
            "name": "C" * 81,
            "type": "expense"
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Category name cannot exceed 80 characters." in response.data


def test_categories_page_displays_income_and_expense_categories(
    app, client, registered_user
):
    from app.services.category_service import create_category

    with app.app_context():
        create_category(
            registered_user["id"],
            "Monthly Salary",
            "income"
        )

        create_category(
            registered_user["id"],
            "Food Shopping",
            "expense"
        )

    _login_route_test_user(client, registered_user)

    response = client.get("/categories")

    assert response.status_code == 200
    assert b"Monthly Salary" in response.data
    assert b"Food Shopping" in response.data
    assert b"Income Categories" in response.data
    assert b"Expense Categories" in response.data


# ==========================================
# BUDGET ROUTE TESTS
# ==========================================

def test_budgets_page_requires_login(client):
    response = client.get("/budgets")

    assert response.status_code == 302
    assert "/login" in response.location


def test_budgets_page_opens_for_logged_in_user(client, registered_user):
    _login_route_test_user(client, registered_user)

    response = client.get("/budgets")

    assert response.status_code == 200
    assert b"Monthly Budgets" in response.data
    assert b"Create a Budget" in response.data


def test_budgets_page_displays_empty_message(client, registered_user):
    _login_route_test_user(client, registered_user)

    response = client.get("/budgets")

    assert response.status_code == 200
    assert b"You haven't created any budgets yet." in response.data


def test_create_overall_budget_success(app, client, registered_user):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "10000",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    assert response.status_code == 302

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        budgets = get_user_budgets(registered_user["id"])

        assert len(budgets) == 1
        assert float(budgets[0].amount) == 10000.00
        assert budgets[0].category_id is None


def test_create_category_specific_budget_success(
    app, client, registered_user
):
    from app.services.category_service import create_category

    with app.app_context():
        category = create_category(
            registered_user["id"], "Food", "expense"
        )
        category_id = category.id

    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": "11",
        "year": "2026",
        "category_id": str(category_id)
    })

    assert response.status_code == 302

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        budgets = get_user_budgets(registered_user["id"])

        assert len(budgets) == 1
        assert budgets[0].category_id == category_id


def test_budgets_page_displays_existing_budget(
    client, registered_user
):
    _login_route_test_user(client, registered_user)

    client.post("/budgets", data={
        "amount": "10000",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    response = client.get("/budgets")

    assert response.status_code == 200
    assert b"Overall Budget" in response.data
    assert b"10,000.00" in response.data
    assert b"Remaining:" in response.data


def test_budgets_page_displays_expense_categories(
    app, client, registered_user
):
    from app.services.category_service import create_category

    with app.app_context():
        create_category(
            registered_user["id"], "Transport", "expense"
        )
        create_category(
            registered_user["id"], "Salary", "income"
        )

    _login_route_test_user(client, registered_user)

    response = client.get("/budgets")

    assert response.status_code == 200
    assert b"Transport" in response.data
    assert b"Salary" not in response.data


def test_create_budget_rejects_zero_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "0",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


def test_create_budget_rejects_negative_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "-100",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


def test_create_budget_rejects_invalid_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "abc",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


@pytest.mark.parametrize("month", ["0", "13", "abc"])
def test_create_budget_rejects_invalid_month(
    app, client, registered_user, month
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": month,
        "year": "2026",
        "category_id": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


@pytest.mark.parametrize("year", ["1999", "abc"])
def test_create_budget_rejects_invalid_year(
    app, client, registered_user, year
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": "11",
        "year": year,
        "category_id": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


def test_create_budget_rejects_non_numeric_category_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": "11",
        "year": "2026",
        "category_id": "invalid"
    })

    assert response.status_code == 200
    assert b"Select a valid expense category." in response.data

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0

def test_create_budget_rejects_income_category(
    app, client, registered_user
):
    from app.services.category_service import create_category

    with app.app_context():
        category = create_category(
            registered_user["id"], "Salary", "income"
        )
        category_id = category.id

    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": "11",
        "year": "2026",
        "category_id": str(category_id)
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


def test_create_budget_rejects_another_users_category(
    app, client, registered_user, another_user
):
    from app.services.category_service import create_category

    with app.app_context():
        category = create_category(
            another_user["id"], "Private Food", "expense"
        )
        category_id = category.id

    _login_route_test_user(client, registered_user)

    response = client.post("/budgets", data={
        "amount": "5000",
        "month": "11",
        "year": "2026",
        "category_id": str(category_id)
    })

    assert response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        assert len(get_user_budgets(registered_user["id"])) == 0


def test_create_budget_rejects_duplicate_overall_budget(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    budget_data = {
        "amount": "10000",
        "month": "11",
        "year": "2026",
        "category_id": ""
    }

    first_response = client.post("/budgets", data=budget_data)
    second_response = client.post("/budgets", data=budget_data)

    assert first_response.status_code == 302
    assert second_response.status_code == 200

    with app.app_context():
        from app.services.budget_service import get_user_budgets

        budgets = get_user_budgets(registered_user["id"])

        assert len(budgets) == 1


def test_budgets_are_isolated_between_users(
    client, registered_user, another_user
):
    _login_route_test_user(client, registered_user)

    client.post("/budgets", data={
        "amount": "10000",
        "month": "11",
        "year": "2026",
        "category_id": ""
    })

    client.post("/logout", follow_redirects=True)

    _login_route_test_user(client, another_user)

    response = client.get("/budgets")

    assert response.status_code == 200
    assert b"10,000.00" not in response.data
    assert b"You haven't created any budgets yet." in response.data


# ==========================================
# SAVINGS GOALS ROUTE TESTS
# ==========================================

def _create_route_test_savings_goal(
    app, client, user, name="New Laptop", target_amount="50000"
):
    _login_route_test_user(client, user)

    response = client.post("/savings-goals", data={
        "name": name,
        "target_amount": target_amount,
        "deadline": ""
    })

    with app.app_context():
        from app.models import SavingsGoal

        goal = SavingsGoal.query.filter_by(
            user_id=user["id"],
            name=name
        ).first()

        assert goal is not None
        return goal.id


def test_savings_goals_page_requires_login(client):
    response = client.get("/savings-goals")

    assert response.status_code == 302
    assert "/login" in response.location


def test_savings_goals_page_opens_for_logged_in_user(
    client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"Savings Goals" in response.data
    assert b"Create a Savings Goal" in response.data
    assert b"Your Savings Goals" in response.data


def test_savings_goals_page_displays_empty_message(
    client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"You haven't created any savings goals yet." in response.data


def test_create_savings_goal_success(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/savings-goals", data={
        "name": "New Laptop",
        "target_amount": "50000",
        "deadline": ""
    })

    assert response.status_code == 302

    with app.app_context():
        from app.models import SavingsGoal

        goal = SavingsGoal.query.filter_by(
            user_id=registered_user["id"],
            name="New Laptop"
        ).first()

        assert goal is not None
        assert float(goal.target_amount) == 50000.00


def test_savings_goals_page_displays_existing_goal(
    client, registered_user, app
):
    _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"New Laptop" in response.data
    assert b"50,000.00" in response.data



def test_create_savings_goal_rejects_zero_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/savings-goals", data={
        "name": "Invalid Goal",
        "target_amount": "0",
        "deadline": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.models import SavingsGoal

        assert SavingsGoal.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 0


def test_create_savings_goal_rejects_negative_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/savings-goals", data={
        "name": "Invalid Goal",
        "target_amount": "-100",
        "deadline": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.models import SavingsGoal

        assert SavingsGoal.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 0


def test_create_savings_goal_rejects_invalid_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post("/savings-goals", data={
        "name": "Invalid Goal",
        "target_amount": "abc",
        "deadline": ""
    })

    assert response.status_code == 200

    with app.app_context():
        from app.models import SavingsGoal

        assert SavingsGoal.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 0


def test_add_savings_progress_success(
    app, client, registered_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.post(
        f"/savings-goals/{goal_id}/add",
        data={"amount": "5000"}
    )

    assert response.status_code == 302

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"New Laptop" in response.data
    assert b"5,000.00" in response.data


def test_add_savings_progress_rejects_zero_amount(
    app, client, registered_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.post(
        f"/savings-goals/{goal_id}/add",
        data={"amount": "0"}
    )

    assert response.status_code == 302

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"New Laptop" in response.data


def test_add_savings_progress_rejects_negative_amount(
    app, client, registered_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.post(
        f"/savings-goals/{goal_id}/add",
        data={"amount": "-500"}
    )

    assert response.status_code == 302

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"New Laptop" in response.data


def test_add_savings_progress_rejects_invalid_amount(
    app, client, registered_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.post(
        f"/savings-goals/{goal_id}/add",
        data={"amount": "abc"}
    )

    assert response.status_code == 302

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"New Laptop" in response.data


def test_delete_savings_goal_success(
    app, client, registered_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, registered_user
    )

    response = client.post(
        f"/savings-goals/{goal_id}/delete"
    )

    assert response.status_code == 302

    with app.app_context():
        from app.models import SavingsGoal

        assert db.session.get(SavingsGoal, goal_id) is None


def test_savings_goals_are_isolated_between_users(
    app, client, registered_user, another_user
):
    _create_route_test_savings_goal(
        app, client, registered_user,
        name="Private Laptop"
    )

    client.post("/logout", follow_redirects=True)

    _login_route_test_user(client, another_user)

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"Private Laptop" not in response.data
    assert b"You haven't created any savings goals yet." in response.data


def test_user_cannot_add_progress_to_another_users_goal(
    app, client, registered_user, another_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, another_user,
        name="Another User Goal"
    )

    client.post("/logout", follow_redirects=True)
    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/savings-goals/{goal_id}/add",
        data={"amount": "5000"}
    )

    assert response.status_code == 302

    client.post("/logout", follow_redirects=True)
    _login_route_test_user(client, another_user)

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"Another User Goal" in response.data
    assert b"5,000.00" not in response.data


def test_user_cannot_delete_another_users_goal(
    app, client, registered_user, another_user
):
    goal_id = _create_route_test_savings_goal(
        app, client, another_user,
        name="Protected Goal"
    )

    client.post("/logout", follow_redirects=True)
    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/savings-goals/{goal_id}/delete"
    )

    assert response.status_code == 302

    client.post("/logout", follow_redirects=True)
    _login_route_test_user(client, another_user)

    response = client.get("/savings-goals")

    assert response.status_code == 200
    assert b"Protected Goal" in response.data


# ==========================================
# REPORTS ROUTE TESTS
# ==========================================

def test_reports_page_requires_login(client):
    response = client.get("/reports")

    assert response.status_code == 302
    assert "/login" in response.location


def test_reports_page_opens_for_logged_in_user(
    client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get("/reports")

    assert response.status_code == 200


def test_reports_page_displays_default_date_range(
    client, registered_user
):
    from datetime import date

    _login_route_test_user(client, registered_user)

    today = date.today()
    default_start = today.replace(day=1)

    response = client.get("/reports")

    assert response.status_code == 200
    assert default_start.isoformat().encode() in response.data
    assert today.isoformat().encode() in response.data


def test_reports_page_accepts_valid_custom_date_range(
    client, registered_user
):
    from datetime import date

    _login_route_test_user(client, registered_user)

    today = date.today()
    start_date = today.replace(day=1)
    end_date = today

    response = client.get(
        "/reports",
        query_string={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    )

    assert response.status_code == 200
    assert start_date.isoformat().encode() in response.data
    assert end_date.isoformat().encode() in response.data


def test_reports_rejects_invalid_start_date(
    client, registered_user
):
    from datetime import date

    _login_route_test_user(client, registered_user)

    response = client.get(
        "/reports",
        query_string={
            "start_date": "invalid-date",
            "end_date": date.today().isoformat()
        }
    )

    assert response.status_code == 302
    assert "/reports" in response.location


def test_reports_rejects_invalid_end_date(
    client, registered_user
):
    from datetime import date

    _login_route_test_user(client, registered_user)

    response = client.get(
        "/reports",
        query_string={
            "start_date": date.today().isoformat(),
            "end_date": "invalid-date"
        }
    )

    assert response.status_code == 302
    assert "/reports" in response.location


def test_reports_rejects_start_date_after_end_date(
    client, registered_user
):
    from datetime import date, timedelta

    _login_route_test_user(client, registered_user)

    today = date.today()
    start_date = today
    end_date = today - timedelta(days=5)

    response = client.get(
        "/reports",
        query_string={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    )

    assert response.status_code == 302
    assert "/reports" in response.location


def test_reports_rejects_future_end_date(
    client, registered_user
):
    from datetime import date, timedelta

    _login_route_test_user(client, registered_user)

    today = date.today()
    future_date = today + timedelta(days=1)

    response = client.get(
        "/reports",
        query_string={
            "start_date": today.isoformat(),
            "end_date": future_date.isoformat()
        }
    )

    assert response.status_code == 302
    assert "/reports" in response.location


# ============================================================
# TRANSACTION HISTORY, FILTERING, EDITING AND DELETING ROUTE TESTS
# ============================================================

from datetime import date, timedelta


def _create_route_test_transaction(
    app,
    user,
    amount="1500",
    transaction_type="expense",
    description="Test transaction",
    category_id=None
):
    from app.services.transaction_service import create_transaction

    with app.app_context():
        transaction = create_transaction(
            user_id=user["id"],
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            category_id=category_id
        )
        return transaction.id


# ----------------------------
# TRANSACTION HISTORY
# ----------------------------

def test_transactions_page_requires_login(client):
    response = client.get("/transactions")

    assert response.status_code == 302
    assert "/login" in response.location


def test_transactions_page_opens(app, client, registered_user):
    _login_route_test_user(client, registered_user)

    response = client.get("/transactions")

    assert response.status_code == 200


def test_transactions_page_displays_user_transactions(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="Monthly shopping"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions")

    assert response.status_code == 200
    assert b"Monthly shopping" in response.data


def test_transactions_page_searches_by_description(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="Electricity bill"
    )

    _create_route_test_transaction(
        app,
        registered_user,
        description="Internet subscription"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions?q=Electricity")

    assert response.status_code == 200
    assert b"Electricity bill" in response.data
    assert b"Internet subscription" not in response.data


def test_transactions_page_filters_by_type(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        transaction_type="income",
        description="Salary payment"
    )

    _create_route_test_transaction(
        app,
        registered_user,
        transaction_type="expense",
        description="Food shopping"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions?type=income")

    assert response.status_code == 200
    assert b"Salary payment" in response.data
    assert b"Food shopping" not in response.data


def test_transactions_page_filters_by_date_range(
    app, client, registered_user
):
    today = date.today()

    _create_route_test_transaction(
        app,
        registered_user,
        description="Date range transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/transactions?start_date={today.isoformat()}"
        f"&end_date={today.isoformat()}"
    )

    assert response.status_code == 200


def test_transactions_page_rejects_invalid_date_filter(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get(
        "/transactions?start_date=invalid-date"
    )

    assert response.status_code == 302
    assert "/transactions" in response.location


def test_transactions_page_rejects_start_date_after_end_date(
    app, client, registered_user
):
    today = date.today()
    yesterday = today - timedelta(days=1)

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/transactions?start_date={today.isoformat()}"
        f"&end_date={yesterday.isoformat()}"
    )

    assert response.status_code == 302


def test_transactions_page_handles_invalid_page_number(
    app, client, registered_user
):
    _create_route_test_transaction(app, registered_user)

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions?page=0")

    assert response.status_code == 200



def test_transactions_page_does_not_show_another_users_transactions(
    app, client, registered_user, another_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="First user transaction"
    )

    _create_route_test_transaction(
        app,
        another_user,
        description="Second user transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions")

    assert response.status_code == 200
    assert b"First user transaction" in response.data
    assert b"Second user transaction" not in response.data


def test_transactions_page_paginates_after_ten_transactions(
    app, client, registered_user
):
    for number in range(12):
        _create_route_test_transaction(
            app,
            registered_user,
            description=f"Pagination transaction {number}"
        )

    _login_route_test_user(client, registered_user)

    response = client.get("/transactions?page=1")

    assert response.status_code == 200

    response = client.get("/transactions?page=2")

    assert response.status_code == 200


# ----------------------------
# EDIT TRANSACTIONS
# ----------------------------

def test_edit_transaction_requires_login(
    app, client, registered_user
):
    transaction_id = _create_route_test_transaction(
        app, registered_user
    )

    response = client.get(
        f"/transactions/{transaction_id}/edit"
    )

    assert response.status_code == 302
    assert "/login" in response.location


def test_edit_transaction_page_opens(
    app, client, registered_user
):
    transaction_id = _create_route_test_transaction(
        app, registered_user
    )

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/transactions/{transaction_id}/edit"
    )

    assert response.status_code == 200


def test_edit_transaction_updates_transaction(
    app, client, registered_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app,
        registered_user,
        amount="1500",
        transaction_type="expense",
        description="Old description"
    )

    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "amount": "2500",
            "type": "expense",
            "description": "Updated description",
            "category_id": "",
            "date": date.today().isoformat()
        },
        follow_redirects=True
    )

    assert response.status_code == 200

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction.amount == Decimal("2500")
        assert transaction.description == "Updated description"
        assert transaction.type == "expense"


def test_edit_transaction_rejects_zero_amount(
    app, client, registered_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app, registered_user, amount="1500"
    )

    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "amount": "0",
            "type": "expense",
            "description": "Invalid update",
            "category_id": "",
            "date": date.today().isoformat()
        }
    )

    assert response.status_code == 200

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction.amount == Decimal("1500")


def test_edit_transaction_rejects_invalid_type(
    app, client, registered_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app, registered_user
    )

    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "amount": "2000",
            "type": "invalid",
            "description": "Invalid type",
            "category_id": "",
            "date": date.today().isoformat()
        }
    )

    assert response.status_code == 200

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction.type == "expense"


def test_user_cannot_edit_another_users_transaction(
    app, client, registered_user, another_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app,
        another_user,
        amount="3000",
        description="Private transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/transactions/{transaction_id}/edit"
    )

    assert response.status_code == 302

    response = client.post(
        f"/transactions/{transaction_id}/edit",
        data={
            "amount": "9000",
            "type": "income",
            "description": "Attempted change",
            "category_id": "",
            "date": date.today().isoformat()
        }
    )

    assert response.status_code == 302

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction.amount == Decimal("3000")
        assert transaction.description == "Private transaction"


# ----------------------------
# DELETE TRANSACTIONS
# ----------------------------

def test_delete_transaction_requires_login(
    app, client, registered_user
):
    transaction_id = _create_route_test_transaction(
        app, registered_user
    )

    response = client.post(
        f"/transactions/{transaction_id}/delete"
    )

    assert response.status_code == 302
    assert "/login" in response.location


def test_delete_transaction_successfully_deletes_record(
    app, client, registered_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app,
        registered_user,
        description="Transaction to delete"
    )

    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/transactions/{transaction_id}/delete",
        follow_redirects=True
    )

    assert response.status_code == 200

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction is None


def test_user_cannot_delete_another_users_transaction(
    app, client, registered_user, another_user
):
    from app.models import Transaction

    transaction_id = _create_route_test_transaction(
        app,
        another_user,
        description="Protected transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.post(
        f"/transactions/{transaction_id}/delete"
    )

    assert response.status_code == 302

    with app.app_context():
        transaction = db.session.get(Transaction, transaction_id)

        assert transaction is not None
        assert transaction.description == "Protected transaction"


def test_delete_transaction_does_not_accept_get(
    app, client, registered_user
):
    transaction_id = _create_route_test_transaction(
        app, registered_user
    )

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/transactions/{transaction_id}/delete"
    )

    assert response.status_code == 405


# ============================================================
# DATA EXPORT AND PERSONAL BACKUP ROUTE TESTS
# ============================================================

import csv
import io
import json


# ----------------------------
# CSV TRANSACTION EXPORT
# ----------------------------

def test_csv_export_requires_login(client):
    response = client.get("/export/transactions")

    assert response.status_code == 302
    assert "/login" in response.location


def test_csv_export_downloads_file(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="CSV export test"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/transactions")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "transactions_" in response.headers["Content-Disposition"]
    assert b"CSV export test" in response.data


def test_csv_export_contains_expected_headers(
    app, client, registered_user
):
    _create_route_test_transaction(
        app, registered_user
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/transactions")

    content = response.data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))

    headers = next(reader)

    assert headers == [
        "Date",
        "Type",
        "Category",
        "Description",
        "Amount",
        "Currency",
        "Amount (KES)",
        "Exchange Rate",
        "Exchange Rate Date"
    ]


def test_csv_export_contains_only_logged_in_users_transactions(
    app, client, registered_user, another_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="My exported transaction"
    )

    _create_route_test_transaction(
        app,
        another_user,
        description="Another user's private transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/transactions")

    assert response.status_code == 200
    assert b"My exported transaction" in response.data
    assert b"Another user's private transaction" not in response.data


def test_csv_export_filters_by_date_range(
    app, client, registered_user
):
    from app.models import Transaction

    first_id = _create_route_test_transaction(
        app,
        registered_user,
        description="Inside export date range"
    )

    second_id = _create_route_test_transaction(
        app,
        registered_user,
        description="Outside export date range"
    )

    today = date.today()
    yesterday = today - timedelta(days=1)

    with app.app_context():
        first = db.session.get(Transaction, first_id)
        second = db.session.get(Transaction, second_id)

        first.date = today
        second.date = yesterday

        db.session.commit()

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/export/transactions?start_date={today.isoformat()}"
        f"&end_date={today.isoformat()}"
    )

    assert response.status_code == 200
    assert b"Inside export date range" in response.data
    assert b"Outside export date range" not in response.data


def test_csv_export_rejects_invalid_start_date(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get(
        "/export/transactions?start_date=invalid-date"
    )

    assert response.status_code == 302
    assert "/reports" in response.location


def test_csv_export_rejects_invalid_end_date(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get(
        "/export/transactions?end_date=invalid-date"
    )

    assert response.status_code == 302
    assert "/reports" in response.location


def test_csv_export_rejects_start_date_after_end_date(
    app, client, registered_user
):
    today = date.today()
    yesterday = today - timedelta(days=1)

    _login_route_test_user(client, registered_user)

    response = client.get(
        f"/export/transactions?start_date={today.isoformat()}"
        f"&end_date={yesterday.isoformat()}"
    )

    assert response.status_code == 302
    assert "/reports" in response.location


# ----------------------------
# PERSONAL JSON BACKUP
# ----------------------------

def test_personal_backup_requires_login(client):
    response = client.get("/export/backup")

    assert response.status_code == 302
    assert "/login" in response.location


def test_personal_backup_downloads_json_file(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="Backup transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/backup")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "finance_backup_" in response.headers["Content-Disposition"]


def test_personal_backup_contains_valid_json(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="Valid JSON backup transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/backup")

    assert response.status_code == 200

    backup = json.loads(response.data.decode("utf-8"))

    assert isinstance(backup, dict)


def test_personal_backup_contains_users_transactions(
    app, client, registered_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="My backup transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/backup")

    assert response.status_code == 200
    assert b"My backup transaction" in response.data


def test_personal_backup_does_not_contain_another_users_transactions(
    app, client, registered_user, another_user
):
    _create_route_test_transaction(
        app,
        registered_user,
        description="My private backup transaction"
    )

    _create_route_test_transaction(
        app,
        another_user,
        description="Another private backup transaction"
    )

    _login_route_test_user(client, registered_user)

    response = client.get("/export/backup")

    assert response.status_code == 200
    assert b"My private backup transaction" in response.data
    assert b"Another private backup transaction" not in response.data


# ============================================================
# SECURITY AND EDGE-CASE ROUTE TESTS
# ============================================================

# ----------------------------
# TRANSACTION ID VALIDATION
# ----------------------------

def test_edit_nonexistent_transaction_redirects(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get(
        "/transactions/999999/edit"
    )

    assert response.status_code == 302
    assert "/transactions" in response.location


def test_update_nonexistent_transaction_redirects(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/999999/edit",
        data={
            "amount": "2000",
            "type": "expense",
            "description": "Nonexistent transaction",
            "category_id": "",
            "date": date.today().isoformat()
        }
    )

    assert response.status_code == 302
    assert "/transactions" in response.location


def test_delete_nonexistent_transaction_redirects(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/999999/delete"
    )

    assert response.status_code == 302
    assert "/transactions" in response.location


def test_edit_transaction_rejects_malformed_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.get(
        "/transactions/invalid/edit"
    )

    assert response.status_code == 404


def test_delete_transaction_rejects_malformed_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/transactions/invalid/delete"
    )

    assert response.status_code == 404


# ----------------------------
# SAVINGS GOAL ID VALIDATION
# ----------------------------

def test_add_progress_to_nonexistent_savings_goal_redirects(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/savings-goals/999999/add",
        data={"amount": "1000"}
    )

    assert response.status_code == 302
    assert "/savings-goals" in response.location


def test_delete_nonexistent_savings_goal_redirects(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/savings-goals/999999/delete"
    )

    assert response.status_code == 302
    assert "/savings-goals" in response.location


def test_add_progress_rejects_malformed_savings_goal_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/savings-goals/invalid/add",
        data={"amount": "1000"}
    )

    assert response.status_code == 404


def test_delete_rejects_malformed_savings_goal_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    response = client.post(
        "/savings-goals/invalid/delete"
    )

    assert response.status_code == 404


# ============================================================
# TRANSACTION INPUT VALIDATION AND EDGE CASE TESTS
# ============================================================

import pytest
from app.models import Transaction


def _count_user_transactions(app, user):
    with app.app_context():
        return Transaction.query.filter_by(
            user_id=user["id"]
        ).count()


# ----------------------------
# MISSING REQUIRED FIELDS
# ----------------------------

def test_add_transaction_rejects_missing_amount(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "type": "expense",
            "description": "Missing amount",
            "category_id": ""
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


def test_add_transaction_rejects_missing_type(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1000",
            "description": "Missing type",
            "category_id": ""
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


# ----------------------------
# INVALID MONETARY VALUES
# ----------------------------

@pytest.mark.parametrize(
    "amount",
    [
        "0",
        "-1",
        "-100.50",
        "abc",
        "1.999",
        "100.123",
        "9999999999.999",
        "10000000000.00",
        "NaN",
        "Infinity",
        "-Infinity",
    ]
)
def test_add_transaction_rejects_invalid_amounts(
    app, client, registered_user, amount
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": amount,
            "type": "expense",
            "description": "Invalid amount test",
            "category_id": ""
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


def test_add_transaction_accepts_two_decimal_places(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "1250.75",
            "type": "expense",
            "description": "Valid decimal amount",
            "category_id": ""
        }
    )

    assert response.status_code == 302
    assert _count_user_transactions(app, registered_user) == before + 1


# ----------------------------
# DESCRIPTION VALIDATION
# ----------------------------

def test_add_transaction_accepts_empty_description(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "",
            "category_id": ""
        }
    )

    assert response.status_code == 302
    assert _count_user_transactions(app, registered_user) == before + 1


def test_add_transaction_rejects_description_over_255_characters(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "A" * 256,
            "category_id": ""
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


# ----------------------------
# CATEGORY VALIDATION
# ----------------------------

def test_add_transaction_rejects_non_numeric_category_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "Invalid category ID",
            "category_id": "abc"
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


def test_add_transaction_rejects_nonexistent_category_id(
    app, client, registered_user
):
    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "Nonexistent category",
            "category_id": "999999"
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


def test_add_transaction_rejects_another_users_category(
    app, client, registered_user, another_user
):
    from app.services.category_service import create_category

    with app.app_context():
        category = create_category(
            another_user["id"],
            "Private Category",
            "expense"
        )
        category_id = category.id

    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "Foreign category",
            "category_id": str(category_id)
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


def test_add_transaction_rejects_category_with_wrong_type(
    app, client, registered_user
):
    from app.services.category_service import create_category

    with app.app_context():
        category = create_category(
            registered_user["id"],
            "Salary Category",
            "income"
        )
        category_id = category.id

    _login_route_test_user(client, registered_user)

    before = _count_user_transactions(app, registered_user)

    response = client.post(
        "/transactions/add",
        data={
            "amount": "500",
            "type": "expense",
            "description": "Wrong category type",
            "category_id": str(category_id)
        }
    )

    assert response.status_code == 200
    assert _count_user_transactions(app, registered_user) == before


# ============================================================
# TRANSACTION SERVICE TESTS
# ============================================================

from decimal import Decimal

from app.services.transaction_service import (
    create_transaction,
    get_user_transactions,
    get_transaction_by_id,
    calculate_balance,
)


# ----------------------------
# CREATE TRANSACTIONS
# ----------------------------

def test_transaction_service_creates_income(app, registered_user):
    with app.app_context():
        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="5000",
            transaction_type="income",
            description="Monthly salary"
        )

        assert transaction.id is not None
        assert transaction.user_id == registered_user["id"]
        assert transaction.amount == Decimal("5000")
        assert transaction.type == "income"
        assert transaction.description == "Monthly salary"


def test_transaction_service_creates_expense(app, registered_user):
    with app.app_context():
        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="1500.50",
            transaction_type="expense",
            description="Shopping"
        )

        assert transaction.id is not None
        assert transaction.amount == Decimal("1500.50")
        assert transaction.type == "expense"


def test_transaction_service_converts_foreign_amount_to_kes(
    app,
    registered_user,
    monkeypatch
):
    observed_date = date(2026, 11, 20)
    monkeypatch.setattr(
        transaction_service,
        "get_exchange_rate",
        lambda source, target, requested_date: (
            Decimal("129.975"),
            observed_date
        )
    )

    with app.app_context():
        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="10.00",
            transaction_type="expense",
            transaction_date=date(2026, 11, 22),
            currency="USD"
        )
        totals = calculate_balance(registered_user["id"])

        assert transaction.original_amount == Decimal("10.00")
        assert transaction.currency == "USD"
        assert transaction.exchange_rate == Decimal("129.975")
        assert transaction.exchange_rate_date == observed_date
        assert transaction.amount == Decimal("1299.75")
        assert totals["expenses"] == Decimal("1299.75")


def test_transaction_service_rejects_unsupported_currency(
    app,
    registered_user,
    monkeypatch
):
    monkeypatch.setattr(
        transaction_service,
        "get_exchange_rate",
        lambda *args: pytest.fail("Rate lookup should not run")
    )

    with app.app_context(), pytest.raises(ValueError):
        create_transaction(
            user_id=registered_user["id"],
            amount="10.00",
            transaction_type="expense",
            currency="XYZ"
        )


def test_exchange_rate_uses_latest_available_rate_on_or_before_date(
    monkeypatch
):
    results = [
        {"date": "2026-11-20", "rates": {"KES": "129.97"}},
        {"date": "2026-11-23", "rates": {"KES": "130.01"}}
    ]
    monkeypatch.setattr(
        exchange_rate_service,
        "urlopen",
        lambda request_url, timeout: io.BytesIO(
            json.dumps(results).encode("utf-8")
        )
    )

    rate, rate_date = exchange_rate_service.get_exchange_rate(
        "USD",
        "KES",
        date(2026, 11, 22)
    )

    assert rate == Decimal("129.97")
    assert rate_date == date(2026, 11, 20)


def test_transaction_service_rejects_zero_amount(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_transaction(
                user_id=registered_user["id"],
                amount="0",
                transaction_type="expense",
                description="Zero amount"
            )


@pytest.mark.parametrize(
    "amount",
    [
        "-10",
        "abc",
        "NaN",
        "Infinity",
        "1.999",
        "10000000000.00"
    ]
)
def test_transaction_service_rejects_invalid_amounts(
    app, registered_user, amount
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_transaction(
                user_id=registered_user["id"],
                amount=amount,
                transaction_type="expense",
                description="Invalid amount"
            )


def test_transaction_service_rejects_invalid_type(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_transaction(
                user_id=registered_user["id"],
                amount="1000",
                transaction_type="transfer",
                description="Invalid transaction type"
            )


def test_transaction_service_rejects_description_over_255_characters(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_transaction(
                user_id=registered_user["id"],
                amount="1000",
                transaction_type="expense",
                description="A" * 256
            )


def test_transaction_service_accepts_empty_description(
    app, registered_user
):
    with app.app_context():
        transaction = create_transaction(
            user_id=registered_user["id"],
            amount="1000",
            transaction_type="expense",
            description=""
        )

        assert transaction.id is not None
        assert transaction.description == ""


# ----------------------------
# RETRIEVE USER TRANSACTIONS
# ----------------------------

def test_transaction_service_returns_user_transactions(
    app, registered_user
):
    with app.app_context():
        create_transaction(
            user_id=registered_user["id"],
            amount="1000",
            transaction_type="income",
            description="First transaction"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="500",
            transaction_type="expense",
            description="Second transaction"
        )

        transactions = get_user_transactions(
            registered_user["id"]
        )

        descriptions = [
            transaction.description
            for transaction in transactions
        ]

        assert len(transactions) == 2
        assert "First transaction" in descriptions
        assert "Second transaction" in descriptions


def test_transaction_service_returns_empty_list_for_user_without_transactions(
    app, registered_user
):
    with app.app_context():
        transactions = get_user_transactions(
            registered_user["id"]
        )

        assert transactions == []


def test_transaction_service_limits_returned_transactions(
    app, registered_user
):
    with app.app_context():
        for number in range(5):
            create_transaction(
                user_id=registered_user["id"],
                amount="100",
                transaction_type="expense",
                description=f"Limited transaction {number}"
            )

        transactions = get_user_transactions(
            registered_user["id"],
            limit=2
        )

        assert len(transactions) == 2


def test_transaction_service_does_not_mix_users(
    app, registered_user, another_user
):
    with app.app_context():
        create_transaction(
            user_id=registered_user["id"],
            amount="1000",
            transaction_type="income",
            description="First user's transaction"
        )

        create_transaction(
            user_id=another_user["id"],
            amount="2000",
            transaction_type="income",
            description="Second user's transaction"
        )

        transactions = get_user_transactions(
            registered_user["id"]
        )

        assert len(transactions) == 1
        assert transactions[0].description == "First user's transaction"


# ----------------------------
# RETRIEVE TRANSACTION BY ID
# ----------------------------

def test_transaction_service_gets_transaction_by_id(
    app, registered_user
):
    with app.app_context():
        created = create_transaction(
            user_id=registered_user["id"],
            amount="2500",
            transaction_type="expense",
            description="Find this transaction"
        )

        transaction = get_transaction_by_id(
            created.id,
            registered_user["id"]
        )

        assert transaction is not None
        assert transaction.id == created.id
        assert transaction.description == "Find this transaction"


def test_transaction_service_does_not_return_another_users_transaction(
    app, registered_user, another_user
):
    with app.app_context():
        created = create_transaction(
            user_id=another_user["id"],
            amount="3000",
            transaction_type="expense",
            description="Private transaction"
        )

        transaction = get_transaction_by_id(
            created.id,
            registered_user["id"]
        )

        assert transaction is None


def test_transaction_service_returns_none_for_nonexistent_id(
    app, registered_user
):
    with app.app_context():
        transaction = get_transaction_by_id(
            999999,
            registered_user["id"]
        )

        assert transaction is None


# ----------------------------
# CALCULATE BALANCE
# ----------------------------

def test_transaction_service_calculates_balance(
    app, registered_user
):
    with app.app_context():
        create_transaction(
            user_id=registered_user["id"],
            amount="10000",
            transaction_type="income",
            description="Salary"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="2500",
            transaction_type="expense",
            description="Food"
        )

        create_transaction(
            user_id=registered_user["id"],
            amount="1500",
            transaction_type="expense",
            description="Transport"
        )

        summary = calculate_balance(
            registered_user["id"]
        )

        assert summary["income"] == Decimal("10000")
        assert summary["expenses"] == Decimal("4000")
        assert summary["balance"] == Decimal("6000")


def test_transaction_service_calculates_zero_balance_for_new_user(
    app, registered_user
):
    with app.app_context():
        summary = calculate_balance(
            registered_user["id"]
        )

        assert summary["income"] == Decimal("0.00")
        assert summary["expenses"] == Decimal("0.00")
        assert summary["balance"] == Decimal("0.00")


def test_transaction_service_calculates_balance_per_user(
    app, registered_user, another_user
):
    with app.app_context():
        create_transaction(
            user_id=registered_user["id"],
            amount="5000",
            transaction_type="income",
            description="First user's income"
        )

        create_transaction(
            user_id=another_user["id"],
            amount="2000",
            transaction_type="income",
            description="Second user's income"
        )

        summary = calculate_balance(
            registered_user["id"]
        )

        assert summary["income"] == Decimal("5000")
        assert summary["expenses"] == Decimal("0.00")
        assert summary["balance"] == Decimal("5000")


# ============================================================
# CATEGORY SERVICE TESTS
# ============================================================

from app.services.category_service import (
    create_category,
    get_user_categories,
    get_category_by_id,
)


# ----------------------------
# CREATE CATEGORIES
# ----------------------------

def test_category_service_creates_income_category(
    app, registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "Salary",
            "income"
        )

        assert category.id is not None
        assert category.user_id == registered_user["id"]
        assert category.name == "Salary"
        assert category.type == "income"


def test_category_service_creates_expense_category(
    app, registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        assert category.id is not None
        assert category.name == "Food"
        assert category.type == "expense"


def test_category_service_strips_category_name(
    app, registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "  Transport  ",
            "expense"
        )

        assert category.name == "Transport"


def test_category_service_normalizes_category_type(
    app, registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "Salary",
            " INCOME "
        )

        assert category.type == "income"


def test_category_service_rejects_empty_name(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_category(
                registered_user["id"],
                "   ",
                "expense"
            )


def test_category_service_rejects_name_over_80_characters(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_category(
                registered_user["id"],
                "A" * 81,
                "expense"
            )


def test_category_service_accepts_name_with_80_characters(
    app, registered_user
):
    with app.app_context():
        category = create_category(
            registered_user["id"],
            "A" * 80,
            "expense"
        )

        assert len(category.name) == 80


def test_category_service_rejects_invalid_type(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_category(
                registered_user["id"],
                "Savings",
                "investment"
            )


def test_category_service_rejects_duplicate_category(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        with pytest.raises(ValueError):
            create_category(
                registered_user["id"],
                "Food",
                "expense"
            )


def test_category_service_rejects_case_insensitive_duplicate(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        with pytest.raises(ValueError):
            create_category(
                registered_user["id"],
                "FOOD",
                "expense"
            )


def test_category_service_allows_same_name_for_different_types(
    app, registered_user
):
    with app.app_context():
        income_category = create_category(
            registered_user["id"],
            "Other",
            "income"
        )

        expense_category = create_category(
            registered_user["id"],
            "Other",
            "expense"
        )

        assert income_category.id != expense_category.id
        assert income_category.type == "income"
        assert expense_category.type == "expense"


def test_different_users_can_create_categories_with_same_name(
    app, registered_user, another_user
):
    with app.app_context():
        first_category = create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        second_category = create_category(
            another_user["id"],
            "Food",
            "expense"
        )

        assert first_category.id != second_category.id


# ----------------------------
# RETRIEVE USER CATEGORIES
# ----------------------------

def test_category_service_returns_all_user_categories(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Salary",
            "income"
        )

        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        categories = get_user_categories(
            registered_user["id"]
        )

        assert len(categories) == 2


def test_category_service_filters_income_categories(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Salary",
            "income"
        )

        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        categories = get_user_categories(
            registered_user["id"],
            category_type="income"
        )

        assert len(categories) == 1
        assert categories[0].name == "Salary"
        assert categories[0].type == "income"


def test_category_service_filters_expense_categories(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Salary",
            "income"
        )

        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        categories = get_user_categories(
            registered_user["id"],
            category_type="expense"
        )

        assert len(categories) == 1
        assert categories[0].name == "Food"
        assert categories[0].type == "expense"


def test_category_service_returns_categories_in_name_order(
    app, registered_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "Transport",
            "expense"
        )

        create_category(
            registered_user["id"],
            "Food",
            "expense"
        )

        create_category(
            registered_user["id"],
            "Rent",
            "expense"
        )

        categories = get_user_categories(
            registered_user["id"]
        )

        names = [category.name for category in categories]

        assert names == ["Food", "Rent", "Transport"]


def test_category_service_returns_empty_list_for_new_user(
    app, registered_user
):
    with app.app_context():
        categories = get_user_categories(
            registered_user["id"]
        )

        assert categories == []


def test_category_service_rejects_invalid_filter_type(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            get_user_categories(
                registered_user["id"],
                category_type="transfer"
            )


def test_category_service_does_not_mix_user_categories(
    app, registered_user, another_user
):
    with app.app_context():
        create_category(
            registered_user["id"],
            "My Food",
            "expense"
        )

        create_category(
            another_user["id"],
            "Private Food",
            "expense"
        )

        categories = get_user_categories(
            registered_user["id"]
        )

        names = [category.name for category in categories]

        assert "My Food" in names
        assert "Private Food" not in names


# ----------------------------
# RETRIEVE CATEGORY BY ID
# ----------------------------

def test_category_service_gets_category_by_id(
    app, registered_user
):
    with app.app_context():
        created = create_category(
            registered_user["id"],
            "Transport",
            "expense"
        )

        category = get_category_by_id(
            created.id,
            registered_user["id"]
        )

        assert category is not None
        assert category.id == created.id
        assert category.name == "Transport"


def test_category_service_does_not_return_another_users_category(
    app, registered_user, another_user
):
    with app.app_context():
        created = create_category(
            another_user["id"],
            "Private Category",
            "expense"
        )

        category = get_category_by_id(
            created.id,
            registered_user["id"]
        )

        assert category is None


def test_category_service_returns_none_for_nonexistent_id(
    app, registered_user
):
    with app.app_context():
        category = get_category_by_id(
            999999,
            registered_user["id"]
        )

        assert category is None


from datetime import date
from decimal import Decimal

from app.models import Budget, Category, Transaction
from app.services.budget_service import (
    validate_budget_amount,
    validate_month_year,
    validate_budget_category,
    create_budget,
    get_user_budgets,
    get_budget_by_id,
    calculate_budget_spending,
)


# ============================================================
# BUDGET SERVICE TESTS
# ============================================================


def _create_budget_test_category(user_id, name="Food", category_type="expense"):
    category = Category(
        user_id=user_id,
        name=name,
        type=category_type
    )
    db.session.add(category)
    db.session.commit()
    return category


def _create_budget_test_transaction(
    user_id,
    amount,
    transaction_type="expense",
    transaction_date=date(2026, 11, 10),
    category_id=None,
    description="Test transaction"
):
    transaction = Transaction(
        user_id=user_id,
        amount=Decimal(str(amount)),
        original_amount=Decimal(str(amount)),
        currency="KES",
        exchange_rate=Decimal("1"),
        exchange_rate_date=transaction_date,
        type=transaction_type,
        date=transaction_date,
        category_id=category_id,
        description=description
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction


# ------------------------------------------------------------
# BUDGET AMOUNT VALIDATION
# ------------------------------------------------------------

def test_validate_budget_amount_accepts_valid_amount():
    assert validate_budget_amount("500.50") == Decimal("500.50")


def test_validate_budget_amount_accepts_integer():
    assert validate_budget_amount("500") == Decimal("500")


def test_validate_budget_amount_accepts_decimal_object():
    assert validate_budget_amount(Decimal("250.75")) == Decimal("250.75")


def test_validate_budget_amount_accepts_maximum_amount():
    assert validate_budget_amount("9999999999.99") == Decimal("9999999999.99")


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "invalid",
        "",
        None,
        " ",
        "12abc",
    ]
)
def test_validate_budget_amount_rejects_non_numeric_values(value):
    with pytest.raises(ValueError):
        validate_budget_amount(value)


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "0.00",
        "-1",
        "-100.50",
    ]
)
def test_validate_budget_amount_rejects_zero_and_negative_values(value):
    with pytest.raises(ValueError):
        validate_budget_amount(value)


@pytest.mark.parametrize(
    "value",
    [
        "NaN",
        "Infinity",
        "-Infinity",
    ]
)
def test_validate_budget_amount_rejects_non_finite_values(value):
    with pytest.raises(ValueError):
        validate_budget_amount(value)


def test_validate_budget_amount_rejects_amount_above_maximum():
    with pytest.raises(ValueError, match="too large"):
        validate_budget_amount("10000000000.00")


def test_validate_budget_amount_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError, match="two decimal places"):
        validate_budget_amount("100.123")


def test_validate_budget_amount_accepts_one_decimal_place():
    assert validate_budget_amount("100.5") == Decimal("100.5")


# ------------------------------------------------------------
# MONTH AND YEAR VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "month, year, expected",
    [
        ("1", "2026", (1, 2026)),
        ("12", "2026", (12, 2026)),
        (" 5 ", " 2025 ", (5, 2025)),
        (1, 2026, (1, 2026)),
    ]
)
def test_validate_month_year_accepts_valid_values(month, year, expected):
    assert validate_month_year(month, year) == expected


@pytest.mark.parametrize(
    "month",
    [
        "0",
        "13",
        "-1",
        "abc",
        "",
        None,
        "1.5",
    ]
)
def test_validate_month_year_rejects_invalid_month(month):
    with pytest.raises(ValueError):
        validate_month_year(month, 2026)


@pytest.mark.parametrize(
    "year",
    [
        "1999",
        "abc",
        "",
        None,
        "-2026",
        "2026.5",
    ]
)
def test_validate_month_year_rejects_invalid_year(year):
    with pytest.raises(ValueError):
        validate_month_year(1, year)


def test_validate_month_year_accepts_year_2000():
    assert validate_month_year(1, 2000) == (1, 2000)


# ------------------------------------------------------------
# BUDGET CATEGORY VALIDATION
# ------------------------------------------------------------

def test_validate_budget_category_accepts_no_category():
    assert validate_budget_category(1, None) is None


def test_validate_budget_category_accepts_empty_category():
    assert validate_budget_category(1, "") is None


def test_validate_budget_category_accepts_owned_expense_category(
    app, registered_user
):
    with app.app_context():
        category = _create_budget_test_category(registered_user["id"])

        result = validate_budget_category(
            registered_user["id"],
            category.id
        )

        assert result == category.id


def test_validate_budget_category_accepts_string_category_id(
    app, registered_user
):
    with app.app_context():
        category = _create_budget_test_category(registered_user["id"])

        result = validate_budget_category(
            registered_user["id"],
            str(category.id)
        )

        assert result == category.id


@pytest.mark.parametrize(
    "category_id",
    [
        "abc",
        "invalid",
        "1.5",
        [],
    ]
)
def test_validate_budget_category_rejects_non_numeric_id(
    registered_user, category_id
):
    with pytest.raises(ValueError):
        validate_budget_category(
            registered_user["id"],
            category_id
        )


def test_validate_budget_category_rejects_nonexistent_category(
    registered_user
):
    with pytest.raises(ValueError):
        validate_budget_category(registered_user["id"], 99999)


def test_validate_budget_category_rejects_another_users_category(
    app, registered_user, another_user
):
    with app.app_context():
        category = _create_budget_test_category(another_user["id"])

        with pytest.raises(ValueError):
            validate_budget_category(
                registered_user["id"],
                category.id
            )


def test_validate_budget_category_rejects_income_category(
    app, registered_user
):
    with app.app_context():
        category = _create_budget_test_category(
            registered_user["id"],
            name="Salary",
            category_type="income"
        )

        with pytest.raises(ValueError):
            validate_budget_category(
                registered_user["id"],
                category.id
            )


# ------------------------------------------------------------
# BUDGET CREATION
# ------------------------------------------------------------

def test_create_budget_without_category(app, registered_user):
    with app.app_context():
        budget = create_budget(
            registered_user["id"],
            "1000.00",
            11,
            2026
        )

        assert budget.id is not None
        assert budget.user_id == registered_user["id"]
        assert budget.amount == Decimal("1000.00")
        assert budget.month == 11
        assert budget.year == 2026
        assert budget.category_id is None


def test_create_budget_with_expense_category(app, registered_user):
    with app.app_context():
        category = _create_budget_test_category(registered_user["id"])

        budget = create_budget(
            registered_user["id"],
            "500.00",
            11,
            2026,
            category.id
        )

        assert budget.category_id == category.id
        assert budget.amount == Decimal("500.00")


def test_create_budget_accepts_string_month_year_and_category_id(
    app, registered_user
):
    with app.app_context():
        category = _create_budget_test_category(registered_user["id"])

        budget = create_budget(
            registered_user["id"],
            "750.00",
            "11",
            "2026",
            str(category.id)
        )

        assert budget.month == 11
        assert budget.year == 2026
        assert budget.category_id == category.id


def test_create_budget_rejects_duplicate_overall_budget(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        create_budget(user_id, "1000", 11, 2026)

        with pytest.raises(ValueError, match="already exists"):
            create_budget(user_id, "1500", 11, 2026)


def test_create_budget_rejects_duplicate_category_budget(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        category = _create_budget_test_category(user_id)

        create_budget(user_id, "500", 11, 2026, category.id)

        with pytest.raises(ValueError, match="already exists"):
            create_budget(user_id, "600", 11, 2026, category.id)


def test_create_budget_allows_different_categories_same_month(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_budget_test_category(user_id, "Food")
        transport = _create_budget_test_category(user_id, "Transport")

        first = create_budget(user_id, "500", 11, 2026, food.id)
        second = create_budget(user_id, "300", 11, 2026, transport.id)

        assert first.id != second.id


def test_create_budget_allows_overall_and_category_budget_same_month(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        category = _create_budget_test_category(user_id)

        overall = create_budget(user_id, "2000", 11, 2026)
        category_budget = create_budget(
            user_id, "500", 11, 2026, category.id
        )

        assert overall.id != category_budget.id


def test_create_budget_allows_same_month_for_different_users(
    app, registered_user, another_user
):
    with app.app_context():
        first = create_budget(
            registered_user["id"], "1000", 11, 2026
        )

        second = create_budget(
            another_user["id"], "1500", 11, 2026
        )

        assert first.id != second.id
        assert first.user_id != second.user_id


@pytest.mark.parametrize(
    "amount, month, year",
    [
        ("0", 11, 2026),
        ("-50", 11, 2026),
        ("abc", 11, 2026),
        ("100.123", 11, 2026),
        ("500", 13, 2026),
        ("500", 11, 1999),
        ("500", "abc", 2026),
        ("500", 11, "abc"),
    ]
)
def test_create_budget_rejects_invalid_details(
    registered_user, amount, month, year
):
    with pytest.raises(ValueError):
        create_budget(
            registered_user["id"],
            amount,
            month,
            year
        )


def test_create_budget_rejects_income_category(
    app, registered_user
):
    with app.app_context():
        category = _create_budget_test_category(
            registered_user["id"],
            "Salary",
            "income"
        )

        with pytest.raises(ValueError):
            create_budget(
                registered_user["id"],
                "500",
                11,
                2026,
                category.id
            )


def test_create_budget_rejects_another_users_category(
    app, registered_user, another_user
):
    with app.app_context():
        category = _create_budget_test_category(another_user["id"])

        with pytest.raises(ValueError):
            create_budget(
                registered_user["id"],
                "500",
                11,
                2026,
                category.id
            )


# ------------------------------------------------------------
# RETRIEVING USER BUDGETS
# ------------------------------------------------------------

def test_get_user_budgets_returns_only_users_budgets(
    app, registered_user, another_user
):
    with app.app_context():
        first = create_budget(
            registered_user["id"], "1000", 11, 2026
        )

        create_budget(
            another_user["id"], "2000", 11, 2026
        )

        budgets = get_user_budgets(registered_user["id"])

        assert len(budgets) == 1
        assert budgets[0].id == first.id


def test_get_user_budgets_filters_by_month(app, registered_user):
    with app.app_context():
        user_id = registered_user["id"]

        november = create_budget(user_id, "1000", 11, 2026)
        create_budget(user_id, "1200", 12, 2026)

        budgets = get_user_budgets(user_id, month=11)

        assert len(budgets) == 1
        assert budgets[0].id == november.id


def test_get_user_budgets_filters_by_year(app, registered_user):
    with app.app_context():
        user_id = registered_user["id"]

        budget_2025 = create_budget(user_id, "1000", 11, 2025)
        create_budget(user_id, "1200", 11, 2026)

        budgets = get_user_budgets(user_id, year=2025)

        assert len(budgets) == 1
        assert budgets[0].id == budget_2025.id


def test_get_user_budgets_filters_by_month_and_year(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        expected = create_budget(user_id, "1000", 11, 2026)
        create_budget(user_id, "1200", 11, 2025)
        create_budget(user_id, "1400", 12, 2026)

        budgets = get_user_budgets(
            user_id,
            month=11,
            year=2026
        )

        assert len(budgets) == 1
        assert budgets[0].id == expected.id


def test_get_user_budgets_orders_newest_year_and_month_first(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        november = create_budget(user_id, "1000", 11, 2026)
        december = create_budget(user_id, "1000", 12, 2026)
        january = create_budget(user_id, "1000", 1, 2027)

        budgets = get_user_budgets(user_id)

        assert [budget.id for budget in budgets] == [
            january.id,
            december.id,
            november.id
        ]


def test_get_user_budgets_returns_empty_list_for_user_without_budgets(
    registered_user
):
    budgets = get_user_budgets(registered_user["id"])

    assert budgets == []


def test_get_user_budgets_rejects_invalid_month(registered_user):
    with pytest.raises(ValueError):
        get_user_budgets(registered_user["id"], month=13)


def test_get_user_budgets_rejects_invalid_year(registered_user):
    with pytest.raises(ValueError):
        get_user_budgets(registered_user["id"], year=1999)


def test_get_budget_by_id_returns_owned_budget(app, registered_user):
    with app.app_context():
        budget = create_budget(
            registered_user["id"], "1000", 11, 2026
        )

        result = get_budget_by_id(
            budget.id,
            registered_user["id"]
        )

        assert result is not None
        assert result.id == budget.id


def test_get_budget_by_id_returns_none_for_another_users_budget(
    app, registered_user, another_user
):
    with app.app_context():
        budget = create_budget(
            another_user["id"], "1000", 11, 2026
        )

        result = get_budget_by_id(
            budget.id,
            registered_user["id"]
        )

        assert result is None


def test_get_budget_by_id_returns_none_for_nonexistent_budget(
    registered_user
):
    result = get_budget_by_id(99999, registered_user["id"])

    assert result is None


# ------------------------------------------------------------
# BUDGET SPENDING CALCULATIONS
# ------------------------------------------------------------

def test_calculate_budget_spending_with_no_transactions(
    app, registered_user
):
    with app.app_context():
        budget = create_budget(
            registered_user["id"], "1000", 11, 2026
        )

        result = calculate_budget_spending(budget)

        assert result["budget"] == Decimal("1000")
        assert result["spent"] == Decimal("0")
        assert result["remaining"] == Decimal("1000")
        assert result["percentage"] == 0.0
        assert result["exceeded"] is False


def test_calculate_budget_spending_sums_expenses(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        budget = create_budget(user_id, "1000", 11, 2026)

        _create_budget_test_transaction(user_id, "100")
        _create_budget_test_transaction(user_id, "250")
        _create_budget_test_transaction(user_id, "50")

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("400")
        assert result["remaining"] == Decimal("600")
        assert result["percentage"] == 40.0
        assert result["exceeded"] is False


def test_calculate_budget_spending_ignores_income_transactions(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        budget = create_budget(user_id, "1000", 11, 2026)

        _create_budget_test_transaction(user_id, "200")
        _create_budget_test_transaction(
            user_id,
            "500",
            transaction_type="income"
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("200")


def test_calculate_budget_spending_ignores_another_users_transactions(
    app, registered_user, another_user
):
    with app.app_context():
        budget = create_budget(
            registered_user["id"], "1000", 11, 2026
        )

        _create_budget_test_transaction(
            registered_user["id"], "100"
        )

        _create_budget_test_transaction(
            another_user["id"], "500"
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")


def test_calculate_budget_spending_ignores_transactions_from_other_months(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        budget = create_budget(user_id, "1000", 11, 2026)

        _create_budget_test_transaction(
            user_id, "100", transaction_date=date(2026, 11, 15)
        )

        _create_budget_test_transaction(
            user_id, "200", transaction_date=date(2026, 10, 31)
        )

        _create_budget_test_transaction(
            user_id, "300", transaction_date=date(2026, 12, 1)
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")


def test_calculate_budget_spending_includes_first_day_of_month(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        budget = create_budget(user_id, "1000", 11, 2026)

        _create_budget_test_transaction(
            user_id, "100", transaction_date=date(2026, 11, 1)
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")


def test_calculate_budget_spending_includes_last_day_of_month(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        budget = create_budget(user_id, "1000", 11, 2026)

        _create_budget_test_transaction(
            user_id, "100", transaction_date=date(2026, 11, 30)
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")


def test_calculate_budget_spending_handles_december(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        budget = create_budget(user_id, "1000", 12, 2026)

        _create_budget_test_transaction(
            user_id, "100", transaction_date=date(2026, 12, 31)
        )

        _create_budget_test_transaction(
            user_id, "200", transaction_date=date(2027, 1, 1)
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")


def test_calculate_budget_spending_filters_by_category(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_budget_test_category(user_id, "Food")
        transport = _create_budget_test_category(user_id, "Transport")

        budget = create_budget(
            user_id, "500", 11, 2026, food.id
        )

        _create_budget_test_transaction(
            user_id, "100", category_id=food.id
        )

        _create_budget_test_transaction(
            user_id, "200", category_id=transport.id
        )

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("100")
        assert result["remaining"] == Decimal("400")


def test_calculate_budget_spending_detects_exceeded_budget(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        budget = create_budget(user_id, "500", 11, 2026)

        _create_budget_test_transaction(user_id, "300")
        _create_budget_test_transaction(user_id, "250")

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("550")
        assert result["remaining"] == Decimal("-50")
        assert result["percentage"] == 110.00000000000001 or result["percentage"] == 110.0
        assert result["exceeded"] is True


def test_calculate_budget_spending_exactly_at_budget_is_not_exceeded(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        budget = create_budget(user_id, "500", 11, 2026)

        _create_budget_test_transaction(user_id, "300")
        _create_budget_test_transaction(user_id, "200")

        result = calculate_budget_spending(budget)

        assert result["spent"] == Decimal("500")
        assert result["remaining"] == Decimal("0")
        assert result["percentage"] == 100.0
        assert result["exceeded"] is False


from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.savings_goal_service import (
    validate_money_amount,
    validate_goal_name,
    validate_deadline,
    create_savings_goal,
    get_user_savings_goals,
    get_savings_goal_by_id,
    update_savings_progress,
    delete_savings_goal,
)


# ============================================================
# SAVINGS GOAL SERVICE TESTS
# ============================================================


# ------------------------------------------------------------
# MONEY AMOUNT VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        ("100", Decimal("100")),
        ("100.50", Decimal("100.50")),
        ("0.01", Decimal("0.01")),
        (100, Decimal("100")),
        (Decimal("250.75"), Decimal("250.75")),
        ("9999999999.99", Decimal("9999999999.99")),
    ]
)
def test_validate_money_amount_accepts_valid_amounts(value, expected):
    assert validate_money_amount(value, "target amount") == expected


@pytest.mark.parametrize(
    "value",
    ["abc", "invalid", "", None, " ", "12abc"]
)
def test_validate_money_amount_rejects_non_numeric_values(value):
    with pytest.raises(ValueError, match="valid target amount"):
        validate_money_amount(value, "target amount")


@pytest.mark.parametrize(
    "value",
    ["0", "0.00", "-1", "-100.50"]
)
def test_validate_money_amount_rejects_zero_and_negative_values(value):
    with pytest.raises(ValueError, match="greater than zero"):
        validate_money_amount(value, "target amount")


@pytest.mark.parametrize(
    "value",
    ["NaN", "Infinity", "-Infinity"]
)
def test_validate_money_amount_rejects_non_finite_values(value):
    with pytest.raises(ValueError):
        validate_money_amount(value, "target amount")


def test_validate_money_amount_rejects_amount_above_maximum():
    with pytest.raises(ValueError, match="too large"):
        validate_money_amount("10000000000.00", "target amount")


def test_validate_money_amount_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError, match="two decimal places"):
        validate_money_amount("100.123", "target amount")


def test_validate_money_amount_accepts_one_decimal_place():
    assert validate_money_amount(
        "100.5", "target amount"
    ) == Decimal("100.5")


def test_validate_money_amount_uses_supplied_field_name():
    with pytest.raises(ValueError, match="savings amount"):
        validate_money_amount("invalid", "savings amount")


# ------------------------------------------------------------
# GOAL NAME VALIDATION
# ------------------------------------------------------------

@pytest.mark.parametrize(
    "name, expected",
    [
        ("Emergency Fund", "Emergency Fund"),
        ("  Holiday Fund  ", "Holiday Fund"),
        ("A", "A"),
        ("x" * 100, "x" * 100),
    ]
)
def test_validate_goal_name_accepts_valid_names(name, expected):
    assert validate_goal_name(name) == expected


@pytest.mark.parametrize(
    "name",
    [None, "", " ", "     ", "\t", "\n"]
)
def test_validate_goal_name_rejects_empty_names(name):
    with pytest.raises(ValueError, match="required"):
        validate_goal_name(name)


def test_validate_goal_name_rejects_name_longer_than_100_characters():
    with pytest.raises(ValueError, match="100 characters"):
        validate_goal_name("x" * 101)


def test_validate_goal_name_strips_surrounding_whitespace():
    assert validate_goal_name("  Laptop Fund  ") == "Laptop Fund"


# ------------------------------------------------------------
# DEADLINE VALIDATION
# ------------------------------------------------------------

def test_validate_deadline_accepts_none():
    assert validate_deadline(None) is None


def test_validate_deadline_accepts_empty_string():
    assert validate_deadline("") is None


def test_validate_deadline_accepts_today():
    today = date.today()
    assert validate_deadline(today) == today


def test_validate_deadline_accepts_future_date_object():
    future = date.today() + timedelta(days=30)
    assert validate_deadline(future) == future


def test_validate_deadline_accepts_future_iso_date():
    future = date.today() + timedelta(days=30)
    assert validate_deadline(future.isoformat()) == future


def test_validate_deadline_accepts_future_datetime():
    future = datetime.combine(
        date.today() + timedelta(days=30),
        datetime.min.time()
    )

    assert validate_deadline(future) == future.date()


def test_validate_deadline_converts_datetime_to_date():
    future = datetime.combine(
        date.today(),
        datetime.min.time()
    )

    result = validate_deadline(future)

    assert result == date.today()
    assert isinstance(result, date)
    assert not isinstance(result, datetime)


def test_validate_deadline_rejects_yesterday():
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(ValueError, match="past"):
        validate_deadline(yesterday)


def test_validate_deadline_rejects_past_iso_date():
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(ValueError, match="past"):
        validate_deadline(yesterday.isoformat())


@pytest.mark.parametrize(
    "deadline",
    ["invalid-date", "2026-99-99", "not-a-date", "2026/12/31"]
)
def test_validate_deadline_rejects_invalid_date_strings(deadline):
    with pytest.raises(ValueError, match="valid deadline"):
        validate_deadline(deadline)


def test_validate_deadline_rejects_invalid_type():
    with pytest.raises(ValueError, match="valid deadline"):
        validate_deadline(object())


# ------------------------------------------------------------
# SAVINGS GOAL CREATION
# ------------------------------------------------------------

def test_create_savings_goal_with_no_deadline(app, registered_user):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"],
            "Emergency Fund",
            "10000"
        )

        assert goal.id is not None
        assert goal.user_id == registered_user["id"]
        assert goal.name == "Emergency Fund"
        assert goal.target_amount == Decimal("10000")
        assert goal.current_amount == Decimal("0.00")
        assert goal.deadline is None


def test_create_savings_goal_with_future_deadline(app, registered_user):
    with app.app_context():
        deadline = date.today() + timedelta(days=60)

        goal = create_savings_goal(
            registered_user["id"],
            "Holiday Fund",
            "5000",
            deadline
        )

        assert goal.deadline == deadline


def test_create_savings_goal_accepts_iso_deadline(app, registered_user):
    with app.app_context():
        deadline = date.today() + timedelta(days=60)

        goal = create_savings_goal(
            registered_user["id"],
            "Holiday Fund",
            "5000",
            deadline.isoformat()
        )

        assert goal.deadline == deadline


def test_create_savings_goal_strips_name(app, registered_user):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"],
            "  Laptop Fund  ",
            "5000"
        )

        assert goal.name == "Laptop Fund"


def test_create_savings_goal_starts_with_zero_progress(
    app, registered_user
):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"],
            "New Goal",
            "2000"
        )

        assert goal.current_amount == Decimal("0.00")


def test_create_savings_goal_accepts_maximum_target(
    app, registered_user
):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"],
            "Large Goal",
            "9999999999.99"
        )

        assert goal.target_amount == Decimal("9999999999.99")


@pytest.mark.parametrize(
    "name, amount",
    [
        ("", "1000"),
        ("   ", "1000"),
        ("x" * 101, "1000"),
        ("Valid Goal", "0"),
        ("Valid Goal", "-100"),
        ("Valid Goal", "abc"),
        ("Valid Goal", "100.123"),
        ("Valid Goal", "10000000000"),
    ]
)
def test_create_savings_goal_rejects_invalid_details(
    registered_user, name, amount
):
    with pytest.raises(ValueError):
        create_savings_goal(
            registered_user["id"],
            name,
            amount
        )


def test_create_savings_goal_rejects_past_deadline(
    registered_user
):
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(ValueError, match="past"):
        create_savings_goal(
            registered_user["id"],
            "Invalid Deadline Goal",
            "1000",
            yesterday
        )


def test_create_savings_goal_does_not_create_record_after_validation_failure(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            create_savings_goal(
                registered_user["id"],
                "",
                "1000"
            )

        goals = get_user_savings_goals(registered_user["id"])

        assert goals == []


# ------------------------------------------------------------
# RETRIEVING SAVINGS GOALS
# ------------------------------------------------------------

def test_get_user_savings_goals_returns_users_goals(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        first = create_savings_goal(user_id, "First Goal", "1000")
        second = create_savings_goal(user_id, "Second Goal", "2000")

        goals = get_user_savings_goals(user_id)

        assert len(goals) == 2
        assert first in goals
        assert second in goals


def test_get_user_savings_goals_does_not_return_another_users_goals(
    app, registered_user, another_user
):
    with app.app_context():
        create_savings_goal(
            registered_user["id"], "My Goal", "1000"
        )

        create_savings_goal(
            another_user["id"], "Other Goal", "2000"
        )

        goals = get_user_savings_goals(registered_user["id"])

        assert len(goals) == 1
        assert goals[0].name == "My Goal"


def test_get_user_savings_goals_returns_empty_list_for_new_user(
    registered_user
):
    goals = get_user_savings_goals(registered_user["id"])

    assert goals == []


def test_get_user_savings_goals_orders_newest_first(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        first = create_savings_goal(user_id, "First Goal", "1000")
        second = create_savings_goal(user_id, "Second Goal", "2000")
        third = create_savings_goal(user_id, "Third Goal", "3000")

        goals = get_user_savings_goals(user_id)

        assert [goal.id for goal in goals] == [
            third.id,
            second.id,
            first.id
        ]


def test_get_savings_goal_by_id_returns_owned_goal(
    app, registered_user
):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"], "My Goal", "1000"
        )

        result = get_savings_goal_by_id(
            goal.id,
            registered_user["id"]
        )

        assert result is not None
        assert result.id == goal.id


def test_get_savings_goal_by_id_returns_none_for_another_users_goal(
    app, registered_user, another_user
):
    with app.app_context():
        goal = create_savings_goal(
            another_user["id"], "Other Goal", "1000"
        )

        result = get_savings_goal_by_id(
            goal.id,
            registered_user["id"]
        )

        assert result is None


def test_get_savings_goal_by_id_returns_none_for_nonexistent_goal(
    registered_user
):
    result = get_savings_goal_by_id(
        99999,
        registered_user["id"]
    )

    assert result is None


# ------------------------------------------------------------
# SAVINGS PROGRESS UPDATES
# ------------------------------------------------------------

def test_update_savings_progress_adds_amount(
    app, registered_user
):
    with app.app_context():
        goal = create_savings_goal(
            registered_user["id"], "Emergency Fund", "1000"
        )

        updated = update_savings_progress(
            goal.id,
            registered_user["id"],
            "200"
        )

        assert updated.current_amount == Decimal("200")


def test_update_savings_progress_accumulates_contributions(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        update_savings_progress(goal.id, user_id, "200")
        updated = update_savings_progress(goal.id, user_id, "300")

        assert updated.current_amount == Decimal("500")


def test_update_savings_progress_accepts_decimal_amount(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        updated = update_savings_progress(
            goal.id,
            user_id,
            Decimal("125.50")
        )

        assert updated.current_amount == Decimal("125.50")


def test_update_savings_progress_accepts_exact_target_amount(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        updated = update_savings_progress(
            goal.id,
            user_id,
            "1000"
        )

        assert updated.current_amount == Decimal("1000")


def test_update_savings_progress_rejects_nonexistent_goal(
    registered_user
):
    with pytest.raises(ValueError, match="not found"):
        update_savings_progress(
            99999,
            registered_user["id"],
            "100"
        )


def test_update_savings_progress_rejects_another_users_goal(
    app, registered_user, another_user
):
    with app.app_context():
        goal = create_savings_goal(
            another_user["id"], "Other Goal", "1000"
        )

        with pytest.raises(ValueError, match="not found"):
            update_savings_progress(
                goal.id,
                registered_user["id"],
                "100"
            )


@pytest.mark.parametrize(
    "amount",
    [
        "0",
        "-100",
        "abc",
        "",
        "100.123",
        "10000000000",
        "NaN",
        "Infinity",
    ]
)
def test_update_savings_progress_rejects_invalid_amounts(
    app, registered_user, amount
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        with pytest.raises(ValueError):
            update_savings_progress(
                goal.id,
                user_id,
                amount
            )


def test_update_savings_progress_rejects_contribution_above_target(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        with pytest.raises(ValueError, match="exceed"):
            update_savings_progress(
                goal.id,
                user_id,
                "1001"
            )

        assert goal.current_amount == Decimal("0.00")


def test_update_savings_progress_rejects_total_above_target(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        update_savings_progress(goal.id, user_id, "700")

        with pytest.raises(ValueError, match="exceed"):
            update_savings_progress(goal.id, user_id, "400")

        assert goal.current_amount == Decimal("700")


def test_update_savings_progress_rejects_update_after_goal_completion(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        update_savings_progress(goal.id, user_id, "1000")

        with pytest.raises(ValueError, match="already complete"):
            update_savings_progress(goal.id, user_id, "1")


def test_update_savings_progress_does_not_change_total_after_invalid_update(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        update_savings_progress(goal.id, user_id, "300")

        with pytest.raises(ValueError):
            update_savings_progress(goal.id, user_id, "800")

        assert goal.current_amount == Decimal("300")


# ------------------------------------------------------------
# SAVINGS GOAL DELETION
# ------------------------------------------------------------

def test_delete_savings_goal_deletes_owned_goal(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        goal = create_savings_goal(user_id, "Emergency Fund", "1000")

        result = delete_savings_goal(goal.id, user_id)

        assert result is True
        assert get_savings_goal_by_id(goal.id, user_id) is None


def test_delete_savings_goal_rejects_nonexistent_goal(
    registered_user
):
    with pytest.raises(ValueError, match="not found"):
        delete_savings_goal(99999, registered_user["id"])


def test_delete_savings_goal_rejects_another_users_goal(
    app, registered_user, another_user
):
    with app.app_context():
        goal = create_savings_goal(
            another_user["id"], "Other Goal", "1000"
        )

        with pytest.raises(ValueError, match="not found"):
            delete_savings_goal(
                goal.id,
                registered_user["id"]
            )

        assert get_savings_goal_by_id(
            goal.id,
            another_user["id"]
        ) is not None


def test_delete_savings_goal_does_not_delete_other_goals(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        first = create_savings_goal(user_id, "First Goal", "1000")
        second = create_savings_goal(user_id, "Second Goal", "2000")

        delete_savings_goal(first.id, user_id)

        assert get_savings_goal_by_id(first.id, user_id) is None
        assert get_savings_goal_by_id(second.id, user_id) is not None


from datetime import date, datetime
from decimal import Decimal

from app.services.report_service import (
    validate_report_dates,
    get_financial_report,
)


# ============================================================
# REPORT SERVICE TESTS
# ============================================================


def _create_report_transaction(
    user_id,
    amount,
    transaction_type,
    transaction_date,
    category_id=None,
    description="Report test transaction"
):
    transaction = Transaction(
        user_id=user_id,
        amount=Decimal(str(amount)),
        original_amount=Decimal(str(amount)),
        currency="KES",
        exchange_rate=Decimal("1"),
        exchange_rate_date=transaction_date,
        type=transaction_type,
        date=transaction_date,
        category_id=category_id,
        description=description
    )

    db.session.add(transaction)
    db.session.commit()

    return transaction


def _create_report_category(
    user_id,
    name,
    category_type="expense"
):
    category = Category(
        user_id=user_id,
        name=name,
        type=category_type
    )

    db.session.add(category)
    db.session.commit()

    return category


# ------------------------------------------------------------
# REPORT DATE VALIDATION
# ------------------------------------------------------------

def test_validate_report_dates_accepts_valid_date_objects():
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)

    assert validate_report_dates(start, end) == (start, end)


def test_validate_report_dates_accepts_same_start_and_end_date():
    report_date = date(2026, 5, 15)

    assert validate_report_dates(
        report_date,
        report_date
    ) == (report_date, report_date)


def test_validate_report_dates_converts_datetime_to_date():
    start = datetime(2026, 1, 1, 10, 30)
    end = datetime(2026, 1, 31, 18, 45)

    result = validate_report_dates(start, end)

    assert result == (
        date(2026, 1, 1),
        date(2026, 1, 31)
    )


def test_validate_report_dates_accepts_datetime_and_date_combination():
    start = datetime(2026, 1, 1, 10, 30)
    end = date(2026, 1, 31)

    assert validate_report_dates(start, end) == (
        date(2026, 1, 1),
        date(2026, 1, 31)
    )


def test_validate_report_dates_rejects_start_after_end():
    start = date(2026, 2, 1)
    end = date(2026, 1, 1)

    with pytest.raises(ValueError, match="Start date"):
        validate_report_dates(start, end)


def test_validate_report_dates_rejects_invalid_start_date():
    with pytest.raises(ValueError, match="start date"):
        validate_report_dates(
            "2026-01-01",
            date(2026, 1, 31)
        )


def test_validate_report_dates_rejects_invalid_end_date():
    with pytest.raises(ValueError, match="end date"):
        validate_report_dates(
            date(2026, 1, 1),
            "2026-01-31"
        )


def test_validate_report_dates_rejects_both_invalid_dates():
    with pytest.raises(ValueError):
        validate_report_dates(
            "invalid",
            "invalid"
        )


def test_validate_report_dates_rejects_none_start_date():
    with pytest.raises(ValueError, match="start date"):
        validate_report_dates(
            None,
            date(2026, 1, 31)
        )


def test_validate_report_dates_rejects_none_end_date():
    with pytest.raises(ValueError, match="end date"):
        validate_report_dates(
            date(2026, 1, 1),
            None
        )


# ------------------------------------------------------------
# EMPTY REPORTS
# ------------------------------------------------------------

def test_get_financial_report_returns_zero_totals_without_transactions(
    app, registered_user
):
    with app.app_context():
        report = get_financial_report(
            registered_user["id"],
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("0.00")
        assert report["total_expenses"] == Decimal("0.00")
        assert report["net_balance"] == Decimal("0.00")
        assert report["transaction_count"] == 0
        assert report["category_breakdown"] == []
        assert report["monthly_data"] == []


def test_get_financial_report_returns_all_expected_keys(
    app, registered_user
):
    with app.app_context():
        report = get_financial_report(
            registered_user["id"],
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert set(report.keys()) == {
            "total_income",
            "total_expenses",
            "net_balance",
            "transaction_count",
            "category_breakdown",
            "monthly_data"
        }


# ------------------------------------------------------------
# INCOME, EXPENSES AND NET BALANCE
# ------------------------------------------------------------

def test_get_financial_report_calculates_total_income(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "500", "income", date(2026, 1, 15)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("1500")


def test_get_financial_report_calculates_total_expenses(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "300", "expense", date(2026, 1, 15)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_expenses"] == Decimal("500")


def test_get_financial_report_calculates_net_balance(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "2000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "750", "expense", date(2026, 1, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["net_balance"] == Decimal("1250")


def test_get_financial_report_supports_negative_net_balance(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "500", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "800", "expense", date(2026, 1, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["net_balance"] == Decimal("-300")


def test_get_financial_report_counts_transactions(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10)
        )

        _create_report_transaction(
            user_id, "300", "expense", date(2026, 1, 15)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["transaction_count"] == 3


def test_get_financial_report_counts_income_and_expenses_together(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["transaction_count"] == 2


# ------------------------------------------------------------
# REPORT DATE RANGE FILTERING
# ------------------------------------------------------------

def test_get_financial_report_includes_start_date(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "100", "income", date(2026, 1, 1)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("100")


def test_get_financial_report_includes_end_date(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 31)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("200")


def test_get_financial_report_excludes_transactions_before_start_date(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "100", "income", date(2025, 12, 31)
        )

        _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 1)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("200")
        assert report["transaction_count"] == 1


def test_get_financial_report_excludes_transactions_after_end_date(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "100", "income", date(2026, 1, 31)
        )

        _create_report_transaction(
            user_id, "200", "income", date(2026, 2, 1)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("100")
        assert report["transaction_count"] == 1


def test_get_financial_report_accepts_single_day_range(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]
        report_date = date(2026, 1, 15)

        _create_report_transaction(
            user_id, "100", "income", report_date
        )

        _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 16)
        )

        report = get_financial_report(
            user_id,
            report_date,
            report_date
        )

        assert report["total_income"] == Decimal("100")
        assert report["transaction_count"] == 1


def test_get_financial_report_rejects_invalid_date_range(
    registered_user
):
    with pytest.raises(ValueError):
        get_financial_report(
            registered_user["id"],
            date(2026, 2, 1),
            date(2026, 1, 1)
        )


# ------------------------------------------------------------
# USER ISOLATION
# ------------------------------------------------------------

def test_get_financial_report_excludes_another_users_transactions(
    app, registered_user, another_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            another_user["id"], "5000", "income", date(2026, 1, 5)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_income"] == Decimal("1000")
        assert report["transaction_count"] == 1


def test_get_financial_report_excludes_another_users_expenses(
    app, registered_user, another_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 5)
        )

        _create_report_transaction(
            another_user["id"], "900", "expense", date(2026, 1, 5)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["total_expenses"] == Decimal("200")
        assert report["transaction_count"] == 1


# ------------------------------------------------------------
# CATEGORY BREAKDOWN
# ------------------------------------------------------------

def test_get_financial_report_groups_expenses_by_category(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_report_category(user_id, "Food")
        transport = _create_report_category(user_id, "Transport")

        _create_report_transaction(
            user_id, "100", "expense", date(2026, 1, 5), food.id
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10), food.id
        )

        _create_report_transaction(
            user_id, "150", "expense", date(2026, 1, 15), transport.id
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        breakdown = {
            item["name"]: item["amount"]
            for item in report["category_breakdown"]
        }

        assert breakdown == {
            "Food": Decimal("300"),
            "Transport": Decimal("150")
        }


def test_get_financial_report_sorts_categories_by_amount_descending(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_report_category(user_id, "Food")
        rent = _create_report_category(user_id, "Rent")
        transport = _create_report_category(user_id, "Transport")

        _create_report_transaction(
            user_id, "100", "expense", date(2026, 1, 5), food.id
        )

        _create_report_transaction(
            user_id, "500", "expense", date(2026, 1, 10), rent.id
        )

        _create_report_transaction(
            user_id, "250", "expense", date(2026, 1, 15), transport.id
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        names = [
            item["name"]
            for item in report["category_breakdown"]
        ]

        assert names == ["Rent", "Transport", "Food"]


def test_get_financial_report_calculates_category_percentages(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_report_category(user_id, "Food")
        transport = _create_report_category(user_id, "Transport")

        _create_report_transaction(
            user_id, "300", "expense", date(2026, 1, 5), food.id
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10), transport.id
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        percentages = {
            item["name"]: item["percentage"]
            for item in report["category_breakdown"]
        }

        assert percentages["Food"] == 60.0
        assert percentages["Transport"] == 40.0


def test_get_financial_report_uses_uncategorized_for_missing_category(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id,
            "150",
            "expense",
            date(2026, 1, 5),
            category_id=None
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["category_breakdown"][0]["name"] == "Uncategorized"
        assert report["category_breakdown"][0]["amount"] == Decimal("150")


def test_get_financial_report_does_not_include_income_in_category_breakdown(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        income_category = _create_report_category(
            user_id,
            "Salary",
            "income"
        )

        _create_report_transaction(
            user_id,
            "1000",
            "income",
            date(2026, 1, 5),
            income_category.id
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["category_breakdown"] == []


def test_get_financial_report_category_percentages_total_100(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        food = _create_report_category(user_id, "Food")
        transport = _create_report_category(user_id, "Transport")

        _create_report_transaction(
            user_id, "300", "expense", date(2026, 1, 5), food.id
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10), transport.id
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        total_percentage = sum(
            item["percentage"]
            for item in report["category_breakdown"]
        )

        assert total_percentage == 100.0


# ------------------------------------------------------------
# MONTHLY REPORT DATA
# ------------------------------------------------------------

def test_get_financial_report_groups_transactions_by_month(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "200", "expense", date(2026, 1, 10)
        )

        _create_report_transaction(
            user_id, "1500", "income", date(2026, 2, 5)
        )

        _create_report_transaction(
            user_id, "400", "expense", date(2026, 2, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 2, 28)
        )

        assert len(report["monthly_data"]) == 2
        assert report["monthly_data"][0]["month"] == "2026-01"
        assert report["monthly_data"][1]["month"] == "2026-02"


def test_get_financial_report_calculates_monthly_income_and_expenses(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "300", "expense", date(2026, 1, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        january = report["monthly_data"][0]

        assert january["income"] == Decimal("1000")
        assert january["expenses"] == Decimal("300")
        assert january["net_balance"] == Decimal("700")


def test_get_financial_report_calculates_negative_monthly_balance(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "500", "expense", date(2026, 1, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["monthly_data"][0]["net_balance"] == Decimal("-300")


def test_get_financial_report_orders_months_chronologically(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "100", "income", date(2026, 3, 5)
        )

        _create_report_transaction(
            user_id, "100", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "100", "income", date(2026, 2, 5)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 3, 31)
        )

        months = [
            item["month"]
            for item in report["monthly_data"]
        ]

        assert months == ["2026-01", "2026-02", "2026-03"]


def test_get_financial_report_calculates_monthly_chart_widths(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "500", "expense", date(2026, 1, 10)
        )

        _create_report_transaction(
            user_id, "500", "income", date(2026, 2, 5)
        )

        _create_report_transaction(
            user_id, "250", "expense", date(2026, 2, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 2, 28)
        )

        january, february = report["monthly_data"]

        assert january["income_width"] == 100.0
        assert january["expense_width"] == 50.0
        assert february["income_width"] == 50.0
        assert february["expense_width"] == 25.0


def test_get_financial_report_chart_widths_never_exceed_100(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "1000", "income", date(2026, 1, 5)
        )

        _create_report_transaction(
            user_id, "700", "expense", date(2026, 1, 10)
        )

        _create_report_transaction(
            user_id, "500", "income", date(2026, 2, 5)
        )

        _create_report_transaction(
            user_id, "900", "expense", date(2026, 2, 10)
        )

        report = get_financial_report(
            user_id,
            date(2026, 1, 1),
            date(2026, 2, 28)
        )

        for item in report["monthly_data"]:
            assert 0 <= item["income_width"] <= 100
            assert 0 <= item["expense_width"] <= 100


def test_get_financial_report_chart_widths_are_zero_without_transactions(
    app, registered_user
):
    with app.app_context():
        report = get_financial_report(
            registered_user["id"],
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert report["monthly_data"] == []


# ------------------------------------------------------------
# TRANSACTION ORDERING
# ------------------------------------------------------------

def test_get_financial_report_orders_transactions_by_date(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        latest = _create_report_transaction(
            user_id, "300", "income", date(2026, 1, 20)
        )

        earliest = _create_report_transaction(
            user_id, "100", "income", date(2026, 1, 5)
        )

        middle = _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 10)
        )

        transactions = Transaction.query.filter_by(
            user_id=user_id
        ).order_by(
            Transaction.date.asc(),
            Transaction.id.asc()
        ).all()

        assert [item.id for item in transactions] == [
            earliest.id,
            middle.id,
            latest.id
        ]


def test_get_financial_report_handles_multiple_years(
    app, registered_user
):
    with app.app_context():
        user_id = registered_user["id"]

        _create_report_transaction(
            user_id, "100", "income", date(2025, 12, 15)
        )

        _create_report_transaction(
            user_id, "200", "income", date(2026, 1, 15)
        )

        report = get_financial_report(
            user_id,
            date(2025, 12, 1),
            date(2026, 1, 31)
        )

        assert len(report["monthly_data"]) == 2
        assert report["monthly_data"][0]["month"] == "2025-12"
        assert report["monthly_data"][1]["month"] == "2026-01"
        assert report["total_income"] == Decimal("300")


import csv
import io
from datetime import date, datetime
from decimal import Decimal

from app.services.export_service import (
    money_to_string,
    date_to_string,
    validate_export_dates,
    get_transactions_for_export,
    generate_transactions_csv,
    generate_personal_backup,
)


def _create_export_category(user_id, name="Food", category_type="expense"):
    category = Category(
        user_id=user_id,
        name=name,
        type=category_type
    )
    db.session.add(category)
    db.session.commit()
    return category


def _create_export_transaction(
    user_id,
    amount="100.00",
    transaction_type="expense",
    description="Test transaction",
    transaction_date=None,
    category_id=None,
    original_amount=None,
    currency="KES",
    exchange_rate="1.0000000000",
    exchange_rate_date=None
):
    transaction_date = transaction_date or date(2026, 1, 15)
    transaction = Transaction(
        user_id=user_id,
        amount=Decimal(amount),
        original_amount=Decimal(
            original_amount if original_amount is not None else amount
        ),
        currency=currency,
        exchange_rate=Decimal(exchange_rate),
        exchange_rate_date=exchange_rate_date or transaction_date,
        type=transaction_type,
        description=description,
        date=transaction_date,
        category_id=category_id
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction


def test_money_to_string_converts_decimal():
    assert money_to_string(Decimal("125.50")) == "125.50"


def test_money_to_string_converts_integer():
    assert money_to_string(100) == "100"


def test_money_to_string_converts_none_to_zero():
    assert money_to_string(None) == "0"


def test_money_to_string_converts_float():
    assert money_to_string(12.5) == "12.5"


def test_date_to_string_converts_date():
    assert date_to_string(date(2026, 5, 10)) == "2026-05-10"


def test_date_to_string_converts_datetime():
    value = datetime(2026, 5, 10, 14, 30)
    assert date_to_string(value) == "2026-05-10T14:30:00"


def test_date_to_string_returns_none_for_none():
    assert date_to_string(None) is None


def test_validate_export_dates_accepts_no_dates():
    assert validate_export_dates() == (None, None)


def test_validate_export_dates_accepts_valid_dates():
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)

    assert validate_export_dates(start, end) == (start, end)


def test_validate_export_dates_converts_datetimes():
    start = datetime(2026, 1, 1, 10, 30)
    end = datetime(2026, 1, 31, 15, 45)

    assert validate_export_dates(start, end) == (
        date(2026, 1, 1),
        date(2026, 1, 31)
    )


@pytest.mark.parametrize("start_date", [
    "2026-01-01",
    123,
    12.5,
    [],
])
def test_validate_export_dates_rejects_invalid_start_date(start_date):
    with pytest.raises(ValueError, match="valid export start date"):
        validate_export_dates(start_date=start_date)


@pytest.mark.parametrize("end_date", [
    "2026-01-31",
    123,
    12.5,
    [],
])
def test_validate_export_dates_rejects_invalid_end_date(end_date):
    with pytest.raises(ValueError, match="valid export end date"):
        validate_export_dates(end_date=end_date)


def test_validate_export_dates_rejects_start_after_end():
    with pytest.raises(ValueError, match="Start date cannot be after end date"):
        validate_export_dates(
            date(2026, 2, 1),
            date(2026, 1, 1)
        )


def test_get_transactions_for_export_returns_user_transactions(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(registered_user["id"])

        transactions = get_transactions_for_export(
            registered_user["id"]
        )

        assert len(transactions) == 1


def test_get_transactions_for_export_excludes_other_users(
    app, registered_user, another_user
):
    with app.app_context():
        _create_export_transaction(registered_user["id"])
        _create_export_transaction(another_user["id"])

        transactions = get_transactions_for_export(
            registered_user["id"]
        )

        assert len(transactions) == 1
        assert transactions[0].user_id == registered_user["id"]


def test_get_transactions_for_export_filters_start_date(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 5)
        )
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 20)
        )

        transactions = get_transactions_for_export(
            registered_user["id"],
            start_date=date(2026, 1, 10)
        )

        assert len(transactions) == 1
        assert transactions[0].date == date(2026, 1, 20)


def test_get_transactions_for_export_filters_end_date(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 5)
        )
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 20)
        )

        transactions = get_transactions_for_export(
            registered_user["id"],
            end_date=date(2026, 1, 10)
        )

        assert len(transactions) == 1
        assert transactions[0].date == date(2026, 1, 5)


def test_get_transactions_for_export_includes_date_boundaries(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 1)
        )
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 31)
        )

        transactions = get_transactions_for_export(
            registered_user["id"],
            date(2026, 1, 1),
            date(2026, 1, 31)
        )

        assert len(transactions) == 2


def test_get_transactions_for_export_orders_newest_first(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 5)
        )
        _create_export_transaction(
            registered_user["id"],
            transaction_date=date(2026, 1, 20)
        )

        transactions = get_transactions_for_export(
            registered_user["id"]
        )

        assert transactions[0].date == date(2026, 1, 20)
        assert transactions[1].date == date(2026, 1, 5)


def test_get_transactions_for_export_rejects_invalid_dates(
    app, registered_user
):
    with app.app_context():
        with pytest.raises(ValueError):
            get_transactions_for_export(
                registered_user["id"],
                start_date="invalid"
            )


def test_generate_transactions_csv_has_correct_headers(
    app, registered_user
):
    with app.app_context():
        csv_content = generate_transactions_csv(
            registered_user["id"]
        )

        rows = list(csv.reader(io.StringIO(csv_content)))

        assert rows[0] == [
            "Date",
            "Type",
            "Category",
            "Description",
            "Amount",
            "Currency",
            "Amount (KES)",
            "Exchange Rate",
            "Exchange Rate Date"
        ]


def test_generate_transactions_csv_exports_transaction(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            amount="250.50",
            transaction_type="expense",
            description="Groceries"
        )

        content = generate_transactions_csv(
            registered_user["id"]
        )

        rows = list(csv.reader(io.StringIO(content)))

        assert rows[1] == [
            "2026-01-15",
            "expense",
            "Uncategorized",
            "Groceries",
            "250.50",
            "KES",
            "250.50",
            "1.0000000000",
            "2026-01-15"
        ]


def test_generate_transactions_csv_includes_category_name(
    app, registered_user
):
    with app.app_context():
        category = _create_export_category(
            registered_user["id"],
            "Transport"
        )

        _create_export_transaction(
            registered_user["id"],
            category_id=category.id
        )

        content = generate_transactions_csv(
            registered_user["id"]
        )

        rows = list(csv.reader(io.StringIO(content)))

        assert rows[1][2] == "Transport"


def test_generate_transactions_csv_uses_uncategorized_for_missing_category(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            category_id=None
        )

        content = generate_transactions_csv(
            registered_user["id"]
        )

        rows = list(csv.reader(io.StringIO(content)))

        assert rows[1][2] == "Uncategorized"


def test_generate_transactions_csv_excludes_other_users(
    app, registered_user, another_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            description="My transaction"
        )
        _create_export_transaction(
            another_user["id"],
            description="Other transaction"
        )

        content = generate_transactions_csv(
            registered_user["id"]
        )

        assert "My transaction" in content
        assert "Other transaction" not in content


def test_generate_transactions_csv_returns_headers_when_empty(
    app, registered_user
):
    with app.app_context():
        content = generate_transactions_csv(
            registered_user["id"]
        )

        rows = list(csv.reader(io.StringIO(content)))

        assert len(rows) == 1


def test_generate_transactions_csv_filters_date_range(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            description="January",
            transaction_date=date(2026, 1, 10)
        )
        _create_export_transaction(
            registered_user["id"],
            description="February",
            transaction_date=date(2026, 2, 10)
        )

        content = generate_transactions_csv(
            registered_user["id"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )

        assert "January" in content
        assert "February" not in content


def test_generate_personal_backup_has_required_metadata(
    app, registered_user
):
    with app.app_context():
        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert backup["application"] == "Personal Finance Manager"
        assert backup["backup_version"] == 3
        assert backup["user_id"] == registered_user["id"]
        assert "backup_date" in backup


def test_generate_personal_backup_contains_empty_collections(
    app, registered_user
):
    with app.app_context():
        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert backup["transactions"] == []
        assert backup["categories"] == []
        assert backup["budgets"] == []
        assert backup["savings_goals"] == []
        assert backup["recurring_items"] == []


def test_generate_personal_backup_exports_transactions(
    app, registered_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            amount="450.75",
            description="School supplies"
        )

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert len(backup["transactions"]) == 1

        transaction = backup["transactions"][0]

        assert transaction["amount"] == "450.75"
        assert transaction["description"] == "School supplies"
        assert transaction["type"] == "expense"
        assert transaction["date"] == "2026-01-15"


def test_generate_personal_backup_exports_categories(
    app, registered_user
):
    with app.app_context():
        category = _create_export_category(
            registered_user["id"],
            "Food"
        )

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert len(backup["categories"]) == 1
        assert backup["categories"][0]["name"] == "Food"
        assert backup["categories"][0]["type"] == "expense"


def test_generate_personal_backup_exports_budgets(
    app, registered_user
):
    with app.app_context():
        budget = Budget(
            user_id=registered_user["id"],
            amount=Decimal("1000.00"),
            month=1,
            year=2026,
            category_id=None
        )
        db.session.add(budget)
        db.session.commit()

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert len(backup["budgets"]) == 1
        assert backup["budgets"][0]["amount"] == "1000.00"
        assert backup["budgets"][0]["month"] == 1
        assert backup["budgets"][0]["year"] == 2026


def test_generate_personal_backup_exports_savings_goals(
    app, registered_user
):
    with app.app_context():
        goal = SavingsGoal(
            user_id=registered_user["id"],
            name="Emergency Fund",
            target_amount=Decimal("5000.00"),
            current_amount=Decimal("1000.00"),
            deadline=date(2026, 12, 31)
        )
        db.session.add(goal)
        db.session.commit()

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert len(backup["savings_goals"]) == 1

        saved_goal = backup["savings_goals"][0]

        assert saved_goal["name"] == "Emergency Fund"
        assert saved_goal["target_amount"] == "5000.00"
        assert saved_goal["current_amount"] == "1000.00"
        assert saved_goal["deadline"] == "2026-12-31"


def test_generate_personal_backup_exports_recurring_items(
    app,
    registered_user
):
    with app.app_context():
        item = create_recurring_item(
            registered_user["id"],
            "Rent",
            "25000.00",
            "expense",
            "monthly",
            date(2026, 12, 31)
        )

        backup = generate_personal_backup(registered_user["id"])

        assert backup["backup_version"] == 3
        assert len(backup["recurring_items"]) == 1
        assert backup["recurring_items"][0] == {
            "id": item.id,
            "name": "Rent",
            "amount": "25000.00",
            "type": "expense",
            "frequency": "monthly",
            "next_due_date": "2026-12-31",
            "day_of_month": 31,
            "is_active": True,
            "category_id": None
        }


def test_generate_personal_backup_excludes_other_users(
    app, registered_user, another_user
):
    with app.app_context():
        _create_export_transaction(
            registered_user["id"],
            description="My transaction"
        )
        _create_export_transaction(
            another_user["id"],
            description="Other transaction"
        )

        backup = generate_personal_backup(
            registered_user["id"]
        )

        assert len(backup["transactions"]) == 1
        assert backup["transactions"][0]["description"] == "My transaction"


def test_generate_personal_backup_returns_json_compatible_data(
    app, registered_user
):
    import json

    with app.app_context():
        _create_export_transaction(registered_user["id"])

        backup = generate_personal_backup(
            registered_user["id"]
        )

        serialized = json.dumps(backup)

        assert isinstance(serialized, str)
        assert "Personal Finance Manager" in serialized


from unittest.mock import patch

from sqlalchemy.exc import IntegrityError


def test_auth_register_handles_integrity_error(client, app):
    with patch(
        "app.routes.auth.db.session.commit",
        side_effect=IntegrityError("statement", {}, Exception())
    ):
        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "Password123"
            },
            follow_redirects=True
        )

    assert response.status_code == 200
    assert b"already registered" in response.data


def test_auth_register_handles_unexpected_database_error(client, app):
    with patch(
        "app.routes.auth.db.session.commit",
        side_effect=RuntimeError("Database unavailable")
    ):
        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "Password123"
            },
            follow_redirects=True
        )

    assert response.status_code == 200
    assert b"Registration failed" in response.data


def test_auth_register_rolls_back_after_integrity_error(app, client):
    with patch(
        "app.routes.auth.db.session.commit",
        side_effect=IntegrityError("statement", {}, Exception())
    ):
        response = client.post(
            "/register",
            data={
                "username": "rollbackuser",
                "email": "rollback@example.com",
                "password": "Password123"
            }
        )

    assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(
            email="rollback@example.com"
        ).first()

        assert user is None


def test_auth_login_rejects_backslash_next_url(client, registered_user):
    response = client.post(
        "/login?next=%5C%5Cexample.com",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_auth_login_rejects_scheme_next_url(client, registered_user):
    response = client.post(
        "/login?next=https://example.com",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_auth_login_rejects_empty_credentials(client):
    response = client.post(
        "/login",
        data={
            "email": "",
            "password": ""
        }
    )

    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_auth_logout_displays_success_message(client, registered_user):
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    response = client.post(
        "/logout",
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"You have been logged out." in response.data


def test_transaction_csv_preview_classifies_rows_and_detects_duplicates(
    app,
    registered_user
):
    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Groceries",
            category_type="expense"
        )
        category_id = category.id

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Type", "Category", "Description", "Amount"])
        writer.writerow(["2026-11-17", "expense", "Groceries", "Market", "125.00"])
        writer.writerow(["2026-11-17", "expense", "Groceries", "Market", "125.00"])
        writer.writerow(["not-a-date", "income", "Groceries", "Invalid", "25.00"])

        preview = preview_transaction_csv(
            registered_user["id"],
            output.getvalue().encode("utf-8")
        )

        assert preview["ready_count"] == 1
        assert preview["duplicate_count"] == 1
        assert preview["invalid_count"] == 1
        assert preview["rows"][0]["category_id"] == category_id
        assert preview["rows"][1]["status"] == "duplicate"
        assert preview["rows"][2]["status"] == "invalid"


def test_transaction_csv_preview_accepts_common_headers_and_kes_amounts(
    app,
    registered_user
):
    with app.app_context():
        preview = preview_transaction_csv(
            registered_user["id"],
            (
                "Posted Date,Transaction Type,Payee,Value\n"
                f'{date.today().isoformat()},expense,Market,"KSh 1,250.00"\n'
            ).encode("utf-8")
        )

        assert preview["ready_count"] == 1
        assert preview["rows"][0]["amount"] == "1250.00"


def test_transaction_csv_import_preserves_foreign_currency_details(
    app,
    registered_user,
    monkeypatch
):
    observed_date = date(2026, 11, 20)
    rate_lookups = []

    def get_month_rates(source, target, start_date, end_date):
        rate_lookups.append((source, target, start_date, end_date))
        return [(observed_date, Decimal("130.00"))]

    monkeypatch.setattr(
        transaction_import_service,
        "get_exchange_rates",
        get_month_rates
    )

    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Travel",
            category_type="expense"
        )
        preview = preview_transaction_csv(
            registered_user["id"],
            (
                "Date,Type,Amount,Currency,Category\n"
                "2026-11-22,expense,10.00,USD,Travel\n"
                "2026-11-22,expense,5.00,USD,Travel\n"
            ).encode("utf-8")
        )
        assert preview["ready_count"] == 2
        assert preview["rows"][0]["amount"] == "1300.00"
        assert preview["rows"][0]["original_amount"] == "10.00"
        assert preview["rows"][0]["currency"] == "USD"
        assert len(rate_lookups) == 1

        imported_count, duplicate_count = import_staged_transactions(
            registered_user["id"],
            preview["rows"]
        )
        transactions = get_user_transactions(registered_user["id"])
        assert imported_count == 2
        assert duplicate_count == 0
        assert {item.original_amount for item in transactions} == {
            Decimal("10.00"),
            Decimal("5.00")
        }
        assert all(item.currency == "USD" for item in transactions)
        assert all(
            item.exchange_rate_date == observed_date
            for item in transactions
        )

        exported = generate_transactions_csv(registered_user["id"])
        reimported_preview = preview_transaction_csv(
            registered_user["id"],
            exported.encode("utf-8")
        )

    assert reimported_preview["duplicate_count"] == 2
    assert all(
        row["currency"] == "USD"
        for row in reimported_preview["rows"]
    )
    assert {
        row["original_amount"]
        for row in reimported_preview["rows"]
    } == {"10.00", "5.00"}


def test_transaction_csv_import_route_previews_then_confirms(
    app,
    client,
    registered_user,
    tmp_path
):
    with app.app_context():
        create_category(
            user_id=registered_user["id"],
            name="Groceries",
            category_type="expense"
        )
    app.config["TRANSACTION_IMPORT_STAGING_DIR"] = str(
        tmp_path / "transaction_imports"
    )
    client.post(
        "/login",
        data={
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
    )

    import_date = date.today().isoformat()
    csv_content = (
        "Date,Type,Category,Description,Amount\n"
        f"{import_date},expense,Groceries,Market,125.00\n"
        f"{import_date},expense,Groceries,Market,125.00\n"
        "invalid,expense,Groceries,Needs review,20.00\n"
    )
    response = client.post(
        "/transactions/import",
        data={
            "action": "preview",
            "file": (io.BytesIO(csv_content.encode("utf-8")), "ledger.csv")
        },
        content_type="multipart/form-data"
    )

    assert response.status_code == 200, response.location
    assert b"1</strong><span>Ready to import" in response.data
    assert b"1</strong><span>Duplicates" in response.data
    assert b"1</strong><span>Rows with errors" in response.data
    token_match = re.search(
        rb'name="preview_token" value="([A-Za-z0-9_-]{32})"',
        response.data
    )
    assert token_match
    token = token_match.group(1).decode("ascii")

    with app.app_context():
        staged = get_staged_transaction_import(
            registered_user["id"],
            token
        )
        assert staged is not None
        assert get_staged_transaction_import(
            registered_user["id"] + 1,
            token
        ) is None

    response = client.post(
        "/transactions/import",
        data={
            "action": "confirm",
            "preview_token": token
        },
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Imported 1 transaction(s); skipped 0 duplicate(s)." in response.data
    with app.app_context():
        assert Transaction.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 1


def test_transaction_csv_import_rechecks_duplicates_at_confirmation(
    app,
    registered_user
):
    with app.app_context():
        category = create_category(
            user_id=registered_user["id"],
            name="Groceries",
            category_type="expense"
        )
        preview = preview_transaction_csv(
            registered_user["id"],
            (
                "Date,Type,Category,Description,Amount\n"
                f"{date.today().isoformat()},expense,Groceries,Market,125.00\n"
            ).encode("utf-8")
        )
        create_transaction(
            user_id=registered_user["id"],
            amount="125.00",
            transaction_type="expense",
            description="Market",
            category_id=category.id,
            transaction_date=date.today()
        )

        imported_count, duplicate_count = import_staged_transactions(
            registered_user["id"],
            preview["rows"]
        )

        assert imported_count == 0
        assert duplicate_count == 1
        assert Transaction.query.filter_by(
            user_id=registered_user["id"]
        ).count() == 1


def test_transaction_csv_import_requires_expected_headers(
    app,
    registered_user
):
    with app.app_context():
        with pytest.raises(ValueError, match="Date, Type, and Amount"):
            preview_transaction_csv(
                registered_user["id"],
                b"Payee,Debit\nMarket,25.00\n"
            )

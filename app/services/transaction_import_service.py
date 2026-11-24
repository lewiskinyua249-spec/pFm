import csv
import io
import json
import re
import secrets
import time
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from flask import current_app

from app import db
from app.models import Category, Transaction
from app.services.transaction_service import (
    validate_amount,
    validate_category,
    validate_description,
    validate_transaction_date,
    validate_transaction_type,
    convert_transaction_amount
)
from app.services.exchange_rate_service import (
    BASE_CURRENCY,
    RATE_LOOKBACK_DAYS,
    get_exchange_rates,
    validate_currency
)


MAX_IMPORT_ROWS = 1000
MAX_IMPORT_BYTES = 2 * 1024 * 1024
STAGED_IMPORT_TTL_SECONDS = 60 * 60
STAGE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32}$")
REQUIRED_HEADERS = {"date", "type", "amount"}
HEADER_ALIASES = {
    "date": {"date", "transaction date", "posted date"},
    "type": {"type", "transaction type"},
    "category": {"category"},
    "description": {"description", "memo", "payee", "details"},
    "amount": {"amount", "original amount", "value"},
    "currency": {"currency", "currency code"},
    "base_amount": {"amount (kes)", "base amount (kes)"},
    "exchange_rate": {"exchange rate"},
    "exchange_rate_date": {"exchange rate date", "rate date"}
}


def _normalize_header(value):
    return " ".join((value or "").strip().casefold().replace("_", " ").split())


def _normalize_description(value):
    return " ".join((value or "").split()).casefold()


def _parse_import_amount(value):
    amount_text = (value or "").strip()
    amount_text = re.sub(r"^[A-Z]{3}\s*", "", amount_text, flags=re.IGNORECASE)
    if "," in amount_text:
        if not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", amount_text):
            raise ValueError("Enter a valid transaction amount.")
        amount_text = amount_text.replace(",", "")
    return validate_amount(amount_text)


def _get_import_amount_details(
    original_amount,
    currency,
    transaction_date,
    raw_base_amount,
    raw_exchange_rate,
    raw_exchange_rate_date,
    rate_cache
):
    provided_metadata = (
        raw_base_amount,
        raw_exchange_rate,
        raw_exchange_rate_date
    )
    if any(value for value in provided_metadata) and not all(
        value for value in provided_metadata
    ):
        raise ValueError(
            "CSV conversion columns must include Amount (KES), "
            "Exchange Rate, and Exchange Rate Date together."
        )

    if all(value for value in provided_metadata):
        base_amount = _parse_import_amount(raw_base_amount)
        try:
            exchange_rate = Decimal(raw_exchange_rate)
            exchange_rate_date = validate_transaction_date(
                raw_exchange_rate_date
            )
        except (InvalidOperation, TypeError) as error:
            raise ValueError("Enter valid exchange rate details.") from error

        if (
            not exchange_rate.is_finite()
            or exchange_rate <= 0
            or exchange_rate_date > transaction_date
        ):
            raise ValueError("Enter valid exchange rate details.")
        if currency == BASE_CURRENCY and (
            exchange_rate != Decimal("1")
            or base_amount != original_amount
        ):
            raise ValueError("KES import amounts must use a rate of 1.")

        expected_amount = (
            original_amount * exchange_rate
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if expected_amount != base_amount:
            raise ValueError(
                "CSV base amount does not match its original amount and rate."
            )
        return base_amount, exchange_rate, exchange_rate_date

    if currency == BASE_CURRENCY:
        base_amount, _, exchange_rate, exchange_rate_date = (
            convert_transaction_amount(
                original_amount,
                currency,
                transaction_date
            )
        )
        return base_amount, exchange_rate, exchange_rate_date

    cache_key = (
        currency,
        transaction_date.year,
        transaction_date.month
    )
    if cache_key not in rate_cache:
        month_start = date(transaction_date.year, transaction_date.month, 1)
        month_end = date(
            transaction_date.year,
            transaction_date.month,
            monthrange(transaction_date.year, transaction_date.month)[1]
        )
        lookup_end = min(month_end, date.today())
        rate_cache[cache_key] = get_exchange_rates(
            currency,
            BASE_CURRENCY,
            month_start - timedelta(days=RATE_LOOKBACK_DAYS),
            lookup_end
        )

    for exchange_rate_date, exchange_rate in reversed(rate_cache[cache_key]):
        if exchange_rate_date <= transaction_date:
            base_amount = (original_amount * exchange_rate).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )
            validate_amount(base_amount)
            return base_amount, exchange_rate, exchange_rate_date

    raise ValueError(
        "No exchange rate is available for that transaction date."
    )


def _transaction_fingerprint(row):
    return (
        row["date"],
        row["type"],
        Decimal(str(row["amount"])),
        _normalize_description(row.get("description")),
        row.get("category_id")
    )


def _existing_fingerprints(user_id, rows):
    if not rows:
        return set()

    start_date = min(row["date"] for row in rows)
    end_date = max(row["date"] for row in rows)
    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).all()

    return {
        _transaction_fingerprint({
            "date": transaction.date,
            "type": transaction.type,
            "amount": transaction.amount,
            "description": transaction.description,
            "category_id": transaction.category_id
        })
        for transaction in transactions
    }


def preview_transaction_csv(user_id, content):
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("CSV file must be 2 MB or smaller.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must use UTF-8 encoding.") from error

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise ValueError("CSV file is empty or missing its header row.")

    mapped_headers = {}
    for header in reader.fieldnames:
        normalized = _normalize_header(header)
        matches = [
            field for field, aliases in HEADER_ALIASES.items()
            if normalized in aliases
        ]
        if matches:
            field = matches[0]
            if field in mapped_headers:
                raise ValueError(f"CSV contains more than one {field} column.")
            mapped_headers[field] = header

    missing_headers = REQUIRED_HEADERS - mapped_headers.keys()
    if missing_headers:
        raise ValueError(
            "CSV must include Date, Type, and Amount columns."
        )

    categories = {
        (category.name.strip().casefold(), category.type): category.id
        for category in Category.query.filter_by(user_id=user_id).all()
    }

    rows = []
    rate_cache = {}
    try:
        for row_number, raw_row in enumerate(reader, start=2):
            if row_number > MAX_IMPORT_ROWS + 1:
                raise ValueError(
                    f"CSV cannot contain more than {MAX_IMPORT_ROWS} transactions."
                )
            if not any((value or "").strip() for value in raw_row.values()):
                continue

            errors = []
            if None in raw_row:
                errors.append("Row has more values than the header.")

            raw_date = (raw_row.get(mapped_headers["date"]) or "").strip()
            raw_type = (raw_row.get(mapped_headers["type"]) or "").strip()
            raw_amount = (raw_row.get(mapped_headers["amount"]) or "").strip()
            raw_description = (
                raw_row.get(mapped_headers.get("description", "")) or ""
            ).strip()
            raw_category = (
                raw_row.get(mapped_headers.get("category", "")) or ""
            ).strip()

            parsed = {
                "row_number": row_number,
                "date": None,
                "type": None,
                "amount": None,
                "original_amount": None,
                "currency": "KES",
                "exchange_rate": None,
                "exchange_rate_date": None,
                "description": raw_description,
                "category_id": None,
                "category": raw_category,
                "status": "invalid",
                "errors": errors
            }

            try:
                if not raw_date:
                    raise ValueError("Date is required.")
                parsed["date"] = validate_transaction_date(raw_date)
            except ValueError as error:
                errors.append(str(error))

            try:
                parsed["type"] = validate_transaction_type(raw_type)
            except ValueError as error:
                errors.append(str(error))

            try:
                parsed["original_amount"] = _parse_import_amount(raw_amount)
            except ValueError as error:
                errors.append(str(error))

            try:
                parsed["currency"] = validate_currency(
                    raw_row.get(mapped_headers.get("currency", "")) or "KES"
                )
                if parsed["original_amount"] is not None and parsed["date"]:
                    transaction_date = validate_transaction_date(
                        parsed["date"]
                    )
                    (
                        parsed["amount"],
                        parsed["exchange_rate"],
                        parsed["exchange_rate_date"]
                    ) = _get_import_amount_details(
                        parsed["original_amount"],
                        parsed["currency"],
                        transaction_date,
                        (
                            raw_row.get(mapped_headers.get("base_amount", ""))
                            or ""
                        ).strip(),
                        (
                            raw_row.get(mapped_headers.get("exchange_rate", ""))
                            or ""
                        ).strip(),
                        (
                            raw_row.get(
                                mapped_headers.get("exchange_rate_date", "")
                            ) or ""
                        ).strip(),
                        rate_cache
                    )
            except ValueError as error:
                errors.append(str(error))

            try:
                parsed["description"] = validate_description(raw_description)
            except ValueError as error:
                errors.append(str(error))

            if parsed["type"] and raw_category:
                category_id = categories.get(
                    (raw_category.casefold(), parsed["type"])
                )
                if category_id is None:
                    errors.append(
                        f"Category '{raw_category}' does not match a "
                        f"{parsed['type']} category in your account."
                    )
                else:
                    parsed["category_id"] = category_id

            if parsed["date"] is not None:
                parsed["date"] = parsed["date"].isoformat()
            if parsed["original_amount"] is not None:
                parsed["original_amount_display"] = (
                    f"{parsed['original_amount']:,.2f}"
                )
                parsed["original_amount"] = str(parsed["original_amount"])
            if parsed["amount"] is not None:
                parsed["amount_display"] = f"{parsed['amount']:,.2f}"
                parsed["amount"] = str(parsed["amount"])
            if parsed["exchange_rate"] is not None:
                parsed["exchange_rate"] = str(parsed["exchange_rate"])
            if parsed["exchange_rate_date"] is not None:
                parsed["exchange_rate_date"] = (
                    parsed["exchange_rate_date"].isoformat()
                )

            if not errors:
                parsed["status"] = "ready"

            rows.append(parsed)

    except csv.Error as error:
        raise ValueError("CSV could not be read. Check its formatting.") from error

    if not rows:
        raise ValueError("CSV contains no transaction rows.")

    valid_rows = [
        row for row in rows
        if row["status"] == "ready"
    ]
    fingerprints = _existing_fingerprints(
        user_id,
        [
            {
                **row,
                "date": date.fromisoformat(row["date"])
            }
            for row in valid_rows
        ]
    )

    for row in valid_rows:
        fingerprint = _transaction_fingerprint({
            **row,
            "date": date.fromisoformat(row["date"])
        })
        if fingerprint in fingerprints:
            row["status"] = "duplicate"
            row["errors"] = ["This transaction is already in your ledger."]
        else:
            fingerprints.add(fingerprint)
            row["status"] = "ready"

    return {
        "rows": rows,
        "ready_count": sum(row["status"] == "ready" for row in rows),
        "duplicate_count": sum(row["status"] == "duplicate" for row in rows),
        "invalid_count": sum(row["status"] == "invalid" for row in rows)
    }


def import_staged_transactions(user_id, rows):
    prepared_rows = []
    for row in rows:
        if row.get("status") != "ready":
            continue

        transaction_type = validate_transaction_type(row.get("type"))
        amount = validate_amount(row.get("amount"))
        original_amount = validate_amount(
            row.get("original_amount", row.get("amount"))
        )
        currency = validate_currency(row.get("currency", "KES"))
        exchange_rate = Decimal(str(row.get("exchange_rate") or "1"))
        if not exchange_rate.is_finite() or exchange_rate <= 0:
            raise ValueError("Enter valid exchange rate details.")
        transaction_date = validate_transaction_date(row.get("date"))
        exchange_rate_date = validate_transaction_date(
            row.get("exchange_rate_date") or transaction_date
        )
        if exchange_rate_date > transaction_date:
            raise ValueError("Enter valid exchange rate details.")
        description = validate_description(row.get("description"))
        category_id = validate_category(
            user_id,
            row.get("category_id"),
            transaction_type
        )
        prepared_rows.append({
            "date": transaction_date,
            "type": transaction_type,
            "amount": amount,
            "original_amount": original_amount,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "exchange_rate_date": exchange_rate_date,
            "description": description,
            "category_id": category_id
        })

    existing = _existing_fingerprints(user_id, prepared_rows)
    seen = set(existing)
    transactions = []
    duplicate_count = 0

    for row in prepared_rows:
        fingerprint = _transaction_fingerprint(row)
        if fingerprint in seen:
            duplicate_count += 1
            continue
        seen.add(fingerprint)
        transactions.append(Transaction(
            user_id=user_id,
            date=row["date"],
            type=row["type"],
            amount=row["amount"],
            original_amount=row["original_amount"],
            currency=row["currency"],
            exchange_rate=row["exchange_rate"],
            exchange_rate_date=row["exchange_rate_date"],
            description=row["description"],
            category_id=row["category_id"]
        ))

    try:
        db.session.add_all(transactions)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return len(transactions), duplicate_count


def _staging_directory():
    configured_directory = current_app.config.get(
        "TRANSACTION_IMPORT_STAGING_DIR"
    )
    if configured_directory:
        directory = Path(configured_directory)
    else:
        directory = Path(current_app.instance_path) / "transaction_imports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _stage_path(token):
    if not isinstance(token, str) or not STAGE_TOKEN_PATTERN.fullmatch(token):
        return None
    return _staging_directory() / f"{token}.json"


def _remove_expired_stages(directory, now):
    for path in directory.glob("*.json"):
        try:
            if now - path.stat().st_mtime > STAGED_IMPORT_TTL_SECONDS:
                path.unlink()
        except FileNotFoundError:
            continue


def stage_transaction_import(user_id, preview):
    directory = _staging_directory()
    now = int(time.time())
    _remove_expired_stages(directory, now)
    token = secrets.token_urlsafe(24)
    payload = {
        "user_id": user_id,
        "created_at": now,
        "preview": preview
    }
    path = _stage_path(token)
    with path.open("x", encoding="utf-8") as staged_file:
        json.dump(payload, staged_file)
    return token


def get_staged_transaction_import(user_id, token):
    path = _stage_path(token)
    if path is None or not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as staged_file:
            payload = json.load(staged_file)
        if payload.get("user_id") != user_id:
            return None
        if int(time.time()) - payload.get("created_at", 0) > STAGED_IMPORT_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        preview = payload.get("preview")
        if not isinstance(preview, dict) or not isinstance(preview.get("rows"), list):
            path.unlink(missing_ok=True)
            return None
        return preview
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None


def delete_staged_transaction_import(token):
    path = _stage_path(token)
    if path is not None:
        path.unlink(missing_ok=True)

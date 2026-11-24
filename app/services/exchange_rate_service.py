import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


BASE_CURRENCY = "KES"
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
RATE_LOOKBACK_DAYS = 7
REQUEST_TIMEOUT_SECONDS = 5

SUPPORTED_CURRENCIES = (
    ("KES", "Kenyan Shilling"),
    ("USD", "US Dollar"),
    ("EUR", "Euro"),
    ("GBP", "British Pound"),
    ("UGX", "Ugandan Shilling"),
    ("TZS", "Tanzanian Shilling"),
    ("RWF", "Rwandan Franc"),
    ("ZAR", "South African Rand"),
    ("NGN", "Nigerian Naira"),
    ("GHS", "Ghanaian Cedi"),
    ("AED", "UAE Dirham"),
    ("CAD", "Canadian Dollar"),
    ("AUD", "Australian Dollar"),
    ("JPY", "Japanese Yen"),
    ("CHF", "Swiss Franc"),
    ("CNY", "Chinese Yuan"),
    ("INR", "Indian Rupee")
)

SUPPORTED_CURRENCY_CODES = {
    code for code, _ in SUPPORTED_CURRENCIES
}


def validate_currency(currency):
    currency = str(currency or "").strip().upper()
    if currency not in SUPPORTED_CURRENCY_CODES:
        raise ValueError("Select a supported currency.")
    return currency


def get_exchange_rates(base_currency, quote_currency, start_date, end_date):
    """Fetch available rates for a date range in one provider request."""
    base_currency = validate_currency(base_currency)
    quote_currency = validate_currency(quote_currency)

    if start_date > end_date:
        raise ValueError("Exchange rate start date cannot follow its end date.")

    if base_currency == quote_currency:
        return [(end_date, Decimal("1"))]

    params = urlencode({
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "base": base_currency,
        "quotes": quote_currency
    })
    request_url = f"{FRANKFURTER_URL}?{params}"

    try:
        with urlopen(
            request_url,
            timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            results = json.load(response)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError(
            "Exchange rates are temporarily unavailable. "
            "Please try again."
        ) from error

    if not isinstance(results, list):
        raise ValueError(
            "No exchange rate is available for that transaction date."
        )

    observations = []
    for result in results:
        try:
            observed_date = date.fromisoformat(result["date"])
            rate = Decimal(str(result["rates"][quote_currency]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue

        if rate.is_finite() and rate > 0:
            observations.append((observed_date, rate))

    if not observations:
        raise ValueError(
            "No exchange rate is available for that transaction date."
        )
    return observations


def get_exchange_rate(base_currency, quote_currency, rate_date):
    """Return the latest historical rate on or before the requested date."""
    start_date = rate_date - timedelta(days=RATE_LOOKBACK_DAYS)
    observations = get_exchange_rates(
        base_currency,
        quote_currency,
        start_date,
        rate_date
    )
    for observed_date, rate in reversed(observations):
        if observed_date <= rate_date:
            return rate, observed_date

    raise ValueError(
        "No exchange rate is available for that transaction date."
    )

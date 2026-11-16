
import os

from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:

    # Application security
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is missing. Check your .env file."
        )

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///finance.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "false").lower() == "true"
    )

    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Remember-me cookie security
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "false").lower() == "true"
    )
    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    # Request size limit
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # CSRF protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

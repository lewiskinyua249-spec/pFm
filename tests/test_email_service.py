from unittest.mock import patch

import pytest

from app import create_app
from app.services.email_service import (
    EmailDeliveryError,
    send_verification_email
)


@pytest.fixture
def app():
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key"
    })


def test_send_verification_email_requires_smtp_sender(app):
    app.config.update({
        "MAIL_SERVER": "",
        "MAIL_DEFAULT_SENDER": "",
        "MAIL_USERNAME": "",
        "MAIL_PASSWORD": ""
    })

    with app.app_context():
        with pytest.raises(EmailDeliveryError, match="not configured"):
            send_verification_email(
                "person@example.com",
                "123456",
                "https://example.com/verify"
            )


def test_send_verification_email_uses_gmail_starttls(app):
    app.config.update({
        "MAIL_SERVER": "smtp.gmail.com",
        "MAIL_PORT": 587,
        "MAIL_USE_TLS": True,
        "MAIL_USE_SSL": False,
        "MAIL_USERNAME": "sender@gmail.com",
        "MAIL_PASSWORD": "abcdefghijklmnop",
        "MAIL_DEFAULT_SENDER": "sender@gmail.com"
    })

    with app.app_context(), patch(
        "app.services.email_service.smtplib.SMTP"
    ) as smtp_factory:
        smtp = smtp_factory.return_value.__enter__.return_value

        send_verification_email(
            "person@example.com",
            "123456",
            "https://example.com/verify/token"
        )

    smtp_factory.assert_called_once_with(
        "smtp.gmail.com",
        587,
        timeout=10
    )
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with(
        "sender@gmail.com",
        "abcdefghijklmnop"
    )
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "person@example.com"
    assert "123456" in message.get_content()
    assert "https://example.com/verify/token" in message.get_content()


def test_gmail_app_password_spaces_are_removed(app):
    app.config.update({
        "MAIL_SERVER": "smtp.gmail.com",
        "MAIL_PORT": 587,
        "MAIL_USE_TLS": True,
        "MAIL_USE_SSL": False,
        "MAIL_USERNAME": "sender@gmail.com",
        "MAIL_PASSWORD": "abcd efgh ijkl mnop",
        "MAIL_DEFAULT_SENDER": "sender@gmail.com"
    })

    with app.app_context(), patch(
        "app.services.email_service.smtplib.SMTP"
    ) as smtp_factory:
        smtp = smtp_factory.return_value.__enter__.return_value

        send_verification_email(
            "person@example.com",
            "123456",
            "https://example.com/verify/token"
        )

    smtp.login.assert_called_once_with(
        "sender@gmail.com",
        "abcdefghijklmnop"
    )


def test_gmail_rejects_non_app_password_before_connecting(app):
    app.config.update({
        "MAIL_SERVER": "smtp.gmail.com",
        "MAIL_PORT": 587,
        "MAIL_USE_TLS": True,
        "MAIL_USE_SSL": False,
        "MAIL_USERNAME": "sender@gmail.com",
        "MAIL_PASSWORD": "short-password",
        "MAIL_DEFAULT_SENDER": "sender@gmail.com"
    })

    with app.app_context(), patch(
        "app.services.email_service.smtplib.SMTP"
    ) as smtp_factory:
        with pytest.raises(
            EmailDeliveryError,
            match="16-character Google App Password"
        ):
            send_verification_email(
                "person@example.com",
                "123456",
                "https://example.com/verify/token"
            )

    smtp_factory.assert_not_called()

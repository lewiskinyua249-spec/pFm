import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be delivered through configured SMTP."""


def send_verification_email(recipient, verification_code, verification_url):
    config = current_app.config
    server = config.get("MAIL_SERVER")
    sender = config.get("MAIL_DEFAULT_SENDER") or config.get("MAIL_USERNAME")
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    use_tls = config.get("MAIL_USE_TLS", True)
    use_ssl = config.get("MAIL_USE_SSL", False)
    is_gmail_smtp = server and server.lower() in {
        "smtp.gmail.com",
        "smtp.googlemail.com"
    }
    if password and is_gmail_smtp:
        password = "".join(password.split())

    if not server or not sender:
        raise EmailDeliveryError("SMTP email delivery is not configured.")
    if use_tls and use_ssl:
        raise EmailDeliveryError(
            "SMTP cannot use STARTTLS and implicit SSL at the same time."
        )
    if bool(username) != bool(password):
        raise EmailDeliveryError(
            "Both SMTP username and password must be configured."
        )
    if is_gmail_smtp and (not username or not password):
        raise EmailDeliveryError(
            "Gmail SMTP requires an email address and App Password."
        )
    if is_gmail_smtp and len(password) != 16:
        raise EmailDeliveryError(
            "Gmail SMTP requires a 16-character Google App Password."
        )

    message = EmailMessage()
    message["Subject"] = "Verify your Personal Finance Manager email"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "Use this verification code to activate your Personal Finance "
        "Manager account:\n\n"
        f"{verification_code}\n\n"
        "Enter the code at:\n"
        f"{verification_url}\n\n"
        "The code expires in 10 minutes. If you did not create this "
        "account, you can ignore this message."
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(
                server,
                config.get("MAIL_PORT", 587),
                timeout=10,
                context=ssl.create_default_context()
            ) as smtp:
                _send_message(smtp, message, username, password)
        else:
            with smtplib.SMTP(
                server,
                config.get("MAIL_PORT", 587),
                timeout=10
            ) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                _send_message(smtp, message, username, password)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError(
            "The SMTP server could not deliver the verification email."
        ) from error


def _send_message(smtp, message, username, password):
    if username and password:
        smtp.login(username, password)
    smtp.send_message(message)

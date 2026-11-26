
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email
from flask import (
    Blueprint,
    current_app,
    render_template,
    redirect,
    url_for,
    flash,
    request
)

from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User
from app.services.email_service import (
    EmailDeliveryError,
    send_verification_email
)


auth = Blueprint("auth", __name__)


def _normalize_email(email):
    try:
        return validate_email(
            email,
            check_deliverability=False
        ).normalized.lower()
    except EmailNotValidError:
        return None


def _hash_verification_code(user_id, code):
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(
        secret,
        f"{user_id}:{code}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _send_email_verification(user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    user.email_verification_code_hash = _hash_verification_code(
        user.id,
        code
    )
    user.email_verification_code_expires_at = now + timedelta(
        seconds=current_app.config["EMAIL_VERIFICATION_CODE_MAX_AGE"]
    )
    user.email_verification_attempts = 0
    db.session.commit()

    verification_url = url_for(
        "auth.verify_email",
        _external=True
    )
    try:
        send_verification_email(user.email, code, verification_url)
    except EmailDeliveryError:
        user.email_verification_code_hash = None
        user.email_verification_code_expires_at = None
        user.email_verification_attempts = 0
        db.session.commit()
        raise

    user.email_verification_sent_at = now
    db.session.commit()


@auth.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email_input = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email_input or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("auth.register"))

        if len(username) > 80:
            flash("Username cannot exceed 80 characters.", "error")
            return redirect(url_for("auth.register"))

        email = _normalize_email(email_input)
        if not email or len(email) > 120:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("auth.register"))

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            if not existing_email.email_verified:
                flash(
                    "This email already has a pending account. "
                    "Request a new verification email.",
                    "error"
                )
                return redirect(url_for("auth.verify_email"))

            flash("Email already registered.", "error")
            return redirect(url_for("auth.register"))

        user = User(
            username=username,
            email=email,
            email_verified=False
        )

        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()

        except IntegrityError:
            db.session.rollback()
            flash(
                "That username or email is already registered.",
                "error"
            )
            return redirect(url_for("auth.register"))

        except Exception:
            db.session.rollback()
            flash(
                "Registration failed. Please try again.",
                "error"
            )
            return redirect(url_for("auth.register"))

        try:
            _send_email_verification(user)
        except EmailDeliveryError:
            current_app.logger.exception(
                "Could not send verification email for user id %s.",
                user.id
            )
            flash(
                "Your account was created, but we could not send the "
                "verification email. Please try again later.",
                "error"
            )
        else:
            flash(
                "Registration successful. Enter the six-digit code sent to "
                "your email to verify your account.",
                "success"
            )

            return redirect(url_for("auth.verify_email"))

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.email_verified:
                flash(
                    "Enter the verification code sent to your email before "
                    "logging in.",
                    "error"
                )
                return redirect(url_for("auth.verify_email"))

            login_user(user)

            next_page = request.args.get("next")

            if next_page:
                parsed_url = urlparse(next_page)

                if (
                    parsed_url.scheme
                    or parsed_url.netloc
                    or not next_page.startswith("/")
                    or next_page.startswith("//")
                    or "\\" in next_page
                ):
                    next_page = None

            return redirect(
                next_page or url_for("main.dashboard")
            )

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@auth.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email_input = request.form.get("email", "").strip()
        email = _normalize_email(email_input)
        code = request.form.get("code", "").strip()

        if not email or len(email) > 120:
            flash("Enter a valid email address.", "error")
            return render_template(
                "verify_email.html",
                email=email_input
            )

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("The email or verification code is incorrect.", "error")
            return render_template(
                "verify_email.html",
                email=email_input
            )

        if user.email_verified:
            flash("This email address is already verified.", "info")
            return redirect(url_for("auth.login"))

        if not user.email_verification_code_hash:
            flash(
                "There is no active code for this account. Request a new one.",
                "error"
            )
            return redirect(url_for("auth.resend_verification"))

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = user.email_verification_code_expires_at
        if not expires_at or now >= expires_at:
            user.email_verification_code_hash = None
            user.email_verification_code_expires_at = None
            user.email_verification_attempts = 0
            db.session.commit()
            flash(
                "Your verification code has expired. Request a new one.",
                "error"
            )
            return redirect(url_for("auth.resend_verification"))

        max_attempts = current_app.config[
            "EMAIL_VERIFICATION_MAX_ATTEMPTS"
        ]
        if user.email_verification_attempts >= max_attempts:
            flash(
                "Too many incorrect codes. Request a new verification code.",
                "error"
            )
            return redirect(url_for("auth.resend_verification"))

        if not re.fullmatch(r"[0-9]{6}", code):
            matches = False
        else:
            matches = hmac.compare_digest(
                _hash_verification_code(user.id, code),
                user.email_verification_code_hash
            )

        if not matches:
            user.email_verification_attempts += 1
            db.session.commit()
            if user.email_verification_attempts >= max_attempts:
                flash(
                    "Too many incorrect codes. Request a new verification code.",
                    "error"
                )
                return redirect(url_for("auth.resend_verification"))

            flash("The email or verification code is incorrect.", "error")
            return render_template(
                "verify_email.html",
                email=email_input
            )

        user.email_verified = True
        user.email_verification_code_hash = None
        user.email_verification_code_expires_at = None
        user.email_verification_attempts = 0
        db.session.commit()
        flash("Email verified. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("verify_email.html", email="")


@auth.route("/verify-email/<_token>")
def redirect_legacy_verification_link(_token):
    flash(
        "Email verification now uses a six-digit code. Request a new code "
        "to continue.",
        "info"
    )
    return redirect(url_for("auth.resend_verification"))


@auth.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email_input = request.form.get("email", "").strip()
        email = _normalize_email(email_input)

        if not email or len(email) > 120:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("auth.resend_verification"))

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("No account was found for that email address.", "error")
            return redirect(url_for("auth.resend_verification"))

        if user.email_verified:
            flash(
                "This email address is already verified. You can log in.",
                "info"
            )
            return redirect(url_for("auth.login"))

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cooldown = current_app.config[
            "EMAIL_VERIFICATION_RESEND_COOLDOWN"
        ]
        if user.email_verification_sent_at:
            elapsed = (
                now - user.email_verification_sent_at
            ).total_seconds()
            if elapsed < cooldown:
                wait_seconds = int(cooldown - elapsed) + 1
                flash(
                    f"Please wait {wait_seconds} seconds before requesting "
                    "another verification email.",
                    "error"
                )
                return redirect(url_for("auth.resend_verification"))

        try:
            _send_email_verification(user)
        except EmailDeliveryError:
            current_app.logger.exception(
                "Could not resend verification email for user id %s.",
                user.id
            )
            flash(
                "We could not send the verification email. Please try again "
                "later.",
                "error"
            )
        else:
            flash("A new verification code has been sent.", "success")
            return redirect(url_for("auth.verify_email"))

        return redirect(url_for("auth.resend_verification"))

    return render_template("resend_verification.html")


@auth.route("/logout", methods=["POST"])
@login_required
def logout():

    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("auth.login"))

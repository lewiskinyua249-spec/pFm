
from urllib.parse import urlparse

from flask import (
    Blueprint,
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


auth = Blueprint("auth", __name__)


@auth.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("auth.register"))

        if len(username) > 80:
            flash("Username cannot exceed 80 characters.", "error")
            return redirect(url_for("auth.register"))

        if len(email) > 120 or "@" not in email:
            flash("Enter a valid email address.", "error")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("auth.register"))

        user = User(
            username=username,
            email=email
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

        flash("Registration successful. You can now log in.", "success")
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


@auth.route("/logout", methods=["POST"])
@login_required
def logout():

    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("auth.login"))

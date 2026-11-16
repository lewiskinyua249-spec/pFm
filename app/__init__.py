
from flask import Flask, jsonify

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from config import Config


# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():

    app = Flask(__name__)

    # Load application configuration
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Login configuration
    login_manager.login_view = "auth.login"
    login_manager.login_message = (
        "Please log in to access this page."
    )
    login_manager.login_message_category = "error"

    # Session protection
    login_manager.session_protection = "strong"

    # Import models
    from app import models
    from app.models import User

    # Load authenticated users
    @login_manager.user_loader
    def load_user(user_id):

        try:
            user_id = int(user_id)

        except (ValueError, TypeError):
            return None

        return db.session.get(User, user_id)

    # Register authentication routes
    from app.routes.auth import auth
    app.register_blueprint(auth)

    # Register main application routes
    from app.routes.main import main
    app.register_blueprint(main)

    # Health check
    @app.route("/health")
    def health():

        return jsonify({
            "status": "healthy",
            "application": "Personal Finance Manager"
        }), 200

    return app

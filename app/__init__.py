from pathlib import Path
import hmac
import secrets

from flask import Flask, abort, request, session

from config import Config
from .extensions import db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @app.context_processor
    def csrf_helpers():
        def csrf_token():
            token = session.get("csrf_token")
            if token is None:
                token = secrets.token_urlsafe(32)
                session["csrf_token"] = token
            return token
        return {"csrf_token": csrf_token}

    @app.before_request
    def csrf_protect():
        if not app.config.get("CSRF_PROTECT", True) or request.method != "POST":
            return None
        if request.endpoint == "mojapos_payments.mojapos_callback":
            return None
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="Invalid or missing form token.")
        return None

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .routes import bp
    app.register_blueprint(bp)

    from .billing import bp as billing_bp
    app.register_blueprint(billing_bp)

    from .payment_gateway import build_gateway
    build_gateway().init_app(app)

    return app

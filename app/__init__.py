from pathlib import Path
from datetime import datetime, timezone
import hmac
import secrets

from flask import Flask, abort, request, send_from_directory, session

from config import Config
from .extensions import db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    from .payment_logging import configure_payment_logging
    configure_payment_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @app.get("/manifest.webmanifest")
    def web_manifest():
        return send_from_directory(
            app.static_folder, "manifest.webmanifest",
            mimetype="application/manifest+json",
        )

    @app.get("/service-worker.js")
    def service_worker():
        response = send_from_directory(
            app.static_folder, "service-worker.js",
            mimetype="application/javascript",
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.context_processor
    def csrf_helpers():
        def csrf_token():
            token = session.get("csrf_token")
            if token is None:
                token = secrets.token_urlsafe(32)
                session["csrf_token"] = token
            return token
        return {"csrf_token": csrf_token, "current_year": datetime.now(timezone.utc).year}

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

    @app.after_request
    def audit_payment_callback(response):
        if request.endpoint == 'mojapos_payments.mojapos_callback':
            from .payment_logging import payment_event
            payment_event('callback_http', http_status=response.status_code)
        return response

    return app

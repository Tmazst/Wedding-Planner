from pathlib import Path
from datetime import datetime, timezone
import hmac
import secrets
import shutil
from decimal import Decimal

from flask import Flask, abort, render_template, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from .extensions import db, login_manager, migrate, socketio


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    if not app.config.get("TESTING") and app.config["SECRET_KEY"] == "dev-change-me":
        raise RuntimeError("Set a strong SECRET_KEY before starting UMSHADO.")

    legacy_photos = app.config.get("LEGACY_WEDDING_PHOTO_FOLDER")
    private_photos = app.config.get("WEDDING_PHOTO_FOLDER")
    if legacy_photos and private_photos:
        legacy_photos = Path(legacy_photos)
        private_photos = Path(private_photos)
        if legacy_photos.exists():
            for old_file in legacy_photos.rglob("*"):
                if not old_file.is_file() or old_file.name == ".gitkeep":
                    continue
                destination = private_photos / old_file.relative_to(legacy_photos)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    old_file.unlink()
                else:
                    shutil.move(str(old_file), str(destination))

    css_path = Path(app.static_folder) / "css" / "app.css"
    app.config["APP_CSS_VERSION"] = (
        str(int(css_path.stat().st_mtime)) if css_path.exists() else "1"
    )

    @app.template_filter("moneyfmt")
    def moneyfmt(value, places=2):
        return f"{Decimal(value or 0):,.{places}f}"
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    from .payment_logging import configure_payment_logging
    configure_payment_logging(app)

    from .security_logging import configure_security_logging
    configure_security_logging(app)

    from .analytics import configure_request_analytics
    configure_request_analytics(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(
        app,
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS"),
    )

    from .admin import record_session_visit
    app.before_request(record_session_visit)

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
        return {
            "csrf_token": csrf_token,
            "current_year": datetime.now(timezone.utc).year,
            "app_css_version": app.config["APP_CSS_VERSION"],
            "vendor_directory_enabled": (
                app.config.get("VENDOR_FEATURE_ENABLED", False)
                and app.config.get("VENDOR_DIRECTORY_ENABLED", False)
            ),
        }

    @app.before_request
    def csrf_protect():
        if not app.config.get("CSRF_PROTECT", True) or request.method != "POST":
            return None
        if request.endpoint in {"mojapos_payments.mojapos_callback", "shared_accounts.lookup"}:
            return None
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="Invalid or missing form token.")
        return None

    @app.errorhandler(400)
    def bad_request(error):
        if error.description == "Invalid or missing form token.":
            return render_template("csrf_expired.html"), 400
        return error

    @app.after_request
    def apply_browser_security(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data:; connect-src 'self' https: wss:; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user if user is not None and user.deleted_at is None else None

    from .routes import bp
    app.register_blueprint(bp)

    from . import realtime
    realtime.register_realtime_handlers()

    from .billing import bp as billing_bp
    app.register_blueprint(billing_bp)

    from .admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    from .assistant import bp as assistant_bp
    app.register_blueprint(assistant_bp)

    from .advanced import bp as advanced_bp
    app.register_blueprint(advanced_bp)

    from .shared_vendors import bp as shared_vendors_bp
    app.register_blueprint(shared_vendors_bp)

    from .shared_accounts import bp as shared_accounts_bp
    app.register_blueprint(shared_accounts_bp)

    from .vendor_routing import route_vendor_accounts
    app.before_request(route_vendor_accounts)

    from .shared_login import bp as shared_login_bp
    app.register_blueprint(shared_login_bp)

    from .payment_gateway import build_gateway
    build_gateway().init_app(app)

    from .retention import register_retention_command
    register_retention_command(app)

    @app.after_request
    def audit_payment_callback(response):
        if request.endpoint == 'mojapos_payments.mojapos_callback':
            from .payment_logging import payment_event
            payment_event('callback_http', http_status=response.status_code)
        return response

    return app

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")

    # A dedicated cookie name prevents legacy/duplicate Flask cookies from
    # trapping installed Chrome PWAs in an authentication loop.
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "umshado_session_v2")
    SESSION_COOKIE_DOMAIN = None
    SESSION_COOKIE_PATH = "/"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'wedding_planner.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FREE_BUDGET_ITEM_LIMIT = int(os.getenv("FREE_BUDGET_ITEM_LIMIT", "4"))
    OWNER_PLAN_PRICE = os.getenv("OWNER_PLAN_PRICE", "40.00")
    STAKEHOLDER_PRICE = os.getenv("STAKEHOLDER_PRICE", "30.00")
    PAYMENT_CURRENCY = os.getenv("MOJAPOS_CURRENCY", "SZL")
    MOJAPOS_MOCK_AUTO_COMPLETE = os.getenv(
        "MOJAPOS_MOCK_AUTO_COMPLETE", "false"
    ).lower() in {"1", "true", "yes", "on"}
    CSRF_PROTECT = True

    # Lightweight request diagnostics are stored in rotating files, not SQLite.
    ANALYTICS_ENABLED = os.getenv("ANALYTICS_ENABLED", "true").lower() in {
        "1", "true", "yes", "on"
    }
    ANALYTICS_LOG_PATH = os.getenv("ANALYTICS_LOG_PATH") or None
    ANALYTICS_LOG_MAX_BYTES = int(os.getenv("ANALYTICS_LOG_MAX_BYTES", str(2 * 1024 * 1024)))
    ANALYTICS_LOG_BACKUP_COUNT = int(os.getenv("ANALYTICS_LOG_BACKUP_COUNT", "3"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    WEDDING_PHOTO_FOLDER = BASE_DIR / "app" / "static" / "uploads" / "weddings"
    # Set to redis://127.0.0.1:6379/0 if realtime events must cross processes.
    SOCKETIO_MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE") or None
    SOCKETIO_CORS_ALLOWED_ORIGINS = None

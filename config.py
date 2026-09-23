import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")

    # A dedicated cookie name prevents legacy/duplicate Flask cookies from
    # trapping installed Chrome PWAs in an authentication loop.
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "umshado_session_v2")
    SESSION_COOKIE_DOMAIN = None
    SESSION_COOKIE_PATH = "/"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'wedding_planner.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FREE_BUDGET_ITEM_LIMIT = int(os.getenv("FREE_BUDGET_ITEM_LIMIT", "4"))
    OWNER_PLAN_PRICE = os.getenv("OWNER_PLAN_PRICE", "60.00")
    STAKEHOLDER_PRICE = os.getenv("STAKEHOLDER_PRICE", "30.00")

    # Advanced is deliberately feature-flagged so the code can be deployed
    # before the programme/invitation designers are opened to customers.
    ADVANCED_PLAN_ENABLED = env_bool("ADVANCED_PLAN_ENABLED", False)
    ADVANCED_PLAN_PRICE = os.getenv("ADVANCED_PLAN_PRICE", "250.00")
    ADVANCED_PROGRAMME_ENABLED = env_bool("ADVANCED_PROGRAMME_ENABLED", True)
    ADVANCED_INVITATION_CARD_ENABLED = env_bool("ADVANCED_INVITATION_CARD_ENABLED", True)

    # Shared vendor directory. Manual quotation entry remains independent of
    # these switches and must continue working even when integration is off.
    VENDOR_FEATURE_ENABLED = env_bool("VENDOR_FEATURE_ENABLED", False)
    VENDOR_DIRECTORY_ENABLED = env_bool("VENDOR_DIRECTORY_ENABLED", False)
    VENDOR_QUOTATION_INTEGRATION_ENABLED = env_bool(
        "VENDOR_QUOTATION_INTEGRATION_ENABLED", False
    )
    VENDOR_ACCOUNT_INTEGRATION_ENABLED = env_bool(
        "VENDOR_ACCOUNT_INTEGRATION_ENABLED", False
    )
    VENDOR_REMOTE_SIGNUP_ENABLED = env_bool("VENDOR_REMOTE_SIGNUP_ENABLED", False)
    VENDOR_API_BASE_URL = os.getenv("VENDOR_API_BASE_URL", "").rstrip("/")
    VENDOR_API_KEY = os.getenv("VENDOR_API_KEY") or None
    VENDOR_API_TIMEOUT_SECONDS = float(os.getenv("VENDOR_API_TIMEOUT_SECONDS", "5"))
    VENDOR_PORTAL_LOGIN_URL = os.getenv("VENDOR_PORTAL_LOGIN_URL", "").strip()
    VENDOR_PORTAL_REGISTER_URL = os.getenv("VENDOR_PORTAL_REGISTER_URL", "").strip()

    PAYMENT_CURRENCY = os.getenv("MOJAPOS_CURRENCY", "SZL")
    MOJAPOS_SUPPORTED_COUNTRIES = tuple(
        country.strip().upper()
        for country in os.getenv("MOJAPOS_SUPPORTED_COUNTRIES", "SZ").split(",")
        if country.strip()
    )
    MOJAPOS_MOCK_AUTO_COMPLETE = env_bool("MOJAPOS_MOCK_AUTO_COMPLETE", False)
    CSRF_PROTECT = True

    # Lightweight request diagnostics are stored in rotating files, not SQLite.
    ANALYTICS_ENABLED = env_bool("ANALYTICS_ENABLED", True)
    ANALYTICS_LOG_PATH = os.getenv("ANALYTICS_LOG_PATH") or None
    ANALYTICS_LOG_MAX_BYTES = int(os.getenv("ANALYTICS_LOG_MAX_BYTES", str(2 * 1024 * 1024)))
    ANALYTICS_LOG_BACKUP_COUNT = int(os.getenv("ANALYTICS_LOG_BACKUP_COUNT", "3"))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    WEDDING_PHOTO_FOLDER = BASE_DIR / "instance" / "uploads" / "weddings"
    LEGACY_WEDDING_PHOTO_FOLDER = BASE_DIR / "app" / "static" / "uploads" / "weddings"
    TERMS_VERSION = "2026-09-21"
    PRIVACY_VERSION = "2026-09-21"
    APP_VISIT_RETENTION_DAYS = int(os.getenv("APP_VISIT_RETENTION_DAYS", "90"))
    ANALYTICS_RETENTION_DAYS = int(os.getenv("ANALYTICS_RETENTION_DAYS", "90"))
    PAYMENT_LOG_RETENTION_DAYS = int(os.getenv("PAYMENT_LOG_RETENTION_DAYS", "90"))
    SECURITY_LOG_RETENTION_DAYS = int(os.getenv("SECURITY_LOG_RETENTION_DAYS", "90"))
    EXPIRED_INVITATION_RETENTION_DAYS = int(
        os.getenv("EXPIRED_INVITATION_RETENTION_DAYS", "90")
    )
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    ASSISTANT_ENABLED = env_bool("ASSISTANT_ENABLED", True)
    ASSISTANT_MAX_MESSAGE_LENGTH = int(os.getenv("ASSISTANT_MAX_MESSAGE_LENGTH", "1200"))
    ASSISTANT_REQUEST_LIMIT = int(os.getenv("ASSISTANT_REQUEST_LIMIT", "20"))
    # Set to redis://127.0.0.1:6379/0 if realtime events must cross processes.
    SOCKETIO_MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE") or None
    SOCKETIO_CORS_ALLOWED_ORIGINS = None

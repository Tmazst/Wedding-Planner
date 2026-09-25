import pytest

from app import create_app
from app.extensions import db
from app.models import User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CSRF_PROTECT = False
    SESSION_COOKIE_SECURE = False
    FREE_BUDGET_ITEM_LIMIT = 4
    OWNER_PLAN_PRICE = "60.00"
    STAKEHOLDER_PRICE = "30.00"
    PAYMENT_CURRENCY = "SZL"
    MOJAPOS_SUPPORTED_COUNTRIES = ("SZ",)
    MOJAPOS_MOCK_AUTO_COMPLETE = True
    ANALYTICS_ENABLED = False
    TERMS_VERSION = "2026-09-18"
    PRIVACY_VERSION = "2026-09-18"
    APP_VISIT_RETENTION_DAYS = 90
    ANALYTICS_RETENTION_DAYS = 90
    PAYMENT_LOG_RETENTION_DAYS = 90
    SECURITY_LOG_RETENTION_DAYS = 90
    EXPIRED_INVITATION_RETENTION_DAYS = 90
    SOCKETIO_MESSAGE_QUEUE = None
    OPENAI_API_KEY = None
    ASSISTANT_ENABLED = False
    VENDOR_FEATURE_ENABLED = True
    VENDOR_ACCOUNT_INTEGRATION_ENABLED = True
    VENDOR_API_BASE_URL = "https://events.example"
    VENDOR_API_KEY = "test-key"
    VENDOR_API_TIMEOUT_SECONDS = 5


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")
    application = create_app(TestConfig)
    application.config["WEDDING_PHOTO_FOLDER"] = tmp_path / "uploads" / "weddings"
    with application.app_context():
        db.create_all()
        vendor = User(
            name="Vendor",
            email="vendor@example.com",
            phone_number="+26876123456",
            phone_country="SZ",
            terms_version=application.config["TERMS_VERSION"],
            privacy_version=application.config["PRIVACY_VERSION"],
        )
        vendor.set_password("secret1")
        regular = User(
            name="Couple",
            email="couple@example.com",
            phone_number="+26876234567",
            phone_country="SZ",
            terms_version=application.config["TERMS_VERSION"],
            privacy_version=application.config["PRIVACY_VERSION"],
        )
        regular.set_password("secret1")
        db.session.add_all([vendor, regular])
        db.session.commit()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_vendor_login_routes_to_vendor_account(client, monkeypatch):
    monkeypatch.setattr(
        "app.shared_vendors.requests.post",
        lambda *args, **kwargs: FakeResponse({"exists": True, "is_vendor": True}),
    )
    login = client.post("/login", data={"email": "vendor@example.com", "password": "secret1"})
    assert login.status_code == 302
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"].endswith("/vendors/account")


def test_general_user_still_routes_to_wedding_setup(client, monkeypatch):
    monkeypatch.setattr(
        "app.shared_vendors.requests.post",
        lambda *args, **kwargs: FakeResponse({"exists": False, "is_vendor": False}),
    )
    login = client.post("/login", data={"email": "couple@example.com", "password": "secret1"})
    assert login.status_code == 302
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"].endswith("/wedding/setup")

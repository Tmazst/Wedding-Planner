import pytest
from itsdangerous import URLSafeTimedSerializer

from app import create_app
from app.extensions import db
from app.models import User
from app.shared_identity import SharedIdentity


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-app-secret"
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
    SHARED_LOGIN_HANDOFF_ENABLED = True
    SHARED_LOGIN_SECRET = "shared-login-test-secret"
    SHARED_LOGIN_MAX_AGE_SECONDS = 90
    UMCIMBY_SSO_RECEIVE_URL = "https://events.example/shared-login/from-umshado"
    VENDOR_FEATURE_ENABLED = True
    VENDOR_ACCOUNT_INTEGRATION_ENABLED = True
    VENDOR_REMOTE_SIGNUP_ENABLED = True
    VENDOR_API_BASE_URL = "https://events.example"
    VENDOR_API_KEY = "test-vendor-key"
    VENDOR_API_TIMEOUT_SECONDS = 5
    VENDOR_PORTAL_LOGIN_URL = "https://events.example/login"
    VENDOR_PORTAL_REGISTER_URL = "https://events.example/register"


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")
    application = create_app(TestConfig)
    application.config["WEDDING_PHOTO_FOLDER"] = tmp_path / "uploads" / "weddings"
    with application.app_context():
        db.create_all()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def token(app, *, source_user_id, email, phone):
    return URLSafeTimedSerializer(
        app.config["SHARED_LOGIN_SECRET"], salt="umcimby-to-umshado"
    ).dumps({
        "source_user_id": str(source_user_id),
        "email": email,
        "phone_number": phone,
        "name": "Planner",
        "source": "umcimby",
        "target": "umshado",
    })


def test_link_survives_remote_email_and_phone_change(app, client):
    with app.app_context():
        user = User(
            name="Planner",
            email="original@example.com",
            phone_number="+26876111111",
            phone_country="SZ",
        )
        user.set_password("secret1")
        db.session.add(user)
        db.session.commit()
        local_user_id = user.id

    first = token(
        app,
        source_user_id=77,
        email="original@example.com",
        phone="+26876111111",
    )
    response = client.get(f"/shared-login/from-umcimby?token={first}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")

    with app.app_context():
        link = db.session.scalar(db.select(SharedIdentity))
        assert link is not None
        assert link.user_id == local_user_id
        assert link.provider == "umcimby"
        assert link.provider_user_id == "77"

    second = token(
        app,
        source_user_id=77,
        email="changed@example.com",
        phone="+26876222222",
    )
    response = client.get(f"/shared-login/from-umcimby?token={second}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as session:
        assert session.get("_user_id") == str(local_user_id)
    with app.app_context():
        assert db.session.query(SharedIdentity).count() == 1

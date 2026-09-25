import pytest
from itsdangerous import URLSafeTimedSerializer

from app import create_app
from app.extensions import db
from app.models import User


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
    TERMS_VERSION = "2026-09-21"
    PRIVACY_VERSION = "2026-09-21"
    APP_VISIT_RETENTION_DAYS = 90
    ANALYTICS_RETENTION_DAYS = 90
    PAYMENT_LOG_RETENTION_DAYS = 90
    SECURITY_LOG_RETENTION_DAYS = 90
    EXPIRED_INVITATION_RETENTION_DAYS = 90
    SOCKETIO_MESSAGE_QUEUE = None
    OPENAI_API_KEY = None
    ASSISTANT_ENABLED = False
    VENDOR_FEATURE_ENABLED = False
    VENDOR_ACCOUNT_INTEGRATION_ENABLED = False
    SHARED_LOGIN_HANDOFF_ENABLED = True
    SHARED_LOGIN_SECRET = "shared-login-test-secret"
    SHARED_LOGIN_MAX_AGE_SECONDS = 90
    UMCIMBY_SSO_RECEIVE_URL = "https://events.example/shared-login/from-umshado"
    SHARED_ACCOUNT_DISCOVERY_ENABLED = True
    SHARED_ACCOUNT_API_KEY = "shared-account-test-key"
    SHARED_ACCOUNT_API_TIMEOUT_SECONDS = 5


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


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_shared_lookup_requires_server_key(app, client):
    with app.app_context():
        user = User(name="Existing", email="existing@example.com", phone_number="+26876123456", phone_country="SZ")
        user.set_password("secret1")
        db.session.add(user)
        db.session.commit()

    denied = client.post("/shared-accounts/api/lookup", json={"email": "existing@example.com"})
    assert denied.status_code == 401

    allowed = client.post(
        "/shared-accounts/api/lookup",
        json={"email": "existing@example.com"},
        headers={"X-Shared-Account-Key": "shared-account-test-key"},
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["exists"] is True


def test_register_detects_existing_umcimby_account(app, client, monkeypatch):
    monkeypatch.setattr(
        "app.shared_accounts.requests.post",
        lambda *args, **kwargs: FakeResponse({
            "exists": True,
            "email": "person@example.com",
            "account_type": "organizer",
        }),
    )
    response = client.post("/shared-accounts/register", data={
        "name": "Person",
        "email": "person@example.com",
        "phone_number": "76123456",
        "phone_country": "SZ",
        "password": "secret1",
        "accept_terms": "yes",
    })
    assert response.status_code == 409
    assert b"Continue with Umcimby" in response.data
    assert b"identity=person%40example.com" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(User).where(User.email == "person@example.com")) is None


def test_umcimby_handoff_can_provision_umshado_account(app, client):
    payload = {
        "email": "new@example.com",
        "phone_number": "+26876123456",
        "phone_country": "SZ",
        "name": "New User",
        "source": "umcimby",
        "target": "umshado",
        "account_type": "organizer",
        "provision": True,
    }
    token = URLSafeTimedSerializer(
        app.config["SHARED_LOGIN_SECRET"], salt="umcimby-to-umshado"
    ).dumps(payload)

    response = client.get(f"/shared-login/from-umcimby?token={token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/legal/accept")
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "new@example.com"))
        assert user is not None
        assert user.phone_country == "SZ"

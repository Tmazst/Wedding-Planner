import pytest
from itsdangerous import URLSafeTimedSerializer

from app import create_app
from app.extensions import db
from app.models import SharedLoginUse, User


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


def make_token(app, email="vendor@example.com", phone="76123456", **overrides):
    payload = {
        "email": email,
        "phone_number": phone,
        "name": "Vendor",
        "source": "umcimby",
        "target": "umshado",
    }
    payload.update(overrides)
    return URLSafeTimedSerializer(
        app.config["SHARED_LOGIN_SECRET"], salt="umcimby-to-umshado"
    ).dumps(payload)


def add_user(app, email="vendor@example.com", phone="76123456"):
    with app.app_context():
        user = User(name="Vendor", email=email, phone_number=phone, phone_country="SZ")
        user.set_password("secret1")
        db.session.add(user)
        db.session.commit()
        return user.id


def test_valid_handoff_logs_in_existing_user_once(app, client):
    user_id = add_user(app)
    token = make_token(app)

    first = client.get(f"/shared-login/from-umcimby?token={token}")
    assert first.status_code == 302
    assert first.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as session:
        assert session.get("_user_id") == str(user_id)
    with app.app_context():
        assert db.session.query(SharedLoginUse).count() == 1

    second = client.get(f"/shared-login/from-umcimby?token={token}")
    assert second.status_code == 302
    assert second.headers["Location"].endswith("/login")


def test_tampered_handoff_is_rejected(app, client):
    add_user(app)
    token = make_token(app)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    response = client.get(f"/shared-login/from-umcimby?token={tampered}", follow_redirects=True)
    assert b"shared login link is invalid" in response.data


def test_identity_conflict_is_rejected(app, client):
    add_user(app, email="one@example.com", phone="76111111")
    add_user(app, email="two@example.com", phone="76222222")
    token = make_token(app, email="one@example.com", phone="76222222")
    response = client.get(f"/shared-login/from-umcimby?token={token}", follow_redirects=True)
    assert b"conflicting email and phone records" in response.data


def test_missing_local_account_goes_to_registration(app, client):
    token = make_token(app)
    response = client.get(f"/shared-login/from-umcimby?token={token}")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/register")


def test_disabled_handoff_returns_404(app, client):
    app.config["SHARED_LOGIN_HANDOFF_ENABLED"] = False
    assert client.get("/shared-login/from-umcimby?token=x").status_code == 404


def test_expired_handoff_is_rejected(app, client):
    add_user(app)
    token = make_token(app)
    app.config["SHARED_LOGIN_MAX_AGE_SECONDS"] = -1
    response = client.get(f"/shared-login/from-umcimby?token={token}", follow_redirects=True)
    assert b"shared login link expired" in response.data


def test_register_page_offers_vendor_account(app, client):
    page = client.get("/register")
    assert page.status_code == 200
    assert b"Create wedding account" in page.data
    assert b"I am a vendor" in page.data
    assert b"/vendors/register-account" in page.data


def test_vendor_signup_creates_remote_and_local_account(app, client, monkeypatch):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("unexpected HTTP error")
        def json(self):
            return self._payload

    calls = []
    def fake_post(url, json, headers, timeout):
        calls.append((url, json))
        if url.endswith("/api/vendors/accounts/lookup"):
            return FakeResponse({"exists": False})
        if url.endswith("/api/vendors/accounts/register"):
            return FakeResponse({"created": True, "is_vendor": True})
        raise AssertionError(url)

    monkeypatch.setattr("app.shared_vendors.requests.post", fake_post)
    response = client.post("/vendors/register-account", data={
        "name": "New Vendor",
        "email": "newvendor@example.com",
        "phone_number": "76123456",
        "phone_country": "SZ",
        "password": "secret1",
        "accept_terms": "yes",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/shared-login/to-umcimby")
    assert len(calls) == 2
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "newvendor@example.com"))
        assert user is not None
        assert user.phone_number == "76123456"


def test_existing_umcimby_vendor_is_sent_to_umcimby_login(app, client, monkeypatch):
    class FakeResponse:
        status_code = 200
        def json(self):
            return {"exists": True, "is_vendor": True, "name": "Existing Vendor"}

    monkeypatch.setattr("app.shared_vendors.requests.post", lambda *args, **kwargs: FakeResponse())
    response = client.post("/vendors/register-account", data={
        "name": "Existing Vendor",
        "email": "vendor@example.com",
        "phone_number": "76123456",
        "phone_country": "SZ",
        "password": "secret1",
        "accept_terms": "yes",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "https://events.example/login"
    with app.app_context():
        assert db.session.scalar(db.select(User).where(User.email == "vendor@example.com")) is None

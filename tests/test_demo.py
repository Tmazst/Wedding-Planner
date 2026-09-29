from app import create_app
from app.extensions import db
from app.models import InvitationCardDesign, User, WeddingProgramme


class TestConfig:
    TESTING = True
    SECRET_KEY = "demo-test-secret"
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
    ADVANCED_PLAN_ENABLED = True
    ADVANCED_PROGRAMME_ENABLED = True
    ADVANCED_INVITATION_CARD_ENABLED = True
    ADVANCED_PLAN_PRICE = "250.00"
    DEMO_MODE_ENABLED = True
    DEMO_ACCOUNT_EMAIL = "demo@umshado.app"
    VENDOR_FEATURE_ENABLED = False
    VENDOR_DIRECTORY_ENABLED = False
    VENDOR_QUOTATION_INTEGRATION_ENABLED = False
    VENDOR_ACCOUNT_INTEGRATION_ENABLED = False
    VENDOR_REMOTE_SIGNUP_ENABLED = False
    SHARED_LOGIN_HANDOFF_ENABLED = False
    SHARED_ACCOUNT_DISCOVERY_ENABLED = False
    ASSISTANT_ENABLED = False
    SOCKETIO_MESSAGE_QUEUE = None
    SOCKETIO_CORS_ALLOWED_ORIGINS = None


def make_app(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")
    app = create_app(TestConfig)
    app.config["WEDDING_PHOTO_FOLDER"] = tmp_path / "uploads" / "weddings"
    app.config["LEGACY_WEDDING_PHOTO_FOLDER"] = tmp_path / "legacy" / "weddings"
    with app.app_context():
        db.create_all()
    return app


def test_seed_demo_creates_complete_advanced_wedding(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo"])
    assert result.exit_code == 0

    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "demo@umshado.app"))
        assert user is not None
        assert len(user.weddings) == 1
        wedding = user.weddings[0]
        assert wedding.title == "Sipho & Nomsa"
        assert wedding.plan_tier == "advanced"
        assert len(wedding.categories) == 8
        assert all(len(category.quotations) == 2 for category in wedding.categories)

        programme = db.session.scalar(db.select(WeddingProgramme).where(WeddingProgramme.wedding_id == wedding.id))
        assert programme is not None
        assert programme.is_published is True
        assert len(programme.items) == 12

        card = db.session.scalar(db.select(InvitationCardDesign).where(InvitationCardDesign.wedding_id == wedding.id))
        assert card is not None
        assert card.is_published is True


def test_demo_is_one_click_and_read_only(monkeypatch, tmp_path):
    app = make_app(monkeypatch, tmp_path)
    app.test_cli_runner().invoke(args=["seed-demo"])
    client = app.test_client()

    response = client.get("/demo", follow_redirects=True)
    assert response.status_code == 200
    assert b"Sipho &amp; Nomsa" in response.data or b"Sipho & Nomsa" in response.data
    assert b"Demo mode:" in response.data

    response = client.post("/wedding/setup", data={
        "partner_one": "Changed",
        "partner_two": "Demo",
        "budget_target": "1",
    })
    assert response.status_code == 302

    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "demo@umshado.app"))
        assert user.weddings[0].title == "Sipho & Nomsa"
        assert str(user.weddings[0].budget_target) == "95000.00"

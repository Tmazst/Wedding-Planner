import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import InvitationCardDesign, Payment, Wedding


class AdvancedPlanTestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CSRF_PROTECT = False
    SESSION_COOKIE_SECURE = False
    FREE_BUDGET_ITEM_LIMIT = 4
    OWNER_PLAN_PRICE = "60.00"
    STAKEHOLDER_PRICE = "30.00"
    ADVANCED_PLAN_ENABLED = True
    ADVANCED_PLAN_PRICE = "250.00"
    ADVANCED_PROGRAMME_ENABLED = True
    ADVANCED_INVITATION_CARD_ENABLED = True
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


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")
    application = create_app(AdvancedPlanTestConfig)
    application.config["WEDDING_PHOTO_FOLDER"] = tmp_path / "uploads" / "weddings"
    with application.app_context():
        db.create_all()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def create_owner_wedding(client):
    client.post("/register", data={
        "name": "Owner",
        "email": "owner@example.com",
        "phone_number": "76123456",
        "phone_country": "SZ",
        "password": "secret1",
        "accept_terms": "yes",
    })
    client.post("/wedding/setup", data={
        "partner_one": "Lindiwe",
        "partner_two": "Sibusiso",
        "budget_target": "80000",
        "location": "Manzini",
    })


def test_advanced_plan_is_advertised_as_e250(client):
    create_owner_wedding(client)
    page = client.get("/pricing")
    assert page.status_code == 200
    assert b"Advanced" in page.data
    assert b"E250" in page.data
    assert b"Wedding programme designer" in page.data
    assert b"Invitation card designer" in page.data
    assert b"advanced-premium" in page.data


def test_free_owner_can_pay_e250_and_unlock_all_advanced_tools(app, client):
    create_owner_wedding(client)

    paid = client.post(
        "/billing/upgrade/advanced",
        data={"payment_confirmed": "yes"},
        follow_redirects=True,
    )
    assert paid.status_code == 200
    assert b"Payment confirmed" in paid.data

    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        payment = db.session.scalar(
            select(Payment).where(Payment.kind == "owner_upgrade_advanced")
        )
        assert wedding.plan_tier == "advanced"
        assert str(payment.amount) == "250.00"
        assert payment.currency == "SZL"
        assert payment.status == "completed"

    advanced_home = client.get("/advanced")
    programme = client.get("/advanced/programme")
    invitation = client.get("/advanced/invitation-card")
    assert advanced_home.status_code == 200
    assert programme.status_code == 200
    assert invitation.status_code == 200
    assert b"Programme Creator" in programme.data
    assert b"Invitation Card Creator" in invitation.data


def test_standard_owner_pays_only_balance_to_reach_advanced(app, client):
    create_owner_wedding(client)

    client.post(
        "/billing/upgrade",
        data={"payment_confirmed": "yes"},
        follow_redirects=True,
    )
    with app.app_context():
        assert db.session.scalar(select(Wedding)).plan_tier == "standard"

    pricing = client.get("/pricing")
    assert b"Upgrade balance" in pricing.data
    assert b"E190" in pricing.data

    client.post(
        "/billing/upgrade/advanced",
        data={"payment_confirmed": "yes"},
        follow_redirects=True,
    )
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        advanced_payment = db.session.scalar(
            select(Payment).where(Payment.kind == "owner_upgrade_advanced")
        )
        assert wedding.plan_tier == "advanced"
        assert str(advanced_payment.amount) == "190.00"
        assert advanced_payment.status == "completed"


def test_invitation_designer_saves_and_renders_wedding_time(app, client):
    create_owner_wedding(client)
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        wedding.plan_tier = "advanced"
        db.session.commit()

    page = client.get("/advanced/invitation-card")
    assert b'name="event_time"' in page.data
    assert b'name="wedding_date"' not in page.data

    saved = client.post("/advanced/invitation-card/design", data={
        "template_key": "floral_elegant",
        "font_style": "elegant",
        "event_time": "14:30",
        "primary_color": "#7d1020",
        "accent_color": "#b88a3b",
        "show_profile_image": "yes",
        "message": "Please celebrate with us.",
    }, follow_redirects=True)
    assert saved.status_code == 200
    assert b"14:30" in saved.data
    with app.app_context():
        design = db.session.scalar(select(InvitationCardDesign))
        assert design.event_time == "14:30"
        assert db.session.scalar(select(Wedding)).wedding_date is None


def test_programme_mobile_preview_keeps_elegant_font_hooks(app, client):
    create_owner_wedding(client)
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        wedding.plan_tier = "advanced"
        db.session.commit()

    page = client.get("/advanced/programme")
    assert page.status_code == 200
    assert b"programme-preview-modal" in page.data
    css = client.get("/static/css/programme-floral-fix.css")
    js = client.get("/static/js/programme-preview.js")
    assert b"programme-preview-modal .font-elegant" in css.data
    assert b"document.fonts.load" in js.data

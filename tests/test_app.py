from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from app import create_app
from app.extensions import db, socketio
from app.models import AppVisit, ActivityEvent, BudgetCategory, Invitation, Payment, User, Wedding, WeddingMember


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CSRF_PROTECT = False
    FREE_BUDGET_ITEM_LIMIT = 4
    OWNER_PLAN_PRICE = "40.00"
    STAKEHOLDER_PRICE = "30.00"
    PAYMENT_CURRENCY = "SZL"
    MOJAPOS_MOCK_AUTO_COMPLETE = True
    ANALYTICS_ENABLED = False


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


def register(client, name, email, phone, invite_token=""):
    return client.post("/register", data={
        "name": name, "email": email, "phone_number": phone,
        "password": "secret1", "invite_token": invite_token,
    })


def create_owner_wedding(client):
    register(client, "Owner", "owner@example.com", "76123456")
    client.post("/wedding/setup", data={
        "partner_one": "Lindiwe", "partner_two": "Sibusiso",
        "budget_target": "80000", "location": "Manzini",
    })


def test_visit_tracking_counts_each_browser_session_once(app):
    first_browser = app.test_client()
    second_browser = app.test_client()

    first_browser.get("/login")
    first_browser.get("/login")
    second_browser.get("/login")

    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(AppVisit)) == 2


def test_admin_dashboard_is_private_and_shows_performance(app, client):
    register(client, "Admin", "admin@example.com", "76000001")
    assert client.get("/admin/").status_code == 403

    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "admin@example.com"))
        user.is_admin = True
        db.session.commit()

    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200
    assert b"App performance" in dashboard.data
    assert b"Registered users" in dashboard.data
    assert b"admin@example.com" in dashboard.data


def test_request_analytics_tracks_auth_outcomes_without_form_data(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")

    class AnalyticsConfig(TestConfig):
        ANALYTICS_ENABLED = True

    analytics_path = tmp_path / "analytics.log"
    AnalyticsConfig.ANALYTICS_LOG_PATH = str(analytics_path)
    application = create_app(AnalyticsConfig)
    with application.app_context():
        db.create_all()

    browser = application.test_client()
    mobile_chrome = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/153.0 Mobile Safari/537.36"
    }
    browser.get("/login", headers=mobile_chrome)
    browser.post(
        "/login",
        data={"email": "missing@example.com", "password": "never-log-this"},
        headers=mobile_chrome,
    )
    browser.post(
        "/register",
        data={
            "name": "Tester",
            "email": "tester@example.com",
            "phone_number": "76000009",
            "password": "private-password",
        },
        headers=mobile_chrome,
    )

    from app.analytics import build_analytics_summary

    summary = build_analytics_summary(application)
    assert summary["login_page_ok"] == 1
    assert summary["login_attempts"] == 1
    assert summary["login_rejected"] == 1
    assert summary["register_attempts"] == 1
    assert summary["register_success"] == 1
    assert summary["recent_events"][0]["device"] == "Mobile"
    assert summary["recent_events"][0]["browser"] == "Chrome"

    audit = analytics_path.read_text(encoding="utf-8")
    assert "missing@example.com" not in audit
    assert "tester@example.com" not in audit
    assert "never-log-this" not in audit
    assert "private-password" not in audit


def test_whatsapp_support_link_is_available_on_public_pages(client):
    page = client.get("/login")
    assert b"https://wa.me/26879651471" in page.data
    assert b"Contact UMSHADO support on WhatsApp" in page.data


def test_stale_login_form_recovers_without_disabling_csrf(monkeypatch, tmp_path):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")

    class ProtectedConfig(TestConfig):
        CSRF_PROTECT = True

    application = create_app(ProtectedConfig)
    browser = application.test_client()
    login_page = browser.get("/login")
    assert login_page.headers["Cache-Control"] == "private, no-store"
    with browser.session_transaction() as session:
        session["csrf_token"] = "new-session-token"
    expired = browser.post("/login", data={"csrf_token": "old-session-token", "email": "x@example.com", "password": "wrong"})
    assert expired.status_code == 400
    assert b"Form expired" in expired.data
    assert expired.headers["Cache-Control"] == "private, no-store"


def test_stale_other_form_has_friendly_error_and_no_store(monkeypatch):
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "true")

    class ProtectedConfig(TestConfig):
        CSRF_PROTECT = True

    application = create_app(ProtectedConfig)
    browser = application.test_client()
    response = browser.post("/logout", data={"csrf_token": "bad"})
    assert response.status_code == 400
    assert b"Form expired" in response.data
    assert response.headers["Cache-Control"] == "private, no-store"


def test_free_limit_and_budget_totals(app, client):
    create_owner_wedding(client)
    for number in range(4):
        response = client.post("/budget", data={
            "name": f"Item {number}", "planned_amount": "10000",
        })
        assert response.status_code == 302

    blocked = client.post("/budget", data={"name": "Fifth item", "planned_amount": "5000"})
    assert blocked.headers["Location"].endswith("/pricing")

    client.post("/budget/1/quotes", data={"vendor_name": "Tech Xolutions", "amount": "8500"})
    client.post("/quotes/1/select")
    budget = client.get("/budget")
    assert b"E8,500.00" in budget.data
    with app.app_context():
        assert len(db.session.scalar(select(Wedding)).categories) == 4


def test_unrestricted_test_owner_bypasses_plan_and_invitation_payments(app, client):
    create_owner_wedding(client)
    with app.app_context():
        owner = db.session.scalar(select(User).where(User.email == "owner@example.com"))
        owner.has_test_access = True
        db.session.commit()

    for number in range(5):
        response = client.post("/budget", data={
            "name": f"Unlimited item {number}", "planned_amount": "1000",
        })
        assert response.headers["Location"].endswith("/budget")

    invited = client.post("/team", data={
        "invitee_name": "Tester", "role": "partner", "payer": "owner",
    }, follow_redirects=True)
    assert b"Access fees are bypassed" in invited.data
    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(BudgetCategory)) == 5
        invitation = db.session.scalar(select(Invitation))
        assert invitation.status == "paid"
        assert db.session.scalar(select(Payment)) is None


def test_admin_and_super_admin_have_full_feature_access(app):
    with app.app_context():
        administrator = User(
            name="Administrator", email="admin@example.com", phone_number="26876000001",
            is_admin=True,
        )
        administrator.set_password("adminpass")
        super_admin = User(
            name="Super Admin", email="super@example.com", phone_number="26876000002",
            is_super_admin=True,
        )
        super_admin.set_password("superpass")
        db.session.add_all([administrator, super_admin])
        db.session.commit()
        assert administrator.has_full_feature_access
        assert super_admin.has_full_feature_access


def test_only_two_unrestricted_test_account_slots(app, monkeypatch):
    import super_admin_cli

    with app.app_context():
        actor = User(
            name="Super Admin", email="super@example.com", phone_number="26876000000",
            is_admin=True, is_super_admin=True,
        )
        actor.set_password("superpass")
        db.session.add(actor)
        db.session.commit()
        monkeypatch.setattr(super_admin_cli, "_authenticate_super_admin", lambda: actor)

        super_admin_cli.create_test_user(
            "Test One", "test1@example.com", "26876000001", "testpass1"
        )
        super_admin_cli.create_test_user(
            "Test Two", "test2@example.com", "26876000002", "testpass2"
        )
        with pytest.raises(super_admin_cli.SuperAdminError, match="slots are already in use"):
            super_admin_cli.create_test_user(
                "Test Three", "test3@example.com", "26876000003", "testpass3"
            )



def test_large_amounts_use_grouping_in_summaries(app, client):
    create_owner_wedding(client)
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        wedding.budget_target = 1250000
        db.session.commit()
    assert b"E1,250,000.00" in client.get("/dashboard").data
    assert b"E1,250,000.00" in client.get("/budget").data


def test_report_view_and_downloadable_pdf(app, client):
    create_owner_wedding(client)
    client.post("/budget", data={"name": "Photography", "planned_amount": "12000"})
    client.post("/budget/1/quotes", data={
        "vendor_name": "Lens Studio", "amount": "10500", "contact": "76123456",
        "notes": "Includes photography and a short highlights video.",
    })
    client.post("/quotes/1/select")

    report = client.get("/report")
    assert report.status_code == 200
    assert b"Budget and selected vendors" in report.data
    assert b"Lens Studio" in report.data
    assert b"E10,500.00" in report.data

    pdf = client.get("/report.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert "attachment" in pdf.headers["Content-Disposition"]


def test_quotation_activity_is_persisted_and_published_live(app, client):
    create_owner_wedding(client)
    client.post("/budget", data={"name": "Photography", "planned_amount": "12000"})
    realtime = socketio.test_client(app, flask_test_client=client, namespace="/planning")
    assert realtime.is_connected("/planning")
    realtime.get_received("/planning")

    client.post("/budget/1/quotes", data={"vendor_name": "Lens Studio", "amount": "10500"})

    with app.app_context():
        activity = db.session.scalars(
            select(ActivityEvent).where(ActivityEvent.kind == "quotation_added")
        ).one()
        assert "Lens Studio" in activity.message
    received = realtime.get_received("/planning")
    live_updates = [item for item in received if item["name"] == "activity:new"]
    assert live_updates
    assert "Lens Studio" in live_updates[0]["args"][0]["message"]
    realtime.disconnect(namespace="/planning")


def test_standard_upgrade_is_exactly_e40(app, client):
    create_owner_wedding(client)
    response = client.post("/billing/upgrade", follow_redirects=True)
    assert b"Payment confirmed" in response.data
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        payment = db.session.scalar(select(Payment))
        assert wedding.plan_tier == "standard"
        assert str(payment.amount) == "40.00"
        assert payment.status == "completed"


def test_owner_paid_invitation_adds_registered_stakeholder(app, client):
    create_owner_wedding(client)
    client.post("/billing/upgrade")
    client.post("/team", data={
        "invitee_name": "Nomsa", "role": "matron_of_honour", "payer": "owner",
    })
    with app.app_context():
        invitation = db.session.scalar(select(Invitation))
        token = invitation.token
        assert invitation.status == "paid"
        payment = db.session.scalars(
            select(Payment).where(Payment.kind == "owner_pays_invite")
        ).one()
        assert str(payment.amount) == "30.00"

    client.post("/logout")
    register(client, "Nomsa", "nomsa@example.com", "76234567", token)
    joined = client.post(f"/invite/{token}/join", follow_redirects=True)
    assert b"Wedding overview" in joined.data
    with app.app_context():
        member = db.session.scalar(select(WeddingMember))
        assert member.role == "matron_of_honour"


def test_invitee_can_pay_their_own_e30_access(app, client):
    create_owner_wedding(client)
    client.post("/billing/upgrade")
    client.post("/team", data={
        "invitee_name": "Bongani", "role": "family_friend", "payer": "invitee",
    })
    with app.app_context():
        token = db.session.scalar(select(Invitation)).token

    client.post("/logout")
    register(client, "Bongani", "bongani@example.com", "76345678", token)
    paid = client.post(f"/invite/{token}/join", follow_redirects=True)
    assert b"Payment confirmed" in paid.data
    with app.app_context():
        invitation = db.session.scalar(select(Invitation))
        payment = db.session.scalars(
            select(Payment).where(Payment.kind == "invitee_pays_invite")
        ).one()
        assert invitation.status == "accepted"
        assert str(payment.amount) == "30.00"
        assert db.session.scalar(select(WeddingMember)) is not None


def test_account_details_can_be_updated(app, client):
    create_owner_wedding(client)
    response = client.post("/account", data={
        "name": "Updated Owner", "email": "updated@example.com", "phone_number": "76456789",
    }, follow_redirects=True)
    assert b"Account details updated" in response.data
    assert b"Free plan" in response.data
    with app.app_context():
        user = db.session.scalar(select(Wedding).where(Wedding.owner_id.is_not(None))).owner
        assert user.name == "Updated Owner"
        assert user.phone_number == "26876456789"


def test_owner_can_upload_couple_photo(app, client):
    create_owner_wedding(client)
    photo = BytesIO()
    Image.new("RGB", (80, 60), "#6f294d").save(photo, "PNG")
    photo.seek(0)
    response = client.post(
        "/wedding/photo", data={"profile_image": (photo, "couple.png")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert b"couple photo has been updated" in response.data
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        assert wedding.profile_image.endswith(".jpg")
        saved = app.config["WEDDING_PHOTO_FOLDER"].parent / wedding.profile_image
        assert saved.is_file()


def test_pwa_files_are_public(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.mimetype == "application/manifest+json"
    assert manifest.json["name"] == "UMSHADO Wedding Planner"
    assert manifest.json["display"] == "standalone"

    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert worker.headers["Service-Worker-Allowed"] == "/"
    assert b"umshado-static-v3" in worker.data
    assert b"/static/css/app.css" not in worker.data
    assert b"request.mode === \"navigate\") return" in worker.data
    assert b"/offline" not in worker.data

    offline = client.get("/offline")
    assert offline.status_code == 200
    assert b"offline" in offline.data



def test_live_mock_mode_and_payment_trace(app, client, monkeypatch):
    from types import SimpleNamespace
    from mojapos_payments.config import MojaposConfig
    from app.payment_gateway import build_gateway
    assert MojaposConfig(mock_mode="false").mock_mode is False
    assert MojaposConfig(mock_mode="true").mock_mode is True

    create_owner_wedding(client)
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "false")
    monkeypatch.setenv("MOJAPOS_API_KEY", "test-not-real")
    gateway = build_gateway()
    app.extensions["mojapos_payments"] = gateway
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"]["metadata"]["externalId"])
        return SimpleNamespace(
            status_code=202, raise_for_status=lambda: None,
            json=lambda: {"transactionId": "gateway-live-123"},
        )

    monkeypatch.setattr(gateway.service._session, "post", fake_post)
    response = client.post("/billing/upgrade", follow_redirects=True)
    assert b"Approve the payment on your phone" in response.data
    assert len(calls) == 1
    with app.app_context():
        payment = db.session.scalar(select(Payment))
        assert payment.status == "pending"
        assert payment.gateway_transaction_id == "gateway-live-123"
        assert payment.external_ref_id == calls[0]
        assert db.session.scalar(select(Wedding)).plan_tier == "free"
        logfile = next(h.baseFilename for h in app.extensions["payment_logger"].handlers
                       if hasattr(h, "baseFilename"))
        with open(logfile, encoding="utf-8") as entries:
            audit = entries.read()
        assert f"event=gateway_accepted payment_id={payment.id}" in audit
        assert "mode=live" in audit
        assert "26876123456" not in audit


def test_old_mock_pending_payment_not_resubmitted(app, client, monkeypatch):
    from app.payment_gateway import build_gateway
    create_owner_wedding(client)
    with app.app_context():
        wedding = db.session.scalar(select(Wedding))
        db.session.add(Payment(
            external_ref_id="oldmock123", kind="owner_upgrade", amount="40.00",
            currency="SZL", status="pending", user_id=wedding.owner_id,
            wedding_id=wedding.id, gateway_transaction_id="mock_oldmock123",
        ))
        db.session.commit()
    monkeypatch.setenv("MOJAPOS_MOCK_MODE", "false")
    gateway = build_gateway()
    app.extensions["mojapos_payments"] = gateway
    def unexpected_post(*args, **kwargs):
        raise AssertionError("Existing pending payment must not trigger another request")
    monkeypatch.setattr(gateway.service._session, "post", unexpected_post)
    response = client.post("/billing/upgrade", follow_redirects=True)
    assert b"Test payment only" in response.data

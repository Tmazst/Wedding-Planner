from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import secrets
import shutil

import click
from flask import Blueprint, current_app, flash, redirect, request, session, url_for
from flask.cli import with_appcontext
from flask_login import current_user, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from .extensions import db
from .models import (
    BudgetCategory,
    InvitationCardDesign,
    ProgrammeItem,
    Quotation,
    User,
    Wedding,
    WeddingProgramme,
)


bp = Blueprint("demo", __name__)
DEMO_INVITE_MAX_AGE = 90 * 60


def _demo_email():
    return current_app.config.get("DEMO_ACCOUNT_EMAIL", "demo@umshado.app").strip().lower()


def _is_demo_user(user):
    return bool(
        current_app.config.get("DEMO_MODE_ENABLED", True)
        and user.is_authenticated
        and user.email.lower() == _demo_email()
    )


def _demo_invite_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="umshado-demo-team-invite")


def _attach_demo_photo(wedding):
    """Copy the bundled demo image into private wedding-photo storage when present."""
    source = Path(current_app.static_folder) / "images" / "demo" / "demo-couple.jpg"
    if not source.is_file():
        wedding.profile_image = None
        return False

    folder = Path(current_app.config["WEDDING_PHOTO_FOLDER"]) / str(wedding.id)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / "demo-couple.jpg"
    shutil.copyfile(source, destination)
    wedding.profile_image = f"weddings/{wedding.id}/demo-couple.jpg"
    return True


def seed_demo_wedding():
    """Create or reset the public marketing demo to a known, complete state."""
    email = _demo_email()
    user = db.session.scalar(select(User).where(User.email == email))
    now = datetime.now(timezone.utc)

    if user is None:
        user = User(
            name="UMSHADO Demo Guest",
            email=email,
            phone_number=None,
            phone_country="SZ",
            has_test_access=True,
            terms_accepted_at=now,
            terms_version=current_app.config["TERMS_VERSION"],
            privacy_version=current_app.config["PRIVACY_VERSION"],
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.flush()
    else:
        user.name = "UMSHADO Demo Guest"
        user.has_test_access = True
        user.deleted_at = None
        user.terms_accepted_at = now
        user.terms_version = current_app.config["TERMS_VERSION"]
        user.privacy_version = current_app.config["PRIVACY_VERSION"]
        for wedding in list(user.weddings):
            db.session.delete(wedding)
        db.session.flush()

    wedding = Wedding(
        title="Sipho & Nomsa",
        partner_one="Sipho",
        partner_two="Nomsa",
        wedding_date=date(2026, 12, 19),
        location="Ezulwini, Eswatini",
        budget_target=Decimal("95000.00"),
        plan_tier="advanced",
        upgraded_at=now,
        owner_id=user.id,
    )
    db.session.add(wedding)
    db.session.flush()
    photo_attached = _attach_demo_photo(wedding)

    budget = [
        ("Venue", "15000.00", [("Ezulwini Gardens Demo Venue", "14500.00"), ("Mountain View Demo Venue", "16000.00")]),
        ("Catering", "26000.00", [("Royal Feast Demo Catering", "25000.00"), ("Emaswati Table Demo Catering", "27200.00")]),
        ("Décor & Flowers", "12000.00", [("Golden Petal Demo Décor", "11800.00"), ("Lily & Linen Demo Events", "12600.00")]),
        ("Photography & Video", "9500.00", [("Moments Studio Demo", "9000.00"), ("EverAfter Media Demo", "10200.00")]),
        ("Wedding Attire", "9000.00", [("Elegant Bride Demo Boutique", "8500.00"), ("Classic Couple Demo Wear", "9400.00")]),
        ("Music, DJ & MC", "6500.00", [("Celebration Sounds Demo", "6200.00"), ("Royal Rhythm Demo", "7000.00")]),
        ("Wedding Cake", "3500.00", [("Sweet Vows Demo Bakery", "3200.00"), ("Sugar Bloom Demo Cakes", "3700.00")]),
        ("Transport", "5000.00", [("Premier Ride Demo Hire", "4800.00"), ("Royal Wheels Demo", "5400.00")]),
    ]

    for category_name, planned_amount, quotes in budget:
        category = BudgetCategory(
            name=category_name,
            planned_amount=Decimal(planned_amount),
            wedding_id=wedding.id,
        )
        db.session.add(category)
        db.session.flush()
        for index, (vendor_name, amount) in enumerate(quotes):
            db.session.add(Quotation(
                vendor_name=vendor_name,
                amount=Decimal(amount),
                contact="Demo quotation",
                notes="Sample quotation included for the UMSHADO product demo.",
                valid_until=date(2026, 11, 30),
                is_selected=index == 0,
                category_id=category.id,
            ))

    programme = WeddingProgramme(
        wedding_id=wedding.id,
        title="Sipho & Nomsa Wedding Programme",
        template_key="floral_elegant",
        font_style="elegant",
        primary_color="#7d1020",
        accent_color="#b88a3b",
        show_profile_image=photo_attached,
        closing_message="Thank you for celebrating this beautiful day with us.",
        is_published=True,
        share_token="umshado-demo-programme",
    )
    db.session.add(programme)
    db.session.flush()

    programme_items = [
        ("09:00", "Guest arrival and seating", "Ushers"),
        ("10:00", "Wedding ceremony begins", "Programme Director"),
        ("10:10", "Entrance of the bridal party", "Bridal Party"),
        ("10:25", "Exchange of vows and rings", "Sipho & Nomsa"),
        ("11:15", "Family photographs", "Photography Team"),
        ("12:30", "Reception and welcome", "MC"),
        ("13:00", "Lunch service", "Catering Team"),
        ("14:15", "Speeches and messages", "Families & Friends"),
        ("15:10", "Cake cutting", "Sipho & Nomsa"),
        ("15:30", "First dance", "Sipho & Nomsa"),
        ("16:00", "Entertainment", "Guest Artist & Band"),
        ("17:30", "Closing remarks", "MC"),
    ]
    for position, (time_label, activity, person_or_group) in enumerate(programme_items):
        db.session.add(ProgrammeItem(
            programme_id=programme.id,
            position=position,
            time_label=time_label,
            activity=activity,
            person_or_group=person_or_group,
            show_to_guests=True,
        ))

    db.session.add(InvitationCardDesign(
        wedding_id=wedding.id,
        template_key="floral_elegant",
        font_style="elegant",
        primary_color="#7d1020",
        accent_color="#b88a3b",
        show_profile_image=photo_attached,
        event_time="10:00",
        message="Together with their families, Sipho and Nomsa invite you to celebrate their wedding day in Ezulwini.",
        is_published=True,
        share_token="umshado-demo-invitation",
    ))

    db.session.commit()
    return user, photo_attached


@bp.get("/demo")
def enter_demo():
    if not current_app.config.get("DEMO_MODE_ENABLED", True):
        return ("Not found", 404)
    user = db.session.scalar(select(User).where(User.email == _demo_email()))
    if user is None:
        flash("The demo account is not prepared yet. Please try again shortly.", "info")
        return redirect(url_for("main.login"))
    if current_user.is_authenticated and current_user.id != user.id:
        logout_user()
    login_user(user)
    session.pop("shared_vendor_role_is_vendor", None)
    session.pop("demo_invitation", None)
    session.pop("demo_invited_name", None)
    session.pop("demo_invited_role", None)
    session["demo_joined_via_invite"] = False
    flash("You are viewing the UMSHADO demo. Changes are disabled so the demo stays ready for everyone.", "info")
    return redirect(url_for("main.dashboard"))


@bp.get("/demo/join/<token>")
def join_demo_invitation(token):
    if not current_app.config.get("DEMO_MODE_ENABLED", True):
        return ("Not found", 404)
    try:
        payload = _demo_invite_serializer().loads(token, max_age=DEMO_INVITE_MAX_AGE)
    except SignatureExpired:
        flash("This demo invitation has expired. Ask the sender to create a new one.", "info")
        return redirect(url_for("main.login"))
    except BadSignature:
        flash("This demo invitation is invalid.", "error")
        return redirect(url_for("main.login"))
    if payload.get("purpose") != "demo-view":
        return ("Not found", 404)

    user = db.session.scalar(select(User).where(User.email == _demo_email()))
    if user is None:
        flash("The demo account is not prepared yet.", "info")
        return redirect(url_for("main.login"))
    if current_user.is_authenticated and current_user.id != user.id:
        logout_user()
    login_user(user)
    session.pop("shared_vendor_role_is_vendor", None)
    session["demo_joined_via_invite"] = True
    session["demo_invited_name"] = payload.get("name")
    session["demo_invited_role"] = payload.get("role")
    session.pop("demo_invitation", None)
    flash("You joined the Sipho & Nomsa demo in view-only mode.", "success")
    return redirect(url_for("main.dashboard"))


def _create_demo_invitation():
    if session.get("demo_joined_via_invite", False):
        flash("Only the main demo visitor can create temporary invitations.", "info")
        return redirect(url_for("billing.team"))

    role = request.form.get("role", "stakeholder")
    if role not in {"partner", "matron_of_honour", "family_friend", "stakeholder"}:
        role = "stakeholder"
    invitee_name = request.form.get("invitee_name", "").strip() or None
    token = _demo_invite_serializer().dumps(
        {
            "purpose": "demo-view",
            "nonce": secrets.token_urlsafe(10),
            "name": invitee_name,
            "role": role,
        }
    )
    session["demo_invitation"] = {
        "name": invitee_name,
        "role": role,
        "url": url_for("demo.join_demo_invitation", token=token, _external=True),
    }
    flash("Temporary demo invitation created. It will expire in 90 minutes.", "success")
    return redirect(url_for("billing.team"))


def demo_read_only_guard():
    if not _is_demo_user(current_user):
        return None
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.endpoint == "main.logout":
        return None
    if request.endpoint == "billing.team" and request.method == "POST":
        return _create_demo_invitation()
    flash("This is a read-only demo. Create your own account to save changes.", "info")
    return redirect(request.referrer or url_for("main.dashboard"))


def demo_context():
    is_demo = _is_demo_user(current_user)
    joined_via_invite = bool(is_demo and session.get("demo_joined_via_invite", False))
    return {
        "is_demo_account": is_demo,
        "demo_can_invite": bool(is_demo and not joined_via_invite),
        "demo_invitation": session.get("demo_invitation") if is_demo and not joined_via_invite else None,
        "demo_invited_name": session.get("demo_invited_name") if joined_via_invite else None,
        "demo_invited_role": session.get("demo_invited_role") if joined_via_invite else None,
    }


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    _, photo_attached = seed_demo_wedding()
    click.echo("UMSHADO demo wedding is ready.")
    if photo_attached:
        click.echo("Demo couple image attached.")
    else:
        click.echo(
            "Demo image not found. Add app/static/images/demo/demo-couple.jpg and run seed-demo again."
        )


def register_demo(app):
    app.register_blueprint(bp)
    app.before_request(demo_read_only_guard)
    app.context_processor(demo_context)
    app.cli.add_command(seed_demo_command)

import hashlib
import secrets
from urllib.parse import urlencode

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import SharedLoginUse, User


bp = Blueprint("shared_login", __name__, url_prefix="/shared-login")


def _enabled():
    return current_app.config.get("SHARED_LOGIN_HANDOFF_ENABLED", False)


def _serializer(salt):
    secret = current_app.config.get("SHARED_LOGIN_SECRET") or ""
    if not secret:
        raise RuntimeError("Shared login secret is not configured.")
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)


def _identity_payload(user, *, provision=False, account_type=None):
    payload = {
        "email": user.email,
        "phone_number": user.phone_number,
        "phone_country": user.phone_country,
        "name": user.name,
        "source": "umshado",
        "target": "umcimby",
    }
    if provision:
        payload["provision"] = True
        payload["account_type"] = account_type or "organizer"
    return payload


def _matching_user(payload):
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone_number") or "").strip()
    email_user = db.session.scalar(select(User).where(User.email == email)) if email else None
    phone_user = db.session.scalar(select(User).where(User.phone_number == phone)) if phone else None
    if email_user and phone_user and email_user.id != phone_user.id:
        return None, True
    return email_user or phone_user, False


def _consume_token(token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if db.session.scalar(select(SharedLoginUse).where(SharedLoginUse.token_hash == token_hash)):
        return False
    db.session.add(SharedLoginUse(token_hash=token_hash))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def _send_to_umcimby(user, *, provision=False, account_type=None):
    destination = current_app.config.get("UMCIMBY_SSO_RECEIVE_URL") or ""
    if not destination:
        flash("Umcimby shared login is not configured yet.", "error")
        return redirect(url_for("main.login"))
    token = _serializer("umshado-to-umcimby").dumps(
        _identity_payload(user, provision=provision, account_type=account_type)
    )
    separator = "&" if "?" in destination else "?"
    return redirect(f"{destination}{separator}{urlencode({'token': token})}")


@bp.route("/continue-to-umcimby", methods=["GET", "POST"])
def continue_to_umcimby():
    """Authenticate the exact UMSHADO account found during Umcimby signup."""
    if not _enabled():
        return ("Not found", 404)
    account_type = request.values.get("account_type", "organizer")
    if account_type not in {"organizer", "vendor"}:
        account_type = "organizer"
    expected_identity = (request.values.get("identity") or "").strip().lower()

    if current_user.is_authenticated:
        if expected_identity and current_user.email.lower() != expected_identity:
            logout_user()
            flash(
                f"Please sign in with the UMSHADO account for {expected_identity} to continue.",
                "info",
            )
        else:
            return _send_to_umcimby(current_user, provision=True, account_type=account_type)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if expected_identity and email != expected_identity:
            flash(f"Please use the UMSHADO account for {expected_identity}.", "error")
        else:
            user = db.session.scalar(select(User).where(User.email == email))
            if user and user.check_password(request.form.get("password", "")):
                login_user(user)
                return _send_to_umcimby(user, provision=True, account_type=account_type)
            flash("Incorrect UMSHADO email or password.", "error")

    return render_template(
        "auth/shared_continue.html",
        source_name="UMSHADO",
        destination_name="Umcimby",
        account_type=account_type,
        expected_identity=expected_identity,
    )


@bp.get("/to-umcimby")
def to_umcimby():
    if not _enabled():
        return ("Not found", 404)
    if not current_user.is_authenticated:
        return redirect(url_for("shared_login.continue_to_umcimby"))
    return _send_to_umcimby(current_user)


@bp.get("/from-umcimby")
def from_umcimby():
    if not _enabled():
        return ("Not found", 404)
    token = request.args.get("token", "")
    try:
        payload = _serializer("umcimby-to-umshado").loads(
            token,
            max_age=current_app.config.get("SHARED_LOGIN_MAX_AGE_SECONDS", 90),
        )
    except SignatureExpired:
        flash("That shared login link expired. Please try again from Umcimby.", "error")
        return redirect(url_for("main.login"))
    except (BadSignature, RuntimeError):
        flash("That shared login link is invalid.", "error")
        return redirect(url_for("main.login"))

    if payload.get("source") != "umcimby" or payload.get("target") != "umshado":
        flash("That shared login link is invalid.", "error")
        return redirect(url_for("main.login"))

    user, identity_conflict = _matching_user(payload)
    if identity_conflict:
        flash("This shared account has conflicting email and phone records. Please sign in normally and contact support.", "error")
        return redirect(url_for("main.login"))

    provisioned = False
    if user is None and payload.get("provision"):
        email = (payload.get("email") or "").strip().lower()
        name = (payload.get("name") or "").strip() or "UMSHADO user"
        phone = (payload.get("phone_number") or "").strip() or None
        phone_country = (payload.get("phone_country") or "SZ").strip().upper()
        if not email:
            flash("The Umcimby account is missing an email address.", "error")
            return redirect(url_for("main.register"))
        user = User(
            name=name,
            email=email,
            phone_number=phone,
            phone_country=phone_country,
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.commit()
        provisioned = True
    elif user is None:
        flash("No UMSHADO account was found for this Umcimby account. Please register first.", "info")
        return redirect(url_for("main.register"))

    if not _consume_token(token):
        flash("That shared login link has already been used. Please start again from Umcimby.", "error")
        return redirect(url_for("main.login"))

    login_user(user)
    flash("Signed in through Umcimby.", "success")
    if provisioned:
        return redirect(url_for("main.accept_legal_terms"))
    return redirect(url_for("main.dashboard"))

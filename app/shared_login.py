from urllib.parse import urlencode

from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required, login_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from .extensions import db
from .models import User


bp = Blueprint("shared_login", __name__, url_prefix="/shared-login")


def _enabled():
    return current_app.config.get("SHARED_LOGIN_HANDOFF_ENABLED", False)


def _serializer(salt):
    secret = current_app.config.get("SHARED_LOGIN_SECRET") or ""
    if not secret:
        raise RuntimeError("Shared login secret is not configured.")
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)


def _identity_payload(user):
    return {
        "email": user.email,
        "phone_number": user.phone_number,
        "name": user.name,
        "source": "umshado",
        "target": "umcimby",
    }


def _matching_user(payload):
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone_number") or "").strip()
    email_user = db.session.scalar(select(User).where(User.email == email)) if email else None
    phone_user = db.session.scalar(select(User).where(User.phone_number == phone)) if phone else None
    if email_user and phone_user and email_user.id != phone_user.id:
        return None, True
    return email_user or phone_user, False


@bp.get("/to-umcimby")
@login_required
def to_umcimby():
    if not _enabled():
        return ("Not found", 404)
    destination = current_app.config.get("UMCIMBY_SSO_RECEIVE_URL") or ""
    if not destination:
        flash("Umcimby shared login is not configured yet.", "error")
        return redirect(url_for("shared_vendors.account"))
    token = _serializer("umshado-to-umcimby").dumps(_identity_payload(current_user))
    separator = "&" if "?" in destination else "?"
    return redirect(f"{destination}{separator}{urlencode({'token': token})}")


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
    if user is None:
        flash("No UMSHADO account was found for this Umcimby account. Please register first.", "info")
        return redirect(url_for("main.register"))

    login_user(user)
    flash("Signed in through Umcimby.", "success")
    return redirect(url_for("main.dashboard"))

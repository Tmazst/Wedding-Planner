import hmac
from urllib.parse import urlsplit

import requests
from flask import Blueprint, current_app, flash, jsonify, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_, select

from .extensions import db
from .models import User
from .phone_numbers import country_options, normalize_phone


bp = Blueprint("shared_accounts", __name__, url_prefix="/shared-accounts")


def _enabled():
    return current_app.config.get("SHARED_ACCOUNT_DISCOVERY_ENABLED", False)


def _api_key():
    return current_app.config.get("SHARED_ACCOUNT_API_KEY") or ""


def _authorized():
    configured = _api_key()
    supplied = request.headers.get("X-Shared-Account-Key", "")
    return bool(configured and supplied and hmac.compare_digest(configured, supplied))


def _remote_origin():
    receive = current_app.config.get("UMCIMBY_SSO_RECEIVE_URL") or ""
    parsed = urlsplit(receive)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("Umcimby shared login URL is not configured.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _remote_lookup(email, phone_number):
    if not _enabled() or not _api_key():
        return None
    response = requests.post(
        f"{_remote_origin()}/shared-accounts/api/lookup",
        json={"email": email, "phone_number": phone_number},
        headers={"X-Shared-Account-Key": _api_key()},
        timeout=current_app.config.get("SHARED_ACCOUNT_API_TIMEOUT_SECONDS", 5),
    )
    response.raise_for_status()
    return response.json()


def _register_page(message, category="info", status=200, continue_url=None):
    flash(message, category)
    return render_template(
        "auth/register.html",
        invite_token=request.form.get("invite_token", ""),
        countries=country_options(),
        selected_country=request.form.get("phone_country", "SZ"),
        phone_value=request.form.get("phone_number", ""),
        name_value=request.form.get("name", ""),
        email_value=request.form.get("email", ""),
        accepted_terms=request.form.get("accept_terms") == "yes",
        shared_continue_url=continue_url,
    ), status


@bp.post("/api/lookup")
def lookup():
    if not _enabled():
        return jsonify({"error": "Shared account discovery is disabled."}), 404
    if not _authorized():
        return jsonify({"error": "Unauthorized."}), 401
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone_number") or "").strip()
    if not email and not phone:
        return jsonify({"error": "Provide an email address or phone number."}), 400
    conditions = []
    if email:
        conditions.append(User.email == email)
    if phone:
        conditions.append(User.phone_number == phone)
    user = db.session.scalar(select(User).where(or_(*conditions)))
    if user is None:
        return jsonify({"exists": False})
    return jsonify({
        "exists": True,
        "name": user.name,
        "email": user.email,
        "phone_number": user.phone_number,
        "account_type": "wedding",
    })


@bp.post("/register")
def register():
    if current_user.is_authenticated:
        return ("Already signed in", 409)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone_country = request.form.get("phone_country", "SZ")
    password = request.form.get("password", "")
    accepted_terms = request.form.get("accept_terms") == "yes"
    try:
        phone_number, phone_country = normalize_phone(
            request.form.get("phone_number"), phone_country
        )
        phone_error = None
    except ValueError as error:
        phone_number, phone_error = None, str(error)

    if not accepted_terms:
        return _register_page("You must agree to the Terms of Use and acknowledge the Privacy Notice.", "error", 400)
    if phone_error:
        return _register_page(phone_error, "error", 400)
    if not name or not email or len(password) < 6:
        return _register_page("Enter your name, email and a password of at least 6 characters.", "error", 400)
    if db.session.scalar(select(User).where(User.email == email)):
        return _register_page("An UMSHADO account with that email already exists. Please log in.", "error", 409)
    if db.session.scalar(select(User).where(User.phone_number == phone_number)):
        return _register_page("An UMSHADO account with that phone number already exists. Please log in.", "error", 409)

    if not request.form.get("invite_token"):
        try:
            remote = _remote_lookup(email, phone_number)
        except (requests.RequestException, RuntimeError, ValueError):
            remote = None
        if remote and remote.get("exists"):
            continue_url = f"{_remote_origin()}/shared-login/continue-to-umshado"
            return _register_page(
                "You already have an Umcimby account. You can use that account to join UMSHADO without creating another password.",
                "info",
                409,
                continue_url,
            )

    user = User(
        name=name,
        email=email,
        phone_number=phone_number,
        phone_country=phone_country,
        terms_accepted_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        terms_version=current_app.config["TERMS_VERSION"],
        privacy_version=current_app.config["PRIVACY_VERSION"],
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    from flask_login import login_user
    from .routes import invitation_redirect
    login_user(user)
    if request.form.get("invite_token"):
        return invitation_redirect()
    return __import__("flask").redirect(url_for("main.setup_wedding"))

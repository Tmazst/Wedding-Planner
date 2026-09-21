from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import InvitationCardDesign, WeddingProgramme
from .routes import current_wedding


bp = Blueprint("advanced", __name__, url_prefix="/advanced")


def _advanced_wedding():
    if not current_app.config["ADVANCED_PLAN_ENABLED"]:
        return None
    wedding = current_wedding()
    if wedding is None:
        return None
    return wedding


def _require_advanced(wedding):
    if wedding.has_advanced_access:
        return None
    flash("Upgrade to Advanced to use programme and invitation-card design tools.", "info")
    return redirect(url_for("billing.pricing"))


@bp.get("")
@login_required
def home():
    wedding = _advanced_wedding()
    if wedding is None:
        return ("Not found", 404)
    locked = not wedding.has_advanced_access
    return render_template(
        "advanced/home.html",
        wedding=wedding,
        locked=locked,
        programme_enabled=current_app.config["ADVANCED_PROGRAMME_ENABLED"],
        invitation_card_enabled=current_app.config["ADVANCED_INVITATION_CARD_ENABLED"],
    )


@bp.get("/programme")
@login_required
def programme():
    wedding = _advanced_wedding()
    if wedding is None or not current_app.config["ADVANCED_PROGRAMME_ENABLED"]:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    programme = wedding.programme
    if programme is None and wedding.owner_id == current_user.id:
        programme = WeddingProgramme(wedding_id=wedding.id)
        db.session.add(programme)
        db.session.commit()
    return render_template(
        "advanced/programme.html",
        wedding=wedding,
        programme=programme,
        is_owner=wedding.owner_id == current_user.id,
    )


@bp.get("/invitation-card")
@login_required
def invitation_card():
    wedding = _advanced_wedding()
    if wedding is None or not current_app.config["ADVANCED_INVITATION_CARD_ENABLED"]:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    design = wedding.invitation_card
    if design is None and wedding.owner_id == current_user.id:
        design = InvitationCardDesign(wedding_id=wedding.id)
        db.session.add(design)
        db.session.commit()
    return render_template(
        "advanced/invitation_card.html",
        wedding=wedding,
        design=design,
        is_owner=wedding.owner_id == current_user.id,
    )

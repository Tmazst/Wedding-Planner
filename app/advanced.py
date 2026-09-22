import secrets
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from .extensions import db
from .models import InvitationCardDesign, ProgrammeItem, WeddingProgramme
from .routes import current_wedding


bp = Blueprint("advanced", __name__, url_prefix="/advanced")

PROGRAMME_TEMPLATES = {
    "floral_elegant": "Floral Elegant",
    "floral_minimal": "Floral Minimal",
    "classic_border": "Classic Border",
}

PROGRAMME_FONTS = {
    "elegant": "Elegant",
    "romantic": "Romantic",
    "classic": "Classic",
    "modern": "Modern",
}

INVITATION_TEMPLATES = PROGRAMME_TEMPLATES
INVITATION_FONTS = PROGRAMME_FONTS


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


def _owner_programme():
    wedding = _advanced_wedding()
    if wedding is None or not current_app.config["ADVANCED_PROGRAMME_ENABLED"]:
        return None, None
    if wedding.owner_id != current_user.id:
        return wedding, None
    programme = wedding.programme
    if programme is None:
        programme = WeddingProgramme(wedding_id=wedding.id)
        db.session.add(programme)
        db.session.commit()
    return wedding, programme


def _owner_invitation_card():
    wedding = _advanced_wedding()
    if wedding is None or not current_app.config["ADVANCED_INVITATION_CARD_ENABLED"]:
        return None, None
    if wedding.owner_id != current_user.id:
        return wedding, None
    design = wedding.invitation_card
    if design is None:
        design = InvitationCardDesign(wedding_id=wedding.id)
        db.session.add(design)
        db.session.commit()
    return wedding, design


def _valid_hex(value, fallback):
    value = (value or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return fallback


def _published_programme(token):
    if not current_app.config["ADVANCED_PLAN_ENABLED"] or not current_app.config["ADVANCED_PROGRAMME_ENABLED"]:
        return None
    return db.session.scalar(
        select(WeddingProgramme).where(
            WeddingProgramme.share_token == token,
            WeddingProgramme.is_published.is_(True),
        )
    )


def _published_invitation_card(token):
    if not current_app.config["ADVANCED_PLAN_ENABLED"] or not current_app.config["ADVANCED_INVITATION_CARD_ENABLED"]:
        return None
    return db.session.scalar(
        select(InvitationCardDesign).where(
            InvitationCardDesign.share_token == token,
            InvitationCardDesign.is_published.is_(True),
        )
    )


def _public_wedding_photo(wedding):
    if not wedding.profile_image:
        return None
    relative_path = Path(wedding.profile_image)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    photo_path = Path(current_app.config["WEDDING_PHOTO_FOLDER"]).parent / relative_path
    return photo_path if photo_path.is_file() else None


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
        template_options=PROGRAMME_TEMPLATES,
        font_options=PROGRAMME_FONTS,
    )


@bp.post("/programme/design")
@login_required
def programme_design():
    wedding, programme = _owner_programme()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    if programme is None:
        return ("Not found", 404)

    template_key = request.form.get("template_key", programme.template_key)
    font_style = request.form.get("font_style", programme.font_style)
    if template_key in PROGRAMME_TEMPLATES:
        programme.template_key = template_key
    if font_style in PROGRAMME_FONTS:
        programme.font_style = font_style
    programme.title = (request.form.get("title") or "Wedding Programme").strip()[:160]
    programme.primary_color = _valid_hex(request.form.get("primary_color"), programme.primary_color)
    programme.accent_color = _valid_hex(request.form.get("accent_color"), programme.accent_color)
    programme.show_profile_image = request.form.get("show_profile_image") == "yes"
    programme.closing_message = (request.form.get("closing_message") or "").strip()[:255] or None
    db.session.commit()
    flash("Programme design saved.", "success")
    return redirect(url_for("advanced.programme"))


@bp.post("/programme/items")
@login_required
def programme_add_item():
    wedding, programme = _owner_programme()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    activity = (request.form.get("activity") or "").strip()
    if not activity:
        flash("Enter a programme activity.", "error")
        return redirect(url_for("advanced.programme"))
    next_position = max((item.position for item in programme.items), default=-1) + 1
    db.session.add(ProgrammeItem(
        programme_id=programme.id,
        position=next_position,
        time_label=(request.form.get("time_label") or "").strip()[:30] or None,
        activity=activity[:180],
        person_or_group=(request.form.get("person_or_group") or "").strip()[:160] or None,
        notes=(request.form.get("notes") or "").strip() or None,
        show_to_guests=request.form.get("show_to_guests") == "yes",
    ))
    db.session.commit()
    flash("Programme activity added.", "success")
    return redirect(url_for("advanced.programme"))


@bp.post("/programme/items/<int:item_id>/move")
@login_required
def programme_move_item(item_id):
    wedding, programme = _owner_programme()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    item = db.session.get(ProgrammeItem, item_id)
    if item is None or item.programme_id != programme.id:
        return ("Not found", 404)
    items = list(programme.items)
    index = next((i for i, current in enumerate(items) if current.id == item.id), None)
    direction = request.form.get("direction")
    if index is not None:
        target_index = index - 1 if direction == "up" else index + 1
        if 0 <= target_index < len(items):
            other = items[target_index]
            item.position, other.position = other.position, item.position
            db.session.commit()
    return redirect(url_for("advanced.programme"))


@bp.post("/programme/items/<int:item_id>/delete")
@login_required
def programme_delete_item(item_id):
    wedding, programme = _owner_programme()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    item = db.session.get(ProgrammeItem, item_id)
    if item is None or item.programme_id != programme.id:
        return ("Not found", 404)
    db.session.delete(item)
    db.session.commit()
    flash("Programme activity removed.", "success")
    return redirect(url_for("advanced.programme"))


@bp.post("/programme/publish")
@login_required
def programme_publish():
    wedding, programme = _owner_programme()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    publish = request.form.get("publish") == "yes"
    programme.is_published = publish
    if publish and not programme.share_token:
        programme.share_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash("Programme sharing enabled." if publish else "Programme sharing disabled.", "success")
    return redirect(url_for("advanced.programme"))


@bp.get("/programme/share/<token>")
def shared_programme(token):
    programme = _published_programme(token)
    if programme is None:
        return ("Not found", 404)
    return render_template(
        "advanced/programme_shared.html",
        wedding=programme.wedding,
        programme=programme,
        public_programme=True,
    )


@bp.get("/programme/share/<token>/photo")
def shared_programme_photo(token):
    programme = _published_programme(token)
    if programme is None or not programme.show_profile_image:
        return ("Not found", 404)
    photo_path = _public_wedding_photo(programme.wedding)
    if photo_path is None:
        return ("Not found", 404)
    response = send_file(photo_path, mimetype="image/jpeg", conditional=True)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


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
        template_options=INVITATION_TEMPLATES,
        font_options=INVITATION_FONTS,
    )


@bp.post("/invitation-card/design")
@login_required
def invitation_card_design():
    wedding, design = _owner_invitation_card()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    if design is None:
        return ("Not found", 404)

    template_key = request.form.get("template_key", design.template_key)
    font_style = request.form.get("font_style", design.font_style)
    if template_key in INVITATION_TEMPLATES:
        design.template_key = template_key
    if font_style in INVITATION_FONTS:
        design.font_style = font_style

    event_time = (request.form.get("event_time") or "").strip()
    if event_time:
        try:
            datetime.strptime(event_time, "%H:%M")
        except ValueError:
            flash("Enter a valid wedding time.", "error")
            return redirect(url_for("advanced.invitation_card"))
    design.event_time = event_time or None
    design.primary_color = _valid_hex(request.form.get("primary_color"), design.primary_color)
    design.accent_color = _valid_hex(request.form.get("accent_color"), design.accent_color)
    design.show_profile_image = request.form.get("show_profile_image") == "yes"
    design.message = (request.form.get("message") or "").strip()[:800] or None
    db.session.commit()
    flash("Invitation card design saved.", "success")
    return redirect(url_for("advanced.invitation_card"))


@bp.post("/invitation-card/publish")
@login_required
def invitation_card_publish():
    wedding, design = _owner_invitation_card()
    if wedding is None:
        return ("Not found", 404)
    locked = _require_advanced(wedding)
    if locked:
        return locked
    publish = request.form.get("publish") == "yes"
    design.is_published = publish
    if publish and not design.share_token:
        design.share_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash("Invitation sharing enabled." if publish else "Invitation sharing disabled.", "success")
    return redirect(url_for("advanced.invitation_card"))


@bp.get("/invitation-card/share/<token>")
def shared_invitation_card(token):
    design = _published_invitation_card(token)
    if design is None:
        return ("Not found", 404)
    return render_template(
        "advanced/invitation_card_shared.html",
        wedding=design.wedding,
        design=design,
        photo_url=url_for("advanced.shared_invitation_card_photo", token=token),
    )


@bp.get("/invitation-card/share/<token>/photo")
def shared_invitation_card_photo(token):
    design = _published_invitation_card(token)
    if design is None or not design.show_profile_image:
        return ("Not found", 404)
    photo_path = _public_wedding_photo(design.wedding)
    if photo_path is None:
        return ("Not found", 404)
    response = send_file(photo_path, mimetype="image/jpeg", conditional=True)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import json
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, select, update
from werkzeug.utils import secure_filename

from .activity import add_activity, publish_activity
from .extensions import db
from .models import ActivityEvent, BudgetCategory, Invitation, Payment, Quotation, User, Wedding, WeddingMember


bp = Blueprint("main", __name__)


def money(value, default="0"):
    try:
        return Decimal(value or default)
    except InvalidOperation:
        return Decimal(default)


def current_wedding():
    owned = db.session.scalar(
        select(Wedding).where(Wedding.owner_id == current_user.id).order_by(Wedding.created_at)
    )
    if owned:
        return owned
    membership = db.session.scalar(
        select(WeddingMember).where(WeddingMember.user_id == current_user.id).order_by(WeddingMember.joined_at)
    )
    return membership.wedding if membership else None


def normalize_phone(value):
    digits = "".join(character for character in (value or "") if character.isdigit())
    if digits.startswith("0"):
        digits = "268" + digits[1:]
    elif len(digits) == 8:
        digits = "268" + digits
    return digits


def invitation_redirect():
    token = request.form.get("invite_token") or request.args.get("invite") or session.pop("invite_token", None)
    return redirect(url_for("billing.accept_invitation", token=token)) if token else redirect(url_for("main.dashboard"))


def report_context(wedding):
    planned_total = sum((category.planned_amount for category in wedding.categories), start=Decimal("0"))
    selected_total = sum(
        (category.selected_quote.amount for category in wedding.categories if category.selected_quote),
        start=Decimal("0"),
    )
    members = [
        {"name": wedding.owner.name, "role": "Couple / Project owner", "email": wedding.owner.email}
    ]
    members.extend(
        {
            "name": membership.user.name,
            "role": membership.role.replace("_", " ").title(),
            "email": membership.user.email,
        }
        for membership in wedding.members
    )
    return {
        "wedding": wedding,
        "planned_total": planned_total,
        "selected_total": selected_total,
        "remaining": wedding.budget_target - selected_total,
        "members": members,
        "generated_at": datetime.now(timezone.utc),
    }


def iso_value(value):
    return value.isoformat() if value else None


def account_export_payload(user):
    owned_weddings = db.session.scalars(
        select(Wedding).where(Wedding.owner_id == user.id).order_by(Wedding.created_at)
    ).all()
    memberships = db.session.scalars(
        select(WeddingMember).where(WeddingMember.user_id == user.id)
    ).all()
    wedding_ids = {wedding.id for wedding in owned_weddings}
    wedding_ids.update(membership.wedding_id for membership in memberships)
    payments = db.session.scalars(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at)
    ).all()
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "name": user.name,
            "email": user.email,
            "phone_number": user.phone_number,
            "created_at": iso_value(user.created_at),
            "terms_accepted_at": iso_value(user.terms_accepted_at),
            "terms_version": user.terms_version,
            "privacy_version": user.privacy_version,
        },
        "weddings": [
            {
                "id": wedding.id,
                "title": wedding.title,
                "partner_one": wedding.partner_one,
                "partner_two": wedding.partner_two,
                "wedding_date": iso_value(wedding.wedding_date),
                "location": wedding.location,
                "budget_target": str(wedding.budget_target),
                "plan_tier": wedding.plan_tier,
                "role": "owner" if wedding.owner_id == user.id else next(
                    membership.role for membership in memberships
                    if membership.wedding_id == wedding.id
                ),
                "budget_items": [
                    {
                        "name": category.name,
                        "planned_amount": str(category.planned_amount),
                        "quotations": [
                            {
                                "vendor_name": quote.vendor_name,
                                "amount": str(quote.amount),
                                "contact": quote.contact,
                                "notes": quote.notes,
                                "valid_until": iso_value(quote.valid_until),
                                "selected": quote.is_selected,
                            }
                            for quote in category.quotations
                        ],
                    }
                    for category in wedding.categories
                ],
            }
            for wedding in db.session.scalars(
                select(Wedding).where(Wedding.id.in_(wedding_ids)).order_by(Wedding.created_at)
            ).all() if wedding_ids
        ],
        "payments": [
            {
                "reference": payment.external_ref_id,
                "kind": payment.kind,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status,
                "created_at": iso_value(payment.created_at),
                "completed_at": iso_value(payment.completed_at),
            }
            for payment in payments
        ],
    }


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard" if current_user.is_authenticated else "main.login"))


@bp.route("/offline")
def offline():
    return render_template("offline.html")


@bp.get("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@bp.get("/terms")
def terms():
    return render_template("legal/terms.html")


@bp.route("/legal/accept", methods=["GET", "POST"])
@login_required
def accept_legal_terms():
    if request.method == "POST":
        if request.form.get("accept_terms") != "yes":
            flash("You must agree to the Terms of Use and acknowledge the Privacy Notice.", "error")
        else:
            current_user.terms_accepted_at = datetime.now(timezone.utc)
            current_user.terms_version = current_app.config["TERMS_VERSION"]
            current_user.privacy_version = current_app.config["PRIVACY_VERSION"]
            db.session.commit()
            token = session.pop("post_legal_invite", None)
            return redirect(
                url_for("billing.accept_invitation", token=token)
                if token else url_for("main.dashboard")
            )
    return render_template("legal/accept.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone_number = normalize_phone(request.form.get("phone_number"))
        password = request.form.get("password", "")
        accepted_terms = request.form.get("accept_terms") == "yes"
        if not accepted_terms:
            flash("You must agree to the Terms of Use and acknowledge the Privacy Notice.", "error")
        elif not name or not email or not phone_number.startswith("268") or len(phone_number) != 11 or len(password) < 6:
            flash("Enter your name, email, Eswatini phone number and a password of at least 6 characters.", "error")
        elif db.session.scalar(select(User).where(User.email == email)):
            flash("An account with that email already exists.", "error")
        elif db.session.scalar(select(User).where(User.phone_number == phone_number)):
            flash("An account with that phone number already exists.", "error")
        else:
            user = User(
                name=name,
                email=email,
                phone_number=phone_number,
                terms_accepted_at=datetime.now(timezone.utc),
                terms_version=current_app.config["TERMS_VERSION"],
                privacy_version=current_app.config["PRIVACY_VERSION"],
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            if request.form.get("invite_token"):
                return invitation_redirect()
            return redirect(url_for("main.setup_wedding"))
    return render_template("auth/register.html", invite_token=request.form.get("invite_token") or request.args.get("invite", ""))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db.session.scalar(select(User).where(User.email == email))
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            if not user.terms_accepted_at:
                token = request.form.get("invite_token") or request.args.get("invite")
                if token:
                    session["post_legal_invite"] = token
                return redirect(url_for("main.accept_legal_terms"))
            return invitation_redirect()
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html", invite_token=request.form.get("invite_token") or request.args.get("invite", ""))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@bp.route("/wedding/setup", methods=["GET", "POST"])
@login_required
def setup_wedding():
    wedding = current_wedding()
    if wedding is not None and wedding.owner_id != current_user.id:
        flash("Only the wedding owner can change the main wedding details.", "error")
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        if wedding is None:
            wedding = Wedding(owner_id=current_user.id)
            db.session.add(wedding)
        wedding.partner_one = request.form.get("partner_one", "").strip()
        wedding.partner_two = request.form.get("partner_two", "").strip()
        wedding.title = f"{wedding.partner_one} & {wedding.partner_two}"
        wedding.location = request.form.get("location", "").strip() or None
        wedding.budget_target = money(request.form.get("budget_target"))
        date_value = request.form.get("wedding_date")
        wedding.wedding_date = datetime.strptime(date_value, "%Y-%m-%d").date() if date_value else None
        if not wedding.partner_one or not wedding.partner_two:
            flash("Please enter both partners' names.", "error")
        else:
            db.session.commit()
            flash("Wedding details saved.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("wedding/setup.html", wedding=wedding)


@bp.route("/account/phone", methods=["GET", "POST"])
@login_required
def account_phone():
    if request.method == "POST":
        phone_number = normalize_phone(request.form.get("phone_number"))
        if not phone_number.startswith("268") or len(phone_number) != 11:
            flash("Enter a valid Eswatini mobile number.", "error")
        else:
            existing = db.session.scalar(select(User).where(User.phone_number == phone_number, User.id != current_user.id))
            if existing:
                flash("That phone number is already linked to another account.", "error")
            else:
                current_user.phone_number = phone_number
                db.session.commit()
                flash("Phone number saved.", "success")
                destination = request.form.get("next")
                if destination == "team":
                    return redirect(url_for("billing.team"))
                if destination and destination.startswith("invite:"):
                    return redirect(url_for("billing.accept_invitation", token=destination.split(":", 1)[1]))
                return redirect(url_for("billing.pricing"))
    return render_template("auth/phone.html", next_step=request.args.get("next", "pricing"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    wedding = current_wedding()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone_number = normalize_phone(request.form.get("phone_number"))
        email_owner = db.session.scalar(select(User).where(User.email == email, User.id != current_user.id))
        phone_owner = db.session.scalar(select(User).where(User.phone_number == phone_number, User.id != current_user.id))
        if not name or not email or not phone_number.startswith("268") or len(phone_number) != 11:
            flash("Enter your name, email and a valid Eswatini mobile number.", "error")
        elif email_owner:
            flash("That email address is already in use.", "error")
        elif phone_owner:
            flash("That phone number is already in use.", "error")
        else:
            current_user.name = name
            current_user.email = email
            current_user.phone_number = phone_number
            db.session.commit()
            flash("Account details updated.", "success")
            return redirect(url_for("main.account"))

    payments = db.session.scalars(
        select(Payment).where(Payment.user_id == current_user.id).order_by(Payment.created_at.desc())
    ).all()
    membership = None
    access_invitation = None
    if wedding and wedding.owner_id != current_user.id:
        membership = db.session.scalar(
            select(WeddingMember).where(
                WeddingMember.wedding_id == wedding.id,
                WeddingMember.user_id == current_user.id,
            )
        )
        access_invitation = db.session.scalar(
            select(Invitation).where(
                Invitation.wedding_id == wedding.id,
                Invitation.accepted_by_user_id == current_user.id,
            )
        )
    return render_template(
        "account.html", wedding=wedding, payments=payments,
        membership=membership, access_invitation=access_invitation,
    )


@bp.get("/account/export")
@login_required
def export_account():
    from .security_logging import security_event
    security_event("account_export", user_id=current_user.id)
    document = BytesIO(json.dumps(
        account_export_payload(current_user), ensure_ascii=False, indent=2
    ).encode("utf-8"))
    return send_file(
        document,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"umshado-account-{current_user.id}.json",
    )


@bp.post("/account/delete")
@login_required
def delete_account():
    if current_user.is_super_admin:
        flash("Transfer or remove the super-admin role before deleting this account.", "error")
        return redirect(url_for("main.account"))
    if request.form.get("confirmation", "").strip().upper() != "DELETE":
        flash("Type DELETE to confirm account deletion.", "error")
        return redirect(url_for("main.account"))
    if not current_user.check_password(request.form.get("password", "")):
        flash("Your password is incorrect. The account was not deleted.", "error")
        return redirect(url_for("main.account"))

    user_id = current_user.id
    from .security_logging import security_event
    security_event("account_deletion", user_id=user_id)
    owned_weddings = db.session.scalars(select(Wedding).where(Wedding.owner_id == user_id)).all()
    for wedding in owned_weddings:
        if wedding.profile_image:
            photo_path = Path(current_app.config["WEDDING_PHOTO_FOLDER"]).parent / wedding.profile_image
            if photo_path.is_file():
                photo_path.unlink()
        db.session.execute(delete(ActivityEvent).where(ActivityEvent.wedding_id == wedding.id))
        db.session.execute(delete(WeddingMember).where(WeddingMember.wedding_id == wedding.id))
        for invitation in list(wedding.invitations):
            has_payment = db.session.scalar(
                select(Payment.id).where(Payment.invitation_id == invitation.id).limit(1)
            ) is not None
            if has_payment:
                invitation.invitee_name = None
                invitation.token = secrets.token_urlsafe(32)
                invitation.status = "archived"
                invitation.accepted_by_user_id = None
            else:
                db.session.delete(invitation)
        for category in list(wedding.categories):
            db.session.delete(category)
        wedding.title = "Deleted wedding project"
        wedding.partner_one = "Deleted"
        wedding.partner_two = "Deleted"
        wedding.wedding_date = None
        wedding.location = None
        wedding.profile_image = None
        wedding.budget_target = Decimal("0")
        wedding.plan_tier = "deleted"

    db.session.execute(delete(WeddingMember).where(WeddingMember.user_id == user_id))
    db.session.execute(update(ActivityEvent).where(
        ActivityEvent.actor_user_id == user_id
    ).values(actor_user_id=None))
    db.session.execute(update(Invitation).where(
        Invitation.accepted_by_user_id == user_id
    ).values(accepted_by_user_id=None))

    current_user.name = "Deleted user"
    current_user.email = f"deleted-{user_id}-{secrets.token_hex(8)}@invalid.umshado"
    current_user.phone_number = None
    current_user.is_admin = False
    current_user.has_test_access = False
    current_user.deleted_at = datetime.now(timezone.utc)
    current_user.set_password(secrets.token_urlsafe(48))
    db.session.commit()
    logout_user()
    flash("Your account and wedding information have been deleted.", "success")
    return redirect(url_for("main.login"))


@bp.route("/wedding/photo", methods=["POST"])
@login_required
def upload_wedding_photo():
    wedding = current_wedding()
    if wedding is None or wedding.owner_id != current_user.id:
        return ("Not found", 404)
    uploaded = request.files.get("profile_image")
    if uploaded is None or not uploaded.filename:
        flash("Choose a photo to upload.", "error")
        return redirect(url_for("main.dashboard"))

    try:
        image = Image.open(uploaded.stream)
        image.verify()
        uploaded.stream.seek(0)
        image = Image.open(uploaded.stream)
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1600, 1600))
        if image.mode not in {"RGB", "L"}:
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        flash("Upload a valid JPG, PNG or WebP image.", "error")
        return redirect(url_for("main.dashboard"))

    folder = Path(current_app.config["WEDDING_PHOTO_FOLDER"]) / str(wedding.id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(12)}.jpg"
    destination = folder / filename
    image.save(destination, "JPEG", quality=88, optimize=True)

    previous = wedding.profile_image
    wedding.profile_image = f"weddings/{wedding.id}/{filename}"
    db.session.commit()
    if previous:
        previous_path = Path(current_app.config["WEDDING_PHOTO_FOLDER"]).parent / previous
        if previous_path.is_file():
            previous_path.unlink()
    flash("Your couple photo has been updated.", "success")
    return redirect(url_for("main.dashboard"))


@bp.get("/wedding/photo")
@login_required
def wedding_photo():
    wedding = current_wedding()
    if wedding is None or not wedding.profile_image:
        return ("Not found", 404)
    relative_path = Path(wedding.profile_image)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return ("Not found", 404)
    photo_path = Path(current_app.config["WEDDING_PHOTO_FOLDER"]).parent / relative_path
    if not photo_path.is_file():
        return ("Not found", 404)
    response = send_file(photo_path, mimetype="image/jpeg", conditional=True)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.route("/dashboard")
@login_required
def dashboard():
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))
    quote_count = sum(len(category.quotations) for category in wedding.categories)
    selected_total = sum((category.selected_amount for category in wedding.categories), start=Decimal("0"))
    remaining = wedding.budget_target - selected_total
    recent_activity = db.session.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.wedding_id == wedding.id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(15)
    ).all()
    return render_template(
        "dashboard.html", wedding=wedding, quote_count=quote_count,
        selected_total=selected_total, remaining=remaining,
        owner_price=Decimal(current_app.config["OWNER_PLAN_PRICE"]),
        stakeholder_price=Decimal(current_app.config["STAKEHOLDER_PRICE"]),
        is_owner=wedding.owner_id == current_user.id,
        recent_activity=recent_activity,
    )


@bp.get("/report")
@login_required
def wedding_report():
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))
    return render_template("wedding/report.html", **report_context(wedding))


@bp.get("/report.pdf")
@login_required
def wedding_report_pdf():
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))
    from .reporting import build_wedding_report

    document = BytesIO()
    build_wedding_report(document, **report_context(wedding))
    document.seek(0)
    safe_title = secure_filename(wedding.title).lower() or "wedding"
    return send_file(
        document,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe_title}-wedding-report.pdf",
    )


@bp.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        free_limit = current_app.config["FREE_BUDGET_ITEM_LIMIT"]
        if not wedding.has_full_feature_access and len(wedding.categories) >= free_limit:
            flash(f"The Free plan includes {free_limit} budget items. Upgrade to add more.", "error")
            return redirect(url_for("billing.pricing"))
        if name:
            db.session.add(BudgetCategory(
                name=name,
                planned_amount=money(request.form.get("planned_amount")),
                wedding_id=wedding.id,
            ))
            activity = add_activity(
                wedding_id=wedding.id,
                actor_user_id=current_user.id,
                kind="budget_item_added",
                message=f"{current_user.name} added {name} to the wedding budget",
            )
            db.session.commit()
            publish_activity(activity)
            flash("Budget item added.", "success")
        else:
            flash("Enter a name for the budget item.", "error")
        return redirect(url_for("main.budget"))
    planned_total = sum((category.planned_amount for category in wedding.categories), start=Decimal("0"))
    chosen_total = sum(
        (category.selected_quote.amount for category in wedding.categories if category.selected_quote),
        start=Decimal("0"),
    )
    return render_template(
        "budget/index.html", wedding=wedding, planned_total=planned_total,
        chosen_total=chosen_total, budget_remaining=wedding.budget_target - chosen_total,
        free_limit=current_app.config["FREE_BUDGET_ITEM_LIMIT"],
        is_owner=wedding.owner_id == current_user.id,
    )


@bp.route("/budget/<int:category_id>/quotes", methods=["GET", "POST"])
@login_required
def quotations(category_id):
    wedding = current_wedding()
    category = db.get_or_404(BudgetCategory, category_id)
    if wedding is None or category.wedding_id != wedding.id:
        return ("Not found", 404)
    if request.method == "POST":
        vendor_name = request.form.get("vendor_name", "").strip()
        amount = money(request.form.get("amount"))
        if not vendor_name or amount <= 0:
            flash("Enter a vendor and a valid quotation amount.", "error")
        else:
            quote = Quotation(
                vendor_name=vendor_name,
                amount=amount,
                contact=request.form.get("contact", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
                category_id=category.id,
            )
            db.session.add(quote)
            activity = add_activity(
                wedding_id=wedding.id,
                actor_user_id=current_user.id,
                kind="quotation_added",
                message=f"{current_user.name} added a {category.name} quotation from {vendor_name}",
            )
            db.session.commit()
            publish_activity(activity)
            flash("Quotation saved.", "success")
            return redirect(url_for("main.quotations", category_id=category.id))
    return render_template("budget/quotations.html", wedding=wedding, category=category)


@bp.route("/quotes/<int:quote_id>/select", methods=["POST"])
@login_required
def select_quote(quote_id):
    quote = db.get_or_404(Quotation, quote_id)
    wedding = current_wedding()
    if wedding is None or quote.category.wedding_id != wedding.id:
        return ("Not found", 404)
    for item in quote.category.quotations:
        item.is_selected = item.id == quote.id
    activity = add_activity(
        wedding_id=wedding.id,
        actor_user_id=current_user.id,
        kind="quotation_selected",
        message=f"{current_user.name} selected {quote.vendor_name} for {quote.category.name}",
    )
    db.session.commit()
    publish_activity(activity)
    flash(f"{quote.vendor_name} selected for {quote.category.name}.", "success")
    return redirect(url_for("main.quotations", category_id=quote.category_id))

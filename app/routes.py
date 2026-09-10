from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from .extensions import db
from .models import BudgetCategory, Quotation, User, Wedding, WeddingMember


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


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard" if current_user.is_authenticated else "main.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone_number = normalize_phone(request.form.get("phone_number"))
        password = request.form.get("password", "")
        if not name or not email or not phone_number.startswith("268") or len(phone_number) != 11 or len(password) < 6:
            flash("Enter your name, email, Eswatini phone number and a password of at least 6 characters.", "error")
        elif db.session.scalar(select(User).where(User.email == email)):
            flash("An account with that email already exists.", "error")
        elif db.session.scalar(select(User).where(User.phone_number == phone_number)):
            flash("An account with that phone number already exists.", "error")
        else:
            user = User(name=name, email=email, phone_number=phone_number)
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


@bp.route("/dashboard")
@login_required
def dashboard():
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))
    quote_count = sum(len(category.quotations) for category in wedding.categories)
    selected_total = sum((category.selected_amount for category in wedding.categories), start=Decimal("0"))
    remaining = wedding.budget_target - selected_total
    return render_template(
        "dashboard.html", wedding=wedding, quote_count=quote_count,
        selected_total=selected_total, remaining=remaining,
        owner_price=Decimal(current_app.config["OWNER_PLAN_PRICE"]),
        stakeholder_price=Decimal(current_app.config["STAKEHOLDER_PRICE"]),
        is_owner=wedding.owner_id == current_user.id,
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
        if wedding.plan_tier == "free" and len(wedding.categories) >= free_limit:
            flash(f"The Free plan includes {free_limit} budget items. Upgrade to add more.", "error")
            return redirect(url_for("billing.pricing"))
        if name:
            db.session.add(BudgetCategory(
                name=name,
                planned_amount=money(request.form.get("planned_amount")),
                wedding_id=wedding.id,
            ))
            db.session.commit()
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
            db.session.add(Quotation(
                vendor_name=vendor_name,
                amount=amount,
                contact=request.form.get("contact", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
                category_id=category.id,
            ))
            db.session.commit()
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
    db.session.commit()
    flash(f"{quote.vendor_name} selected for {quote.category.name}.", "success")
    return redirect(url_for("main.quotations", category_id=quote.category_id))

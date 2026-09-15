import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from mojapos_payments import make_external_ref_id

from .extensions import db
from .activity import add_activity, publish_activity
from .models import Invitation, Payment, WeddingMember
from .payment_gateway import complete_mock_payment
from .payment_logging import payment_event
from .routes import current_wedding



bp = Blueprint("billing", __name__)


def configured_price(key):
    return Decimal(current_app.config[key]).quantize(Decimal("0.01"))


def create_gateway_payment(*, kind, amount, wedding, invitation=None):
    existing = db.session.scalar(
        select(Payment).where(
            Payment.kind == kind,
            Payment.user_id == current_user.id,
            Payment.wedding_id == wedding.id,
            Payment.invitation_id == (invitation.id if invitation else None),
            Payment.status == "pending",
        ).order_by(Payment.created_at.desc())
    )
    if existing:
        payment_event('payment_reused', payment_id=existing.id, ref=existing.external_ref_id,
                      gateway_id=existing.gateway_transaction_id, kind=existing.kind)
        return existing
    payment = Payment(
        external_ref_id=make_external_ref_id(),
        kind=kind,
        amount=amount,
        currency=current_app.config["PAYMENT_CURRENCY"],
        user_id=current_user.id,
        wedding_id=wedding.id,
        invitation_id=invitation.id if invitation else None,
        status="pending",
    )
    db.session.add(payment)
    db.session.commit()  # webhook must be able to find this row before the API call

    gateway = current_app.extensions["mojapos_payments"]
    mode = 'mock' if gateway.service.config.mock_mode else 'live'
    payment_event('payment_created', payment_id=payment.id, ref=payment.external_ref_id,
                  kind=kind, amount=payment.amount, currency=payment.currency, mode=mode)
    payment_event('gateway_request', payment_id=payment.id, ref=payment.external_ref_id, mode=mode)
    result = gateway.service.initiate_payment(
        external_ref_id=payment.external_ref_id,
        amount=payment.amount,
        phone_number=current_user.phone_number,
        message="Wedding Planner access payment",
        note="Wedding Planner subscription",
    )
    if not result.get("success"):
        payment_event('gateway_rejected', payment_id=payment.id, ref=payment.external_ref_id,
                      mode=result.get('mode'), http_status=result.get('http_status'),
                      error_kind=result.get('error_kind'), elapsed_ms=result.get('elapsed_ms'))
        payment.status = "failed"
        payment.failure_reason = result.get("error", "The payment could not be started.")[:255]
        db.session.commit()
        return payment

    payment.gateway_transaction_id = result.get("gateway_transaction_id")
    payment.provider_reference = result.get("provider_reference")
    db.session.commit()
    payment_event('gateway_accepted', payment_id=payment.id, ref=payment.external_ref_id,
                  mode=result.get('mode'), http_status=result.get('http_status'),
                  gateway_id=payment.gateway_transaction_id, elapsed_ms=result.get('elapsed_ms'))
    complete_mock_payment(payment)
    return payment


@bp.route("/pricing")
@login_required
def pricing():
    wedding = current_wedding()
    return render_template(
        "billing/pricing.html", wedding=wedding,
        owner_price=configured_price("OWNER_PLAN_PRICE"),
        stakeholder_price=configured_price("STAKEHOLDER_PRICE"),
        free_limit=current_app.config["FREE_BUDGET_ITEM_LIMIT"],
    )


@bp.route("/billing/upgrade", methods=["POST"])
@login_required
def upgrade():
    wedding = current_wedding()
    if wedding is None or wedding.owner_id != current_user.id:
        return ("Not found", 404)
    if wedding.plan_tier == "standard":
        flash("This wedding is already on the Standard plan.", "info")
        return redirect(url_for("main.dashboard"))
    if not current_user.phone_number:
        flash("Add your MoMo phone number before starting payment.", "info")
        return redirect(url_for("main.account_phone", next="pricing"))
    payment = create_gateway_payment(
        kind="owner_upgrade", amount=configured_price("OWNER_PLAN_PRICE"), wedding=wedding
    )
    return redirect(url_for("billing.payment_status", payment_id=payment.id))


@bp.route("/team", methods=["GET", "POST"])
@login_required
def team():
    wedding = current_wedding()
    if wedding is None or wedding.owner_id != current_user.id:
        return ("Not found", 404)
    if wedding.plan_tier != "standard":
        flash("Upgrade to Standard before inviting stakeholders.", "error")
        return redirect(url_for("billing.pricing"))

    if request.method == "POST":
        payer = request.form.get("payer")
        if payer not in {"owner", "invitee"}:
            flash("Choose who will pay the stakeholder access fee.", "error")
            return redirect(url_for("billing.team"))
        if payer == "owner" and not current_user.phone_number:
            flash("Add your MoMo phone number before paying for an invitation.", "info")
            return redirect(url_for("main.account_phone", next="team"))
        role = request.form.get("role", "stakeholder")
        if role not in {"partner", "matron_of_honour", "family_friend", "stakeholder"}:
            role = "stakeholder"
        invitation = Invitation(
            token=secrets.token_urlsafe(32),
            wedding_id=wedding.id,
            invited_by_user_id=current_user.id,
            invitee_name=request.form.get("invitee_name", "").strip() or None,
            role=role,
            payer=payer,
            status="awaiting_payment" if payer == "owner" else "pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.session.add(invitation)
        db.session.commit()
        if payer == "owner":
            payment = create_gateway_payment(
                kind="owner_pays_invite",
                amount=configured_price("STAKEHOLDER_PRICE"),
                wedding=wedding,
                invitation=invitation,
            )
            return redirect(url_for("billing.payment_status", payment_id=payment.id))
        flash("Invitation created. Share the link with your stakeholder.", "success")
        return redirect(url_for("billing.team"))

    return render_template(
        "billing/team.html", wedding=wedding,
        stakeholder_price=configured_price("STAKEHOLDER_PRICE"),
    )


@bp.route("/invite/<token>")
def accept_invitation(token):
    invitation = db.session.scalar(select(Invitation).where(Invitation.token == token))
    if invitation is None:
        return render_template("billing/invitation.html", invitation=None), 404
    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expired = expires_at < now
    already_member = False
    if current_user.is_authenticated:
        already_member = db.session.scalar(
            select(WeddingMember).where(
                WeddingMember.wedding_id == invitation.wedding_id,
                WeddingMember.user_id == current_user.id,
            )
        ) is not None
    return render_template(
        "billing/invitation.html", invitation=invitation, expired=expired,
        already_member=already_member,
        stakeholder_price=configured_price("STAKEHOLDER_PRICE"),
    )


@bp.route("/invite/<token>/join", methods=["POST"])
@login_required
def join_invitation(token):
    invitation = db.session.scalar(select(Invitation).where(Invitation.token == token))
    if invitation is None or invitation.status not in {"pending", "paid"}:
        flash("This invitation is no longer available.", "error")
        return redirect(url_for("main.dashboard"))
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        flash("This invitation has expired. Ask the wedding owner for a new link.", "error")
        return redirect(url_for("billing.accept_invitation", token=token))
    if invitation.wedding.owner_id == current_user.id:
        flash("The wedding owner cannot join through their own invitation.", "error")
        return redirect(url_for("main.dashboard"))

    if invitation.payer == "owner":
        if invitation.status != "paid":
            flash("The access payment is still pending.", "error")
            return redirect(url_for("billing.accept_invitation", token=token))
        existing = db.session.scalar(
            select(WeddingMember).where(
                WeddingMember.wedding_id == invitation.wedding_id,
                WeddingMember.user_id == current_user.id,
            )
        )
        if existing is None:
            db.session.add(WeddingMember(
                wedding_id=invitation.wedding_id, user_id=current_user.id, role=invitation.role
            ))
        invitation.status = "accepted"
        invitation.accepted_by_user_id = current_user.id
        invitation.accepted_at = datetime.now(timezone.utc)
        role_label = invitation.role.replace("_", " ").title()
        activity = add_activity(
            wedding_id=invitation.wedding_id,
            actor_user_id=current_user.id,
            kind="member_joined",
            message=f"{role_label} {current_user.name} has joined the wedding project",
        )
        db.session.commit()
        publish_activity(activity)
        flash("You have joined the wedding project.", "success")
        return redirect(url_for("main.dashboard"))

    if not current_user.phone_number:
        flash("Add your MoMo phone number before starting payment.", "info")
        return redirect(url_for("main.account_phone", next=f"invite:{token}"))

    payment = create_gateway_payment(
        kind="invitee_pays_invite",
        amount=configured_price("STAKEHOLDER_PRICE"),
        wedding=invitation.wedding,
        invitation=invitation,
    )
    return redirect(url_for("billing.payment_status", payment_id=payment.id))


@bp.route("/billing/payments/<int:payment_id>")
@login_required
def payment_status(payment_id):
    payment = db.get_or_404(Payment, payment_id)
    if payment.user_id != current_user.id:
        return ("Not found", 404)
    return render_template("billing/payment_status.html", payment=payment)

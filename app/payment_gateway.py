from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app
from sqlalchemy import select, update

from mojapos_payments import MojaposConfig, MojaposPayments, PaymentHandler, PaymentRecord

from .extensions import db
from .models import Invitation, Payment, WeddingMember
from .payment_logging import payment_event


def _decimal(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


class WeddingPaymentHandler(PaymentHandler):
    def get_payment(self, external_ref_id):
        row = db.session.scalar(select(Payment).where(Payment.external_ref_id == external_ref_id))
        if row is None:
            return None
        return PaymentRecord(
            external_ref_id=row.external_ref_id,
            kind=row.kind,
            amount=float(row.amount),
            status=row.status,
            gateway_transaction_id=row.gateway_transaction_id,
            metadata={
                "payment_id": row.id,
                "user_id": row.user_id,
                "wedding_id": row.wedding_id,
                "invitation_id": row.invitation_id,
            },
        )

    def on_payment_completed(self, record, webhook):
        row = db.session.scalar(select(Payment).where(Payment.external_ref_id == record.external_ref_id))
        if row is None or row.status != "pending":
            return

        if _decimal(webhook.amount) != row.amount or (webhook.currency and webhook.currency != row.currency):
            row.status = "review"
            row.failure_reason = "Gateway amount or currency did not match the expected payment."
            db.session.commit()
            payment_event('callback_review', payment_id=row.id, ref=row.external_ref_id,
                          reason='amount_or_currency_mismatch')
            return

        claimed = db.session.execute(
            update(Payment)
            .where(Payment.id == row.id, Payment.status == "pending")
            .values(
                status="completed",
                gateway_transaction_id=webhook.gateway_transaction_id,
                provider_reference=webhook.provider_reference,
                completed_at=datetime.now(timezone.utc),
            )
        )
        if claimed.rowcount != 1:
            db.session.rollback()
            return

        if row.kind == "owner_upgrade":
            row.wedding.plan_tier = "standard"
            row.wedding.upgraded_at = datetime.now(timezone.utc)
        elif row.kind in {"owner_pays_invite", "invitee_pays_invite"}:
            invitation = row.invitation
            if invitation is None:
                db.session.rollback()
                return
            if row.kind == "owner_pays_invite":
                invitation.status = "paid"
            else:
                invitation.status = "accepted"
                invitation.accepted_by_user_id = row.user_id
                invitation.accepted_at = datetime.now(timezone.utc)
                self._ensure_member(invitation.wedding_id, row.user_id, invitation.role)
        db.session.commit()
        payment_event('callback_completed', payment_id=row.id, ref=row.external_ref_id, kind=row.kind)

    def on_payment_failed(self, record, webhook):
        db.session.execute(
            update(Payment)
            .where(Payment.external_ref_id == record.external_ref_id, Payment.status == "pending")
            .values(status="failed", failure_reason="Payment was declined or cancelled.")
        )
        db.session.commit()
        payment_event('callback_failed', ref=record.external_ref_id)

    @staticmethod
    def _ensure_member(wedding_id, user_id, role="stakeholder"):
        existing = db.session.scalar(
            select(WeddingMember).where(
                WeddingMember.wedding_id == wedding_id,
                WeddingMember.user_id == user_id,
            )
        )
        if existing is None:
            db.session.add(WeddingMember(wedding_id=wedding_id, user_id=user_id, role=role))


def build_gateway():
    return MojaposPayments(MojaposConfig.from_env(), handler=WeddingPaymentHandler())


def complete_mock_payment(payment):
    """Complete only explicitly enabled mock payments; production always waits for a webhook."""
    gateway = current_app.extensions["mojapos_payments"]
    if not gateway.service.config.mock_mode or not current_app.config["MOJAPOS_MOCK_AUTO_COMPLETE"]:
        return
    record = gateway.handler.get_payment(payment.external_ref_id)
    if record is None:
        return

    class MockWebhook:
        amount = float(payment.amount)
        currency = payment.currency
        gateway_transaction_id = payment.gateway_transaction_id
        provider_reference = "mock"

    gateway.handler.on_payment_completed(record, MockWebhook())

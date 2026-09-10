"""Contract types between the blueprint and the host application.

The blueprint is 100% database-agnostic: the host implements `PaymentHandler`
against its own ORM/models and the blueprint never imports a host table.
"""
from dataclasses import dataclass, field
from typing import Optional


class MojaposError(Exception):
    """Raised for blueprint misuse or unrecoverable gateway errors."""


@dataclass
class PaymentRecord:
    """The *host's* payment/order row, expressed in blueprint terms.

    The host's `get_payment()` returns one of these (typically built from its
    own DB row). `status` MUST reflect the persisted value so that duplicate
    webhooks are detected before any side effect runs.
    """
    external_ref_id: str                 # our uuid4 hex sent as metadata.externalId
    kind: str                            # 'topup' | 'entry_fee' | 'payout' | anything the host defines
    amount: float
    status: str = 'pending'              # pending | completed | failed
    gateway_transaction_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PaymentWebhook:
    """A MojaPOS webhook normalised into one flat, typed object.

    Handles both the real *enveloped* payload (everything under `data`, our ref
    inside `data.providerResponse.externalId`, amount as a STRING like '1.00')
    and the legacy flat payload (top-level keys + `metadata`).
    """
    event: str
    status: str                          # completed | failed | pending
    gateway_transaction_id: str
    provider_reference: Optional[str]
    external_ref_id: Optional[str]
    amount: float
    currency: Optional[str]
    payer_phone: Optional[str]
    raw: dict


class PaymentHandler:
    """Host adapter -- implement these four methods with your own models.

    Recommended shape (see the README and `example/demo_app.py`):

      * topup   -> on_payment_completed credits the user's wallet (idempotent)
      * entry_fee -> on_payment_completed registers the tournament participant
      * payout  -> on_payment_completed marks the payout/withdrawal as paid

    Idempotency contract: `get_payment()` reads persisted state. If the record
    is already 'completed' the blueprint ignores the webhook before calling
    `on_payment_completed`. Inside the callback you should still guard with a
    conditional update (e.g. WHERE status='pending') as belt-and-braces.
    """

    def get_payment(self, external_ref_id: str) -> Optional[PaymentRecord]:
        """Return the host payment with this external_ref_id, or None.

        Never credit anything for an unknown reference.
        """
        raise NotImplementedError

    def on_payment_completed(self, record: PaymentRecord, webhook: PaymentWebhook) -> None:
        """MojaPOS reports the payment as successful. Persist the side effect."""
        raise NotImplementedError

    def on_payment_failed(self, record: PaymentRecord, webhook: PaymentWebhook) -> None:
        """MojaPOS reports the payment as failed. Mark the record failed."""
        raise NotImplementedError


def make_external_ref_id() -> str:
    """Strong reference we hand to MojaPOS and use to match webhooks back.

    Real webhooks only echo this id (as data.providerResponse.externalId), so it
    is the single source of truth for finding the host payment row.
    """
    import uuid
    return uuid.uuid4().hex[:12]


def coerce_amount(raw) -> float:
    """Webhooks deliver amount as a string ('1.00') -- coerce defensively."""
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0

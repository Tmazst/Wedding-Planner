"""MojaPOS Payment Blueprint -- a drop-in, DB-agnostic gateway integration.

Two-minute wiring in any Flask app:

    from mojapos_payments import MojaposConfig, MojaposPayments

    config = MojaposConfig.from_env()                 # reads MOJAPOS_* env vars
    payments = MojaposPayments(config, handler=MyPaymentHandler())

    app = Flask(__name__)
    payments.init_app(app)

    # Done: POST {callback_url} is live, plus payments.service is ready to use.
    # A runnable reference implementation lives in example/demo_app.py.

See the README for the full guide (wallet-first topup, entry fees, payouts).
"""
import re

from flask import Blueprint, jsonify, request

from . import signatures
from .config import MojaposConfig
from .payments import (
    MojaposError,
    PaymentHandler,
    PaymentRecord,
    PaymentWebhook,
    coerce_amount,
    make_external_ref_id,
)
from .service import MojaposService

__all__ = [
    'MojaposConfig',
    'MojaposPayments',
    'MojaposService',
    'MojaposError',
    'PaymentHandler',
    'PaymentRecord',
    'PaymentWebhook',
    'make_external_ref_id',
]

__version__ = '1.0.0'


class MojaposPayments:
    """Facade that bundles config + gateway client + webhook callback.

    The callback blueprint is registered per Flask app through `init_app`, which
    keeps it usable in blueprinted/application-factory projects.
    """

    def __init__(self, config=None, handler=None, callback_path=None):
        self.config = config if config is not None else MojaposConfig.from_env()
        if isinstance(self.config, dict):
            self.config = MojaposConfig(**self.config)
        if callback_path is not None:
            self.config.callback_path = callback_path
        self.service = MojaposService(self.config)
        self.handler = handler
        self._registered_apps = set()

    # ------------------------------------------------------------- setup ---

    def init_app(self, app, handler=None):
        """Register the webhook route and stash this instance on the app."""
        if handler is not None:
            self.handler = handler
        if self.handler is None or not isinstance(self.handler, PaymentHandler):
            raise MojaposError(
                'A PaymentHandler is required. Pass one to MojaposPayments(...) '
                'or init_app(app, handler=...).'
            )

        if id(app) in self._registered_apps:
            return self

        app.extensions.setdefault('mojapos_payments', self)
        blueprint = Blueprint(
            'mojapos_payments',
            __name__,
            url_prefix=self.config.callback_path.rstrip('/'),
        )

        @blueprint.route('', methods=['POST'])
        @blueprint.route('/', methods=['POST'])
        def mojapos_callback():
            return self.handle_webhook()

        app.register_blueprint(blueprint)
        self._registered_apps.add(id(app))
        print(f'[mojapos] webhook callback registered at POST {self.config.callback_path}')
        return self
    # ------------------------------------------------------ webhook handling

    def handle_webhook(self):
        """Entry point for MojaPOS callbacks.

        Proven against the real production payload shape:

            { 'event': 'payment.success',
              'data': { 'transactionId': ..., 'status': 'COMPLETED',
                        'amount': '1.00', 'providerResponse':
                          { 'externalId': '<our ref>', 'payer': {...}, ... } } }

        Flow: verify signature (optional) -> normalise -> find host payment by
        external_ref_id -> NEVER credit an unknown reference -> dispatch to the
        host PaymentHandler -> return HTTP 200 so MojaPOS stops retrying.
        """
        payload = request.get_json(silent=True) or {}
        if not payload:
            return jsonify({'status': 'error', 'error': 'missing payload'}), 400

        if self.config.verify_webhook:
            if not self.config.webhook_secret:
                print('[mojapos] verify_webhook enabled but MOJAPOS_WEBHOOK_SECRET is empty')
                return jsonify({'status': 'error', 'error': 'server not configured to verify'}), 500
            signature = (
                request.headers.get('X-Signature')
                or request.headers.get('X-Mojapos-Signature')
                or ''
            )
            if not signature or not signatures.verify_signature(payload, signature, self.config.webhook_secret):
                print('[mojapos] webhook signature invalid')
                return jsonify({'status': 'error', 'error': 'invalid signature'}), 401

        try:
            webhook = self._normalise(payload)
        except MojaposError as exc:
            return jsonify({'status': 'error', 'error': str(exc)}), 400

        # Match the webhook to a host payment record. Real payloads carry no
        # user/type information -- only our external_ref_id, echoed back.
        record = None
        if webhook.external_ref_id:
            try:
                record = self.handler.get_payment(webhook.external_ref_id)
            except Exception as exc:  # host lookup must not crash the callback
                print(f'[mojapos] handler.get_payment raised: {exc}')
                record = None

        if record is None:
            print(f'[mojapos] no host payment for externalId={webhook.external_ref_id} - ignoring (never credit blindly)')
            return jsonify({'status': 'received'}), 200

        # Duplicate / late deliveries are safe to drop.
        if record.status == 'completed' and webhook.status == 'completed':
            print(f'[mojapos] duplicate completed webhook for {webhook.external_ref_id} - ignoring')
            return jsonify({'status': 'received'}), 200

        try:
            if webhook.status == 'completed':
                record.status = 'completed'
                record.gateway_transaction_id = webhook.gateway_transaction_id
                self.handler.on_payment_completed(record, webhook)
            elif webhook.status == 'failed':
                record.status = 'failed'
                self.handler.on_payment_failed(record, webhook)
            else:  # pending / other -> acknowledge but do nothing yet
                print(f'[mojapos] non-final status {webhook.status!r} acknowledged')
        except Exception as exc:  # handler failure should not crash MojaPOS's retry
            print(f'[mojapos] handler raised during dispatch: {exc}')
            return jsonify({'status': 'error', 'error': 'handler failed'}), 500

        return jsonify({'status': 'received'}), 200

    # ------------------------------------------------------------ helpers ---

    def _normalise(self, payload) -> PaymentWebhook:
        """Turn any payload shape we have ever seen into one typed object."""
        data = payload.get('data') or payload
        if not isinstance(data, dict):
            raise MojaposError('payload has no data object')
        provider_response = data.get('providerResponse') or {}
        metadata = payload.get('metadata') or data.get('metadata') or {}

        event = str(payload.get('event') or '').lower()
        if 'success' in event:
            status = 'completed'
        elif 'fail' in event:
            status = 'failed'
        else:
            status = str(data.get('status') or payload.get('status') or 'pending').lower()
            if status in ('successful', 'success', 'paid'):
                status = 'completed'

        gateway_id = data.get('transactionId') or payload.get('transactionId') or payload.get('transaction_id')
        if not gateway_id:
            raise MojaposError('missing transactionId in webhook')

        external_ref_id = (
            provider_response.get('externalId')
            or data.get('externalId')
            or metadata.get('externalId')
            or metadata.get('external_ref_id')
        )

        payer = provider_response.get('payer') or {}
        return PaymentWebhook(
            event=event,
            status=status,
            gateway_transaction_id=str(gateway_id),
            provider_reference=data.get('providerReference') or payload.get('providerReference'),
            external_ref_id=str(external_ref_id) if external_ref_id else None,
            amount=coerce_amount(data.get('amount') or payload.get('amount')),
            currency=data.get('currency') or payload.get('currency'),
            payer_phone=payer.get('partyId') or data.get('phoneNumber'),
            raw=payload,
        )

    # ---------------------------------------------------- initiate helpers --

    def begin_topup(self, *, user_id, amount, phone_number, kind='topup',
                    description='Wallet top-up', **extra_metadata) -> dict:
        """Reference helper -- the host usually inlines this against its ORM.

        Builds a pending PaymentRecord + gateway request. The host is
        responsible for PERSISTING the pending record (with its own id) BEFORE
        the gateway returns, otherwise a fast webhook cannot be matched.
        Returns {'record': ..., 'gateway': {...}}.
        """
        record = PaymentRecord(
            external_ref_id=make_external_ref_id(),
            kind=kind,
            amount=float(amount),
            status='pending',
            metadata={'user_id': user_id, 'note': description, **extra_metadata},
        )
        result = self.service.initiate_payment(
            external_ref_id=record.external_ref_id,
            amount=amount,
            phone_number=phone_number,
            message=description,
            note=description,
        )
        if result.get('success'):
            record.gateway_transaction_id = result.get('gateway_transaction_id')
        return {'record': record, 'gateway': result}


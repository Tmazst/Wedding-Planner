"""MojaPOS HTTP client -- no Flask dependency.

`MojaposService` talks to the gateway using a config object, so it can be used
standalone (scripts, tasks) or through the `MojaposPayments` facade. Set
`mock_mode=True` in development to avoid hitting the live gateway.
"""
import requests

from . import signatures
from .config import MojaposConfig
from .payments import MojaposError


class MojaposService:
    def __init__(self, config):
        self.config = config if isinstance(config, MojaposConfig) else MojaposConfig(**config)
        self._session = requests.Session()

    # ------------------------------------------------------------------ # 

    def initiate_payment(self, *, external_ref_id, amount, phone_number,
                         message, note=None, provider=None):
        """Ask MojaPOS to collect `amount` from `phone_number`.

        This single call covers topups and entry fees -- the only difference is
        the human-readable message. Payouts use `payout()` below.

        Returns a dict:
            success=True  -> {success, gateway_transaction_id, provider_reference,
                              status, payment_url}
            success=False -> {success, error}
        """
        print("[TEST PAY]--Payment Initiated, CONFIG--",self.config.mock_mode)
        if self.config.mock_mode:

            return {
                'success': True,
                'gateway_transaction_id': f'mock_{external_ref_id}',
                'provider_reference': None,
                'payment_url': None,
                'status': 'PENDING',
            }

        payload = {
            'provider': provider or self.config.provider,
            'amount': float(amount),
            'currency': self.config.currency,
            'phoneNumber': str(phone_number),
            'metadata': {
                'externalId': external_ref_id,
                'payerMessage': message,
                'payeeNote': note or message,
            },
        }
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.config.api_key}',
        }
        # Optional request signing. Only enabled if the gateway advertises it;
        # see signatures.py for the scheme.
        if self.config.api_key and self.config.webhook_secret:
            headers['X-Signature'] = signatures.sign_payload(payload, self.config.webhook_secret)

        try:
            response = self._session.post(
                self.config.initiate_url, json=payload, headers=headers, timeout=20
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            print(f'[mojapos] initiate error: {exc}')
            return {'success': False, 'error': str(exc)}

        try:
            body = response.json() or {}
        except ValueError:
            body = {}

        gateway_id = body.get('transactionId') or body.get('id')
        if gateway_id:
            return {
                'success': True,
                'gateway_transaction_id': gateway_id,
                'provider_reference': body.get('providerReference'),
                'payment_url': body.get('paymentUrl') or body.get('payment_url'),
                'status': body.get('status', 'PENDING'),
            }
        return {'success': False, 'error': body.get('message') or body.get('error') or 'gateway did not return a transactionId'}

    def payout(self, *, external_ref_id, amount, phone_number, message, note=None, provider=None):
        """Payout variant. MojaPOS may route payouts to a separate endpoint --
        point MojaposConfig.initiate_path (or subclass) at it.

        NOTE: confirm the exact payout URL + payload keys with the MojaPOS API
        docs for your contract; this mirrors the initiate payload for parity.
        """
        if self.config.mock_mode:
            return {
                'success': True,
                'gateway_transaction_id': f'mock_payout_{external_ref_id}',
                'provider_reference': None,
                'payment_url': None,
                'status': 'PENDING',
            }
        return self.initiate_payment(
            external_ref_id=external_ref_id, amount=amount, phone_number=phone_number,
            message=message, note=note, provider=provider,
        )

    def get_transaction_status(self, gateway_transaction_id):
        """Poll a payment's status. Endpoint per MojaPOS docs; adjust to taste."""
        if self.config.mock_mode:
            return {'status': 'completed'}
        headers = {'Authorization': f'Bearer {self.config.api_key}'}
        url = f"{self.config.api_url}/payments/pay/{gateway_transaction_id}"
        try:
            response = self._session.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            print(f'[mojapos] status lookup error: {exc}')
            return {'status': 'unknown', 'error': str(exc)}

"""MojaPOS gateway configuration.

Everything can be supplied from environment variables, so wiring into any host
project is just a matter of exporting the right values. No Flask dependency:
the config object is passed to the service / blueprint directly.
"""
import os


class MojaposConfig:
    """Runtime configuration for one MojaPOS integration.

    Args mirror the environment variables used in production:

        MOJAPOS_API_URL                  base URL, e.g. https://mojapos.com/api
        MOJAPOS_API_KEY                  your gateway bearer token
        MOJAPOS_WEBHOOK_SECRET           shared secret used to sign webhooks
        MOJAPOS_VERIFY_WEBHOOK_SIGNATURE true/1 to require a valid webhook signature
        MOJAPOS_MOCK_MODE                true/1 to fake gateway calls (no HTTP)
        MOJAPOS_PROVIDER                 default provider key, e.g. MTN_MOMO
        MOJAPOS_CURRENCY                 currency code, e.g. SZL
    """

    def __init__(self, api_url=None, api_key=None, webhook_secret=None,
                 verify_webhook=False, mock_mode=False, provider='MTN_MOMO',
                 currency='SZL', initiate_path='/payments/pay',
                 callback_path='/api/payment/callback'):
        self.api_url = (api_url or os.environ.get('MOJAPOS_API_URL', 'https://mojapos.com/api')).rstrip('/')
        self.api_key = api_key or os.environ.get('MOJAPOS_API_KEY', '') or ''
        self.webhook_secret = webhook_secret or os.environ.get('MOJAPOS_WEBHOOK_SECRET', '') or ''
        self.verify_webhook = bool(verify_webhook)
        self.mock_mode = bool(mock_mode)
        self.provider = provider
        self.currency = currency
        self.initiate_path = initiate_path
        self.callback_path = callback_path or '/api/payment/callback'

    @property
    def initiate_url(self):
        return f'{self.api_url}{self.initiate_path}'

    @classmethod
    def from_env(cls, **overrides):
        """Build a config from environment variables (optionally overriding keys)."""
        env = os.environ
        cfg = cls(
            api_url=env.get('MOJAPOS_API_URL'),
            api_key=env.get('MOJAPOS_API_KEY'),
            webhook_secret=env.get('MOJAPOS_WEBHOOK_SECRET'),
            verify_webhook=env.get('MOJAPOS_VERIFY_WEBHOOK_SIGNATURE', 'false').lower() in ('1', 'true', 'yes', 'on'),
            mock_mode=env.get('MOJAPOS_MOCK_MODE', 'false').lower() in ('1', 'true', 'yes', 'on'),
            provider=env.get('MOJAPOS_PROVIDER', 'MTN_MOMO'),
            currency=env.get('MOJAPOS_CURRENCY', 'SZL'),
            initiate_path=env.get('MOJAPOS_INITIATE_PATH', '/payments/pay'),
            callback_path=env.get('MOJAPOS_CALLBACK_PATH', '/api/payment/callback'),
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

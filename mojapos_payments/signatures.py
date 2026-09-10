"""HMAC-SHA256 request / webhook signatures.

MojaPOS's exact signing scheme is still being confirmed on the gateway side.
These helpers implement the standard *canonical-JSON + HMAC-SHA256* scheme this
blueprint uses between its own service and callback; if MojaPOS later publishes
a different algorithm, only the two functions below need to change.

The callback only enforces signatures when MojaposConfig.verify_webhook is
enabled -- until then it accepts unsigned webhooks so you can test with MojaPOS's
dashboard "resend" button.
"""
import hashlib
import hmac
import json


def canonical_json(payload) -> str:
    """Deterministic JSON so both sides hash the exact same bytes."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)


def sign_payload(payload, secret: str) -> str:
    return hmac.new(str(secret).encode('utf-8'),
                    canonical_json(payload).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def verify_signature(payload, provided: str, secret: str) -> bool:
    if not provided or not secret:
        return False
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, provided.lower())

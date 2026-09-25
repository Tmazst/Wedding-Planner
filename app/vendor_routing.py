"""Route shared vendor accounts to the vendor area instead of wedding setup."""

import requests
from flask import redirect, request, session, url_for
from flask_login import current_user

from .shared_vendors import _account_enabled, _vendor_account_lookup


_VENDOR_ROLE_USER_KEY = "shared_vendor_role_user_id"
_VENDOR_ROLE_VALUE_KEY = "shared_vendor_role_is_vendor"


def route_vendor_accounts():
    """Keep Umcimby vendors out of the wedding-owner setup flow.

    Umcimby remains the source of truth for vendor status. We only check when an
    authenticated user is about to enter the wedding dashboard/setup flow, then
    cache the answer for that logged-in browser session.
    """
    if request.endpoint not in {"main.dashboard", "main.setup_wedding"}:
        return None
    if not current_user.is_authenticated or not _account_enabled():
        return None

    cached_user_id = session.get(_VENDOR_ROLE_USER_KEY)
    if cached_user_id == current_user.id and _VENDOR_ROLE_VALUE_KEY in session:
        is_vendor = bool(session.get(_VENDOR_ROLE_VALUE_KEY))
    else:
        try:
            account = _vendor_account_lookup()
        except (requests.RequestException, ValueError, RuntimeError):
            # If Umcimby is temporarily unavailable, do not break normal UMSHADO
            # access. The vendor account page itself will show service errors.
            return None
        is_vendor = bool(account.get("exists") and account.get("is_vendor"))
        session[_VENDOR_ROLE_USER_KEY] = current_user.id
        session[_VENDOR_ROLE_VALUE_KEY] = is_vendor

    if is_vendor:
        return redirect(url_for("shared_vendors.vendor_account"))
    return None

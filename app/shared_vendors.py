import requests

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required


bp = Blueprint("shared_vendors", __name__, url_prefix="/vendors")


def _enabled():
    return (
        current_app.config.get("VENDOR_FEATURE_ENABLED", False)
        and current_app.config.get("VENDOR_DIRECTORY_ENABLED", False)
    )


def _api_get(path, params=None):
    base_url = current_app.config.get("VENDOR_API_BASE_URL", "")
    api_key = current_app.config.get("VENDOR_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("Shared vendor service is not configured.")
    response = requests.get(
        f"{base_url}{path}",
        params=params,
        headers={"X-Vendor-API-Key": api_key},
        timeout=current_app.config.get("VENDOR_API_TIMEOUT_SECONDS", 5),
    )
    response.raise_for_status()
    return response.json()


@bp.get("")
@login_required
def directory():
    if not _enabled():
        return ("Not found", 404)
    query = request.args.get("q", "").strip()
    vendors = []
    service_error = None
    try:
        payload = _api_get("/api/vendors", {"q": query} if query else None)
        vendors = payload.get("vendors", [])
    except (requests.RequestException, ValueError, RuntimeError):
        service_error = "The vendor directory is temporarily unavailable. Manual quotation entry still works normally."
    return render_template(
        "vendors/directory.html",
        vendors=vendors,
        query=query,
        service_error=service_error,
        quotation_integration_enabled=current_app.config.get(
            "VENDOR_QUOTATION_INTEGRATION_ENABLED", False
        ),
    )


@bp.get("/<int:store_id>")
@login_required
def detail(store_id):
    if not _enabled():
        return ("Not found", 404)
    try:
        vendor = _api_get(f"/api/vendors/{store_id}")
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return ("Not found", 404)
        return render_template("vendors/unavailable.html"), 503
    except (requests.RequestException, ValueError, RuntimeError):
        return render_template("vendors/unavailable.html"), 503
    return render_template(
        "vendors/detail.html",
        vendor=vendor,
        quotation_integration_enabled=current_app.config.get(
            "VENDOR_QUOTATION_INTEGRATION_ENABLED", False
        ),
    )

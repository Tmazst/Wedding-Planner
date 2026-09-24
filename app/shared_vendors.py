from decimal import Decimal, InvalidOperation

import requests
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .activity import add_activity, publish_activity
from .extensions import db
from .models import BudgetCategory, Quotation


bp = Blueprint("shared_vendors", __name__, url_prefix="/vendors")


def _enabled():
    return (
        current_app.config.get("VENDOR_FEATURE_ENABLED", False)
        and current_app.config.get("VENDOR_DIRECTORY_ENABLED", False)
    )


def _account_enabled():
    return (
        current_app.config.get("VENDOR_FEATURE_ENABLED", False)
        and current_app.config.get("VENDOR_ACCOUNT_INTEGRATION_ENABLED", False)
    )


def _api_headers():
    api_key = current_app.config.get("VENDOR_API_KEY")
    if not api_key:
        raise RuntimeError("Shared vendor service is not configured.")
    return {"X-Vendor-API-Key": api_key}


def _api_url(path):
    base_url = current_app.config.get("VENDOR_API_BASE_URL", "")
    if not base_url:
        raise RuntimeError("Shared vendor service is not configured.")
    return f"{base_url}{path}"


def _api_get(path, params=None):
    response = requests.get(
        _api_url(path),
        params=params,
        headers=_api_headers(),
        timeout=current_app.config.get("VENDOR_API_TIMEOUT_SECONDS", 5),
    )
    response.raise_for_status()
    return response.json()


def _api_post(path, payload):
    response = requests.post(
        _api_url(path),
        json=payload,
        headers=_api_headers(),
        timeout=current_app.config.get("VENDOR_API_TIMEOUT_SECONDS", 5),
    )
    if response.status_code >= 400:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {}
        message = error_payload.get("error") or "Vendor service request failed."
        error = requests.HTTPError(message, response=response)
        raise error
    return response.json()


def _vendor_account_lookup():
    return _api_post("/api/vendors/accounts/lookup", {
        "email": current_user.email,
        "phone_number": current_user.phone_number,
        "phone_country": current_user.phone_country,
    })


def _product_from_vendor(vendor, product_id):
    return next(
        (product for product in vendor.get("products", []) if int(product.get("id", -1)) == product_id),
        None,
    )


def _product_notes(product):
    parts = [product.get("name") or "Vendor product"]
    if product.get("description"):
        parts.append(product["description"])
    if product.get("price_unit"):
        parts.append(f"Unit: {product['price_unit']}")
    return " · ".join(parts)


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
        account_integration_enabled=_account_enabled(),
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

    wedding = None
    categories = []
    quotation_enabled = current_app.config.get("VENDOR_QUOTATION_INTEGRATION_ENABLED", False)
    if quotation_enabled:
        from .routes import current_wedding
        wedding = current_wedding()
        categories = wedding.categories if wedding is not None else []

    return render_template(
        "vendors/detail.html",
        vendor=vendor,
        wedding=wedding,
        categories=categories,
        quotation_integration_enabled=quotation_enabled,
    )


@bp.post("/<int:store_id>/products/<int:product_id>/quotation")
@login_required
def add_product_to_quotation(store_id, product_id):
    if not _enabled() or not current_app.config.get("VENDOR_QUOTATION_INTEGRATION_ENABLED", False):
        return ("Not found", 404)

    from .routes import current_wedding
    wedding = current_wedding()
    if wedding is None:
        return redirect(url_for("main.setup_wedding"))

    category_id = request.form.get("category_id", type=int)
    category = db.session.get(BudgetCategory, category_id) if category_id else None
    if category is None or category.wedding_id != wedding.id:
        flash("Choose a wedding budget item first.", "error")
        return redirect(url_for("shared_vendors.detail", store_id=store_id))

    try:
        vendor = _api_get(f"/api/vendors/{store_id}")
    except (requests.RequestException, ValueError, RuntimeError):
        flash("The vendor service is temporarily unavailable. You can still add the quotation manually.", "error")
        return redirect(url_for("main.quotations", category_id=category.id))

    product = _product_from_vendor(vendor, product_id)
    if product is None:
        return ("Not found", 404)

    contact = vendor.get("contact_phone") or vendor.get("contact_email") or ""
    notes = _product_notes(product)
    price = None
    if product.get("publish_price") and product.get("price"):
        try:
            price = Decimal(str(product["price"]))
        except (InvalidOperation, ValueError):
            price = None

    if price is None or price <= 0:
        flash("This vendor has not published a price. Their details were copied into the manual quotation form.", "info")
        return redirect(url_for(
            "main.quotations",
            category_id=category.id,
            vendor_name=vendor.get("store_name", ""),
            contact=contact,
            notes=notes,
        ))

    quote = Quotation(
        vendor_name=vendor.get("store_name") or "Vendor",
        amount=price,
        contact=contact or None,
        notes=notes,
        category_id=category.id,
    )
    db.session.add(quote)
    activity = add_activity(
        wedding_id=wedding.id,
        actor_user_id=current_user.id,
        kind="quotation_added",
        message=f"{current_user.name} added a {category.name} quotation from {quote.vendor_name}",
    )
    db.session.commit()
    publish_activity(activity)
    flash("Vendor product added as a quotation. Manual quotation entry remains available.", "success")
    return redirect(url_for("main.quotations", category_id=category.id))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def vendor_account():
    if not _account_enabled():
        return ("Not found", 404)

    login_url = current_app.config.get("VENDOR_PORTAL_LOGIN_URL") or None
    register_url = current_app.config.get("VENDOR_PORTAL_REGISTER_URL") or None
    remote_signup = current_app.config.get("VENDOR_REMOTE_SIGNUP_ENABLED", False)
    handoff_enabled = current_app.config.get("SHARED_LOGIN_HANDOFF_ENABLED", False)
    account = None
    service_error = None

    try:
        account = _vendor_account_lookup()
    except (requests.RequestException, ValueError, RuntimeError):
        service_error = "Umcimby vendor accounts are temporarily unavailable. Please try again later."

    if request.method == "POST" and service_error is None:
        if not remote_signup:
            flash("Vendor sign-up from UMSHADO is not enabled yet. Please register through Umcimby.", "info")
            return redirect(register_url or url_for("shared_vendors.vendor_account"))
        if account and account.get("exists"):
            if account.get("is_vendor"):
                flash("Your vendor account already exists. Please login through Event Organiser (Umcimby) instead.", "info")
            else:
                flash("An Umcimby account already exists with these details. Please login through Umcimby for account help.", "info")
            return redirect(
                url_for("shared_login.to_umcimby")
                if handoff_enabled else (login_url or url_for("shared_vendors.vendor_account"))
            )

        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6:
            flash("Choose a vendor password of at least 6 characters.", "error")
        elif password != confirm:
            flash("The vendor passwords do not match.", "error")
        elif not current_user.phone_number:
            flash("Add your phone number to your UMSHADO account before creating a vendor account.", "error")
        else:
            try:
                _api_post("/api/vendors/accounts/register", {
                    "name": current_user.name,
                    "email": current_user.email,
                    "phone_number": current_user.phone_number,
                    "phone_country": current_user.phone_country,
                    "password": password,
                })
            except requests.HTTPError as error:
                flash(str(error), "error")
            except (requests.RequestException, ValueError, RuntimeError):
                flash("Umcimby vendor sign-up is temporarily unavailable.", "error")
            else:
                flash("Vendor account created. Continue to Umcimby to set up your store.", "success")
                return redirect(
                    url_for("shared_login.to_umcimby")
                    if handoff_enabled else (login_url or url_for("shared_vendors.vendor_account"))
                )

    return render_template(
        "vendors/account.html",
        account=account,
        service_error=service_error,
        remote_signup_enabled=remote_signup,
        login_url=login_url,
        register_url=register_url,
    )

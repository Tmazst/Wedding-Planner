"""Controlled OpenAI-powered guidance and project actions for UMSHADO."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import secrets
import time

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required
from sqlalchemy import delete, select

from .activity import add_activity, publish_activity
from .extensions import db
from .models import (
    AssistantPendingAction,
    BudgetCategory,
    Quotation,
    Wedding,
    WeddingMember,
)


bp = Blueprint("assistant", __name__, url_prefix="/assistant")

ASSISTANT_INSTRUCTIONS = """
You are the UMSHADO Planning Assistant inside the UMSHADO Wedding Planner.
Be warm, practical, brief, and easy to understand. UMSHADO currently helps users
set up a wedding, manage budgets and quotations, invite trusted stakeholders,
view activity, and download a professional report. The Free plan allows four
budget items. Standard access costs E60 once for one wedding project. Stakeholder
access costs E30 for that wedding project. Never claim that a feature exists if
it is not listed here.

Use the available tools whenever a user asks about their own project, budget, or
quotations. Never guess project figures. All write tools only prepare a proposed
change; the user must confirm it separately in the UMSHADO interface. Do not say
that a change has been completed until the tool result explicitly says so.

You cannot make payments, approve MoMo prompts, delete accounts or projects,
change permissions, remove stakeholders, send messages, or inspect photographs.
Guide users to the normal UMSHADO screen for those tasks. Never ask for a
password, MoMo PIN, card details, API key, invitation token, or other secret.
Amounts are normally in Eswatini lilangeni (SZL), displayed with E. Make clear
that planning figures are user-provided estimates, not financial advice.
""".strip()


TOOLS = [
    {
        "type": "function",
        "name": "get_project_summary",
        "description": "Get the current user's authorised wedding project and budget summary.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_budget_items",
        "description": "List budget items, planned amounts, and selected quotation details.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_quotations",
        "description": "List vendor quotations for the current wedding project.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_add_budget_item",
        "description": "Prepare a new budget item for the user to confirm. This does not save it yet.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short budget item name."},
                "planned_amount": {"type": "number", "minimum": 0},
            },
            "required": ["name", "planned_amount"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_update_budget_item",
        "description": "Prepare changes to an existing budget item for confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "name": {"type": ["string", "null"]},
                "planned_amount": {"type": ["number", "null"], "minimum": 0},
            },
            "required": ["item_id", "name", "planned_amount"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_add_quotation",
        "description": "Prepare a vendor quotation for an existing budget item for confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "vendor_name": {"type": "string"},
                "amount": {"type": "number", "exclusiveMinimum": 0},
                "contact": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
            },
            "required": ["item_id", "vendor_name", "amount", "contact", "notes"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class AssistantUnavailable(RuntimeError):
    pass


def _current_wedding():
    owned = db.session.scalar(
        select(Wedding).where(Wedding.owner_id == current_user.id).order_by(Wedding.created_at)
    )
    if owned:
        return owned
    membership = db.session.scalar(
        select(WeddingMember)
        .where(WeddingMember.user_id == current_user.id)
        .order_by(WeddingMember.joined_at)
    )
    return membership.wedding if membership else None


def _money(value, *, allow_zero=True):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Enter a valid amount.") from error
    minimum = Decimal("0") if allow_zero else Decimal("0.01")
    if amount < minimum or amount > Decimal("999999999.99"):
        raise ValueError("Enter an amount within the supported range.")
    return amount


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _format_amount(value):
    return f"E{Decimal(value):,.2f}"


def _project_summary(wedding):
    planned = sum((item.planned_amount for item in wedding.categories), start=Decimal("0"))
    selected = sum((item.selected_amount for item in wedding.categories), start=Decimal("0"))
    return {
        "title": wedding.title,
        "couple": f"{wedding.partner_one} and {wedding.partner_two}",
        "date": wedding.wedding_date.isoformat() if wedding.wedding_date else None,
        "location": wedding.location,
        "plan": wedding.plan_tier,
        "budget_target": str(wedding.budget_target),
        "planned_total": str(planned),
        "selected_total": str(selected),
        "remaining_after_selected": str(wedding.budget_target - selected),
        "budget_item_count": len(wedding.categories),
        "quotation_count": sum(len(item.quotations) for item in wedding.categories),
    }


def _budget_items(wedding):
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "planned_amount": str(item.planned_amount),
                "quotation_count": len(item.quotations),
                "selected_quotation": (
                    {
                        "vendor": item.selected_quote.vendor_name,
                        "amount": str(item.selected_quote.amount),
                    }
                    if item.selected_quote else None
                ),
            }
            for item in wedding.categories[:60]
        ]
    }


def _quotations(wedding):
    rows = []
    for item in wedding.categories:
        for quote in item.quotations:
            rows.append({
                "budget_item_id": item.id,
                "budget_item": item.name,
                "vendor": quote.vendor_name,
                "amount": str(quote.amount),
                "selected": quote.is_selected,
                "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
            })
            if len(rows) >= 100:
                return {"quotations": rows, "truncated": True}
    return {"quotations": rows, "truncated": False}


def _create_confirmation(wedding, action, payload, summary):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.session.execute(
        delete(AssistantPendingAction).where(
            AssistantPendingAction.user_id == current_user.id,
            AssistantPendingAction.wedding_id == wedding.id,
        )
    )
    db.session.add(AssistantPendingAction(
        token_hash=_token_hash(token),
        action=action,
        payload=payload,
        user_id=current_user.id,
        wedding_id=wedding.id,
        created_at=now,
        expires_at=now + timedelta(minutes=15),
    ))
    db.session.commit()
    return {
        "token": token,
        "summary": summary,
        "confirm_label": "Confirm change",
        "expires_in_minutes": 15,
    }


def _tool_result(name, arguments, wedding):
    if name == "get_project_summary":
        return _project_summary(wedding), None
    if name == "list_budget_items":
        return _budget_items(wedding), None
    if name == "list_quotations":
        return _quotations(wedding), None
    if name == "propose_add_budget_item":
        item_name = str(arguments.get("name") or "").strip()[:120]
        amount = _money(arguments.get("planned_amount"))
        if not item_name:
            return {"error": "A budget item name is required."}, None
        confirmation = _create_confirmation(
            wedding,
            "add_budget_item",
            {"name": item_name, "planned_amount": str(amount)},
            f"Add {item_name} to the budget with a planned amount of {_format_amount(amount)}?",
        )
        return {"status": "awaiting_user_confirmation"}, confirmation
    if name == "propose_update_budget_item":
        item = db.session.get(BudgetCategory, arguments.get("item_id"))
        if item is None or item.wedding_id != wedding.id:
            return {"error": "That budget item was not found in this wedding project."}, None
        new_name = arguments.get("name")
        new_name = str(new_name).strip()[:120] if new_name is not None else None
        new_amount = arguments.get("planned_amount")
        if not new_name and new_amount is None:
            return {"error": "Provide a new name or planned amount."}, None
        payload = {"item_id": item.id, "name": new_name}
        changes = []
        if new_name:
            changes.append(f"rename {item.name} to {new_name}")
        if new_amount is not None:
            amount = _money(new_amount)
            payload["planned_amount"] = str(amount)
            changes.append(f"set its planned amount to {_format_amount(amount)}")
        confirmation = _create_confirmation(
            wedding, "update_budget_item", payload,
            "Confirm that you want to " + " and ".join(changes) + "?",
        )
        return {"status": "awaiting_user_confirmation"}, confirmation
    if name == "propose_add_quotation":
        item = db.session.get(BudgetCategory, arguments.get("item_id"))
        if item is None or item.wedding_id != wedding.id:
            return {"error": "That budget item was not found in this wedding project."}, None
        vendor = str(arguments.get("vendor_name") or "").strip()[:160]
        amount = _money(arguments.get("amount"), allow_zero=False)
        if not vendor:
            return {"error": "A vendor name is required."}, None
        payload = {
            "item_id": item.id,
            "vendor_name": vendor,
            "amount": str(amount),
            "contact": (str(arguments.get("contact") or "").strip()[:120] or None),
            "notes": (str(arguments.get("notes") or "").strip()[:1000] or None),
        }
        confirmation = _create_confirmation(
            wedding, "add_quotation", payload,
            f"Add a {_format_amount(amount)} quotation from {vendor} under {item.name}?",
        )
        return {"status": "awaiting_user_confirmation"}, confirmation
    return {"error": "This assistant action is not available."}, None


def _safe_history(raw_history, limit):
    cleaned = []
    if not isinstance(raw_history, list):
        return cleaned
    for item in raw_history[-8:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()[:limit]
        if content:
            cleaned.append({"role": item["role"], "content": content})
    return cleaned


def _response_items(response):
    result = []
    for item in response.output:
        if hasattr(item, "model_dump"):
            result.append(item.model_dump(exclude_none=True))
        else:
            result.append(item)
    return result


def run_assistant(message, history, wedding):
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not current_app.config.get("ASSISTANT_ENABLED", True) or not api_key:
        raise AssistantUnavailable("The planning assistant has not been configured yet.")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise AssistantUnavailable("The planning assistant is not installed yet.") from error

    client = current_app.extensions.get("openai_client") or OpenAI(api_key=api_key)
    model = current_app.config.get("OPENAI_MODEL", "gpt-5.4-mini")
    conversation = [*history, {"role": "user", "content": message}]
    response = client.responses.create(
        model=model,
        instructions=ASSISTANT_INSTRUCTIONS,
        input=conversation,
        tools=TOOLS,
        store=False,
        max_output_tokens=700,
    )
    for _ in range(4):
        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            return response.output_text.strip() or "I could not prepare a response. Please try again.", None
        outputs = []
        for call in calls:
            try:
                arguments = json.loads(call.arguments or "{}")
                result, confirmation = _tool_result(call.name, arguments, wedding)
            except (ValueError, json.JSONDecodeError) as error:
                result, confirmation = {"error": str(error)}, None
            if confirmation is not None:
                return "Please review and confirm this proposed change.", confirmation
            outputs.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result),
            })
        conversation = [*conversation, *_response_items(response), *outputs]
        response = client.responses.create(
            model=model,
            instructions=ASSISTANT_INSTRUCTIONS,
            input=conversation,
            tools=TOOLS,
            store=False,
            max_output_tokens=700,
        )
    return "I could not complete that request safely. Please try a simpler question.", None


def _rate_limit_ok():
    now = time.time()
    attempts = [value for value in session.get("assistant_request_times", []) if now - value < 600]
    limit = current_app.config.get("ASSISTANT_REQUEST_LIMIT", 20)
    if len(attempts) >= limit:
        return False
    attempts.append(now)
    session["assistant_request_times"] = attempts
    return True


@bp.post("/message")
@login_required
def message():
    wedding = _current_wedding()
    if wedding is None:
        return jsonify(error="Set up your wedding project before using the planning assistant."), 400
    if not _rate_limit_ok():
        return jsonify(error="Please wait a few minutes before sending another assistant message."), 429
    payload = request.get_json(silent=True) or {}
    limit = current_app.config.get("ASSISTANT_MAX_MESSAGE_LENGTH", 1200)
    user_message = str(payload.get("message") or "").strip()
    if not user_message:
        return jsonify(error="Enter a message for the planning assistant."), 400
    if len(user_message) > limit:
        return jsonify(error=f"Keep the message under {limit} characters."), 400
    history = _safe_history(payload.get("history"), limit)
    try:
        reply, confirmation = run_assistant(user_message, history, wedding)
    except AssistantUnavailable as error:
        return jsonify(error=str(error)), 503
    except Exception as error:
        current_app.logger.warning("Planning assistant request failed: %s", type(error).__name__)
        return jsonify(error="The planning assistant is temporarily unavailable. Please try again."), 503
    return jsonify(reply=reply, confirmation=confirmation)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@bp.post("/confirm")
@login_required
def confirm():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token") or "")
    pending = db.session.scalar(
        select(AssistantPendingAction).where(
            AssistantPendingAction.token_hash == _token_hash(token),
            AssistantPendingAction.user_id == current_user.id,
        )
    ) if token else None
    if pending is None:
        return jsonify(error="This confirmation is invalid or has already been used."), 400
    if _aware(pending.expires_at) < datetime.now(timezone.utc):
        db.session.delete(pending)
        db.session.commit()
        return jsonify(error="This confirmation has expired. Ask the assistant to prepare it again."), 400
    wedding = _current_wedding()
    if wedding is None or wedding.id != pending.wedding_id:
        return jsonify(error="You no longer have access to that wedding project."), 403

    action_payload = pending.payload
    activity = None
    if pending.action == "add_budget_item":
        free_limit = current_app.config["FREE_BUDGET_ITEM_LIMIT"]
        if not wedding.has_full_feature_access and len(wedding.categories) >= free_limit:
            return jsonify(error=f"The Free plan includes {free_limit} budget items. Upgrade to add more."), 409
        item = BudgetCategory(
            name=action_payload["name"],
            planned_amount=_money(action_payload["planned_amount"]),
            wedding_id=wedding.id,
        )
        db.session.add(item)
        activity = add_activity(
            wedding_id=wedding.id,
            actor_user_id=current_user.id,
            kind="assistant_budget_item_added",
            message=f"{current_user.name} added {item.name} to the budget with the planning assistant",
        )
        reply = f"{item.name} has been added to the wedding budget."
    elif pending.action == "update_budget_item":
        item = db.session.get(BudgetCategory, action_payload["item_id"])
        if item is None or item.wedding_id != wedding.id:
            return jsonify(error="That budget item is no longer available."), 404
        if action_payload.get("name"):
            item.name = action_payload["name"]
        if "planned_amount" in action_payload:
            item.planned_amount = _money(action_payload["planned_amount"])
        activity = add_activity(
            wedding_id=wedding.id,
            actor_user_id=current_user.id,
            kind="assistant_budget_item_updated",
            message=f"{current_user.name} updated {item.name} with the planning assistant",
        )
        reply = f"{item.name} has been updated."
    elif pending.action == "add_quotation":
        item = db.session.get(BudgetCategory, action_payload["item_id"])
        if item is None or item.wedding_id != wedding.id:
            return jsonify(error="That budget item is no longer available."), 404
        quote = Quotation(
            vendor_name=action_payload["vendor_name"],
            amount=_money(action_payload["amount"], allow_zero=False),
            contact=action_payload.get("contact"),
            notes=action_payload.get("notes"),
            category_id=item.id,
        )
        db.session.add(quote)
        activity = add_activity(
            wedding_id=wedding.id,
            actor_user_id=current_user.id,
            kind="assistant_quotation_added",
            message=f"{current_user.name} added a {item.name} quotation from {quote.vendor_name} with the planning assistant",
        )
        reply = f"The quotation from {quote.vendor_name} has been added under {item.name}."
    else:
        db.session.delete(pending)
        db.session.commit()
        return jsonify(error="That assistant action is no longer supported."), 400

    db.session.delete(pending)
    db.session.commit()
    if activity is not None:
        publish_activity(activity)
    return jsonify(reply=reply, refresh=True)

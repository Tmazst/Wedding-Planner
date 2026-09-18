"""Privacy-conscious request diagnostics for the MVP admin dashboard."""

import json
import logging
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import perf_counter

from flask import current_app, g, request, session
from flask_login import current_user


EXCLUDED_PREFIXES = ("/admin", "/static/", "/socket.io/", "/api/")
EXCLUDED_ENDPOINTS = {"web_manifest", "service_worker"}
AUTH_ENDPOINTS = {"main.login": "login", "main.register": "register"}


def _analytics_path(app):
    configured = app.config.get("ANALYTICS_LOG_PATH")
    return Path(configured) if configured else Path(app.instance_path) / "analytics.log"


def configure_request_analytics(app):
    """Register lightweight request logging without writing into SQLite."""
    if not app.config.get("ANALYTICS_ENABLED", True):
        return

    log_path = _analytics_path(app)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"umshado.analytics.{id(app)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_path,
        maxBytes=app.config.get("ANALYTICS_LOG_MAX_BYTES", 2 * 1024 * 1024),
        backupCount=app.config.get("ANALYTICS_LOG_BACKUP_COUNT", 3),
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    app.extensions["request_analytics_logger"] = logger
    app.extensions["request_analytics_path"] = log_path

    app.before_request(_start_request)
    app.after_request(_record_request)


def _should_track():
    if request.method not in {"GET", "POST"}:
        return False
    if request.path.startswith(EXCLUDED_PREFIXES):
        return False
    return request.endpoint not in EXCLUDED_ENDPOINTS


def _start_request():
    if not _should_track():
        return
    g.analytics_started_at = perf_counter()
    if "analytics_session_ref" not in session:
        session["analytics_session_ref"] = secrets.token_hex(6)


def _device_and_browser():
    agent = (request.user_agent.string or "").lower()

    if any(token in agent for token in ("android", "iphone", "ipad", "mobile")):
        device = "Mobile"
    else:
        device = "Desktop"

    if "edg/" in agent:
        browser = "Edge"
    elif "crios/" in agent or "chrome/" in agent:
        browser = "Chrome"
    elif "firefox/" in agent or "fxios/" in agent:
        browser = "Firefox"
    elif "safari/" in agent:
        browser = "Safari"
    else:
        browser = "Other"
    return device, browser


def _outcome(status_code):
    auth_name = AUTH_ENDPOINTS.get(request.endpoint)
    if auth_name:
        if request.method == "GET":
            suffix = "available" if status_code < 400 else "failed"
            return f"{auth_name}_page_{suffix}"
        if status_code >= 500:
            return f"{auth_name}_server_error"
        if status_code >= 400:
            return f"{auth_name}_request_error"
        if 300 <= status_code < 400 and current_user.is_authenticated:
            return f"{auth_name}_success"
        return f"{auth_name}_rejected"

    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "request_error"
    if status_code >= 300:
        return "redirected"
    return "page_available"


def _record_request(response):
    started_at = getattr(g, "analytics_started_at", None)
    if started_at is None:
        return response

    logger = current_app.extensions.get("request_analytics_logger")
    if logger is None:
        return response

    device, browser = _device_and_browser()
    route = request.url_rule.rule if request.url_rule is not None else request.path
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_ref": session.get("analytics_session_ref", "unknown"),
        "user_id": int(current_user.get_id()) if current_user.is_authenticated else None,
        "method": request.method,
        "route": route[:255],
        "endpoint": (request.endpoint or "unknown")[:120],
        "status": response.status_code,
        "outcome": _outcome(response.status_code),
        "device": device,
        "browser": browser,
        "duration_ms": max(0, round((perf_counter() - started_at) * 1000)),
    }
    try:
        logger.info(json.dumps(event, separators=(",", ":")))
    except (OSError, ValueError, TypeError):
        current_app.logger.exception("Could not record request analytics")
    return response


def _read_events(app, days):
    log_path = Path(app.extensions.get("request_analytics_path", _analytics_path(app)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    backup_count = app.config.get("ANALYTICS_LOG_BACKUP_COUNT", 3)
    paths = [Path(f"{log_path}.{number}") for number in range(backup_count, 0, -1)]
    paths.append(log_path)

    events = []
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as log_file:
                for line in log_file:
                    try:
                        event = json.loads(line)
                        timestamp = datetime.fromisoformat(event["timestamp"])
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        continue
                    if timestamp >= cutoff:
                        events.append(event)
        except OSError:
            app.logger.exception("Could not read request analytics")
    return events


def build_analytics_summary(app, days=7):
    """Return dashboard-ready diagnostics from the rotating JSON-lines log."""
    events = _read_events(app, days) if app.config.get("ANALYTICS_ENABLED", True) else []

    def matches(endpoint=None, method=None, outcomes=None):
        selected = events
        if endpoint is not None:
            selected = [event for event in selected if event.get("endpoint") == endpoint]
        if method is not None:
            selected = [event for event in selected if event.get("method") == method]
        if outcomes is not None:
            selected = [event for event in selected if event.get("outcome") in outcomes]
        return selected

    issue_outcomes = {
        "login_rejected",
        "register_rejected",
        "login_request_error",
        "register_request_error",
        "login_server_error",
        "register_server_error",
        "request_error",
        "server_error",
    }
    issues = [
        event for event in events
        if event.get("status", 0) >= 400 or event.get("outcome") in issue_outcomes
    ]

    login_pages = matches("main.login", "GET")
    login_attempts = matches("main.login", "POST")
    register_pages = matches("main.register", "GET")
    register_attempts = matches("main.register", "POST")

    page_totals = defaultdict(lambda: {"requests": 0, "issues": 0, "total_ms": 0})
    for event in events:
        page = page_totals[event.get("route", "unknown")]
        page["requests"] += 1
        page["total_ms"] += event.get("duration_ms", 0)
        if event in issues:
            page["issues"] += 1

    page_health = []
    for route, values in page_totals.items():
        requests_count = values["requests"]
        page_health.append({
            "route": route,
            "requests": requests_count,
            "issues": values["issues"],
            "success_rate": round((requests_count - values["issues"]) / requests_count * 100),
            "average_ms": round(values["total_ms"] / requests_count),
        })
    page_health.sort(key=lambda item: (-item["issues"], -item["requests"], item["route"]))

    return {
        "days": days,
        "requests": len(events),
        "unique_sessions": len({event.get("session_ref") for event in events}),
        "issues": len(issues),
        "login_page_ok": sum(event.get("status", 500) < 400 for event in login_pages),
        "login_page_failed": sum(event.get("status", 0) >= 400 for event in login_pages),
        "login_attempts": len(login_attempts),
        "login_success": sum(event.get("outcome") == "login_success" for event in login_attempts),
        "login_rejected": sum(event.get("outcome") != "login_success" for event in login_attempts),
        "register_page_ok": sum(event.get("status", 500) < 400 for event in register_pages),
        "register_page_failed": sum(event.get("status", 0) >= 400 for event in register_pages),
        "register_attempts": len(register_attempts),
        "register_success": sum(event.get("outcome") == "register_success" for event in register_attempts),
        "register_rejected": sum(event.get("outcome") != "register_success" for event in register_attempts),
        "page_health": page_health[:15],
        "recent_issues": list(reversed(issues[-20:])),
        "recent_events": list(reversed(events[-30:])),
    }

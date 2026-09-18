"""Data-retention cleanup for privacy and operational records."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from sqlalchemy import delete, select

from .extensions import db
from .models import AppVisit, Invitation, Payment


def _rewrite_recent_lines(path, cutoff, timestamp_reader):
    if not path.exists():
        return 0
    kept = []
    removed = 0
    with path.open(encoding="utf-8", errors="replace") as source:
        for line in source:
            timestamp = timestamp_reader(line)
            if timestamp is not None and timestamp < cutoff:
                removed += 1
            else:
                kept.append(line)
    temporary = path.with_suffix(path.suffix + ".retention")
    with temporary.open("w", encoding="utf-8") as destination:
        destination.writelines(kept)
    os.replace(temporary, path)
    return removed


def _analytics_timestamp(line):
    try:
        value = datetime.fromisoformat(json.loads(line)["timestamp"])
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _payment_timestamp(line):
    try:
        value = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
        return value.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def register_retention_command(app):
    @app.cli.command("data-retention-cleanup")
    def data_retention_cleanup():
        """Remove records after the published retention periods."""
        now = datetime.now(timezone.utc)
        visits_cutoff = now - timedelta(days=app.config["APP_VISIT_RETENTION_DAYS"])
        invite_cutoff = now - timedelta(days=app.config["EXPIRED_INVITATION_RETENTION_DAYS"])

        deleted_visits = db.session.execute(
            delete(AppVisit).where(AppVisit.created_at < visits_cutoff)
        ).rowcount
        paid_invitation_ids = select(Payment.invitation_id).where(
            Payment.invitation_id.is_not(None)
        )
        deleted_invitations = db.session.execute(
            delete(Invitation).where(
                Invitation.expires_at < invite_cutoff,
                Invitation.id.not_in(paid_invitation_ids),
            )
        ).rowcount
        db.session.commit()

        analytics_cutoff = now - timedelta(days=app.config["ANALYTICS_RETENTION_DAYS"])
        analytics_path = Path(
            app.config.get("ANALYTICS_LOG_PATH") or Path(app.instance_path) / "analytics.log"
        )
        analytics_removed = 0
        for path in [analytics_path, *analytics_path.parent.glob(f"{analytics_path.name}.*")]:
            if path.suffix == ".retention":
                continue
            analytics_removed += _rewrite_recent_lines(
                path, analytics_cutoff, _analytics_timestamp
            )

        payment_cutoff = now - timedelta(days=app.config["PAYMENT_LOG_RETENTION_DAYS"])
        payment_path = Path(app.instance_path) / "payments.log"
        payment_removed = 0
        for path in [payment_path, *payment_path.parent.glob("payments.log.*")]:
            if path.suffix == ".retention":
                continue
            payment_removed += _rewrite_recent_lines(
                path, payment_cutoff, _payment_timestamp
            )

        security_cutoff = now - timedelta(days=app.config["SECURITY_LOG_RETENTION_DAYS"])
        security_path = Path(app.instance_path) / "security.log"
        security_removed = 0
        for path in [security_path, *security_path.parent.glob("security.log.*")]:
            if path.suffix == ".retention":
                continue
            security_removed += _rewrite_recent_lines(
                path, security_cutoff, _payment_timestamp
            )

        click.echo(
            "Retention cleanup complete: "
            f"{deleted_visits or 0} visits, {deleted_invitations or 0} invitations, "
            f"{analytics_removed} analytics events, {payment_removed} payment log entries "
            f"and {security_removed} security log entries removed."
        )

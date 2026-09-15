from datetime import timezone

from flask import current_app

from .extensions import db, socketio
from .models import ActivityEvent


def wedding_room(wedding_id):
    return f"wedding:{wedding_id}"


def activity_payload(activity):
    created_at = activity.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "id": activity.id,
        "kind": activity.kind,
        "message": activity.message,
        "actor_name": activity.actor.name if activity.actor else None,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }


def add_activity(*, wedding_id, actor_user_id, kind, message):
    activity = ActivityEvent(
        wedding_id=wedding_id,
        actor_user_id=actor_user_id,
        kind=kind,
        message=message[:255],
    )
    db.session.add(activity)
    db.session.flush()
    return activity


def publish_activity(activity):
    try:
        socketio.emit(
            "activity:new",
            activity_payload(activity),
            to=wedding_room(activity.wedding_id),
            namespace="/planning",
        )
    except Exception:
        # Planning writes and payment callbacks must still succeed if the
        # realtime transport or optional Redis service is briefly unavailable.
        current_app.logger.exception("Could not publish wedding activity %s", activity.id)

from collections import defaultdict
from threading import Lock, Timer

from flask import current_app, request
from flask_login import current_user
from flask_socketio import emit, join_room
from sqlalchemy import select

from .activity import wedding_room
from .extensions import db, socketio
from .models import WeddingMember
from .routes import current_wedding


ROLE_LABELS = {
    "owner": "Couple",
    "partner": "Partner",
    "matron_of_honour": "Matron of Honour",
    "family_friend": "Family / Friend",
    "stakeholder": "Stakeholder",
}
PRESENCE_GRACE_SECONDS = 5

# This intentionally targets a single realtime worker. Redis can distribute
# emitted events, while shared presence can be added when the app is scaled.
_presence = defaultdict(dict)
_sid_index = {}
_presence_lock = Lock()


def _role_for(wedding, user_id):
    if wedding.owner_id == user_id:
        return "owner"
    membership = db.session.scalar(
        select(WeddingMember).where(
            WeddingMember.wedding_id == wedding.id,
            WeddingMember.user_id == user_id,
        )
    )
    return membership.role if membership else "stakeholder"


def _presence_list(wedding_id):
    with _presence_lock:
        return [
            {"user_id": user_id, "name": state["name"], "role": ROLE_LABELS.get(state["role"], state["role"].replace("_", " ").title())}
            for user_id, state in _presence[wedding_id].items()
            if state["sids"] or state.get("timer") is not None
        ]


def _broadcast_state(wedding_id):
    socketio.emit(
        "presence:state",
        {"users": _presence_list(wedding_id)},
        to=wedding_room(wedding_id),
        namespace="/planning",
    )


def _finish_disconnect(app, wedding_id, user_id):
    with app.app_context():
        with _presence_lock:
            state = _presence[wedding_id].get(user_id)
            if not state or state["sids"]:
                return
            name = state["name"]
            del _presence[wedding_id][user_id]
            if not _presence[wedding_id]:
                _presence.pop(wedding_id, None)
        socketio.emit(
            "presence:event",
            {"kind": "offline", "message": f"{name} has left", "actor_name": name},
            to=wedding_room(wedding_id),
            namespace="/planning",
        )
        _broadcast_state(wedding_id)


def planning_connect(auth=None):
    if not current_user.is_authenticated:
        return False
    wedding = current_wedding()
    if wedding is None:
        return False

    room = wedding_room(wedding.id)
    join_room(room)
    role = _role_for(wedding, current_user.id)
    announce_online = False
    with _presence_lock:
        state = _presence[wedding.id].get(current_user.id)
        if state is None:
            state = {"name": current_user.name, "role": role, "sids": set(), "timer": None}
            _presence[wedding.id][current_user.id] = state
            announce_online = True
        elif state.get("timer") is not None:
            state["timer"].cancel()
            state["timer"] = None
        state["sids"].add(request.sid)
        _sid_index[request.sid] = (wedding.id, current_user.id)

    emit("presence:state", {"users": _presence_list(wedding.id)})
    if announce_online:
        emit(
            "presence:event",
            {"kind": "online", "message": f"{current_user.name} is online", "actor_name": current_user.name},
            to=room,
        )
        _broadcast_state(wedding.id)


def planning_disconnect(reason=None):
    app = current_app._get_current_object()
    with _presence_lock:
        identity = _sid_index.pop(request.sid, None)
        if identity is None:
            return
        wedding_id, user_id = identity
        state = _presence[wedding_id].get(user_id)
        if state is None:
            return
        state["sids"].discard(request.sid)
        if state["sids"]:
            return
        timer = Timer(PRESENCE_GRACE_SECONDS, _finish_disconnect, args=(app, wedding_id, user_id))
        timer.daemon = True
        state["timer"] = timer
        timer.start()


def register_realtime_handlers():
    """Attach handlers to the current Socket.IO server instance."""
    socketio.on_event("connect", planning_connect, namespace="/planning")
    socketio.on_event("disconnect", planning_disconnect, namespace="/planning")

from datetime import datetime, time, timedelta, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, render_template, request, session
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .analytics import build_analytics_summary
from .extensions import db
from .models import AppVisit, User, Wedding


bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not (current_user.is_admin or current_user.is_super_admin):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def record_session_visit():
    """Record one visit per browser session without retaining identity or IP data."""
    if request.method != "GET" or session.get("app_visit_recorded"):
        return
    if request.path.startswith(("/admin", "/static/", "/socket.io/")) or request.endpoint in {
        "web_manifest",
        "service_worker",
    }:
        return

    try:
        db.session.add(AppVisit())
        db.session.commit()
        session["app_visit_recorded"] = True
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record application visit")


@bp.get("")
@bp.get("/")
@admin_required
def dashboard():
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    seven_day_start = today_start - timedelta(days=6)

    total_visits = db.session.scalar(select(func.count(AppVisit.id))) or 0
    visits_today = db.session.scalar(
        select(func.count(AppVisit.id)).where(AppVisit.created_at >= today_start)
    ) or 0
    total_users = db.session.scalar(select(func.count(User.id))) or 0
    users_today = db.session.scalar(
        select(func.count(User.id)).where(User.created_at >= today_start)
    ) or 0
    total_weddings = db.session.scalar(select(func.count(Wedding.id))) or 0

    visit_rows = db.session.execute(
        select(func.date(AppVisit.created_at), func.count(AppVisit.id))
        .where(AppVisit.created_at >= seven_day_start)
        .group_by(func.date(AppVisit.created_at))
    ).all()
    user_rows = db.session.execute(
        select(func.date(User.created_at), func.count(User.id))
        .where(User.created_at >= seven_day_start)
        .group_by(func.date(User.created_at))
    ).all()
    visits_by_day = {str(day): count for day, count in visit_rows}
    users_by_day = {str(day): count for day, count in user_rows}
    daily_activity = []
    for offset in range(7):
        day = seven_day_start.date() + timedelta(days=offset)
        key = day.isoformat()
        daily_activity.append({
            "date": day,
            "visits": visits_by_day.get(key, 0),
            "registrations": users_by_day.get(key, 0),
        })

    recent_users = db.session.scalars(
        select(User).order_by(User.created_at.desc()).limit(8)
    ).all()
    request_analytics = build_analytics_summary(current_app, days=7)
    return render_template(
        "admin/dashboard.html",
        total_visits=total_visits,
        visits_today=visits_today,
        total_users=total_users,
        users_today=users_today,
        total_weddings=total_weddings,
        daily_activity=daily_activity,
        recent_users=recent_users,
        request_analytics=request_analytics,
    )

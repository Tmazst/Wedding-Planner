from datetime import datetime, timezone

from sqlalchemy import select

from .extensions import db
from .models import User


class SharedIdentity(db.Model):
    """Permanent link between a local user and the same account in the peer app."""

    __table_args__ = (
        db.UniqueConstraint("provider", "provider_user_id", name="uq_shared_identity_provider_user"),
        db.UniqueConstraint("user_id", "provider", name="uq_shared_identity_user_provider"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    provider = db.Column(db.String(20), nullable=False, index=True)
    provider_user_id = db.Column(db.String(64), nullable=False, index=True)
    linked_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def linked_user(provider, provider_user_id):
    if not provider or not provider_user_id:
        return None
    link = db.session.scalar(
        select(SharedIdentity).where(
            SharedIdentity.provider == provider,
            SharedIdentity.provider_user_id == str(provider_user_id),
        )
    )
    return db.session.get(User, link.user_id) if link else None


def stage_identity_link(user, provider, provider_user_id):
    """Stage a permanent link. Return False if either side is linked elsewhere."""
    if not provider or not provider_user_id:
        return True

    provider_user_id = str(provider_user_id)
    remote_link = db.session.scalar(
        select(SharedIdentity).where(
            SharedIdentity.provider == provider,
            SharedIdentity.provider_user_id == provider_user_id,
        )
    )
    if remote_link:
        return remote_link.user_id == user.id

    local_link = db.session.scalar(
        select(SharedIdentity).where(
            SharedIdentity.user_id == user.id,
            SharedIdentity.provider == provider,
        )
    )
    if local_link:
        return local_link.provider_user_id == provider_user_id

    db.session.add(
        SharedIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
    )
    return True

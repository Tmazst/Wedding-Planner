"""Add persistent wedding activity events.

Revision ID: 004_live_activity
Revises: 003_wedding_profile_image
"""
from alembic import op
import sqlalchemy as sa


revision = "004_live_activity"
down_revision = "003_wedding_profile_image"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activity_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_event_wedding_id", "activity_event", ["wedding_id"])
    op.create_index("ix_activity_event_actor_user_id", "activity_event", ["actor_user_id"])
    op.create_index("ix_activity_event_kind", "activity_event", ["kind"])
    op.create_index("ix_activity_event_created_at", "activity_event", ["created_at"])


def downgrade():
    op.drop_table("activity_event")

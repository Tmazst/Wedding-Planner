"""Add event time to invitation card design.

Revision ID: 011_invitation_event_time
Revises: 010_advanced_programme
"""
from alembic import op
import sqlalchemy as sa


revision = "011_invitation_event_time"
down_revision = "010_advanced_programme"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invitation_card_design",
        sa.Column("event_time", sa.String(length=10), nullable=True),
    )


def downgrade():
    op.drop_column("invitation_card_design", "event_time")

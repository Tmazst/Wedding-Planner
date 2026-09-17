"""Add privacy-friendly application visits.

Revision ID: 006_app_visits
Revises: 005_admin_test_access
"""
from alembic import op
import sqlalchemy as sa


revision = "006_app_visits"
down_revision = "005_admin_test_access"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_visit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_visit_created_at", "app_visit", ["created_at"])


def downgrade():
    op.drop_index("ix_app_visit_created_at", table_name="app_visit")
    op.drop_table("app_visit")

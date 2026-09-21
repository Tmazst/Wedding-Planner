"""Add short-lived assistant action confirmations.

Revision ID: 009_assistant_actions
Revises: 008_international_phone
"""
from alembic import op
import sqlalchemy as sa


revision = "009_assistant_actions"
down_revision = "008_international_phone"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_pending_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_pending_action_token_hash",
        "assistant_pending_action",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_assistant_pending_action_user_id",
        "assistant_pending_action",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_pending_action_wedding_id",
        "assistant_pending_action",
        ["wedding_id"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_pending_action_created_at",
        "assistant_pending_action",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_pending_action_expires_at",
        "assistant_pending_action",
        ["expires_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_assistant_pending_action_expires_at", table_name="assistant_pending_action")
    op.drop_index("ix_assistant_pending_action_created_at", table_name="assistant_pending_action")
    op.drop_index("ix_assistant_pending_action_wedding_id", table_name="assistant_pending_action")
    op.drop_index("ix_assistant_pending_action_user_id", table_name="assistant_pending_action")
    op.drop_index("ix_assistant_pending_action_token_hash", table_name="assistant_pending_action")
    op.drop_table("assistant_pending_action")

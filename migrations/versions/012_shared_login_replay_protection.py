"""add shared login replay protection

Revision ID: 012_shared_login_replay_protection
Revises: 011_invitation_event_time
"""

from alembic import op
import sqlalchemy as sa

revision = "012_shared_login_replay_protection"
down_revision = "011_invitation_event_time"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_login_use",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shared_login_use_token_hash", "shared_login_use", ["token_hash"], unique=True)
    op.create_index("ix_shared_login_use_consumed_at", "shared_login_use", ["consumed_at"], unique=False)


def downgrade():
    op.drop_index("ix_shared_login_use_consumed_at", table_name="shared_login_use")
    op.drop_index("ix_shared_login_use_token_hash", table_name="shared_login_use")
    op.drop_table("shared_login_use")

"""add permanent shared identity links

Revision ID: 013_shared_identity_links
Revises: 012_shared_login_replay_protection
"""

from alembic import op
import sqlalchemy as sa

revision = "013_shared_identity_links"
down_revision = "012_shared_login_replay_protection"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shared_identity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_user_id", sa.String(length=64), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_shared_identity_provider_user"),
        sa.UniqueConstraint("user_id", "provider", name="uq_shared_identity_user_provider"),
    )
    op.create_index("ix_shared_identity_user_id", "shared_identity", ["user_id"], unique=False)
    op.create_index("ix_shared_identity_provider", "shared_identity", ["provider"], unique=False)
    op.create_index("ix_shared_identity_provider_user_id", "shared_identity", ["provider_user_id"], unique=False)


def downgrade():
    op.drop_index("ix_shared_identity_provider_user_id", table_name="shared_identity")
    op.drop_index("ix_shared_identity_provider", table_name="shared_identity")
    op.drop_index("ix_shared_identity_user_id", table_name="shared_identity")
    op.drop_table("shared_identity")

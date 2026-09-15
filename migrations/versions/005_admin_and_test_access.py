"""Add administrator roles and unrestricted test access.

Revision ID: 005_admin_test_access
Revises: 004_live_activity
"""
from alembic import op
import sqlalchemy as sa


revision = "005_admin_test_access"
down_revision = "004_live_activity"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("has_test_access", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index("ix_user_is_admin", ["is_admin"])
        batch_op.create_index("ix_user_is_super_admin", ["is_super_admin"])
        batch_op.create_index("ix_user_has_test_access", ["has_test_access"])


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_has_test_access")
        batch_op.drop_index("ix_user_is_super_admin")
        batch_op.drop_index("ix_user_is_admin")
        batch_op.drop_column("has_test_access")
        batch_op.drop_column("is_super_admin")
        batch_op.drop_column("is_admin")

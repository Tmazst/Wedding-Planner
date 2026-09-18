"""Add legal consent and account deletion records.

Revision ID: 007_legal_consent
Revises: 006_app_visits
"""
from alembic import op
import sqlalchemy as sa


revision = "007_legal_consent"
down_revision = "006_app_visits"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("terms_accepted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("terms_version", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("privacy_version", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_user_deleted_at", ["deleted_at"], unique=False)


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_deleted_at")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("privacy_version")
        batch_op.drop_column("terms_version")
        batch_op.drop_column("terms_accepted_at")

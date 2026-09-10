"""add wedding profile image

Revision ID: 003_wedding_profile_image
Revises: 002_pricing_invitations
"""
from alembic import op
import sqlalchemy as sa

revision = "003_wedding_profile_image"
down_revision = "002_pricing_invitations"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("wedding") as batch_op:
        batch_op.add_column(sa.Column("profile_image", sa.String(length=255), nullable=True))

def downgrade():
    with op.batch_alter_table("wedding") as batch_op:
        batch_op.drop_column("profile_image")

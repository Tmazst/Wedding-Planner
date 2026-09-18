"""Store country-aware international phone numbers.

Revision ID: 008_international_phone
Revises: 007_legal_consent
"""
from alembic import op
import sqlalchemy as sa


revision = "008_international_phone"
down_revision = "007_legal_consent"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column("phone_country", sa.String(length=2), nullable=False, server_default="SZ")
        )
        batch_op.create_index("ix_user_phone_country", ["phone_country"], unique=False)
    op.execute(
        "UPDATE user SET phone_number = '+' || phone_number "
        "WHERE phone_number IS NOT NULL AND phone_number NOT LIKE '+%'"
    )


def downgrade():
    op.execute(
        "UPDATE user SET phone_number = substr(phone_number, 2) "
        "WHERE phone_number LIKE '+%'"
    )
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_phone_country")
        batch_op.drop_column("phone_country")

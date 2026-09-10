"""Add pricing, payments and stakeholder invitations.

Revision ID: 002_pricing_invitations
Revises: 001_initial_schema
"""
from alembic import op
import sqlalchemy as sa


revision = "002_pricing_invitations"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("phone_number", sa.String(length=20), nullable=True))
        batch_op.create_index("ix_user_phone_number", ["phone_number"], unique=True)

    with op.batch_alter_table("wedding") as batch_op:
        batch_op.add_column(sa.Column("plan_tier", sa.String(length=20), nullable=False, server_default="free"))
        batch_op.add_column(sa.Column("upgraded_at", sa.DateTime(), nullable=True))

    op.create_table(
        "invitation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=False),
        sa.Column("invitee_name", sa.String(length=120), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("payer", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitation_token", "invitation", ["token"], unique=True)
    op.create_index("ix_invitation_wedding_id", "invitation", ["wedding_id"], unique=False)

    op.create_table(
        "wedding_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wedding_id", "user_id", name="uq_wedding_member"),
    )
    op.create_index("ix_wedding_member_user_id", "wedding_member", ["user_id"], unique=False)
    op.create_index("ix_wedding_member_wedding_id", "wedding_member", ["wedding_id"], unique=False)

    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_ref_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("invitation_id", sa.Integer(), nullable=True),
        sa.Column("gateway_transaction_id", sa.String(length=120), nullable=True),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitation.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_external_ref_id", "payment", ["external_ref_id"], unique=True)
    op.create_index("ix_payment_invitation_id", "payment", ["invitation_id"], unique=False)
    op.create_index("ix_payment_status", "payment", ["status"], unique=False)
    op.create_index("ix_payment_user_id", "payment", ["user_id"], unique=False)
    op.create_index("ix_payment_wedding_id", "payment", ["wedding_id"], unique=False)


def downgrade():
    op.drop_table("payment")
    op.drop_table("wedding_member")
    op.drop_table("invitation")
    with op.batch_alter_table("wedding") as batch_op:
        batch_op.drop_column("upgraded_at")
        batch_op.drop_column("plan_tier")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_index("ix_user_phone_number")
        batch_op.drop_column("phone_number")


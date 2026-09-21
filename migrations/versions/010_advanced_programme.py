"""Add advanced programme and invitation card scaffolding.

Revision ID: 010_advanced_programme
Revises: 009_assistant_actions
"""
from alembic import op
import sqlalchemy as sa


revision = "010_advanced_programme"
down_revision = "009_assistant_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wedding_programme",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("template_key", sa.String(length=40), nullable=False),
        sa.Column("font_style", sa.String(length=40), nullable=False),
        sa.Column("primary_color", sa.String(length=16), nullable=False),
        sa.Column("accent_color", sa.String(length=16), nullable=False),
        sa.Column("show_profile_image", sa.Boolean(), nullable=False),
        sa.Column("closing_message", sa.String(length=255), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wedding_id"),
    )
    op.create_index("ix_wedding_programme_wedding_id", "wedding_programme", ["wedding_id"], unique=True)
    op.create_index("ix_wedding_programme_share_token", "wedding_programme", ["share_token"], unique=True)

    op.create_table(
        "programme_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("programme_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("time_label", sa.String(length=30), nullable=True),
        sa.Column("activity", sa.String(length=180), nullable=False),
        sa.Column("person_or_group", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("show_to_guests", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["programme_id"], ["wedding_programme.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_programme_item_programme_id", "programme_item", ["programme_id"], unique=False)

    op.create_table(
        "invitation_card_design",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wedding_id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=40), nullable=False),
        sa.Column("font_style", sa.String(length=40), nullable=False),
        sa.Column("primary_color", sa.String(length=16), nullable=False),
        sa.Column("accent_color", sa.String(length=16), nullable=False),
        sa.Column("show_profile_image", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wedding_id"),
    )
    op.create_index("ix_invitation_card_design_wedding_id", "invitation_card_design", ["wedding_id"], unique=True)
    op.create_index("ix_invitation_card_design_share_token", "invitation_card_design", ["share_token"], unique=True)


def downgrade():
    op.drop_index("ix_invitation_card_design_share_token", table_name="invitation_card_design")
    op.drop_index("ix_invitation_card_design_wedding_id", table_name="invitation_card_design")
    op.drop_table("invitation_card_design")
    op.drop_index("ix_programme_item_programme_id", table_name="programme_item")
    op.drop_table("programme_item")
    op.drop_index("ix_wedding_programme_share_token", table_name="wedding_programme")
    op.drop_index("ix_wedding_programme_wedding_id", table_name="wedding_programme")
    op.drop_table("wedding_programme")

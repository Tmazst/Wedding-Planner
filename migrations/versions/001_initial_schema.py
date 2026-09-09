"""Initial wedding budget schema.

Revision ID: 001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("user", sa.Column("id", sa.Integer(), nullable=False), sa.Column("name", sa.String(length=120), nullable=False), sa.Column("email", sa.String(length=255), nullable=False), sa.Column("password_hash", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.create_table("wedding", sa.Column("id", sa.Integer(), nullable=False), sa.Column("title", sa.String(length=160), nullable=False), sa.Column("partner_one", sa.String(length=100), nullable=False), sa.Column("partner_two", sa.String(length=100), nullable=False), sa.Column("wedding_date", sa.Date(), nullable=True), sa.Column("location", sa.String(length=160), nullable=True), sa.Column("budget_target", sa.Numeric(precision=12, scale=2), nullable=False), sa.Column("owner_id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["owner_id"], ["user.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_wedding_owner_id"), "wedding", ["owner_id"], unique=False)
    op.create_table("budget_category", sa.Column("id", sa.Integer(), nullable=False), sa.Column("name", sa.String(length=120), nullable=False), sa.Column("planned_amount", sa.Numeric(precision=12, scale=2), nullable=False), sa.Column("wedding_id", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["wedding_id"], ["wedding.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_budget_category_wedding_id"), "budget_category", ["wedding_id"], unique=False)
    op.create_table("quotation", sa.Column("id", sa.Integer(), nullable=False), sa.Column("vendor_name", sa.String(length=160), nullable=False), sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False), sa.Column("contact", sa.String(length=120), nullable=True), sa.Column("notes", sa.Text(), nullable=True), sa.Column("valid_until", sa.Date(), nullable=True), sa.Column("is_selected", sa.Boolean(), nullable=False), sa.Column("category_id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["category_id"], ["budget_category.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_quotation_category_id"), "quotation", ["category_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_quotation_category_id"), table_name="quotation")
    op.drop_table("quotation")
    op.drop_index(op.f("ix_budget_category_wedding_id"), table_name="budget_category")
    op.drop_table("budget_category")
    op.drop_index(op.f("ix_wedding_owner_id"), table_name="wedding")
    op.drop_table("wedding")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")


from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    has_test_access = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    weddings = db.relationship("Wedding", backref="owner", lazy=True, cascade="all, delete-orphan")
    memberships = db.relationship("WeddingMember", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def has_full_feature_access(self):
        """Whether this account bypasses normal package and payment limits."""
        return self.is_admin or self.is_super_admin or self.has_test_access


class Wedding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    partner_one = db.Column(db.String(100), nullable=False)
    partner_two = db.Column(db.String(100), nullable=False)
    wedding_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(160), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True)
    budget_target = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    plan_tier = db.Column(db.String(20), default="free", nullable=False)
    upgraded_at = db.Column(db.DateTime, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    categories = db.relationship("BudgetCategory", backref="wedding", lazy=True, cascade="all, delete-orphan")
    members = db.relationship("WeddingMember", backref="wedding", lazy=True, cascade="all, delete-orphan")
    invitations = db.relationship("Invitation", backref="wedding", lazy=True, cascade="all, delete-orphan")
    activities = db.relationship("ActivityEvent", backref="wedding", lazy=True, cascade="all, delete-orphan")

    @property
    def estimated_total(self):
        return sum((category.selected_amount for category in self.categories), start=0)

    @property
    def has_full_feature_access(self):
        return self.plan_tier == "standard" or self.owner.has_full_feature_access


class BudgetCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    planned_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    quotations = db.relationship("Quotation", backref="category", lazy=True, cascade="all, delete-orphan")

    @property
    def selected_quote(self):
        return next((quote for quote in self.quotations if quote.is_selected), None)

    @property
    def selected_amount(self):
        return self.selected_quote.amount if self.selected_quote else self.planned_amount


class Quotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor_name = db.Column(db.String(160), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    contact = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    is_selected = db.Column(db.Boolean, default=False, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("budget_category.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ActivityEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    actor = db.relationship("User", foreign_keys=[actor_user_id])


class WeddingMember(db.Model):
    __table_args__ = (db.UniqueConstraint("wedding_id", "user_id", name="uq_wedding_member"),)

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(40), default="stakeholder", nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Invitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    invitee_name = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(40), default="stakeholder", nullable=False)
    payer = db.Column(db.String(20), nullable=False)  # owner | invitee
    status = db.Column(db.String(30), default="pending", nullable=False)
    accepted_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_ref_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="SZL", nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    invitation_id = db.Column(db.Integer, db.ForeignKey("invitation.id"), nullable=True, index=True)
    gateway_transaction_id = db.Column(db.String(120), nullable=True)
    provider_reference = db.Column(db.String(120), nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    wedding = db.relationship("Wedding", foreign_keys=[wedding_id])
    invitation = db.relationship("Invitation", foreign_keys=[invitation_id])

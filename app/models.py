from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True, index=True)
    phone_country = db.Column(db.String(2), default="SZ", nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False, index=True)
    has_test_access = db.Column(db.Boolean, default=False, nullable=False, index=True)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    terms_version = db.Column(db.String(20), nullable=True)
    privacy_version = db.Column(db.String(20), nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    weddings = db.relationship("Wedding", backref="owner", lazy=True, cascade="all, delete-orphan")
    memberships = db.relationship("WeddingMember", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def phone_display(self):
        if not self.phone_number:
            return ""
        from .phone_numbers import format_phone_for_display
        return format_phone_for_display(self.phone_number, self.phone_country)

    @property
    def is_active(self):
        return self.deleted_at is None

    @property
    def has_full_feature_access(self):
        """Whether this account bypasses normal package and payment limits."""
        return self.is_admin or self.is_super_admin or self.has_test_access


class AppVisit(db.Model):
    """One privacy-friendly visit recorded per browser session."""

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


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
    programme = db.relationship("WeddingProgramme", backref="wedding", uselist=False, cascade="all, delete-orphan")
    invitation_card = db.relationship("InvitationCardDesign", backref="wedding", uselist=False, cascade="all, delete-orphan")

    @property
    def estimated_total(self):
        return sum((category.selected_amount for category in self.categories), start=0)

    @property
    def has_full_feature_access(self):
        return self.plan_tier in {"standard", "advanced"} or self.owner.has_full_feature_access

    @property
    def has_advanced_access(self):
        return self.plan_tier == "advanced" or self.owner.has_full_feature_access


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


class WeddingProgramme(db.Model):
    """Advanced-plan programme content and lightweight design selections."""

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), unique=True, nullable=False, index=True)
    title = db.Column(db.String(160), default="Wedding Programme", nullable=False)
    template_key = db.Column(db.String(40), default="floral_elegant", nullable=False)
    font_style = db.Column(db.String(40), default="elegant", nullable=False)
    primary_color = db.Column(db.String(16), default="#7d1020", nullable=False)
    accent_color = db.Column(db.String(16), default="#b88a3b", nullable=False)
    show_profile_image = db.Column(db.Boolean, default=True, nullable=False)
    closing_message = db.Column(db.String(255), nullable=True)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    share_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    items = db.relationship("ProgrammeItem", backref="programme", lazy=True, cascade="all, delete-orphan", order_by="ProgrammeItem.position")


class ProgrammeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey("wedding_programme.id"), nullable=False, index=True)
    position = db.Column(db.Integer, default=0, nullable=False)
    time_label = db.Column(db.String(30), nullable=True)
    activity = db.Column(db.String(180), nullable=False)
    person_or_group = db.Column(db.String(160), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    show_to_guests = db.Column(db.Boolean, default=True, nullable=False)


class InvitationCardDesign(db.Model):
    """Advanced-plan invitation-card design settings; card editor comes next."""

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), unique=True, nullable=False, index=True)
    template_key = db.Column(db.String(40), default="floral_elegant", nullable=False)
    font_style = db.Column(db.String(40), default="elegant", nullable=False)
    primary_color = db.Column(db.String(16), default="#7d1020", nullable=False)
    accent_color = db.Column(db.String(16), default="#b88a3b", nullable=False)
    show_profile_image = db.Column(db.Boolean, default=True, nullable=False)
    message = db.Column(db.Text, nullable=True)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    share_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


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


class AssistantPendingAction(db.Model):
    """Short-lived, server-side confirmation for an assistant write action."""

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    wedding_id = db.Column(db.Integer, db.ForeignKey("wedding.id"), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    wedding = db.relationship("Wedding", foreign_keys=[wedding_id])

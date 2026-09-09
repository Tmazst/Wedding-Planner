from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    weddings = db.relationship("Wedding", backref="owner", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Wedding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    partner_one = db.Column(db.String(100), nullable=False)
    partner_two = db.Column(db.String(100), nullable=False)
    wedding_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(160), nullable=True)
    budget_target = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    categories = db.relationship("BudgetCategory", backref="wedding", lazy=True, cascade="all, delete-orphan")

    @property
    def estimated_total(self):
        return sum((category.selected_amount for category in self.categories), start=0)


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


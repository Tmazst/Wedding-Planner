import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'wedding_planner.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FREE_BUDGET_ITEM_LIMIT = int(os.getenv("FREE_BUDGET_ITEM_LIMIT", "4"))
    OWNER_PLAN_PRICE = os.getenv("OWNER_PLAN_PRICE", "40.00")
    STAKEHOLDER_PRICE = os.getenv("STAKEHOLDER_PRICE", "30.00")
    PAYMENT_CURRENCY = os.getenv("MOJAPOS_CURRENCY", "SZL")
    MOJAPOS_MOCK_AUTO_COMPLETE = os.getenv(
        "MOJAPOS_MOCK_AUTO_COMPLETE", "false"
    ).lower() in {"1", "true", "yes", "on"}
    CSRF_PROTECT = True

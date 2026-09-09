from app import create_app
from app.extensions import db


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


def test_budget_and_quotation_flow():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    client = app.test_client()
    response = client.post("/register", data={"name":"Thabo","email":"test@example.com","password":"secret1"})
    assert response.status_code == 302
    response = client.post("/wedding/setup", data={"partner_one":"Lindiwe","partner_two":"Sibusiso","budget_target":"80000","location":"Manzini"})
    assert response.status_code == 302
    response = client.post("/budget", data={"name":"Photography","planned_amount":"10000"})
    assert response.status_code == 302
    response = client.post("/budget/1/quotes", data={"vendor_name":"Tech Xolutions","amount":"8500","contact":"76000000"})
    assert response.status_code == 302
    response = client.post("/quotes/1/select")
    assert response.status_code == 302
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"E8500.00" in dashboard.data


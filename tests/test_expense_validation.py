from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_expense_not_found():
    response = client.get("/expenses/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"


def test_update_expense_not_found():
    payload = {
        "amount": 100.00,
        "description": "Updated expense",
        "category_id": 1,
    }

    response = client.put("/expenses/9999", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"


def test_delete_expense_not_found():
    response = client.delete("/expenses/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"


def test_create_expense_invalid_amount():
    payload = {
        "amount": -50.00,
        "description": "Invalid expense",
        "category_id": 1,
    }

    response = client.post("/expenses/", json=payload)

    assert response.status_code == 422


def test_create_expense_missing_required_field():
    payload = {
        "description": "Missing amount",
        "category_id": 1,
    }

    response = client.post("/expenses/", json=payload)

    assert response.status_code == 422
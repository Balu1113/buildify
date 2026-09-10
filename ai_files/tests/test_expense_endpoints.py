from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_create_expense_success():
    payload = {
        "amount": 100.50,
        "description": "Dinner",
        "category_id": 1,
    }

    response = client.post("/expenses/", json=payload)

    assert response.status_code == 200

    data = response.json()

    assert data["amount"] == 100.50
    assert data["description"] == "Dinner"
    assert data["category_id"] == 1
    assert data["user_id"] == 1
    assert "id" in data


def test_read_expenses():
    response = client.get("/expenses/")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_delete_expense_not_found():
    response = client.delete("/expenses/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_update_expense_success():
    # Create expense
    create_response = client.post(
        "/expenses/",
        json={
            "amount": 50.25,
            "description": "Lunch",
            "category_id": 1,
        },
    )

    assert create_response.status_code == 200
    expense_id = create_response.json()["id"]

    # Update expense
    update_response = client.put(
        f"/expenses/{expense_id}",
        json={
            "amount": 75.50,
            "description": "Dinner",
            "category_id": 2,
        },
    )

    assert update_response.status_code == 200

    data = update_response.json()

    assert data["id"] == expense_id
    assert data["amount"] == 75.50
    assert data["description"] == "Dinner"
    assert data["category_id"] == 2


def test_update_expense_not_found():
    response = client.put(
        "/expenses/9999",
        json={
            "amount": 100,
            "description": "Test",
            "category_id": 1,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"


def test_delete_expense_success():
    # Create expense
    create_response = client.post(
        "/expenses/",
        json={
            "amount": 25.00,
            "description": "Coffee",
            "category_id": 1,
        },
    )

    assert create_response.status_code == 200
    expense_id = create_response.json()["id"]

    # Delete expense
    delete_response = client.delete(f"/expenses/{expense_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}

    # Verify it is gone
    expenses_response = client.get("/expenses/")

    assert expenses_response.status_code == 200

    expenses = expenses_response.json()

    assert all(expense["id"] != expense_id for expense in expenses)


def test_delete_expense_not_found():
    response = client.delete("/expenses/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app
from api.endpoints import get_db
from models.database import Base

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize database schema
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()

client = TestClient(app)

def test_create_expense():
    payload = {
        "amount": 15.75, 
        "description": "Coffee", 
        "category_id": 1, 
        "ai_label": "Beverage"
    }
    response = client.post("/expenses/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 15.75
    assert data["description"] == "Coffee"
    assert "id" in data

def test_read_expenses():
    client.post("/expenses/", json={"amount": 5.0, "description": "Test", "category_id": 1})
    response = client.get("/expenses/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_update_task():
    # Setup
    task_payload = {"title": "Task 1", "description": "Desc", "priority": "medium", "status": "todo"}
    resp = client.post("/tasks/", json=task_payload)
    task_id = resp.json()["id"]
    
    # Update
    update_payload = {"title": "Updated", "description": "New", "priority": "high", "status": "done"}
    resp = client.put(f"/tasks/{task_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"
    assert resp.json()["status"] == "done"

def test_delete_task():
    task_payload = {"title": "To Delete", "description": "...", "priority": "low", "status": "todo"}
    resp = client.post("/tasks/", json=task_payload)
    task_id = resp.json()["id"]
    
    resp = client.delete(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

def test_update_task_not_found():
    payload = {"title": "X", "description": "Y", "priority": "low", "status": "todo"}
    response = client.put("/tasks/9999", json=payload)
    assert response.status_code == 404

def test_delete_task_not_found():
    response = client.delete("/tasks/9999")
    assert response.status_code == 404

def test_update_expense_not_found():
    payload = {"amount": 20.0, "description": "Updated", "category_id": 1}
    response = client.put("/expenses/9999", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"

def test_delete_expense_not_found():
    response = client.delete("/expenses/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Expense not found"

def test_create_expense_invalid_payload():
    payload = {"description": "Invalid", "category_id": 1}
    response = client.post("/expenses/", json=payload)
    assert response.status_code == 422
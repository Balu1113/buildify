import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app
from models.database import Base
from api.endpoints import get_db

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
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


def test_create_expense_success():
    """Test successful expense creation."""
    payload = {
        "amount": 50.25,
        "description": "Lunch",
        "category_id": 1
    }
    response = client.post("/expenses/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 50.25
    assert data["description"] == "Lunch"
    assert "id" in data
    assert data["user_id"] == 1

def test_create_expense_invalid_input():
    """Test that invalid amount triggers a 422 error."""
    payload = {
        "amount": "not-a-number",
        "description": "Coffee",
        "category_id": 1
    }
    response = client.post("/expenses/", json=payload)
    assert response.status_code == 422

def test_create_expense_missing_required_fields():
    """Test that missing fields trigger a 422 error."""
    payload = {
        "amount": 10.00
        # Missing description and category_id
    }
    response = client.post("/expenses/", json=payload)
    assert response.status_code == 422
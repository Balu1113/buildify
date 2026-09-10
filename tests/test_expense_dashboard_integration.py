import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models.database import Base
from api.endpoints import get_db

# Setup for in-memory database tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables for tests
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

def test_create_expense_via_api():
    """
    Validate that the backend correctly processes manual expense entries 
    sent from the frontend via the /expenses/ POST endpoint.
    """
    payload = {
        "amount": 15.50,
        "description": "Test manual expense",
        "category_id": 2
    }
    response = client.post("/expenses/", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 15.50
    assert data["description"] == "Test manual expense"
    assert data["category_id"] == 2
    assert "id" in data

def test_create_expense_missing_category():
    """
    Validate that the API rejects requests missing the required category_id,
    as expected by Pydantic schema validation.
    """
    payload = {
        "amount": 10.0,
        "description": "Missing category test"
        # category_id omitted
    }
    response = client.post("/expenses/", json=payload)
    
    # 422 Unprocessable Entity is returned by FastAPI for validation errors
    assert response.status_code == 422
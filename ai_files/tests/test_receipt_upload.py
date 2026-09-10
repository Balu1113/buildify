import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app
from models.database import Base
from api.endpoints import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Database setup for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables for testing
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

@patch('api.endpoints.parse_receipt_image')
def test_upload_receipt_success(mock_parse):
    """
    Test that the /expenses/upload endpoint successfully processes a dummy file
    by mocking the Gemini service and returning parsed data.
    """
    mock_parse.return_value = {
        "amount": 25.0,
        "description": "Coffee Shop",
        "category_id": 1,
        "ai_label": "food"
    }
    
    response = client.post(
        "/expenses/upload",
        files={"file": ("receipt.jpg", b"fake_image_content", "image/jpeg")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 25.0
    assert data["description"] == "Coffee Shop"
    assert data["category_id"] == 1
    assert "id" in data

@patch('api.endpoints.parse_receipt_image')
def test_upload_receipt_parsing_failure(mock_parse):
    """
    Test that the API returns 400 when the service layer returns None (parsing failure).
    """
    mock_parse.return_value = None
    
    response = client.post(
        "/expenses/upload",
        files={"file": ("bad_receipt.jpg", b"bad_content", "image/jpeg")}
    )
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not parse receipt"
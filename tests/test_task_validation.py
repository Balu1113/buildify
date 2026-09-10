import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app
from api.endpoints import get_db
from models.database import Base

# Database setup for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_create_task_invalid_priority():
    payload = {
        "title": "Fix bug",
        "description": "A task",
        "priority": "urgent",  # Invalid
        "status": "todo"
    }
    response = client.post("/tasks/", json=payload)
    assert response.status_code == 422

def test_create_task_invalid_status():
    payload = {
        "title": "Fix bug",
        "description": "A task",
        "priority": "medium",
        "status": "pending"  # Invalid
    }
    response = client.post("/tasks/", json=payload)
    assert response.status_code == 422

def test_create_task_empty_title():
    payload = {
        "title": "",  # Empty string violates min_length=1
        "description": "A task",
        "priority": "medium",
        "status": "todo"
    }
    response = client.post("/tasks/", json=payload)
    assert response.status_code == 422

def test_create_task_valid_payload():
    payload = {
        "title": "Valid Task",
        "description": "This should work",
        "priority": "high",
        "status": "in_progress"
    }
    response = client.post("/tasks/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Valid Task"
    assert data["priority"] == "high"
    assert data["status"] == "in_progress"

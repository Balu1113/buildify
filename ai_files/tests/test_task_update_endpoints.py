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


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()

    
@pytest.fixture
def task_fixture():
    payload = {"title": "Initial Task", "description": "Initial Desc", "priority": "medium", "status": "todo"}
    response = client.post("/tasks/", json=payload)
    return response.json()["id"]

def test_update_task_success(task_fixture):
    update_payload = {"title": "Updated", "description": "New", "priority": "high", "status": "done"}
    response = client.put(f"/tasks/{task_fixture}", json=update_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["status"] == "done"

def test_update_task_partial_update(task_fixture):
    # Updating only status
    update_payload = {"title": "Initial Task", "description": "Initial Desc", "priority": "medium", "status": "in_progress"}
    response = client.put(f"/tasks/{task_fixture}", json=update_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

def test_update_task_not_found():
    payload = {"title": "X", "description": "Y", "priority": "low", "status": "todo"}
    response = client.put("/tasks/9999", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"

def test_update_task_invalid_enum(task_fixture):
    payload = {"title": "X", "description": "Y", "priority": "invalid_priority", "status": "todo"}
    response = client.put(f"/tasks/{task_fixture}", json=payload)
    assert response.status_code == 422

def test_update_task_empty_title(task_fixture):
    payload = {"title": "", "description": "Y", "priority": "low", "status": "todo"}
    response = client.put(f"/tasks/{task_fixture}", json=payload)
    assert response.status_code == 422
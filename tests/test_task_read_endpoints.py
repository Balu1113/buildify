import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app
from api.endpoints import get_db
from models.database import Base
from models.task import Task as TaskModel

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


def test_read_tasks_empty():
    response = client.get("/tasks/")
    assert response.status_code == 200
    assert response.json() == []

def test_read_tasks_populated():
    # Setup data
    db = TestingSessionLocal()
    task1 = TaskModel(title="Task 1", description="Desc 1")
    task2 = TaskModel(title="Task 2", description="Desc 2")
    db.add(task1)
    db.add(task2)
    db.commit()
    db.close()

    response = client.get("/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Task 1"
    assert data[1]["title"] == "Task 2"

def test_read_task_by_id_success():
    # Setup data
    db = TestingSessionLocal()
    task = TaskModel(title="Specific Task", description="Details")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Specific Task"
    assert data["id"] == task_id

def test_read_task_by_id_not_found():
    response = client.get("/tasks/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"
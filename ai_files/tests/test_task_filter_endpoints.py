from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_filter_tasks_by_status():
    client.post(
        "/tasks/",
        json={
            "title": "Todo Task",
            "priority": "high",
            "status": "todo",
        },
    )

    client.post(
        "/tasks/",
        json={
            "title": "Completed Task",
            "priority": "medium",
            "status": "done",
        },
    )

    response = client.get("/tasks/filter?status=todo")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Todo Task"


def test_filter_tasks_by_priority():
    client.post(
        "/tasks/",
        json={
            "title": "High Priority",
            "priority": "high",
            "status": "todo",
        },
    )

    client.post(
        "/tasks/",
        json={
            "title": "Low Priority",
            "priority": "low",
            "status": "todo",
        },
    )

    response = client.get("/tasks/filter?priority=high")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "High Priority"


def test_filter_tasks_by_status_and_priority():
    client.post(
        "/tasks/",
        json={
            "title": "Matching Task",
            "priority": "high",
            "status": "in_progress",
        },
    )

    client.post(
        "/tasks/",
        json={
            "title": "Different Priority",
            "priority": "low",
            "status": "in_progress",
        },
    )

    response = client.get(
        "/tasks/filter?status=in_progress&priority=high"
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Matching Task"


def test_filter_tasks_without_filters():
    client.post(
        "/tasks/",
        json={
            "title": "Task 1",
            "priority": "medium",
            "status": "todo",
        },
    )

    client.post(
        "/tasks/",
        json={
            "title": "Task 2",
            "priority": "high",
            "status": "done",
        },
    )

    response = client.get("/tasks/filter")

    assert response.status_code == 200
    assert len(response.json()) == 2
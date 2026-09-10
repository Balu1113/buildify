from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_delete_task_success(client):
    task_payload = {
        "title": "Task to delete",
        "description": "Cleanup",
        "priority": "medium",
        "status": "todo",
    }

    resp = client.post("/tasks/", json=task_payload)

    # POST /tasks/ creates a new resource
    assert resp.status_code == 201

    task_id = resp.json()["id"]

    # Delete
    resp = client.delete(f"/tasks/{task_id}")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Verify deleted
    resp_get = client.get(f"/tasks/{task_id}")

    assert resp_get.status_code == 404


def test_delete_task_not_found(client):
    response = client.delete("/tasks/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_delete_task_persistence(client):
    resp1 = client.post(
        "/tasks/",
        json={"title": "Task 1", "status": "todo"},
    )

    assert resp1.status_code == 201

    resp2 = client.post(
        "/tasks/",
        json={"title": "Task 2", "status": "todo"},
    )

    assert resp2.status_code == 201

    task1_id = resp1.json()["id"]
    task2_id = resp2.json()["id"]

    # Delete Task 1
    response = client.delete(f"/tasks/{task1_id}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Task 2 should still exist
    resp = client.get(f"/tasks/{task2_id}")

    assert resp.status_code == 200
    assert resp.json()["title"] == "Task 2"

    # Task 1 should be gone
    resp_gone = client.get(f"/tasks/{task1_id}")

    assert resp_gone.status_code == 404
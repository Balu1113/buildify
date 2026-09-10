from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_suggest_task_priority():
    response = client.post(
        "/tasks/suggest-priority",
        json={
            "title": "Fix production payment failure",
            "description": "Users are unable to complete payments",
            "priority": "medium",
            "status": "todo",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "suggested_priority" in data
    assert data["suggested_priority"] in {
        "high",
        "medium",
        "low",
    }
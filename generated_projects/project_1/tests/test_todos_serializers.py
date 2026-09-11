import pytest
from apps.todos.models import Todo
from apps.todos.serializers import TodoSerializer

@pytest.mark.django_db
def test_todo_serializer_valid_data(user):
    """Test serializer with string labels (API requirement)."""
    data = {
        "title": "Valid Task",
        "description": "Valid Desc",
        "status": "completed",
        "priority": "high",
        "due_date": "2025-01-01"
    }
    serializer = TodoSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    todo = serializer.save(user=user)
    assert todo.status == Todo.Status.COMPLETED
    assert todo.priority == Todo.Priority.HIGH

@pytest.mark.django_db
def test_todo_serializer_invalid_status(user):
    """Test serializer validation for invalid status/priority."""
    data = {
        "title": "Invalid Task",
        "status": "not-a-status",
        "priority": "low"
    }
    serializer = TodoSerializer(data=data)
    assert not serializer.is_valid()
    assert "status" in serializer.errors

@pytest.mark.django_db
def test_todo_serializer_representation(user):
    """Test serializer output format (must return strings, not integers)."""
    todo = Todo.objects.create(
        user=user, 
        title="Rep Task",
        status=Todo.Status.COMPLETED,
        priority=Todo.Priority.MEDIUM
    )
    serializer = TodoSerializer(todo)
    assert serializer.data['status'] == "completed"
    assert serializer.data['priority'] == "medium"

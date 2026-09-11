import pytest
from apps.todos.models import Todo

@pytest.mark.django_db
def test_todo_model_creation(user):
    """Test Todo model field initialization and defaults."""
    todo = Todo.objects.create(
        user=user,
        title="New Task",
        description="Task Details"
    )
    assert todo.title == "New Task"
    assert todo.description == "Task Details"
    assert todo.status == Todo.Status.PENDING
    assert todo.priority == Todo.Priority.LOW
    assert todo.user == user

@pytest.mark.django_db
def test_todo_string_rep(user):
    todo = Todo.objects.create(user=user, title="Rep Test")
    assert str(todo) == "Rep Test"

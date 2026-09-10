import pytest
from pydantic import ValidationError
from schemas.task_schemas import TaskCreate
from models.task import PriorityEnum, StatusEnum

def test_task_schema_validation_success():
    data = {
        "title": "Valid Task",
        "description": "A description",
        "priority": "high",
        "status": "todo"
    }
    task = TaskCreate(**data)
    assert task.title == "Valid Task"
    assert task.priority == PriorityEnum.high

def test_task_schema_validation_defaults():
    data = {"title": "Minimal Task"}
    task = TaskCreate(**data)
    assert task.priority == PriorityEnum.medium
    assert task.status == StatusEnum.todo

def test_task_schema_validation_invalid_enum():
    with pytest.raises(ValidationError):
        TaskCreate(title="Bad Task", priority="invalid_priority")
    
    with pytest.raises(ValidationError):
        TaskCreate(title="Bad Task", status="invalid_status")
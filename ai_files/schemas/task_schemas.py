from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from models.task import PriorityEnum, StatusEnum


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    priority: PriorityEnum = PriorityEnum.medium
    status: StatusEnum = StatusEnum.todo


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
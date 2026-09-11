from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class ExpenseBase(BaseModel):
    amount: float = Field(..., gt=0)
    description: str
    category_id: int
    ai_label: Optional[str] = None

class ExpenseCreate(ExpenseBase):
    pass

class Expense(ExpenseBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
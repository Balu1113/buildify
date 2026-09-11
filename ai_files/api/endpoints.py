from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from models.database import SessionLocal
from models.expense_models import Expense as ExpenseModel
from models.task import Task as TaskModel, PriorityEnum, StatusEnum
from schemas.expense_schemas import Expense, ExpenseCreate
from schemas.task_schemas import Task, TaskCreate
from services.gemini_service import parse_receipt_image
from services.task_ai_service import suggest_task_priority
import datetime

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/tasks/", response_model=List[Task])
def read_tasks(db: Session = Depends(get_db)):
    return db.query(TaskModel).all()

@router.get("/tasks/filter", response_model=List[Task])
def filter_tasks(
    status: StatusEnum | None = Query(None),
    priority: PriorityEnum | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(TaskModel)

    if status is not None:
        query = query.filter(TaskModel.status == status)

    if priority is not None:
        query = query.filter(TaskModel.priority == priority)

    return query.all()

@router.get("/tasks/{task_id}", response_model=Task)
def read_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return db_task

@router.post("/tasks/", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    db_task = TaskModel(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, task: TaskCreate, db: Session = Depends(get_db)):
    db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in task.model_dump().items():
        setattr(db_task, key, value)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(db_task)
    db.commit()
    return {"ok": True}

@router.post("/expenses/", response_model=Expense)
def create_expense(expense: ExpenseCreate, db: Session = Depends(get_db)):
    db_expense = ExpenseModel(**expense.model_dump(), user_id=1)
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@router.get("/expenses/summary")
def get_monthly_summary(db: Session = Depends(get_db)):
    today = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    start_of_month = datetime.datetime(today.year, today.month, 1)
    
    summary = db.query(ExpenseModel.category_id, func.sum(ExpenseModel.amount)).filter(
        ExpenseModel.date >= start_of_month
    ).group_by(ExpenseModel.category_id).all()
    
    return [{"category_id": row[0], "total": row[1]} for row in summary]


@router.get("/expenses/{expense_id}", response_model=Expense)
def read_expense(expense_id: int, db: Session = Depends(get_db)):
    db_expense = db.query(ExpenseModel).filter(ExpenseModel.id == expense_id).first()
    if not db_expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return db_expense

@router.post("/expenses/upload")
async def upload_receipt(file: UploadFile = File(...), db: Session = Depends(get_db)):

    content = await file.read()

    parsed_data = parse_receipt_image(
        content,
        file.content_type or "image/jpeg"
    )
    
    if not parsed_data:
        raise HTTPException(status_code=400, detail="Could not parse receipt")
        
    db_expense = ExpenseModel(**parsed_data, user_id=1)
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@router.get("/expenses/", response_model=List[Expense])
def read_expenses(db: Session = Depends(get_db)):
    return db.query(ExpenseModel).all()

@router.put("/expenses/{expense_id}", response_model=Expense)
def update_expense(expense_id: int, expense: ExpenseCreate, db: Session = Depends(get_db)):
    db_expense = db.query(ExpenseModel).filter(ExpenseModel.id == expense_id).first()
    if not db_expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    for key, value in expense.model_dump().items():
        setattr(db_expense, key, value)
    db.commit()
    return db_expense

@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    db_expense = db.query(ExpenseModel).filter(ExpenseModel.id == expense_id).first()
    if not db_expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(db_expense)
    db.commit()
    return {"ok": True}


@router.post("/tasks/suggest-priority")
def suggest_priority(
    task: TaskCreate,
):
    priority = suggest_task_priority(
        title=task.title,
        description=task.description,
    )

    return {
        "suggested_priority": priority
    }
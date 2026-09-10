from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from services.gemini_service import GeminiParser
from api.endpoints import router as expense_router

load_dotenv()

app = FastAPI(
    title="Student Task Management API",
    description="A RESTful backend service for managing student tasks and expenses.",
    version="1.0.0"
)

parser = GeminiParser()

app.include_router(expense_router)

@app.post("/parse-expense", tags=["Expenses"])
def parse_expense_endpoint(text: str):
    result = parser.parse_expense(text)
    if not result:
        raise HTTPException(status_code=422, detail="Could not parse expense data")
    return result
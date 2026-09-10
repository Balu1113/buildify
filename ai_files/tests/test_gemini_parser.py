import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def mock_parser(mocker):
    # Patch the parser instance inside main.py
    return mocker.patch('main.parser.parse_expense')

def test_parse_expense_success(mock_parser):
    """
    Verify that a valid expense string returns structured JSON data.
    """
    mock_data = {"amount": 15.50, "merchant": "Starbucks", "category": "Food"}
    mock_parser.return_value = mock_data
    
    response = client.post("/parse-expense?text=Spent%2015.50%20at%20Starbucks")
    
    assert response.status_code == 200
    assert response.json() == mock_data
    mock_parser.assert_called_once_with("Spent 15.50 at Starbucks")

def test_parse_expense_endpoint_invalid_input(mock_parser):
    """
    Verify that when the service returns None, the endpoint returns a 422 error.
    """
    mock_parser.return_value = None
    
    response = client.post("/parse-expense?text=Invalid%20data")
    
    assert response.status_code == 422
    assert response.json() == {"detail": "Could not parse expense data"}
    mock_parser.assert_called_once_with("Invalid data")
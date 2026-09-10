import pytest
from services.gemini_service import GeminiParser, ExpenseData

@pytest.fixture
def parser():
    return GeminiParser()

def test_gemini_parser_successful_extraction(mocker, parser):
    # Mock the generate_response function in services.gemini_service
    mocker.patch('services.gemini_service.generate_response', return_value='{"amount": 10.0, "merchant": "TestStore", "category": "Food"}')
    
    result = parser.parse_expense("spent 10 at teststore")
    
    assert isinstance(result, ExpenseData)
    assert result.amount == 10.0
    assert result.merchant == "TestStore"
    assert result.category == "Food"

def test_gemini_parser_malformed_json(mocker, parser):
    # Mock returns non-json text
    mocker.patch('services.gemini_service.generate_response', return_value='Not a JSON string')
    
    result = parser.parse_expense("garbage input")
    
    assert result is None

def test_gemini_parser_cleans_markdown(mocker, parser):
    # Mock returns markdown wrapped json
    mocker.patch('services.gemini_service.generate_response', return_value='```json\n{"amount": 5.0, "merchant": "Shop", "category": "Misc"}\n```')
    
    result = parser.parse_expense("test input")
    
    assert result is not None
    assert isinstance(result, ExpenseData)
    assert result.amount == 5.0
    assert result.merchant == "Shop"
    assert result.category == "Misc"
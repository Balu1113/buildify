from unittest.mock import patch

from services.gemini_service import GeminiParser, parse_receipt_image


def test_parse_expense_success():
    mock_response = """
    {
        "amount": 250.50,
        "merchant": "Swiggy",
        "category": "Food"
    }
    """

    with patch(
        "services.gemini_service.client.models.generate_content"
    ) as mock_generate:

        mock_generate.return_value.text = mock_response

        parser = GeminiParser()
        result = parser.parse_expense("Swiggy order total 250.50")

        assert result is not None
        assert result.amount == 250.50
        assert result.merchant == "Swiggy"
        assert result.category == "Food"

        mock_generate.assert_called_once()


def test_parse_expense_invalid_json():
    with patch(
        "services.gemini_service.client.models.generate_content"
    ) as mock_generate:

        mock_generate.return_value.text = "This is not JSON"

        parser = GeminiParser()
        result = parser.parse_expense("Some expense")

        assert result is None


def test_parse_receipt_image_success():
    mock_response = """
    {
        "amount": 499.99,
        "merchant": "Amazon",
        "category": "Shopping"
    }
    """

    with patch(
        "services.gemini_service.client.models.generate_content"
    ) as mock_generate:

        mock_generate.return_value.text = mock_response

        result = parse_receipt_image(
            b"fake image content",
            "image/jpeg"
        )

        assert result is not None
        assert result["amount"] == 499.99
        assert result["merchant"] == "Amazon"
        assert result["category"] == "Shopping"

        mock_generate.assert_called_once()


def test_parse_receipt_image_invalid_response():
    with patch(
        "services.gemini_service.client.models.generate_content"
    ) as mock_generate:

        mock_generate.return_value.text = "Invalid response"

        result = parse_receipt_image(
            b"fake image content",
            "image/jpeg"
        )

        assert result is None
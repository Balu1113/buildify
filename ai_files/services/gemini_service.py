import json
import re
from typing import Optional

from pydantic import BaseModel, Field
from llm.client import client, MODEL_NAME


def generate_response(prompt: str) -> str:
    """Return the model text through a small seam that tests can mock."""
    return client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    ).text


class ExpenseData(BaseModel):
    amount: float = Field(..., description="The total expense amount")
    merchant: str = Field(..., description="The store or service name")
    category: str = Field(
        ...,
        description="The spending category such as Food, Transport, Utilities"
    )


class GeminiParser:

    def parse_expense(self, text: str) -> Optional[ExpenseData]:

        prompt = f"""
Extract expense details from this text:

{text}

Return ONLY valid JSON with exactly these keys:
{{
    "amount": <float>,
    "merchant": "<string>",
    "category": "<string>"
}}

Do not include markdown, code blocks, or explanations.
"""

        try:
            response_text = generate_response(prompt).strip()

            clean_json = re.sub(
                r"```json\s*|\s*```",
                "",
                response_text
            ).strip()

            data = json.loads(clean_json)

            return ExpenseData(**data)

        except Exception as e:
            print(f"Error parsing expense text: {e}")
            return None


def parse_receipt_image(
    image_content: bytes,
    mime_type: str = "image/jpeg"
) -> Optional[dict]:

    prompt = """
Analyze this receipt image and extract the expense information.

Return ONLY valid JSON with exactly these keys:

{
    "amount": <float>,
    "merchant": "<string>",
    "category": "<string>"
}

Rules:
- amount must be the final/total amount paid
- merchant must be the store/business name
- category should be a simple category such as Food, Transport,
  Shopping, Utilities, Healthcare, Entertainment, or Other
- Do not include markdown
- Do not include explanations
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                {
                    "mime_type": mime_type,
                    "data": image_content,
                },
            ],
        )

        response_text = response.text.strip()

        clean_json = re.sub(
            r"```json\s*|\s*```",
            "",
            response_text
        ).strip()

        data = json.loads(clean_json)

        expense = ExpenseData(**data)

        return expense.model_dump()

    except Exception as e:
        print(f"Error parsing receipt image: {e}")
        return None
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")


API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is not set. "
        "Add it to your .env file."
    )


client = genai.Client(
    api_key=API_KEY
)


MODEL_NAME = os.getenv("GEMINI_MODEL_NAME")


def generate_response(prompt: str) -> str:

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    return response.text


def generate_image_response(prompt: str, image_content: bytes, mime_type: str) -> str:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            prompt,
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_content,
                }
            },
        ],
    )

    return response.text
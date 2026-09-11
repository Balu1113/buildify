import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY is not set")

url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = {
    "model": "openrouter/free",
    "messages": [
        {
            "role": "system",
            "content": "You are an expert software developer."
        },
        {
            "role": "user",
            "content": """
Write a Python function that checks whether a string is a palindrome.

Return only the Python code.
"""
        }
    ]
}

response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=120,
)

print("Status:", response.status_code)

if response.ok:
    result = response.json()
    print("\nModel:", result.get("model"))
    print("\nResponse:")
    print(result["choices"][0]["message"]["content"])
else:
    print("\nRequest failed:")
    print(response.text)
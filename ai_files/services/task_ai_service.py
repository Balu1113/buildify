from llm.client import generate_response


def suggest_task_priority(
    title: str,
    description: str | None = None,
) -> str:
    prompt = f"""
You are an AI task management assistant.

Analyze this task and determine its priority.

Task title:
{title}

Task description:
{description or "No description provided"}

Choose exactly one priority:
high
medium
low

Return ONLY the priority word.
"""

    try:
        response = generate_response(prompt).strip().lower()

        if response in {"high", "medium", "low"}:
            return response

        return "medium"

    except Exception as e:
        print(f"Error suggesting task priority: {e}")
        return "medium"
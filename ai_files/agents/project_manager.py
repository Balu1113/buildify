import asyncio
import json

from llm.client import generate_response
from mcp_client.client import MCPProjectClient


SYSTEM_PROMPT = """
You are the Project Manager Agent for an AI Student Project Manager.

Your job is to understand a student's software project idea and break it
into practical development tasks.

Create 5-8 practical tasks.

Each task must contain:
- title
- description
- priority: high, medium, or low

Do not write code.
Do not create vague tasks.
Tasks should represent real software development work.

Use the configured Gemini API for AI functionality.
Do not recommend OpenAI or other paid providers.

Return ONLY valid JSON in this format:

{
    "project_name": "...",
    "project_description": "...",
    "tasks": [
        {
            "title": "...",
            "description": "...",
            "priority": "high|medium|low"
        }
    ]
}
"""


async def main():

    print("\n" + "=" * 60)
    print("AI STUDENT PROJECT MANAGER")
    print("=" * 60)

    project_idea = input(
        "\nDescribe your project:\n> "
    )

    # ==========================================================
    # 1. GEMINI GENERATES PROJECT PLAN
    # ==========================================================

    prompt = f"""
{SYSTEM_PROMPT}

Student project idea:

{project_idea}
"""

    print("\nThinking...\n")

    response = generate_response(prompt)

    print("RAW AI RESPONSE:")
    print(response)

    try:
        plan = json.loads(response)

    except json.JSONDecodeError:
        print("\nAI returned invalid JSON.")
        return

    # ==========================================================
    # 2. DISPLAY GENERATED PLAN
    # ==========================================================

    print("\n" + "-" * 60)
    print("AI GENERATED PROJECT PLAN")
    print("-" * 60)

    print(f"\nProject: {plan['project_name']}")
    print(f"Description: {plan['project_description']}")

    print("\nTasks:")

    for i, task in enumerate(plan["tasks"], 1):

        print(f"\n{i}. {task['title']}")
        print(f"   Priority: {task['priority']}")
        print(f"   {task['description']}")

    # ==========================================================
    # 3. CONNECT TO MCP
    # ==========================================================

    print("\n" + "-" * 60)
    print("CONNECTING TO MCP PROJECT SERVER")
    print("-" * 60)

    mcp = MCPProjectClient()

    await mcp.connect()

    print("MCP connection successful!")

    # ==========================================================
    # 4. CREATE PROJECT USING MCP
    # ==========================================================

    print("\n" + "-" * 60)
    print("CREATING PROJECT THROUGH MCP")
    print("-" * 60)

    project_result = await mcp.call_tool(
        "create_project",
        {
            "name": plan["project_name"],
            "description": plan["project_description"],
        },
    )

    project = project_result[0]

    print(json.dumps(project, indent=2))

    project_id = project["project_id"]

    # ==========================================================
    # 5. CREATE TASKS USING MCP
    # ==========================================================

    print("\n" + "-" * 60)
    print("CREATING TASKS THROUGH MCP")
    print("-" * 60)

    for task in plan["tasks"]:

        task_result = await mcp.call_tool(
            "create_task",
            {
                "project_id": project_id,
                "title": task["title"],
                "description": task["description"],
                "priority": task["priority"],
            },
        )

        created_task = task_result[0]

        print(
            f"✓ {created_task['task_id']} | "
            f"{created_task['title']} | "
            f"{created_task['priority']}"
        )

    # ==========================================================
    # 6. GET PROJECT FROM MCP
    # ==========================================================

    print("\n" + "-" * 60)
    print("FINAL PROJECT")
    print("-" * 60)

    project_result = await mcp.call_tool(
        "get_project",
        {
            "project_id": project_id,
        },
    )

    final_project = project_result[0]

    print(json.dumps(final_project, indent=2))

    # ==========================================================
    # 7. LIST TASKS FROM MCP
    # ==========================================================

    print("\n" + "-" * 60)
    print("FINAL TASK LIST")
    print("-" * 60)

    tasks_result = await mcp.call_tool(
        "list_tasks",
        {
            "project_id": project_id,
        },
    )

    tasks = tasks_result

    for i, task in enumerate(tasks, 1):

        print(
            f"{i}. "
            f"{task['status']:12} | "
            f"{task['priority']:8} | "
            f"{task['title']}"
        )

    # ==========================================================
    # 8. CLOSE MCP CONNECTION
    # ==========================================================

    await mcp.disconnect()

    print("\n" + "=" * 60)
    print("PROJECT CREATED SUCCESSFULLY")
    print("=" * 60)

    print(f"\nProject ID: {project_id}")


if __name__ == "__main__":
    asyncio.run(main())
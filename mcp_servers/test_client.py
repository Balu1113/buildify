import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


server_params = StdioServerParameters(
    command="python",
    args=["mcp_servers/project_server.py"],
)


async def main():

    async with stdio_client(server_params) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            print("\n" + "=" * 60)
            print("MCP PROJECT MANAGEMENT TEST")
            print("=" * 60)

            # ==================================================
            # 1. DISCOVER TOOLS
            # ==================================================

            tools_result = await session.list_tools()

            print("\nAvailable tools:")

            for tool in tools_result.tools:
                print(f"  ✓ {tool.name}")

            # ==================================================
            # 2. CREATE PROJECT
            # ==================================================

            print("\n" + "-" * 60)
            print("1. CREATING PROJECT")
            print("-" * 60)

            project_result = await session.call_tool(
                "create_project",
                arguments={
                    "name": "AI Student Project Manager",
                    "description": (
                        "A multi-agent AI system that helps "
                        "students plan and manage software projects."
                    ),
                },
            )

            project = json.loads(
                project_result.content[0].text
            )

            print(json.dumps(project, indent=2))

            project_id = project["project_id"]

            # ==================================================
            # 3. GET PROJECT
            # ==================================================

            print("\n" + "-" * 60)
            print("2. GETTING PROJECT")
            print("-" * 60)

            project_result = await session.call_tool(
                "get_project",
                arguments={
                    "project_id": project_id
                },
            )

            project = json.loads(
                project_result.content[0].text
            )

            print(json.dumps(project, indent=2))

            # ==================================================
            # 4. CREATE TASKS
            # ==================================================

            print("\n" + "-" * 60)
            print("3. CREATING TASKS")
            print("-" * 60)

            task_titles = [
                (
                    "Design project architecture",
                    "Define frontend, backend and database architecture.",
                    "high",
                ),
                (
                    "Create backend API",
                    "Implement the initial FastAPI backend.",
                    "high",
                ),
                (
                    "Create database schema",
                    "Design the database tables for project management.",
                    "medium",
                ),
                (
                    "Build frontend dashboard",
                    "Create the student project dashboard.",
                    "medium",
                ),
            ]

            created_tasks = []

            for title, description, priority in task_titles:

                result = await session.call_tool(
                    "create_task",
                    arguments={
                        "project_id": project_id,
                        "title": title,
                        "description": description,
                        "priority": priority,
                    },
                )

                task = json.loads(
                    result.content[0].text
                )

                created_tasks.append(task)

                print(
                    f"\n✓ {task['task_id']} | "
                    f"{task['title']} | "
                    f"{task['priority']}"
                )

            # ==================================================
            # 5. LIST TASKS
            # ==================================================

            print("\n" + "-" * 60)
            print("4. LISTING PROJECT TASKS")
            print("-" * 60)

            result = await session.call_tool(
                "list_tasks",
                arguments={
                    "project_id": project_id
                },
            )

            print("\nRAW RESPONSE FROM list_tasks:")    
            print(result.content[0].text)

            tasks_response = json.loads(
                result.content[0].text
            )

            print("Raw list_tasks response:")
            print(json.dumps(tasks_response, indent=2))

            # Handle either:
            # {"tasks": [...]}
            # or directly [...]
            if isinstance(tasks_response, dict):
                tasks = tasks_response.get("tasks", [])
            else:
                tasks = tasks_response

            for task in tasks:
                print(
                    f"{task['task_id']} | "
                    f"{task['status']} | "
                    f"{task['priority']} | "
                    f"{task['title']}"
                )

            # ==================================================
            # 6. UPDATE FIRST TASK
            # ==================================================

            first_task = created_tasks[0]

            print("\n" + "-" * 60)
            print("5. UPDATING FIRST TASK")
            print("-" * 60)

            result = await session.call_tool(
                "update_task",
                arguments={
                    "task_id": first_task["task_id"],
                    "status": "in_progress",
                },
            )

            updated_task = json.loads(
                result.content[0].text
            )

            print(json.dumps(updated_task, indent=2))

            # ==================================================
            # 7. FINAL TASK LIST
            # ==================================================

            print("\n" + "-" * 60)
            print("6. FINAL PROJECT STATE")
            print("-" * 60)

            result = await session.call_tool(
                "list_tasks",
                arguments={
                    "project_id": project_id
                },
            )

            tasks = [
                json.loads(content.text)
                for content in result.content
                if hasattr(content, "text")
            ]

            for task in tasks:

                print(
                    f"{task['status']:12} | "
                    f"{task['priority']:8} | "
                    f"{task['title']}"
                )

            print("\n" + "=" * 60)
            print("MCP WORKFLOW COMPLETED SUCCESSFULLY")
            print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
import json
import asyncio

from llm.client import generate_response
from mcp_client.client import MCPProjectClient


SYSTEM_PROMPT = """
You are the Task Planner Agent in an AI Student Project Manager.

Your job is to review an existing software project and its tasks.

You must identify tasks that are:

- too broad
- missing important implementation steps
- incorrectly prioritized
- duplicated
- poorly ordered

You should improve the development plan.

Do not write code.

Return ONLY valid JSON in this format:

{
    "analysis": "...",
    "actions": [
        {
            "action": "update_task",
            "task_id": "...",
            "changes": {
                "status": "...",
                "priority": "...",
                "title": "...",
                "description": "..."
            }
        },
        {
            "action": "delete_task",
            "task_id": "..."
        },
        {
            "action": "create_task",
            "title": "...",
            "description": "...",
            "priority": "high|medium|low"
        }
    ]
}

Rules:

1. Only include actions that are actually required.

2. Use the exact task_id values provided in CURRENT TASKS.

3. Never invent a task_id.

4. Use update_task when an existing task should be changed.

5. Use delete_task when a task is duplicated or clearly unnecessary.

6. Use create_task when a genuinely missing task is required.

7. Do not merely describe a recommendation.
   Represent the recommendation as an executable action.

8. Do not modify tasks unnecessarily.

9. Do not create duplicate tasks.

10. If a task needs a priority change, use update_task.

11. If a task needs its title or description changed, use update_task.

12. If a task should be removed, use delete_task.

13. If a task is poorly ordered, remember that the current MCP system
    does not have a reorder operation. Do not pretend that you can reorder
    tasks unless an available MCP tool supports reordering.

14. Do not write code.

15. Do not invent requirements unrelated to the project.

16. If no changes are required, return:

{
    "analysis": "...",
    "actions": []
}

17. Every existing task modification must be represented as an
    executable update_task action.

18. Every new task must be represented as a create_task action.

19. Every unnecessary or duplicate task must be represented as a
    delete_task action.

20. Return ONLY valid JSON.
"""


# ==============================================================
# HELPERS
# ==============================================================


def print_separator(title=None):

    print("\n" + "=" * 60)

    if title:
        print(title)
        print("=" * 60)


def find_task(tasks, task_id):

    for task in tasks:

        if (
            isinstance(task, dict)
            and task.get("task_id") == task_id
        ):
            return task

    return None


def print_mcp_error(result, operation):

    print(
        f"\n⚠ MCP error during {operation}:"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
        if not isinstance(result, str)
        else result
    )


def is_error_response(value):

    return (
        isinstance(value, dict)
        and "error" in value
    )


# ==============================================================
# MAIN
# ==============================================================


async def main():

    print("\n" + "=" * 60)
    print("TASK PLANNER AGENT")
    print("=" * 60)

    mcp = MCPProjectClient()

    await mcp.connect()

    print("\nMCP connection successful!")

    try:

        # ======================================================
        # 1. GET PROJECT ID
        # ======================================================

        project_id = input(
            "\nEnter Project ID:\n> "
        ).strip()

        if not project_id:

            print(
                "\nProject ID cannot be empty."
            )

            return

        # ======================================================
        # 2. GET PROJECT
        # ======================================================

        project_result = await mcp.call_tool(
            "get_project",
            {
                "project_id": project_id
            }
        )

        if not project_result:

            print(
                "\nProject not found."
            )

            return

        project = project_result[0]

        if not isinstance(project, dict):

            print(
                "\nUnexpected project response:"
            )

            print(
                json.dumps(
                    project,
                    indent=2
                )
                if not isinstance(project, str)
                else project
            )

            return

        if "error" in project:

            print(
                f"\nMCP Error: "
                f"{project['error']}"
            )

            return

        if "name" not in project:

            print(
                "\nMCP returned a project without "
                "the expected 'name' field:"
            )

            print(
                json.dumps(
                    project,
                    indent=2
                )
            )

            return

        # ======================================================
        # 3. GET CURRENT TASKS
        # ======================================================

        tasks_result = await mcp.call_tool(
            "list_tasks",
            {
                "project_id": project_id
            }
        )

        if not isinstance(tasks_result, list):

            print(
                "\nUnexpected task response:"
            )

            print(
                json.dumps(
                    tasks_result,
                    indent=2
                )
                if not isinstance(tasks_result, str)
                else tasks_result
            )

            return

        tasks = [
            task
            for task in tasks_result
            if isinstance(task, dict)
        ]

        # ======================================================
        # 4. DISPLAY CURRENT PROJECT
        # ======================================================

        print_separator(
            "CURRENT PROJECT"
        )

        print(
            f"\nProject: "
            f"{project['name']}"
        )

        print(
            f"Description: "
            f"{project.get('description', '')}"
        )

        print("\nCurrent tasks:")

        if not tasks:

            print(
                "No tasks found."
            )

        else:

            for i, task in enumerate(
                tasks,
                1
            ):

                print(
                    f"{i}. "
                    f"{task.get('title', '')} "
                    f"[{task.get('priority', '')}] "
                    f"[{task.get('status', '')}] "
                    f"(ID: {task.get('task_id', '')})"
                )

        # ======================================================
        # 5. SEND PROJECT TO GEMINI
        # ======================================================

        prompt = f"""
{SYSTEM_PROMPT}

PROJECT:

{json.dumps(project, indent=2)}

CURRENT TASKS:

{json.dumps(tasks, indent=2)}
"""

        print_separator(
            "TASK PLANNER ANALYZING..."
        )

        response = generate_response(
            prompt
        )

        print(
            "\nRAW AI RESPONSE:"
        )

        print(response)

        # ======================================================
        # 6. PARSE AI RESPONSE
        # ======================================================

        try:

            analysis = json.loads(
                response
            )

        except json.JSONDecodeError:

            print(
                "\n⚠ AI returned invalid JSON."
            )

            return

        # ======================================================
        # 7. VALIDATE AI RESPONSE
        # ======================================================

        if not isinstance(
            analysis,
            dict
        ):

            print(
                "\n⚠ AI response must be a JSON object."
            )

            return

        ai_analysis = analysis.get(
            "analysis",
            ""
        )

        actions = analysis.get(
            "actions",
            []
        )

        if not isinstance(
            actions,
            list
        ):

            print(
                "\n⚠ AI returned an invalid actions field."
            )

            return

        # ======================================================
        # 8. DISPLAY ANALYSIS
        # ======================================================

        print_separator(
            "TASK PLANNER ANALYSIS"
        )

        print(
            f"\n{ai_analysis}"
        )

        # ======================================================
        # 9. DISPLAY PLANNED ACTIONS
        # ======================================================

        print_separator(
            "PLANNED MCP ACTIONS"
        )

        if not actions:

            print(
                "\nNo changes required."
            )

        else:

            for i, action in enumerate(
                actions,
                1
            ):

                if not isinstance(
                    action,
                    dict
                ):

                    print(
                        f"\n{i}. ⚠ Invalid action:"
                    )

                    print(
                        json.dumps(
                            action,
                            indent=2
                        )
                        if not isinstance(
                            action,
                            str
                        )
                        else action
                    )

                    continue

                action_type = action.get(
                    "action"
                )

                print(
                    f"\n{i}. Action: "
                    f"{action_type}"
                )

                # ------------------------------------------------
                # UPDATE
                # ------------------------------------------------

                if action_type == "update_task":

                    print(
                        f"   Task ID: "
                        f"{action.get('task_id')}"
                    )

                    print(
                        "   Changes:"
                    )

                    print(
                        json.dumps(
                            action.get(
                                "changes",
                                {}
                            ),
                            indent=6
                        )
                    )

                # ------------------------------------------------
                # DELETE
                # ------------------------------------------------

                elif action_type == "delete_task":

                    print(
                        f"   Task ID: "
                        f"{action.get('task_id')}"
                    )

                # ------------------------------------------------
                # CREATE
                # ------------------------------------------------

                elif action_type == "create_task":

                    print(
                        f"   Title: "
                        f"{action.get('title')}"
                    )

                    print(
                        f"   Priority: "
                        f"{action.get('priority')}"
                    )

                    print(
                        f"   Description: "
                        f"{action.get('description')}"
                    )

                else:

                    print(
                        "   ⚠ Unknown action type"
                    )

        # ======================================================
        # 10. EXECUTE ACTIONS
        # ======================================================

        if actions:

            print_separator(
                "EXECUTING MCP ACTIONS"
            )

        for action in actions:

            if not isinstance(
                action,
                dict
            ):

                print(
                    "\n⚠ Skipping invalid action."
                )

                continue

            action_type = action.get(
                "action"
            )

            # ==================================================
            # UPDATE TASK
            # ==================================================

            if action_type == "update_task":

                task_id = action.get(
                    "task_id"
                )

                changes = action.get(
                    "changes",
                    {}
                )

                if not task_id:

                    print(
                        "\n⚠ Cannot update task: "
                        "missing task_id."
                    )

                    continue

                matching_task = find_task(
                    tasks,
                    task_id
                )

                if not matching_task:

                    print(
                        f"\n⚠ Cannot update task. "
                        f"Task ID not found: {task_id}"
                    )

                    continue

                if not isinstance(
                    changes,
                    dict
                ):

                    print(
                        f"\n⚠ Invalid changes for "
                        f"task {task_id}"
                    )

                    continue

                # ------------------------------------------------
                # Allowed fields
                # ------------------------------------------------

                allowed_fields = {
                    "status",
                    "priority",
                    "title",
                    "description"
                }

                clean_changes = {
                    key: value
                    for key, value in changes.items()
                    if (
                        key in allowed_fields
                        and value is not None
                    )
                }

                if not clean_changes:

                    print(
                        f"\nℹ No valid changes for "
                        f"{task_id}"
                    )

                    continue

                # ------------------------------------------------
                # Validate priority
                # ------------------------------------------------

                if "priority" in clean_changes:

                    if clean_changes["priority"] not in {
                        "high",
                        "medium",
                        "low"
                    }:

                        print(
                            f"\n⚠ Invalid priority "
                            f"for task {task_id}"
                        )

                        continue

                # ------------------------------------------------
                # Validate status
                # ------------------------------------------------

                if "status" in clean_changes:

                    if clean_changes["status"] not in {
                        "todo",
                        "in_progress",
                        "completed",
                        "blocked"
                    }:

                        print(
                            f"\n⚠ Invalid status "
                            f"for task {task_id}"
                        )

                        continue

                # ------------------------------------------------
                # Remove unchanged values
                # ------------------------------------------------

                actual_changes = {}

                for key, value in clean_changes.items():

                    if (
                        matching_task.get(key)
                        != value
                    ):

                        actual_changes[key] = value

                if not actual_changes:

                    print(
                        f"\nℹ No changes needed for "
                        f"{matching_task.get('title')}"
                    )

                    continue

                # ------------------------------------------------
                # MCP UPDATE
                # ------------------------------------------------

                result = await mcp.call_tool(
                    "update_task",
                    {
                        "task_id": task_id,
                        **actual_changes
                    }
                )

                if not result:

                    print(
                        f"\n⚠ MCP returned no response "
                        f"for update: {task_id}"
                    )

                    continue

                updated_task = result[0]

                # IMPORTANT:
                # Never blindly call .get()
                # on the MCP response.

                if not isinstance(
                    updated_task,
                    dict
                ):

                    print(
                        f"\n⚠ Unexpected MCP response "
                        f"for update_task {task_id}:"
                    )

                    print(
                        updated_task
                    )

                    continue

                if is_error_response(
                    updated_task
                ):

                    print_mcp_error(
                        updated_task,
                        f"update_task {task_id}"
                    )

                    continue

                print(
                    f"✓ UPDATED | "
                    f"{updated_task.get('task_id')} | "
                    f"{updated_task.get('title')} | "
                    f"{updated_task.get('priority')} | "
                    f"{updated_task.get('status')}"
                )

                # Keep local task state synchronized.

                matching_task.update(
                    updated_task
                )

            # ==================================================
            # DELETE TASK
            # ==================================================

            elif action_type == "delete_task":

                task_id = action.get(
                    "task_id"
                )

                if not task_id:

                    print(
                        "\n⚠ Cannot delete task: "
                        "missing task_id."
                    )

                    continue

                matching_task = find_task(
                    tasks,
                    task_id
                )

                if not matching_task:

                    print(
                        f"\n⚠ Cannot delete task. "
                        f"Task ID not found: {task_id}"
                    )

                    continue

                result = await mcp.call_tool(
                    "delete_task",
                    {
                        "task_id": task_id
                    }
                )

                if not result:

                    print(
                        f"\n⚠ MCP returned no response "
                        f"for delete: {task_id}"
                    )

                    continue

                deleted_result = result[0]

                if not isinstance(
                    deleted_result,
                    dict
                ):

                    print(
                        f"\n⚠ Unexpected MCP response "
                        f"for delete_task {task_id}:"
                    )

                    print(
                        deleted_result
                    )

                    continue

                if is_error_response(
                    deleted_result
                ):

                    print_mcp_error(
                        deleted_result,
                        f"delete_task {task_id}"
                    )

                    continue

                print(
                    f"✓ DELETED | "
                    f"{task_id} | "
                    f"{matching_task.get('title')}"
                )

                tasks.remove(
                    matching_task
                )

            # ==================================================
            # CREATE TASK
            # ==================================================

            elif action_type == "create_task":

                title = action.get(
                    "title"
                )

                description = action.get(
                    "description"
                )

                priority = action.get(
                    "priority",
                    "medium"
                )

                if not title:

                    print(
                        "\n⚠ Cannot create task: "
                        "title missing."
                    )

                    continue

                if not description:

                    print(
                        f"\n⚠ Cannot create task "
                        f"'{title}': description missing."
                    )

                    continue

                if priority not in {
                    "high",
                    "medium",
                    "low"
                }:

                    print(
                        f"\n⚠ Invalid priority "
                        f"for new task: {priority}"
                    )

                    continue

                # ------------------------------------------------
                # Duplicate protection
                # ------------------------------------------------

                duplicate = next(
                    (
                        task
                        for task in tasks
                        if (
                            isinstance(task, dict)
                            and task.get(
                                "title",
                                ""
                            ).strip().lower()
                            == title.strip().lower()
                        )
                    ),
                    None
                )

                if duplicate:

                    print(
                        f"\nℹ Skipping duplicate task: "
                        f"{title}"
                    )

                    continue

                # ------------------------------------------------
                # MCP CREATE
                # ------------------------------------------------

                result = await mcp.call_tool(
                    "create_task",
                    {
                        "project_id": project_id,
                        "title": title,
                        "description": description,
                        "priority": priority
                    }
                )

                if not result:

                    print(
                        f"\n⚠ MCP returned no response "
                        f"for create: {title}"
                    )

                    continue

                created_task = result[0]

                if not isinstance(
                    created_task,
                    dict
                ):

                    print(
                        f"\n⚠ Unexpected MCP response "
                        f"for create_task:"
                    )

                    print(
                        created_task
                    )

                    continue

                if is_error_response(
                    created_task
                ):

                    print_mcp_error(
                        created_task,
                        f"create_task {title}"
                    )

                    continue

                print(
                    f"✓ CREATED | "
                    f"{created_task.get('task_id')} | "
                    f"{created_task.get('title')} | "
                    f"{created_task.get('priority')}"
                )

                # Add to local state so another create
                # action cannot duplicate it.

                tasks.append(
                    created_task
                )

            # ==================================================
            # UNKNOWN ACTION
            # ==================================================

            else:

                print(
                    f"\n⚠ Unknown MCP action: "
                    f"{action_type}"
                )

        # ======================================================
        # 11. RELOAD FINAL TASK LIST FROM MCP
        # ======================================================

        final_result = await mcp.call_tool(
            "list_tasks",
            {
                "project_id": project_id
            }
        )

        if not isinstance(
            final_result,
            list
        ):

            print(
                "\n⚠ Unable to retrieve final task list."
            )

            return

        final_tasks = [
            task
            for task in final_result
            if isinstance(task, dict)
        ]

        # ======================================================
        # 12. DISPLAY FINAL TASK LIST
        # ======================================================

        print_separator(
            "UPDATED PROJECT TASK LIST"
        )

        if not final_tasks:

            print(
                "\nNo tasks found."
            )

        else:

            for i, task in enumerate(
                final_tasks,
                1
            ):

                print(
                    f"{i}. "
                    f"{task.get('status', ''):12} | "
                    f"{task.get('priority', ''):8} | "
                    f"{task.get('title', '')}"
                )

        # ======================================================
        # 13. SUMMARY
        # ======================================================

        print_separator()

        print(
            "Task Planner successfully reviewed "
            "and applied the project plan."
        )

    finally:

        # ======================================================
        # 14. DISCONNECT MCP
        # ======================================================

        await mcp.disconnect()

    print(
        "\n" + "=" * 60
    )

    print(
        "TASK PLANNER COMPLETED"
    )

    print(
        "=" * 60
    )


# ==============================================================
# ENTRY POINT
# ==============================================================

if __name__ == "__main__":

    asyncio.run(main())
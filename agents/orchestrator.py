import asyncio
import json

from mcp_client.client import MCPProjectClient

from agents.developer import run_developer
from agents.tester import run_testing_agent
from agents.debugger import run_debugger
from agents.reviewer import run_reviewer


# ==============================================================
# CONFIGURATION
# ==============================================================


MAX_DEBUG_RETRIES = 2


PRIORITY_ORDER = {
    "high": 1,
    "medium": 2,
    "low": 3,
}


# ==============================================================
# HELPERS
# ==============================================================


def print_separator(title=None):

    print("\n" + "=" * 60)

    if title:
        print(title)
        print("=" * 60)


def print_json(value):

    try:

        print(
            json.dumps(
                value,
                indent=2
            )
        )

    except TypeError:

        print(str(value))


def parse_mcp_item(item):

    if isinstance(item, dict):

        return item

    if isinstance(item, str):

        try:

            return json.loads(item)

        except json.JSONDecodeError:

            return item

    if hasattr(item, "text"):

        text = item.text

        if isinstance(text, str):

            try:

                return json.loads(text)

            except json.JSONDecodeError:

                return text

    return item


def parse_mcp_result(result):

    if result is None:

        return []

    if not isinstance(result, list):

        result = [result]

    parsed = []

    for item in result:

        value = parse_mcp_item(
            item
        )

        if isinstance(value, list):

            parsed.extend(
                value
            )

        else:

            parsed.append(
                value
            )

    return parsed


def first_dict(result):

    for item in parse_mcp_result(
        result
    ):

        if isinstance(item, dict):

            return item

    return None


def find_task(
    tasks,
    task_id
):

    for task in tasks:

        if (
            isinstance(task, dict)
            and task.get("task_id")
            == task_id
        ):

            return task

    return None


def select_next_task(tasks):

    """
    Select the next unfinished task.

    Priority:
        1. in_progress tasks
        2. todo tasks

    Within each status, priority is:
        high -> medium -> low

    If priorities are equal, preserve the
    original project task ordering.
    """

    unfinished_tasks = [
        task
        for task in tasks
        if (
            isinstance(task, dict)
            and task.get("status") in {
                "todo",
                "in_progress"
            }
        )
    ]

    if not unfinished_tasks:
        return None

    unfinished_tasks.sort(
        key=lambda task: (
            0 if task.get("status") == "in_progress" else 1,
            PRIORITY_ORDER.get(
                str(
                    task.get(
                        "priority",
                        ""
                    )
                ).lower(),
                99
            )
        )
    )

    return unfinished_tasks[0]



async def update_task_status(
    mcp,
    task_id,
    status
):

    try:

        result = await mcp.call_tool(
            "update_task",
            {
                "task_id": task_id,
                "status": status
            }
        )

    except Exception as exc:

        print(
            f"\n⚠ Failed to update task "
            f"{task_id}: {exc}"
        )

        return False

    for item in parse_mcp_result(
        result
    ):

        if (
            isinstance(item, dict)
            and item.get("error")
        ):

            print(
                f"\n⚠ Task status update failed: "
                f"{item['error']}"
            )

            return False

    print(
        f"✓ TASK STATUS | "
        f"{task_id} -> {status}"
    )

    return True


# ==============================================================
# TESTER
# ==============================================================


async def run_tester(
    project_id,
    task_id,
    project=None,
    tasks=None,
    selected_task=None
):

    """
    Run the actual Testing Agent.

    The Testing Agent owns:
    - source inspection
    - test generation
    - test validation
    - test execution

    It does not own implementation task completion.
    """

    print_separator(
        "TESTING AGENT"
    )

    try:

        tester_result = await run_testing_agent(
            project_id=project_id,
            task_id=task_id,
            project=project,
            tasks=tasks,
            selected_task=selected_task,
            show_output=True
        )

    except Exception as exc:

        print(
            f"\n✗ Testing Agent exception: "
            f"{exc}"
        )

        return {
            "success": False,
            "status": "failed",
            "error": str(exc)
        }

    return tester_result


# ==============================================================
# DEBUGGER
# ==============================================================


async def run_debugger_agent(
    project_id,
    task_id
):

    """
    Run the real Debugger Agent.

    The Debugger Agent is programmatically callable
    through agents.debugger.run_debugger().
    """

    print_separator(
        "DEBUGGER AGENT"
    )

    print(
        f"Project: {project_id}"
    )

    print(
        f"Task: {task_id}"
    )

    try:

        debugger_result = await run_debugger(
            project_id=project_id,
            task_id=task_id
        )

    except Exception as exc:

        print(
            f"\n✗ Debugger Agent exception: "
            f"{exc}"
        )

        return {
            "success": False,
            "status": "failed",
            "error": str(exc)
        }

    return debugger_result


# ==============================================================
# REVIEWER
# ==============================================================


async def run_reviewer_agent(
    project_id,
    task_id,
    project=None,
    tasks=None,
    selected_task=None
):

    print_separator(
        "CODE REVIEW AGENT"
    )

    try:

        reviewer_result = await run_reviewer(
            project_id=project_id,
            task_id=task_id,
            project=project,
            tasks=tasks,
            selected_task=selected_task,
            show_output=True
        )

    except Exception as exc:

        print(
            f"\n✗ Reviewer Agent exception: "
            f"{exc}"
        )

        return {
            "success": False,
            "status": "failed",
            "error": str(exc)
        }

    return reviewer_result

# ==============================================================
# TASK EXECUTION
# ==============================================================


async def execute_task(
    mcp,
    project_id,
    project,
    tasks,
    task
):

    task_id = task.get(
        "task_id"
    )

    task_title = task.get(
        "title",
        ""
    )

    print_separator(
        "EXECUTING TASK"
    )

    print(
        f"\nTask: {task_title}"
    )

    print(
        f"Task ID: {task_id}"
    )

    print(
        f"Priority: "
        f"{task.get('priority', '')}"
    )

    print(
        f"Status: "
        f"{task.get('status', '')}"
    )

    # ==========================================================
    # MARK TASK IN PROGRESS
    # ==========================================================

    status_updated = await update_task_status(
        mcp,
        task_id,
        "in_progress"
    )

    if not status_updated:

        return {
            "success": False,
            "stage": "status_update",
            "error": (
                "Could not mark task "
                "as in_progress."
            )
        }

    # ==========================================================
    # DEVELOPER AGENT
    # ==========================================================

    print_separator(
        "STARTING DEVELOPER AGENT"
    )

    try:

        developer_result = await run_developer(
            project_id,
            task_id
        )

    except Exception as exc:

        print(
            f"\n✗ Developer Agent exception: "
            f"{exc}"
        )

        developer_result = {
            "success": False,
            "status": "failed",
            "error": str(exc)
        }

    print_separator(
        "DEVELOPER AGENT RESULT"
    )

    print_json(
        developer_result
    )

    if not developer_result.get(
        "success",
        False
    ):

        print(
            "\n⚠ Developer stage failed."
        )

        await update_task_status(
            mcp,
            task_id,
            "in_progress"
        )

        return {
            "success": False,
            "stage": "developer",
            "developer": developer_result
        }

    print(
        "\n✓ Developer Agent successfully "
        "implemented the task."
    )

    # ==========================================================
    # TESTING AGENT
    # ==========================================================

    tester_result = await run_tester(
        project_id=project_id,
        task_id=task_id,
        project=project,
        tasks=tasks,
        selected_task=task
    )

    print_separator(
        "TESTING AGENT RESULT"
    )

    print_json(
        tester_result
    )

    # ==========================================================
    # TESTER FAILURE
    # ==========================================================

    if not tester_result.get(
        "success",
        False
    ):

        print(
            "\n⚠ Testing Agent reported "
            "a failure."
        )

        # ======================================================
        # TESTER FAILURE CLASSIFICATION
        # ======================================================
        # Only invoke the Debugger when pytest actually ran and
        # reported a failure. Generation, validation, creation, or
        # read-back failures are Testing Agent failures and must not
        # be mistaken for implementation failures.
        # ======================================================
        test_run = tester_result.get(
            "test_run",
            {}
        )

        pytest_executed = (
            isinstance(test_run, dict)
            and test_run.get("executed") is True
        )

        if not pytest_executed:
            error_message = tester_result.get(
                "error",
                "Testing Agent failed before pytest execution."
            )

            print(
                "\n✗ Testing Agent failed before "
                "pytest execution."
            )
            print(
                f"Reason: {error_message}"
            )

            await update_task_status(
                mcp,
                task_id,
                "in_progress"
            )

            return {
                "success": False,
                "stage": "testing",
                "developer": developer_result,
                "tester": tester_result,
                "debugger": {
                    "success": False,
                    "status": "not_run",
                    "reason": (
                        "Debugger was not run because "
                        "pytest did not execute."
                    )
                }
            }

        # ======================================================
        # DEBUGGER
        # ======================================================

        debugger_result = await run_debugger_agent(
            project_id,
            task_id
        )

        print_separator(
            "DEBUGGER AGENT RESULT"
        )

        print_json(
            debugger_result
        )

        if not debugger_result.get(
            "success",
            False
        ):

            print(
                "\n✗ Debugger could not "
                "resolve the failure."
            )

            await update_task_status(
                mcp,
                task_id,
                "in_progress"
            )

            return {
                "success": False,
                "stage": "debugger",
                "developer": developer_result,
                "tester": tester_result,
                "debugger": debugger_result
            }

        print(
            "\n✓ Debugger Agent successfully "
            "resolved the failure."
        )

        # ======================================================
        # AFTER DEBUGGING, TESTS HAVE ALREADY BEEN RE-RUN
        # BY THE DEBUGGER.
        #
        # Therefore we only continue when the debugger reports
        # success.
        # ======================================================

        tester_after_debug = {
            "success": True,
            "status": "passed_after_debugger"
        }

        tester_result = {
            **tester_result,
            "after_debugger": tester_after_debug
        }

    else:

        # ======================================================
        # TESTS ALREADY PASSED
        # ======================================================

        print(
            "\n✓ Testing Agent successfully "
            "generated and executed tests."
        )

        debugger_result = {
            "success": True,
            "status": "not_required",
            "reason": "Tests passed on first execution."
        }

    # ==========================================================
    # REVIEWER AGENT
    # ==========================================================

    reviewer_result = await run_reviewer_agent(
        project_id=project_id,
        task_id=task_id,
        project=project,
        tasks=tasks,
        selected_task=task
    )
    
    print_separator(
        "CODE REVIEW AGENT RESULT"
    )

    print_json(
        reviewer_result
    )

    if not reviewer_result.get(
        "success",
        False
    ):

        print(
            "\n⚠ Code review failed."
        )

        await update_task_status(
            mcp,
            task_id,
            "in_progress"
        )

        return {
            "success": False,
            "stage": "review",
            "developer": developer_result,
            "tester": tester_result,
            "debugger": debugger_result,
            "reviewer": reviewer_result
        }

    print(
        "\n✓ Reviewer Agent approved "
        "the implementation."
    )

    # ==========================================================
    # COMPLETED
    # ==========================================================

    completed_status_updated = await update_task_status(
        mcp,
        task_id,
        "completed"
    )

    if not completed_status_updated:

        return {
            "success": False,
            "stage": "status_update",
            "developer": developer_result,
            "tester": tester_result,
            "debugger": debugger_result,
            "reviewer": reviewer_result,
            "error": (
                "Pipeline succeeded but "
                "task status could not be "
                "updated to completed."
            )
        }

    print_separator(
        "TASK COMPLETED"
    )

    print(
        f"\n✓ {task_title}"
    )

    return {
        "success": True,
        "stage": "completed",
        "developer": developer_result,
        "tester": tester_result,
        "debugger": debugger_result,
        "reviewer": reviewer_result
    }


# ==============================================================
# MAIN
# ==============================================================


async def main():

    print_separator(
        "ORCHESTRATOR AGENT"
    )

    mcp = MCPProjectClient()

    await mcp.connect()

    print(
        "\nProject MCP connection successful!"
    )

    try:

        # ======================================================
        # PROJECT ID
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
        # GET PROJECT
        # ======================================================

        project_result = await mcp.call_tool(
            "get_project",
            {
                "project_id": project_id
            }
        )

        project = first_dict(
            project_result
        )

        if not project:

            print(
                "\nProject not found."
            )

            return

        if project.get("error"):

            print(
                f"\nMCP Error: "
                f"{project['error']}"
            )

            return

        # ======================================================
        # GET TASKS
        # ======================================================

        tasks_result = await mcp.call_tool(
            "list_tasks",
            {
                "project_id": project_id
            }
        )

        tasks = [
            item
            for item in parse_mcp_result(
                tasks_result
            )
            if (
                isinstance(item, dict)
                and not item.get("error")
            )
        ]

        if not tasks:

            print(
                "\nNo tasks found."
            )

            return

        # ======================================================
        # PROJECT
        # ======================================================

        print_separator(
            "PROJECT"
        )

        print(
            f"\nProject: "
            f"{project.get('name', '')}"
        )

        print(
            f"Description: "
            f"{project.get('description', '')}"
        )

        # ======================================================
        # TASK SUMMARY
        # ======================================================

        print_separator(
            "TASK SUMMARY"
        )

        for task in tasks:

            print(
                f"\n[{task.get('status', '').upper()}] "
                f"{str(task.get('priority', '')).upper()} "
                f"| {task.get('task_id', '')}"
            )

            print(
                f"  {task.get('title', '')}"
            )

        # ======================================================
        # SELECT NEXT TASK
        # ======================================================

        selected_task = select_next_task(
            tasks
        )

        if not selected_task:

            print_separator(
                "PROJECT COMPLETE"
            )

            print(
                "\n✓ All tasks are completed."
            )

            return

        # ======================================================
        # NEXT TASK
        # ======================================================

        print_separator(
            "NEXT TASK"
        )

        print(
            f"\nTitle: "
            f"{selected_task.get('title', '')}"
        )

        print(
            f"Task ID: "
            f"{selected_task.get('task_id', '')}"
        )

        print(
            f"Priority: "
            f"{selected_task.get('priority', '')}"
        )

        print(
            f"Description: "
            f"{selected_task.get('description', '')}"
        )

        # ======================================================
        # CONFIRM
        # ======================================================

        confirmation = input(
            "\nExecute this task through the "
            "Developer → Tester → Debugger → Reviewer "
            "pipeline? (y/n):\n> "
        ).strip().lower()

        if confirmation not in {
            "y",
            "yes"
        }:

            print(
                "\nExecution cancelled."
            )

            return

        # ======================================================
        # EXECUTE TASK
        # ======================================================

        result = await execute_task(
            mcp=mcp,
            project_id=project_id,
            project=project,
            tasks=tasks,
            task=selected_task
        )

        # ======================================================
        # FINAL RESULT
        # ======================================================

        print_separator(
            "ORCHESTRATOR RESULT"
        )

        print_json(
            {
                "project_id": project_id,
                "project": project.get(
                    "name",
                    ""
                ),
                "task": selected_task,
                "result": result
            }
        )

        if result.get(
            "success",
            False
        ):

            print(
                "\n✓ Orchestrator completed "
                "the task successfully."
            )

        else:

            print(
                "\n⚠ Orchestrator stopped at: "
                f"{result.get('stage', 'unknown')}"
            )

    finally:

        try:

            await mcp.disconnect()

        except Exception as exc:

            print(
                f"\n⚠ MCP disconnect error: "
                f"{exc}"
            )

        print(
            "\n" + "=" * 60
        )

        print(
            "ORCHESTRATOR AGENT COMPLETED"
        )

        print(
            "=" * 60
        )


# ==============================================================
# ENTRY POINT
# ==============================================================


if __name__ == "__main__":

    asyncio.run(
        main()
    )

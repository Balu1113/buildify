import ast
import asyncio
import json
import posixpath
import subprocess
import sys

from llm.client import generate_response
from mcp_client.client import MCPProjectClient
from mcp_client.file_client import MCPFileClient


SYSTEM_PROMPT = """
You are the Debug Agent in an AI Student Project Manager.

Your job is to debug ONE software development task whose automated tests
are failing.

You are given:
- the project information
- the selected task
- the project file structure
- relevant source files
- relevant test files
- pytest output

You must reason from the ACTUAL SOURCE CODE and ACTUAL TEST OUTPUT.

Return ONLY valid JSON:

{
    "task": "...",
    "diagnosis": "...",
    "root_cause": "...",
    "failure_type": "production_code|test_code|dependency|configuration|environment|unknown",
    "fix_strategy": "...",
    "files_to_modify": [
        "..."
    ],
    "files_to_create": [],
    "dependencies": [],
    "changes": [
        {
            "action": "update|create",
            "path": "...",
            "content": "COMPLETE FILE CONTENT"
        }
    ],
    "verification": [
        "..."
    ]
}

Rules:

1. Focus only on the selected task.

2. Inspect the actual source code and actual test output.

3. Do not guess about the cause of a failure.

4. Distinguish between:
   - production code failures
   - test code failures
   - dependency failures
   - configuration failures
   - environment failures
   - import/collection failures

5. Fix the root cause, not merely the visible symptom.

6. Reuse the existing project architecture.

7. Do not rewrite unrelated files.

8. Do not invent functions, classes, endpoints, models, or APIs.

9. Use exact file paths from the supplied project structure.

10. Only modify files that were actually inspected.

11. Never modify a test merely to hide a legitimate production-code failure.

12. If the test is genuinely incorrect, the test may be fixed.

13. Do not make real external API calls.

14. Never expose API keys or secrets.

15. Every changed file must contain COMPLETE resulting file content.

16. Return ONLY valid JSON.
"""


# ==============================================================
# GENERAL HELPERS
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

        value = parse_mcp_item(item)

        if isinstance(value, list):
            parsed.extend(value)
        else:
            parsed.append(value)

    return parsed


def first_dict(result):

    for item in parse_mcp_result(result):

        if isinstance(item, dict):
            return item

    return None


def response_has_error(result):

    for item in parse_mcp_result(result):

        if (
            isinstance(item, dict)
            and item.get("error")
        ):
            return item["error"]

    return None


def find_task(tasks, task_id):

    for task in tasks:

        if (
            isinstance(task, dict)
            and task.get("task_id") == task_id
        ):
            return task

    return None


def display_task(task):

    print(
        f"\nTitle: "
        f"{task.get('title', '')}"
    )

    print(
        f"Priority: "
        f"{task.get('priority', '')}"
    )

    print(
        f"Status: "
        f"{task.get('status', '')}"
    )

    print(
        f"Task ID: "
        f"{task.get('task_id', '')}"
    )

    print(
        f"Description: "
        f"{task.get('description', '')}"
    )


# ==============================================================
# PATH HELPERS
# ==============================================================


def normalize_path(path):

    if not isinstance(path, str):
        return ""

    path = path.replace("\\", "/").strip()

    if path == ".":
        return "."

    return path.rstrip("/")


def is_safe_relative_path(path):

    if not isinstance(path, str):
        return False

    path = path.replace("\\", "/").strip()

    if not path:
        return False

    if path.startswith("/"):
        return False

    if ":" in path.split("/")[0]:
        return False

    normalized = posixpath.normpath(path)

    if normalized == "..":
        return False

    if normalized.startswith("../"):
        return False

    return True


# ==============================================================
# FILE DISCOVERY
# ==============================================================


async def get_project_files(file_mcp):

    discovered_files = set()
    visited_directories = set()

    directories = ["."]

    while directories:

        current_directory = normalize_path(
            directories.pop()
        )

        if current_directory in visited_directories:
            continue

        visited_directories.add(
            current_directory
        )

        try:

            result = await file_mcp.list_files(
                current_directory
            )

        except Exception as exc:

            print(
                f"\n⚠ Failed to list "
                f"{current_directory}: {exc}"
            )

            continue

        for item in parse_mcp_result(result):

            if not isinstance(item, dict):
                continue

            item_path = normalize_path(
                item.get("path", "")
            )

            item_type = item.get("type")

            if not item_path:
                continue

            if item_type == "directory":

                if item_path not in visited_directories:
                    directories.append(item_path)

            elif item_type == "file":

                discovered_files.add(
                    item_path
                )

    return sorted(discovered_files)


async def read_file_safe(
    file_mcp,
    path
):

    try:

        result = await file_mcp.read_file(
            path
        )

    except Exception as exc:

        print(
            f"\n⚠ Failed to read "
            f"{path}: {exc}"
        )

        return None

    for item in parse_mcp_result(result):

        if not isinstance(item, dict):
            continue

        if item.get("error"):

            print(
                f"\n⚠ MCP error reading "
                f"{path}: "
                f"{item['error']}"
            )

            return None

        if "content" in item:

            return item.get(
                "content",
                ""
            )

    return None


async def read_files(
    file_mcp,
    paths
):

    contents = []

    for path in paths:

        content = await read_file_safe(
            file_mcp,
            path
        )

        if content is None:
            continue

        contents.append(
            {
                "path": path,
                "content": content
            }
        )

    return contents


# ==============================================================
# PYTHON VALIDATION
# ==============================================================


def validate_python_content(
    path,
    content
):

    if not path.endswith(".py"):
        return True, None

    try:

        ast.parse(
            content,
            filename=path
        )

        return True, None

    except SyntaxError as exc:

        return (
            False,
            f"{exc.msg} "
            f"(line {exc.lineno}, "
            f"column {exc.offset})"
        )

    except Exception as exc:

        return False, str(exc)


# ==============================================================
# TEST EXECUTION
# ==============================================================


def run_pytest(test_paths):

    if not test_paths:

        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "No test files supplied.",
            "passed": False
        }

    print(
        "\nExecuting pytest:"
    )

    for path in test_paths:

        print(
            f"  • {path}"
        )

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *test_paths,
                "-v"
            ],
            capture_output=True,
            text=True
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "passed": result.returncode == 0
        }

    except Exception as exc:

        return {
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "passed": False
        }


# ==============================================================
# DEBUG IMPLEMENTATION
# ==============================================================


async def debug_task(
    project_mcp,
    file_mcp,
    project_id,
    task_id
):

    # ==========================================================
    # GET PROJECT
    # ==========================================================

    project_result = await project_mcp.call_tool(
        "get_project",
        {
            "project_id": project_id
        }
    )

    project = first_dict(
        project_result
    )

    if not project:

        return {
            "success": False,
            "status": "project_not_found",
            "error": "Project not found."
        }

    if project.get("error"):

        return {
            "success": False,
            "status": "project_error",
            "error": project["error"]
        }

    # ==========================================================
    # GET TASKS
    # ==========================================================

    tasks_result = await project_mcp.call_tool(
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

        return {
            "success": False,
            "status": "no_tasks",
            "error": "No tasks found."
        }

    selected_task = find_task(
        tasks,
        task_id
    )

    if not selected_task:

        return {
            "success": False,
            "status": "task_not_found",
            "error": f"Task not found: {task_id}"
        }

    # ==========================================================
    # DISPLAY PROJECT
    # ==========================================================

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

    # ==========================================================
    # DISPLAY TASK
    # ==========================================================

    print_separator(
        "SELECTED TASK"
    )

    display_task(
        selected_task
    )

    # ==========================================================
    # DISCOVER FILES
    # ==========================================================

    print_separator(
        "INSPECTING PROJECT FILES"
    )

    project_files = await get_project_files(
        file_mcp
    )

    print(
        f"\nFound "
        f"{len(project_files)} project files."
    )

    for path in project_files:

        print(
            f"  • {path}"
        )

    # ==========================================================
    # RUN EXISTING TESTS
    # ==========================================================

    print_separator(
        "RUNNING EXISTING TESTS"
    )

    existing_test_files = [
        path
        for path in project_files
        if (
            path.startswith("tests/")
            and path.endswith(".py")
        )
    ]

    if not existing_test_files:

        print(
            "\n⚠ No pytest files found."
        )

        return {
            "success": False,
            "status": "no_tests",
            "error": "No pytest files found."
        }

    test_result = run_pytest(
        existing_test_files
    )

    print(
        "\nPYTEST OUTPUT:"
    )

    print(
        test_result["stdout"]
    )

    if test_result["stderr"]:

        print(
            "\nPYTEST ERRORS:"
        )

        print(
            test_result["stderr"]
        )

    # ==========================================================
    # TESTS ALREADY PASS
    # ==========================================================

    if test_result["passed"]:

        print_separator(
            "DEBUG RESULT"
        )

        print(
            "\n✓ All tests already pass."
        )

        print(
            "No debugging changes are required."
        )

        return {
            "success": True,
            "status": "already_passing",
            "task_id": task_id,
            "task": selected_task.get(
                "title",
                ""
            ),
            "tests": {
                "executed": True,
                "passed": True,
                "returncode": 0
            },
            "changes": [],
            "diagnosis": None
        }

    # ==========================================================
    # FAILURE OUTPUT
    # ==========================================================

    failure_output = (
        test_result["stdout"]
        + "\n"
        + test_result["stderr"]
    )

    # ==========================================================
    # IDENTIFY RELEVANT FILES
    # ==========================================================

    print_separator(
        "IDENTIFYING RELEVANT FILES"
    )

    file_selection_prompt = f"""
Identify the source and test files that are relevant to this failure.

PROJECT:

{json.dumps(project, indent=2)}

TASK:

{json.dumps(selected_task, indent=2)}

PROJECT FILES:

{json.dumps(project_files, indent=2)}

PYTEST FAILURE:

{failure_output}

Return ONLY:

{{
    "relevant_files": [
        "exact/path/to/file.py"
    ]
}}

Rules:

- Only select files from PROJECT FILES.
- Include the source file responsible for the failure.
- Include the failing test file.
- Include directly related dependencies when necessary.
- Do not select unrelated files.
"""

    selection_response = generate_response(
        file_selection_prompt
    )

    try:

        selection = json.loads(
            selection_response
        )

    except json.JSONDecodeError:

        return {
            "success": False,
            "status": "invalid_file_selection",
            "error": "Invalid JSON from file-selection step."
        }

    relevant_files = selection.get(
        "relevant_files",
        []
    )

    if not isinstance(
        relevant_files,
        list
    ):

        relevant_files = []

    relevant_files = [
        normalize_path(path)
        for path in relevant_files
        if (
            normalize_path(path)
            in project_files
        )
    ]

    # Always include existing test files because
    # pytest output is directly relevant to debugging.
    for test_path in existing_test_files:

        if test_path not in relevant_files:

            relevant_files.append(
                test_path
            )

    print(
        "\nRelevant files:"
    )

    for path in relevant_files:

        print(
            f"  • {path}"
        )

    # ==========================================================
    # READ RELEVANT FILES
    # ==========================================================

    print_separator(
        "READING RELEVANT FILES"
    )

    existing_files = await read_files(
        file_mcp,
        relevant_files
    )

    for file_data in existing_files:

        print(
            f"\n--- "
            f"{file_data['path']} "
            f"---"
        )

        print(
            file_data["content"]
        )

    if not existing_files:

        return {
            "success": False,
            "status": "source_read_failed",
            "error": "No relevant source files could be read."
        }

    # ==========================================================
    # DEBUG ATTEMPTS
    # ==========================================================

    max_attempts = 3

    debugging_successful = False

    final_diagnosis = None

    applied_changes = []

    for attempt in range(
        1,
        max_attempts + 1
    ):

        print_separator(
            f"DEBUGGING ATTEMPT {attempt}/{max_attempts}"
        )

        # ======================================================
        # DEBUG PROMPT
        # ======================================================

        debug_prompt = f"""
{SYSTEM_PROMPT}

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

PROJECT FILE STRUCTURE:

{json.dumps(project_files, indent=2)}

RELEVANT EXISTING FILES:

{json.dumps(existing_files, indent=2)}

CURRENT PYTEST RESULT:

{json.dumps(test_result, indent=2)}

Attempt number: {attempt}

IMPORTANT:

The current pytest output is the actual failure evidence.

Do not assume a failure exists if the output does not show one.

If modifying an existing file:
- use action "update"
- use its exact existing path
- provide complete resulting file content
- only modify a file that appears in RELEVANT EXISTING FILES

If creating a file:
- use action "create"
- the path must not already exist

Do not modify tests simply to make tests pass unless the tests are
demonstrably incorrect.

Do not introduce unrelated improvements.
"""

        response = generate_response(
            debug_prompt
        )

        print(
            "\nRAW DEBUG RESPONSE:"
        )

        print(
            response
        )

        try:

            debug_plan = json.loads(
                response
            )

        except json.JSONDecodeError:

            print(
                "\n⚠ Invalid JSON from Debug Agent."
            )

            break

        if not isinstance(
            debug_plan,
            dict
        ):

            print(
                "\n⚠ Debug response must "
                "be a JSON object."
            )

            break

        final_diagnosis = debug_plan

        # ======================================================
        # DISPLAY DIAGNOSIS
        # ======================================================

        print(
            "\nDiagnosis:"
        )

        print(
            debug_plan.get(
                "diagnosis",
                ""
            )
        )

        print(
            "\nRoot cause:"
        )

        print(
            debug_plan.get(
                "root_cause",
                ""
            )
        )

        print(
            "\nFailure type:"
        )

        print(
            debug_plan.get(
                "failure_type",
                ""
            )
        )

        print(
            "\nFix strategy:"
        )

        print(
            debug_plan.get(
                "fix_strategy",
                ""
            )
        )

        changes = debug_plan.get(
            "changes",
            []
        )

        if not isinstance(
            changes,
            list
        ):

            print(
                "\n⚠ Invalid changes field."
            )

            break

        # ======================================================
        # VALIDATE CHANGES
        # ======================================================

        print_separator(
            "VALIDATING DEBUG CHANGES"
        )

        valid_changes = []

        validation_failed = False

        inspected_paths = {
            file_data["path"]
            for file_data in existing_files
        }

        seen_paths = set()

        for change in changes:

            if not isinstance(
                change,
                dict
            ):

                validation_failed = True

                print(
                    "\n⚠ Invalid change object."
                )

                continue

            action = change.get(
                "action"
            )

            path = normalize_path(
                change.get(
                    "path",
                    ""
                )
            )

            content = change.get(
                "content"
            )

            if action not in {
                "update",
                "create"
            }:

                validation_failed = True

                print(
                    f"\n⚠ Invalid action "
                    f"'{action}' for "
                    f"{path}"
                )

                continue

            if not is_safe_relative_path(
                path
            ):

                validation_failed = True

                print(
                    f"\n⚠ Unsafe path: "
                    f"{path}"
                )

                continue

            if path in seen_paths:

                validation_failed = True

                print(
                    f"\n⚠ Duplicate change: "
                    f"{path}"
                )

                continue

            seen_paths.add(
                path
            )

            if not isinstance(
                content,
                str
            ):

                validation_failed = True

                print(
                    f"\n⚠ Invalid content "
                    f"for {path}"
                )

                continue

            # --------------------------------------------------
            # UPDATE validation
            # --------------------------------------------------

            if action == "update":

                if path not in project_files:

                    validation_failed = True

                    print(
                        f"\n⚠ Cannot update "
                        f"missing file: "
                        f"{path}"
                    )

                    continue

                if path not in inspected_paths:

                    validation_failed = True

                    print(
                        f"\n⚠ Cannot update "
                        f"uninspected file: "
                        f"{path}"
                    )

                    continue

            # --------------------------------------------------
            # CREATE validation
            # --------------------------------------------------

            if action == "create":

                if path in project_files:

                    validation_failed = True

                    print(
                        f"\n⚠ Cannot create "
                        f"existing file: "
                        f"{path}"
                    )

                    continue

            # --------------------------------------------------
            # Python validation
            # --------------------------------------------------

            valid_python, syntax_error = (
                validate_python_content(
                    path,
                    content
                )
            )

            if not valid_python:

                validation_failed = True

                print(
                    f"\n⚠ Invalid Python "
                    f"in {path}: "
                    f"{syntax_error}"
                )

                continue

            valid_changes.append(
                {
                    "action": action,
                    "path": path,
                    "content": content
                }
            )

        if validation_failed:

            print(
                "\n⚠ Debug-change validation failed."
            )

            break

        if not valid_changes:

            print(
                "\n⚠ Debug Agent proposed "
                "no changes."
            )

            break

        # ======================================================
        # APPLY CHANGES
        # ======================================================

        print_separator(
            "APPLYING DEBUG CHANGES"
        )

        changes_applied = 0

        for change in valid_changes:

            path = change["path"]

            try:

                if change["action"] == "update":

                    result = await file_mcp.update_file(
                        path,
                        change["content"]
                    )

                else:

                    result = await file_mcp.create_file(
                        path,
                        change["content"]
                    )

            except Exception as exc:

                print(
                    f"\n⚠ Failed to apply "
                    f"{path}: {exc}"
                )

                continue

            error = response_has_error(
                result
            )

            if error:

                print(
                    f"\n⚠ MCP error for "
                    f"{path}: {error}"
                )

                continue

            print(
                f"✓ {change['action'].upper()}ED | "
                f"{path}"
            )

            changes_applied += 1

            applied_changes.append(
                path
            )

        if changes_applied != len(
            valid_changes
        ):

            print(
                "\n⚠ Not all changes "
                "were applied."
            )

            break

        # ======================================================
        # VERIFY CHANGES
        # ======================================================

        print_separator(
            "VERIFYING DEBUG CHANGES"
        )

        changed_paths = [
            change["path"]
            for change in valid_changes
        ]

        verified_files = await read_files(
            file_mcp,
            changed_paths
        )

        verification_failed = False

        for change in valid_changes:

            matching = next(
                (
                    item
                    for item in verified_files
                    if item["path"]
                    == change["path"]
                ),
                None
            )

            if not matching:

                verification_failed = True

                print(
                    f"✗ Could not verify "
                    f"{change['path']}"
                )

                continue

            if (
                matching["content"]
                != change["content"]
            ):

                verification_failed = True

                print(
                    f"✗ Content mismatch: "
                    f"{change['path']}"
                )

                continue

            valid_python, syntax_error = (
                validate_python_content(
                    change["path"],
                    matching["content"]
                )
            )

            if not valid_python:

                verification_failed = True

                print(
                    f"✗ Invalid Python: "
                    f"{change['path']} | "
                    f"{syntax_error}"
                )

                continue

            print(
                f"✓ VERIFIED | "
                f"{change['path']}"
            )

        if verification_failed:

            print(
                "\n⚠ Verification failed."
            )

            break

        # ======================================================
        # RE-RUN TESTS
        # ======================================================

        print_separator(
            "RE-RUNNING TESTS"
        )

        project_files = await get_project_files(
            file_mcp
        )

        existing_test_files = [
            path
            for path in project_files
            if (
                path.startswith("tests/")
                and path.endswith(".py")
            )
        ]

        test_result = run_pytest(
            existing_test_files
        )

        print(
            "\nPYTEST OUTPUT:"
        )

        print(
            test_result["stdout"]
        )

        if test_result["stderr"]:

            print(
                "\nPYTEST ERRORS:"
            )

            print(
                test_result["stderr"]
            )

        if test_result["passed"]:

            debugging_successful = True

            print(
                "\n✓ TESTS PASSED "
                f"AFTER ATTEMPT {attempt}"
            )

            break

        print(
            f"\n⚠ Tests still failing "
            f"after attempt {attempt}."
        )

        # ======================================================
        # REFRESH SOURCE
        # ======================================================

        relevant_files = [
            path
            for path in relevant_files
            if path in project_files
        ]

        existing_files = await read_files(
            file_mcp,
            relevant_files
        )

    # ==========================================================
    # TASK STATUS
    # ==========================================================

    print_separator(
        "TASK STATUS"
    )

    target_status = (
        "completed"
        if debugging_successful
        else "in_progress"
    )

    print(
        f"\nTarget status: "
        f"{target_status.upper()}"
    )

    status_updated = False

    try:

        status_result = await project_mcp.call_tool(
            "update_task",
            {
                "task_id": task_id,
                "status": target_status
            }
        )

        status_error = response_has_error(
            status_result
        )

        if status_error:

            print(
                f"\n⚠ Could not update "
                f"task status: "
                f"{status_error}"
            )

        else:

            updated_task = first_dict(
                status_result
            )

            if updated_task:

                status_updated = True

                print(
                    f"✓ TASK STATUS UPDATED | "
                    f"{updated_task.get('task_id')} | "
                    f"{updated_task.get('status')}"
                )

            else:

                print(
                    "\n✓ Task status update requested."
                )

                status_updated = True

    except Exception as exc:

        print(
            f"\n⚠ Exception while updating "
            f"task status: {exc}"
        )

    # ==========================================================
    # STRUCTURED RESULT
    # ==========================================================

    structured_result = {
        "success": debugging_successful,
        "status": (
            "debugged"
            if debugging_successful
            else "failed"
        ),
        "task": selected_task.get(
            "title",
            ""
        ),
        "task_id": task_id,
        "debugging": {
            "successful": debugging_successful,
            "max_attempts": max_attempts,
            "final_test_result": {
                "returncode": test_result["returncode"],
                "passed": test_result["passed"]
            }
        },
        "diagnosis": final_diagnosis,
        "changes": applied_changes,
        "task_status": target_status,
        "task_status_updated": status_updated
    }

    print_separator(
        "STRUCTURED DEBUG RESULT"
    )

    print_json(
        structured_result
    )

    return structured_result


# ==============================================================
# CALLABLE ORCHESTRATOR ENTRY POINT
# ==============================================================


async def run_debugger(
    project_id,
    task_id
):

    """
    Callable entry point used by the Orchestrator.

    This function owns its MCP connections and returns a structured
    result instead of requiring interactive input.
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

    project_mcp = MCPProjectClient()
    file_mcp = MCPFileClient()

    try:

        await project_mcp.connect()
        await file_mcp.connect()

        print(
            "\nProject MCP connection successful!"
        )

        print(
            "File MCP connection successful!"
        )

        result = await debug_task(
            project_mcp,
            file_mcp,
            project_id,
            task_id
        )

        return result

    except Exception as exc:

        print(
            f"\n✗ Debugger Agent exception: "
            f"{exc}"
        )

        return {
            "success": False,
            "status": "failed",
            "error": str(exc),
            "task_id": task_id
        }

    finally:

        try:

            await file_mcp.disconnect()

        except Exception as exc:

            print(
                f"\n⚠ File MCP disconnect error: "
                f"{exc}"
            )

        try:

            await project_mcp.disconnect()

        except Exception as exc:

            print(
                f"\n⚠ Project MCP disconnect error: "
                f"{exc}"
            )


# ==============================================================
# INTERACTIVE CLI
# ==============================================================


async def main():

    print_separator(
        "DEBUG AGENT"
    )

    project_mcp = MCPProjectClient()
    file_mcp = MCPFileClient()

    await project_mcp.connect()
    await file_mcp.connect()

    print(
        "\nProject MCP connection successful!"
    )

    print(
        "File MCP connection successful!"
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

        project_result = await project_mcp.call_tool(
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

        tasks_result = await project_mcp.call_tool(
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
        # DISPLAY PROJECT
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
        # DISPLAY TASKS
        # ======================================================

        print_separator(
            "AVAILABLE TASKS"
        )

        for i, task in enumerate(
            tasks,
            1
        ):

            print(
                f"\n{i}. "
                f"{task.get('title', '')}"
            )

            print(
                f"   Priority: "
                f"{task.get('priority', '')}"
            )

            print(
                f"   Status: "
                f"{task.get('status', '')}"
            )

            print(
                f"   ID: "
                f"{task.get('task_id', '')}"
            )

        # ======================================================
        # SELECT TASK
        # ======================================================

        task_id = input(
            "\nEnter Task ID to debug:\n> "
        ).strip()

        if not task_id:

            print(
                "\nTask ID cannot be empty."
            )

            return

        selected_task = find_task(
            tasks,
            task_id
        )

        if not selected_task:

            print(
                f"\nTask not found: "
                f"{task_id}"
            )

            return

        # ======================================================
        # RUN DEBUGGER
        # ======================================================

        result = await debug_task(
            project_mcp,
            file_mcp,
            project_id,
            task_id
        )

        # ======================================================
        # FINAL RESULT
        # ======================================================

        print_separator(
            "DEBUG AGENT RESULT"
        )

        print_json(
            result
        )

        if result.get(
            "success",
            False
        ):

            print(
                "\n✓ Debug Agent successfully "
                "resolved or verified the task."
            )

        else:

            print(
                "\n⚠ Debug Agent could not "
                "fully resolve the failure."
            )

    finally:

        try:

            await file_mcp.disconnect()

        except Exception:
            pass

        try:

            await project_mcp.disconnect()

        except Exception:
            pass

        print(
            "\n" + "=" * 60
        )

        print(
            "DEBUG AGENT COMPLETED"
        )

        print(
            "=" * 60
        )


# ==============================================================
# ENTRY POINT
# ==============================================================


if __name__ == "__main__":

    asyncio.run(main())
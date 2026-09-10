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
You are the Code Review Agent in an AI Student Project Manager.

Your job is to review ONE completed software development task after its
implementation and automated tests have passed.

You are given:
- project information
- selected task
- other project tasks
- complete project file structure
- relevant source files
- relevant test files
- test execution results

You must review the ACTUAL SOURCE CODE.

Your job is NOT to modify files.

Return ONLY valid JSON:

{
    "task": "...",
    "overall_status": "approved|changes_required",
    "score": 0,
    "summary": "...",
    "findings": [
        {
            "severity": "critical|high|medium|low|info",
            "category": "correctness|architecture|security|performance|maintainability|testing|api_contract|error_handling|dependency|other",
            "file": "...",
            "issue": "...",
            "recommendation": "..."
        }
    ],
    "strengths": [
        "..."
    ],
    "test_assessment": "...",
    "approval_reason": "...",
    "recommended_next_action": "..."
}

Rules:

1. Focus only on the selected task.

2. Review the actual implementation, not the task description alone.

3. Do not invent functionality that does not exist.

4. Do not report an issue unless the supplied source code supports it.

5. Distinguish genuine problems from harmless warnings.

6. Do not require unrelated refactoring.

7. Check whether the implementation satisfies the selected task.

8. Check consistency with the existing project architecture.

9. Check API contracts against the actual schemas/models/services.

10. Check error handling.

11. Check security issues such as hardcoded secrets, unsafe input handling,
    or inappropriate exposure of sensitive data.

12. Check whether tests meaningfully cover the implementation.

13. Existing passing tests do not automatically mean the implementation
    is correct.

14. Do not recommend changes merely because a different implementation
    style is possible.

15. Do not modify files.

16. Every finding must identify the relevant file when possible.

17. Score from 0 to 10:
    9-10 = excellent
    7-8 = good with minor issues
    5-6 = significant improvements required
    0-4 = unacceptable

18. overall_status should be:
    "approved" when there are no critical/high issues.
    "changes_required" when there is at least one critical/high issue.

19. Return ONLY valid JSON.
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

            parsed.extend(
                value
            )

        else:

            parsed.append(
                value
            )

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


def find_task(
    tasks,
    task_id
):

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

                    directories.append(
                        item_path
                    )

            elif item_type == "file":

                discovered_files.add(
                    item_path
                )

    return sorted(
        discovered_files
    )


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
            "executed": False,
            "returncode": 1,
            "stdout": "",
            "stderr": "No pytest files found.",
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
            "executed": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "passed": result.returncode == 0
        }

    except Exception as exc:

        return {
            "executed": False,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "passed": False
        }


# ==============================================================
# REVIEW VALIDATION
# ==============================================================


def validate_review_structure(review):

    errors = []

    if not isinstance(
        review,
        dict
    ):

        return [
            "Review response must be a JSON object."
        ]

    overall_status = review.get(
        "overall_status"
    )

    if overall_status not in {
        "approved",
        "changes_required"
    }:

        errors.append(
            "Invalid overall_status."
        )

    score = review.get(
        "score"
    )

    if not isinstance(
        score,
        (int, float)
    ):

        errors.append(
            "Review score must be numeric."
        )

    else:

        if score < 0 or score > 10:

            errors.append(
                "Review score must be between 0 and 10."
            )

    findings = review.get(
        "findings",
        []
    )

    if not isinstance(
        findings,
        list
    ):

        errors.append(
            "findings must be a list."
        )

    else:

        valid_severities = {
            "critical",
            "high",
            "medium",
            "low",
            "info"
        }

        valid_categories = {
            "correctness",
            "architecture",
            "security",
            "performance",
            "maintainability",
            "testing",
            "api_contract",
            "error_handling",
            "dependency",
            "other"
        }

        for index, finding in enumerate(
            findings,
            1
        ):

            if not isinstance(
                finding,
                dict
            ):

                errors.append(
                    f"Finding {index} must be an object."
                )

                continue

            severity = finding.get(
                "severity"
            )

            if severity not in valid_severities:

                errors.append(
                    f"Finding {index} has invalid severity."
                )

            category = finding.get(
                "category"
            )

            if category not in valid_categories:

                errors.append(
                    f"Finding {index} has invalid category."
                )

    strengths = review.get(
        "strengths",
        []
    )

    if not isinstance(
        strengths,
        list
    ):

        errors.append(
            "strengths must be a list."
        )

    critical_or_high = []

    if isinstance(
        findings,
        list
    ):

        for finding in findings:

            if not isinstance(
                finding,
                dict
            ):

                continue

            if finding.get("severity") in {
                "critical",
                "high"
            }:

                critical_or_high.append(
                    finding
                )

    if overall_status in {
        "approved",
        "changes_required"
    }:

        expected_status = (
            "changes_required"
            if critical_or_high
            else "approved"
        )

        if overall_status != expected_status:

            errors.append(
                "overall_status is inconsistent "
                "with critical/high findings."
            )

    return errors


# ==============================================================
# CORE PROGRAMMATIC REVIEWER
# ==============================================================


async def run_reviewer(
    project_id,
    task_id,
    project=None,
    tasks=None,
    selected_task=None,
    show_output=True
):

    """
    Programmatic entry point for the Code Review Agent.

    This function is designed to be called by the Orchestrator.

    Parameters:
        project_id:
            Project identifier.

        task_id:
            Task identifier.

        project:
            Optional already-fetched project object.

        tasks:
            Optional already-fetched project task list.

        selected_task:
            Optional already-selected task object.

        show_output:
            Whether to print reviewer progress to stdout.

    Returns:
        Structured dictionary containing:
            success
            status
            task
            task_id
            review
            tests
            relevant_files
            error
    """

    project_mcp = None
    file_mcp = None

    try:

        if show_output:

            print_separator(
                "CODE REVIEW AGENT"
            )

        # ======================================================
        # VALIDATE INPUT
        # ======================================================

        if not project_id:

            return {
                "success": False,
                "status": "failed",
                "error": "Project ID cannot be empty."
            }

        if not task_id:

            return {
                "success": False,
                "status": "failed",
                "error": "Task ID cannot be empty."
            }

        # ======================================================
        # MCP CONNECTION
        # ======================================================

        project_mcp = MCPProjectClient()
        file_mcp = MCPFileClient()

        await project_mcp.connect()
        await file_mcp.connect()

        if show_output:

            print(
                "\nProject MCP connection successful!"
            )

            print(
                "File MCP connection successful!"
            )

        # ======================================================
        # GET PROJECT IF NOT PROVIDED
        # ======================================================

        if project is None:

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
                    "status": "failed",
                    "error": "Project not found."
                }

            if project.get("error"):

                return {
                    "success": False,
                    "status": "failed",
                    "error": project["error"]
                }

        # ======================================================
        # GET TASKS IF NOT PROVIDED
        # ======================================================

        if tasks is None:

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
                "status": "failed",
                "error": "No tasks found."
            }

        # ======================================================
        # FIND SELECTED TASK IF NOT PROVIDED
        # ======================================================

        if selected_task is None:

            selected_task = find_task(
                tasks,
                task_id
            )

        if not selected_task:

            return {
                "success": False,
                "status": "failed",
                "error": (
                    f"Task not found: {task_id}"
                )
            }

        # ======================================================
        # DISPLAY TASK
        # ======================================================

        if show_output:

            print_separator(
                "SELECTED TASK"
            )

            display_task(
                selected_task
            )

        # ======================================================
        # DISCOVER PROJECT FILES
        # ======================================================

        if show_output:

            print_separator(
                "INSPECTING PROJECT FILES"
            )

        project_files = await get_project_files(
            file_mcp
        )

        if show_output:

            print(
                f"\nFound "
                f"{len(project_files)} project files."
            )

        # ======================================================
        # IDENTIFY RELEVANT FILES
        # ======================================================

        if show_output:

            print_separator(
                "IDENTIFYING RELEVANT FILES"
            )

        file_selection_prompt = f"""
Identify the existing source and test files that should be reviewed
for this ONE completed task.

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

PROJECT FILES:

{json.dumps(project_files, indent=2)}

Return ONLY:

{{
    "relevant_files": [
        "exact/path/to/file.py"
    ]
}}

Rules:

- Only use paths from PROJECT FILES.
- Include implementation files.
- Include directly related models, schemas, services, or frontend
  files when relevant.
- Include tests relevant to the selected task.
- Keep the list focused.
- Do not invent paths.
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
                "status": "invalid_response",
                "error": (
                    "Invalid JSON from "
                    "file-selection step."
                )
            }

        if not isinstance(
            selection,
            dict
        ):

            return {
                "success": False,
                "status": "invalid_response",
                "error": (
                    "File-selection response "
                    "must be a JSON object."
                )
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

        if show_output:

            print(
                "\nRelevant files:"
            )

            if relevant_files:

                for path in relevant_files:

                    print(
                        f"  • {path}"
                    )

            else:

                print(
                    "  None"
                )

        # ======================================================
        # READ RELEVANT FILES
        # ======================================================

        if show_output:

            print_separator(
                "READING RELEVANT FILES"
            )

        existing_files = await read_files(
            file_mcp,
            relevant_files
        )

        if not existing_files:

            return {
                "success": False,
                "status": "failed",
                "error": (
                    "No relevant files could be read."
                ),
                "relevant_files": relevant_files
            }

        if show_output:

            for file_data in existing_files:

                print(
                    f"\n--- "
                    f"{file_data['path']} "
                    f"---"
                )

                print(
                    file_data["content"]
                )

        # ======================================================
        # FIND TEST FILES
        # ======================================================

        test_files = [
            path
            for path in project_files
            if (
                path.startswith("tests/")
                and path.endswith(".py")
            )
        ]

        # ======================================================
        # READ RELEVANT TEST FILES
        # ======================================================

        relevant_test_files = [
            path
            for path in relevant_files
            if (
                path.startswith("tests/")
                and path.endswith(".py")
            )
        ]

        # If the AI did not select tests explicitly,
        # include the existing test files so that the
        # review has actual test coverage information.
        if not relevant_test_files:

            relevant_test_files = test_files

        test_file_contents = await read_files(
            file_mcp,
            relevant_test_files
        )

        # ======================================================
        # RUN TESTS
        # ======================================================

        if show_output:

            print_separator(
                "VERIFYING TEST RESULTS"
            )

        test_result = run_pytest(
            test_files
        )

        if show_output:

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

        # ======================================================
        # BUILD COMPLETE REVIEW CONTEXT
        # ======================================================

        review_files = existing_files[:]

        existing_paths = {
            item["path"]
            for item in review_files
        }

        for test_file in test_file_contents:

            if test_file["path"] not in existing_paths:

                review_files.append(
                    test_file
                )

        # ======================================================
        # BUILD REVIEW PROMPT
        # ======================================================

        review_prompt = f"""
{SYSTEM_PROMPT}

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

OTHER PROJECT TASKS:

{json.dumps(
    [
        task
        for task in tasks
        if task.get("task_id") != task_id
    ],
    indent=2
)}

PROJECT FILE STRUCTURE:

{json.dumps(project_files, indent=2)}

RELEVANT SOURCE AND TEST FILES:

{json.dumps(review_files, indent=2)}

TEST FILES EXECUTED:

{json.dumps(test_files, indent=2)}

TEST EXECUTION RESULT:

{json.dumps(test_result, indent=2)}

IMPORTANT:

The supplied source files are the source of truth.

Only report findings that are supported by the supplied files.

Do not assume functionality that is not shown.

Do not recommend changes to files that were not supplied unless
the recommendation is explicitly identified as a future action
rather than an immediate code change.

Remember:
- You are reviewing.
- You are not modifying files.
- Return ONLY valid JSON.
"""

        # ======================================================
        # CALL REVIEW AGENT
        # ======================================================

        if show_output:

            print_separator(
                "CODE REVIEW AGENT ANALYZING..."
            )

        response = generate_response(
            review_prompt
        )

        if show_output:

            print(
                "\nRAW AI RESPONSE:"
            )

            print(
                response
            )

        # ======================================================
        # PARSE REVIEW
        # ======================================================

        try:

            review = json.loads(
                response
            )

        except json.JSONDecodeError:

            return {
                "success": False,
                "status": "invalid_response",
                "error": (
                    "AI returned invalid JSON."
                ),
                "raw_response": response,
                "tests": {
                    "executed": test_result["executed"],
                    "passed": test_result["passed"],
                    "returncode": test_result["returncode"]
                }
            }

        # ======================================================
        # VALIDATE REVIEW
        # ======================================================

        validation_errors = (
            validate_review_structure(
                review
            )
        )

        if validation_errors:

            if show_output:

                print(
                    "\n⚠ Review validation failed:"
                )

                for error in validation_errors:

                    print(
                        f"  • {error}"
                    )

            return {
                "success": False,
                "status": "invalid_review",
                "error": (
                    "Review response failed validation."
                ),
                "validation_errors": validation_errors,
                "review": review,
                "tests": {
                    "executed": test_result["executed"],
                    "passed": test_result["passed"],
                    "returncode": test_result["returncode"]
                }
            }

        # ======================================================
        # CONSISTENCY CHECK
        # ======================================================

        findings = review.get(
            "findings",
            []
        )

        critical_or_high = [
            finding
            for finding in findings
            if (
                isinstance(finding, dict)
                and finding.get("severity")
                in {
                    "critical",
                    "high"
                }
            )
        ]

        expected_status = (
            "changes_required"
            if critical_or_high
            else "approved"
        )

        if review.get(
            "overall_status"
        ) != expected_status:

            review["overall_status"] = (
                expected_status
            )

            if show_output:

                print(
                    "\n⚠ Review status was "
                    "inconsistent with findings."
                )

                print(
                    f"✓ Corrected status to: "
                    f"{expected_status}"
                )

        overall_status = review.get(
            "overall_status"
        )

        # ======================================================
        # DISPLAY REVIEW
        # ======================================================

        if show_output:

            print_separator(
                "CODE REVIEW RESULT"
            )

            print(
                f"\nTask: "
                f"{review.get('task', selected_task.get('title', ''))}"
            )

            print(
                f"\nOverall Status: "
                f"{overall_status.upper()}"
            )

            print(
                f"\nScore: "
                f"{review.get('score')}/10"
            )

            print(
                "\nSummary:"
            )

            print(
                review.get(
                    "summary",
                    ""
                )
            )

            print(
                "\nStrengths:"
            )

            strengths = review.get(
                "strengths",
                []
            )

            if strengths:

                for strength in strengths:

                    print(
                        f"  ✓ {strength}"
                    )

            else:

                print(
                    "  None identified."
                )

            print(
                "\nFindings:"
            )

            if findings:

                for index, finding in enumerate(
                    findings,
                    1
                ):

                    if not isinstance(
                        finding,
                        dict
                    ):

                        continue

                    print(
                        f"\n{index}. "
                        f"[{finding.get('severity', '').upper()}] "
                        f"{finding.get('category', '')}"
                    )

                    print(
                        f"   File: "
                        f"{finding.get('file', '')}"
                    )

                    print(
                        f"   Issue: "
                        f"{finding.get('issue', '')}"
                    )

                    print(
                        f"   Recommendation: "
                        f"{finding.get('recommendation', '')}"
                    )

            else:

                print(
                    "  No findings."
                )

            print(
                "\nTest Assessment:"
            )

            print(
                review.get(
                    "test_assessment",
                    ""
                )
            )

            print(
                "\nApproval Reason:"
            )

            print(
                review.get(
                    "approval_reason",
                    ""
                )
            )

            print(
                "\nRecommended Next Action:"
            )

            print(
                review.get(
                    "recommended_next_action",
                    ""
                )
            )

        # ======================================================
        # STRUCTURED RESULT
        # ======================================================

        structured_result = {
            "success": (
                overall_status == "approved"
            ),
            "status": overall_status,
            "task": selected_task.get(
                "title",
                ""
            ),
            "task_id": task_id,
            "review": review,
            "tests": {
                "executed": test_result["executed"],
                "passed": test_result["passed"],
                "returncode": test_result["returncode"]
            },
            "relevant_files": relevant_files,
            "reviewed_files": [
                item["path"]
                for item in review_files
            ]
        }

        if show_output:

            print_separator(
                "STRUCTURED REVIEW RESULT"
            )

            print_json(
                structured_result
            )

            print_separator()

            if overall_status == "approved":

                print(
                    "✓ Code Review Agent approved "
                    "the implementation."
                )

            else:

                print(
                    "⚠ Code Review Agent found "
                    "issues requiring attention."
                )

        return structured_result

    except Exception as exc:

        if show_output:

            print(
                f"\n✗ Code Review Agent exception: "
                f"{exc}"
            )

        return {
            "success": False,
            "status": "failed",
            "task": (
                selected_task.get(
                    "title",
                    ""
                )
                if isinstance(
                    selected_task,
                    dict
                )
                else ""
            ),
            "task_id": task_id,
            "error": str(exc)
        }

    finally:

        if file_mcp is not None:

            try:

                await file_mcp.disconnect()

            except Exception:

                pass

        if project_mcp is not None:

            try:

                await project_mcp.disconnect()

            except Exception:

                pass


# ==============================================================
# CLI MAIN
# ==============================================================


async def main():

    print_separator(
        "CODE REVIEW AGENT"
    )

    project_id = input(
        "\nEnter Project ID:\n> "
    ).strip()

    if not project_id:

        print(
            "\nProject ID cannot be empty."
        )

        return

    task_id = input(
        "\nEnter Task ID to review:\n> "
    ).strip()

    if not task_id:

        print(
            "\nTask ID cannot be empty."
        )

        return

    result = await run_reviewer(
        project_id=project_id,
        task_id=task_id,
        show_output=True
    )

    print_separator(
        "CODE REVIEW AGENT COMPLETED"
    )

    if result.get(
        "success",
        False
    ):

        print(
            "\n✓ Code review completed successfully."
        )

    else:

        print(
            "\n⚠ Code review completed with status: "
            f"{result.get('status', 'failed')}"
        )


# ==============================================================
# ENTRY POINT
# ==============================================================


if __name__ == "__main__":

    asyncio.run(
        main()
    )
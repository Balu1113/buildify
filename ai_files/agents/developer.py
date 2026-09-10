import ast
import asyncio
import json
import posixpath

from llm.client import generate_response
from mcp_client.client import MCPProjectClient
from mcp_client.file_client import MCPFileClient


SYSTEM_PROMPT = """
You are the Developer Agent in an AI Student Project Manager.

Your job is to take ONE software development task from an existing project,
inspect the existing project files, and implement that task.

You are given:
- the project information
- the selected task
- the other project tasks
- the existing project files relevant to the task

First understand the existing project structure and code.

Return ONLY valid JSON in this format:

{
    "task": "...",
    "objective": "...",
    "requirements": [
        "..."
    ],
    "files_to_create": [
        "..."
    ],
    "files_to_modify": [
        "..."
    ],
    "dependencies": [
        "..."
    ],
    "implementation_steps": [
        "..."
    ],
    "testing_strategy": [
        "..."
    ],
    "file_changes": [
        {
            "action": "create|update",
            "path": "...",
            "content": "..."
        }
    ]
}

Rules:

1. Focus only on the selected task.

2. Inspect the existing files before proposing changes.

3. Reuse the existing project architecture whenever possible.

4. Do not unnecessarily rewrite existing files.

5. Do not duplicate functionality already present in the project.

6. Only create files that are genuinely required.

7. Only modify files that are genuinely required.

8. Use exact relative file paths from the project.

9. Do not invent files unrelated to the selected task.

10. file_changes must contain only changes required to implement
    the selected task.

11. For an existing file, use:
    "action": "update"

12. For a new file, use:
    "action": "create"

13. Never use "update" for a file that does not exist.

14. Never use "create" for a file that already exists.

15. Preserve existing functionality when modifying files.

16. Do not modify unrelated code.

17. Do not write code outside the file_changes section.

18. The content field must contain the COMPLETE resulting file content,
    not a partial snippet.

19. Do not overwrite an existing file unless the change is actually
    necessary for the selected task.

20. Do not remove existing functionality unrelated to the selected task.

21. Do not invent requirements unrelated to the selected task.

22. Dependencies must be appropriate for the existing project.

23. Do not use deprecated libraries or APIs when the existing project
    already uses a newer supported approach.

24. Do not expose API keys or secrets in source code.

25. Never put actual secret values inside generated files.

26. If an environment variable is required, reference the variable name
    and explain its purpose through the implementation.

27. If no file changes are required, return an empty file_changes array.

28. Return ONLY valid JSON.
"""


# ==============================================================
# GENERAL HELPERS
# ==============================================================


def parse_llm_json(response, purpose):
    """Parse an LLM JSON response and recover once from malformed JSON."""
    if not isinstance(response, str):
        raise json.JSONDecodeError("LLM response is not text", str(response), 0)

    text = response.strip()

    # Remove markdown code fences if the model wrapped the JSON.
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        print(
            f"\n⚠ LLM returned malformed JSON while {purpose}."
        )
        print("Attempting one JSON-repair retry...")

        repair_prompt = f"""
The previous LLM response was intended to be valid JSON for {purpose},
but it was malformed and could not be parsed.

PREVIOUS RESPONSE:
{text}

Return ONLY a corrected, valid JSON object.
Do not use markdown code fences.
Do not add explanations.

IMPORTANT: The JSON contains source-code strings. Escape every double
quote that appears inside a source-code string (for example, Python
code such as f\"/tasks/{{task_id}}\" must be represented with escaped
double quotes inside the JSON string). Preserve the intended code and
all fields from the previous response.
"""

        repaired_response = generate_response(repair_prompt)
        repaired_text = repaired_response.strip()

        if repaired_text.startswith("```") and repaired_text.endswith("```"):
            lines = repaired_text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            repaired_text = "\n".join(lines).strip()

        try:
            repaired = json.loads(repaired_text)
        except json.JSONDecodeError as second_error:
            raise second_error from first_error

        print("✓ JSON repair successful.")
        return repaired


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
# MCP RESPONSE HELPERS
# ==============================================================


def parse_mcp_item(item):

    """
    Convert one MCP response item into a Python object.

    MCP responses may sometimes arrive as:
    - dict
    - JSON string
    - TextContent-like object containing .text
    """

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

    """
    Normalize MCP results into a list of Python objects.
    """

    if result is None:

        return []

    if not isinstance(result, list):

        result = [result]

    parsed = []

    for item in result:

        value = parse_mcp_item(item)

        # Some MCP tools may return a JSON list encoded
        # inside a single TextContent response.
        if isinstance(value, list):

            parsed.extend(value)

        else:

            parsed.append(value)

    return parsed


# ==============================================================
# FILE PATH HELPERS
# ==============================================================


def normalize_path(path):

    if not isinstance(path, str):

        return ""

    path = path.replace("\\", "/")

    path = path.strip()

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
# RECURSIVE FILE DISCOVERY
# ==============================================================


async def get_project_files(file_mcp):

    """
    Recursively discover files through the File MCP.

    The File MCP list_files operation lists one directory at a time,
    so we explicitly traverse directories.
    """

    discovered_files = set()
    visited_directories = set()

    directories = ["."]

    while directories:

        current_directory = directories.pop()

        current_directory = normalize_path(
            current_directory
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

        items = parse_mcp_result(result)

        for item in items:

            if not isinstance(item, dict):

                continue

            item_path = normalize_path(
                item.get("path", "")
            )

            item_type = item.get(
                "type"
            )

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


# ==============================================================
# READ FILES
# ==============================================================


async def read_file_safe(
    file_mcp,
    file_path
):

    try:

        result = await file_mcp.read_file(
            file_path
        )

    except Exception as exc:

        print(
            f"\n⚠ Failed to read "
            f"{file_path}: {exc}"
        )

        return None

    items = parse_mcp_result(result)

    for item in items:

        if isinstance(item, dict):

            if item.get("error"):

                print(
                    f"\n⚠ MCP error reading "
                    f"{file_path}: "
                    f"{item['error']}"
                )

                return None

            if "content" in item:

                return item.get(
                    "content",
                    ""
                )

    return None


async def read_relevant_files(
    file_mcp,
    file_paths
):

    contents = []

    for file_path in file_paths:

        content = await read_file_safe(
            file_mcp,
            file_path
        )

        if content is None:

            continue

        contents.append(
            {
                "path": file_path,
                "content": content
            }
        )

    return contents


# ==============================================================
# FILE RESPONSE VALIDATION
# ==============================================================


def response_has_error(result):

    items = parse_mcp_result(result)

    for item in items:

        if isinstance(item, dict):

            if item.get("error"):

                return item.get(
                    "error"
                )

    return None


def first_dict(result):

    items = parse_mcp_result(result)

    for item in items:

        if isinstance(item, dict):

            return item

    return None


# ==============================================================
# PYTHON VALIDATION
# ==============================================================


def validate_python_content(
    file_path,
    content
):

    """
    Validate Python source without executing it.

    This catches syntax errors before we mark the task complete.
    """

    if not file_path.endswith(".py"):

        return True, None

    try:

        ast.parse(
            content,
            filename=file_path
        )

        return True, None

    except SyntaxError as exc:

        message = (
            f"{exc.msg} "
            f"(line {exc.lineno}, "
            f"column {exc.offset})"
        )

        return False, message

    except Exception as exc:

        return False, str(exc)


# ==============================================================
# MAIN
# ==============================================================


def parse_llm_json(response, purpose):
    """Parse LLM JSON and retry once when the model returns malformed JSON."""
    if not isinstance(response, str):
        raise json.JSONDecodeError(
            "LLM response is not text",
            str(response),
            0
        )

    text = response.strip()

    # Remove markdown fences if the model wrapped the JSON.
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)

    except json.JSONDecodeError as first_error:

        print(
            f"\n⚠ LLM returned malformed JSON while {purpose}."
        )

        print(
            "Attempting one JSON-repair retry..."
        )

        repair_prompt = f"""
The previous LLM response was intended to be valid JSON for {purpose},
but it was malformed and could not be parsed.

PREVIOUS RESPONSE:
{text}

Return ONLY a corrected, valid JSON object.
Do not use markdown code fences.
Do not add explanations.

IMPORTANT:
The JSON contains source-code strings. Escape every double quote that
appears inside a source-code string. For example, Python code such as:

response = client.get(f"/tasks/{{task_id}}")

must be represented correctly as a JSON string with the inner quotes
escaped. Preserve the intended source code and all fields from the
previous response.
"""

        repaired_response = generate_response(
            repair_prompt
        )

        repaired_text = repaired_response.strip()

        if (
            repaired_text.startswith("```")
            and repaired_text.endswith("```")
        ):
            lines = repaired_text.splitlines()

            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            repaired_text = "\n".join(lines).strip()

        try:
            repaired = json.loads(
                repaired_text
            )

        except json.JSONDecodeError as second_error:
            raise second_error from first_error

        print(
            "✓ JSON repair successful."
        )

        return repaired


async def run_developer(project_id=None, task_id=None):

    print_separator(
        "DEVELOPER AGENT"
    )

    mcp = MCPProjectClient()

    file_mcp = MCPFileClient()

    await mcp.connect()

    await file_mcp.connect()

    print(
        "\nProject MCP connection successful!"
    )

    print(
        "File MCP connection successful!"
    )

    try:

        # ======================================================
        # 1. PROJECT ID
        # ======================================================

        if project_id is None:
            project_id = input(
                "\nEnter Project ID:\n> "
            ).strip()

        if not project_id:

            print(
                "\nProject ID cannot be empty."
            )

            return {
                "success": False,
                "status": "failed",
                "stage": "developer",
                "error": "Project ID cannot be empty."
            }

        # ======================================================
        # 2. GET PROJECT
        # ======================================================

        project_result = await mcp.call_tool(
            "get_project",
            {
                "project_id": project_id
            }
        )

        project_items = parse_mcp_result(
            project_result
        )

        if not project_items:

            print(
                "\nProject not found."
            )

            return

        project = first_dict(
            project_items
        )

        if not project:

            print(
                "\nUnexpected project response:"
            )

            print_json(
                project_items
            )

            return

        if project.get("error"):

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

            print_json(
                project
            )

            return

        # ======================================================
        # 3. GET TASKS
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
            if isinstance(item, dict)
        ]

        tasks = [
            task
            for task in tasks
            if not task.get("error")
        ]

        if not tasks:

            print(
                "\nNo tasks found for this project."
            )

            return

        # ======================================================
        # 4. DISPLAY PROJECT
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
        # 5. DISPLAY TASKS
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
        # 6. SELECT TASK
        # ======================================================

        if task_id is None:
            task_id = input(
                "\nEnter Task ID to develop:\n> "
            ).strip()

        if not task_id:

            print(
                "\nTask ID cannot be empty."
            )

            return {
                "success": False,
                "status": "failed",
                "stage": "developer",
                "error": "Task ID cannot be empty."
            }

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
        # 7. DISPLAY SELECTED TASK
        # ======================================================

        print_separator(
            "SELECTED TASK"
        )

        display_task(
            selected_task
        )

        # ======================================================
        # 8. DISCOVER ALL PROJECT FILES
        # ======================================================

        print_separator(
            "INSPECTING PROJECT FILES"
        )

        project_files = await get_project_files(
            file_mcp
        )

        print(
            f"\nFound "
            f"{len(project_files)} project files:"
        )

        if project_files:

            for file_path in project_files:

                print(
                    f"  • {file_path}"
                )

        else:

            print(
                "  No files found."
            )

        # ======================================================
        # 9. IDENTIFY RELEVANT FILES
        # ======================================================

        print_separator(
            "IDENTIFYING RELEVANT FILES"
        )

        file_selection_prompt = f"""
You are helping a Developer Agent identify which existing files
are relevant to ONE development task.

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

PROJECT FILES:

{json.dumps(project_files, indent=2)}

Return ONLY valid JSON:

{{
    "relevant_files": [
        "exact/path/to/file.py"
    ]
}}

Rules:

- Only select files from PROJECT FILES.
- Do not invent file paths.
- Select only files relevant to the selected task.
- Keep the list as small as reasonably possible.
"""

        file_selection_response = generate_response(
            file_selection_prompt
        )

        try:

            file_selection = parse_llm_json(
                file_selection_response,
                "selecting relevant project files"
            )

        except (json.JSONDecodeError, TypeError) as exc:

            print(
                "\n⚠ AI returned invalid JSON "
                "while selecting files."
            )

            print(
                f"Reason: {exc}"
            )

            return {
                "success": False,
                "status": "failed",
                "stage": "developer",
                "error": str(exc)
            }

        relevant_files = file_selection.get(
            "relevant_files",
            []
        )

        if not isinstance(
            relevant_files,
            list
        ):

            relevant_files = []

        # Only allow files actually discovered.
        relevant_files = [
            normalize_path(file_path)
            for file_path in relevant_files
            if normalize_path(file_path)
            in project_files
        ]

        print(
            "\nRelevant files:"
        )

        if relevant_files:

            for file_path in relevant_files:

                print(
                    f"  • {file_path}"
                )

        else:

            print(
                "  None"
            )

        # ======================================================
        # 10. READ RELEVANT FILES
        # ======================================================

        print_separator(
            "READING RELEVANT FILES"
        )

        existing_files = await read_relevant_files(
            file_mcp,
            relevant_files
        )

        if existing_files:

            for file_data in existing_files:

                print(
                    f"\n--- "
                    f"{file_data['path']} "
                    f"---"
                )

                print(
                    file_data["content"]
                )

        else:

            print(
                "\nNo existing relevant files "
                "need to be inspected."
            )

        # ======================================================
        # 11. BUILD DEVELOPER PROMPT
        # ======================================================

        prompt = f"""
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

RELEVANT EXISTING FILES:

{json.dumps(existing_files, indent=2)}
"""

        # ======================================================
        # 12. CALL GEMINI
        # ======================================================

        print_separator(
            "DEVELOPER AGENT ANALYZING..."
        )

        response = generate_response(
            prompt
        )

        print(
            "\nRAW AI RESPONSE:"
        )

        print(response)

        # ======================================================
        # 13. PARSE PLAN
        # ======================================================

        try:

            implementation_plan = parse_llm_json(
                response,
                "creating the implementation plan"
            )

        except (json.JSONDecodeError, TypeError) as exc:

            print(
                "\n⚠ AI returned invalid JSON after repair retry."
            )

            print(
                f"Reason: {exc}"
            )

            return {
                "success": False,
                "status": "failed",
                "stage": "developer",
                "error": str(exc)
            }

        if not isinstance(
            implementation_plan,
            dict
        ):

            print(
                "\n⚠ AI response must be a JSON object."
            )

            return

        # ======================================================
        # 14. NORMALIZE FILE CHANGES
        # ======================================================

        file_changes = implementation_plan.get(
            "file_changes",
            []
        )

        if not isinstance(
            file_changes,
            list
        ):

            print(
                "\n⚠ Invalid file_changes field."
            )

            return

        # ======================================================
        # 15. DISPLAY TECHNICAL PLAN
        # ======================================================

        print_separator(
            "TECHNICAL IMPLEMENTATION PLAN"
        )

        print(
            "\nTask:"
        )

        print(
            implementation_plan.get(
                "task",
                selected_task.get(
                    "title",
                    ""
                )
            )
        )

        print(
            "\nObjective:"
        )

        print(
            implementation_plan.get(
                "objective",
                ""
            )
        )

        requirements = implementation_plan.get(
            "requirements",
            []
        )

        print(
            "\nRequirements:"
        )

        if requirements:

            for i, requirement in enumerate(
                requirements,
                1
            ):

                print(
                    f"{i}. {requirement}"
                )

        else:

            print(
                "No requirements identified."
            )

        files_to_create = implementation_plan.get(
            "files_to_create",
            []
        )

        files_to_modify = implementation_plan.get(
            "files_to_modify",
            []
        )

        print(
            "\nFiles to create:"
        )

        if files_to_create:

            for file_path in files_to_create:

                print(
                    f"  + {file_path}"
                )

        else:

            print(
                "  None"
            )

        print(
            "\nFiles to modify:"
        )

        if files_to_modify:

            for file_path in files_to_modify:

                print(
                    f"  ~ {file_path}"
                )

        else:

            print(
                "  None"
            )

        dependencies = implementation_plan.get(
            "dependencies",
            []
        )

        print(
            "\nDependencies:"
        )

        if dependencies:

            for dependency in dependencies:

                print(
                    f"  • {dependency}"
                )

        else:

            print(
                "  None"
            )

        implementation_steps = implementation_plan.get(
            "implementation_steps",
            []
        )

        print(
            "\nImplementation steps:"
        )

        if implementation_steps:

            for i, step in enumerate(
                implementation_steps,
                1
            ):

                print(
                    f"{i}. {step}"
                )

        else:

            print(
                "No implementation steps identified."
            )

        testing_strategy = implementation_plan.get(
            "testing_strategy",
            []
        )

        print(
            "\nTesting strategy:"
        )

        if testing_strategy:

            for i, test in enumerate(
                testing_strategy,
                1
            ):

                print(
                    f"{i}. {test}"
                )

        else:

            print(
                "No testing strategy identified."
            )

        # ======================================================
        # 16. VALIDATE PROPOSED CHANGES
        # ======================================================

        print_separator(
            "VALIDATING PROPOSED FILE CHANGES"
        )

        valid_changes = []

        validation_failed = False

        existing_file_set = set(
            project_files
        )

        seen_paths = set()

        for change in file_changes:

            if not isinstance(
                change,
                dict
            ):

                print(
                    "\n⚠ Invalid file change object."
                )

                validation_failed = True

                continue

            action = change.get(
                "action"
            )

            file_path = normalize_path(
                change.get(
                    "path",
                    ""
                )
            )

            content = change.get(
                "content"
            )

            # --------------------------------------------------
            # Basic validation
            # --------------------------------------------------

            if action not in {
                "create",
                "update"
            }:

                print(
                    f"\n⚠ Invalid action "
                    f"'{action}' for "
                    f"{file_path}"
                )

                validation_failed = True

                continue

            if not is_safe_relative_path(
                file_path
            ):

                print(
                    f"\n⚠ Unsafe file path: "
                    f"{file_path}"
                )

                validation_failed = True

                continue

            if not isinstance(
                content,
                str
            ):

                print(
                    f"\n⚠ Missing or invalid "
                    f"content for "
                    f"{file_path}"
                )

                validation_failed = True

                continue

            # --------------------------------------------------
            # Duplicate path protection
            # --------------------------------------------------

            if file_path in seen_paths:

                print(
                    f"\n⚠ Duplicate file change: "
                    f"{file_path}"
                )

                validation_failed = True

                continue

            seen_paths.add(
                file_path
            )

            # --------------------------------------------------
            # CREATE must be new
            # --------------------------------------------------

            if action == "create":

                if file_path in existing_file_set:

                    print(
                        f"\n⚠ Cannot CREATE existing "
                        f"file: {file_path}"
                    )

                    validation_failed = True

                    continue

            # --------------------------------------------------
            # UPDATE must already exist
            # --------------------------------------------------

            if action == "update":

                if file_path not in existing_file_set:

                    print(
                        f"\n⚠ Cannot UPDATE missing "
                        f"file: {file_path}"
                    )

                    validation_failed = True

                    continue

                # An update should have been inspected
                # before Gemini was allowed to modify it.
                if file_path not in relevant_files:

                    print(
                        f"\n⚠ Refusing to UPDATE "
                        f"{file_path}: "
                        f"file was not inspected."
                    )

                    validation_failed = True

                    continue

            # --------------------------------------------------
            # Python syntax validation
            # --------------------------------------------------

            valid_python, syntax_error = (
                validate_python_content(
                    file_path,
                    content
                )
            )

            if not valid_python:

                print(
                    f"\n⚠ Python syntax error "
                    f"in {file_path}: "
                    f"{syntax_error}"
                )

                validation_failed = True

                continue

            valid_changes.append(
                {
                    "action": action,
                    "path": file_path,
                    "content": content
                }
            )

        # ------------------------------------------------------
        # Check declared files against actual changes
        # ------------------------------------------------------

        actual_change_paths = {
            change["path"]
            for change in valid_changes
        }

        declared_create_paths = {
            normalize_path(path)
            for path in files_to_create
            if isinstance(path, str)
        }

        declared_modify_paths = {
            normalize_path(path)
            for path in files_to_modify
            if isinstance(path, str)
        }

        undeclared_paths = (
            actual_change_paths
            - declared_create_paths
            - declared_modify_paths
        )

        if undeclared_paths:

            print(
                "\n⚠ AI proposed file changes that "
                "were not declared in files_to_create "
                "or files_to_modify:"
            )

            for path in sorted(
                undeclared_paths
            ):

                print(
                    f"  • {path}"
                )

            validation_failed = True

        if validation_failed:

            print(
                "\n⚠ File-change validation failed."
            )

            print(
                "No file changes will be applied."
            )

            file_changes = []

        else:

            file_changes = valid_changes

            print(
                f"\n✓ Validated "
                f"{len(file_changes)} "
                f"file changes."
            )

        # ======================================================
        # 17. DISPLAY PROPOSED CHANGES
        # ======================================================

        print_separator(
            "PROPOSED FILE CHANGES"
        )

        if not file_changes:

            print(
                "\nNo valid file changes."
            )

        else:

            for i, change in enumerate(
                file_changes,
                1
            ):

                print(
                    f"\n{i}. "
                    f"{change['action']} | "
                    f"{change['path']}"
                )

        # ======================================================
        # 18. APPLY FILE CHANGES
        # ======================================================

        successful_changes = 0

        if file_changes:

            print_separator(
                "APPLYING FILE CHANGES"
            )

            for change in file_changes:

                action = change["action"]

                file_path = change["path"]

                content = change["content"]

                try:

                    if action == "create":

                        result = await file_mcp.create_file(
                            file_path,
                            content
                        )

                    else:

                        result = await file_mcp.update_file(
                            file_path,
                            content
                        )

                except Exception as exc:

                    print(
                        f"\n⚠ Exception while "
                        f"{action}ing "
                        f"{file_path}: "
                        f"{exc}"
                    )

                    continue

                error = response_has_error(
                    result
                )

                if error:

                    print(
                        f"\n⚠ Failed to "
                        f"{action} "
                        f"{file_path}: "
                        f"{error}"
                    )

                    continue

                response_dict = first_dict(
                    result
                )

                # A string response is still accepted if
                # there is no explicit MCP error.
                print(
                    f"✓ {action.upper()}ED | "
                    f"{file_path}"
                )

                successful_changes += 1

            print(
                f"\nSuccessfully applied "
                f"{successful_changes}/"
                f"{len(file_changes)} "
                f"file changes."
            )

        else:

            print(
                "\nNo file changes to apply."
            )

        # ======================================================
        # 19. VERIFY FILES AFTER CHANGES
        # ======================================================

        print_separator(
            "VERIFYING PROJECT FILES"
        )

        final_files = await get_project_files(
            file_mcp
        )

        print(
            f"\nProject currently contains "
            f"{len(final_files)} files."
        )

        for file_path in final_files:

            print(
                f"  • {file_path}"
            )

        # ======================================================
        # 20. VERIFY EACH CHANGED FILE
        # ======================================================

        print_separator(
            "VERIFYING CHANGED FILES"
        )

        verification_failed = False

        if file_changes:

            for change in file_changes:

                file_path = change["path"]

                expected_content = change[
                    "content"
                ]

                if file_path not in final_files:

                    print(
                        f"✗ MISSING | "
                        f"{file_path}"
                    )

                    verification_failed = True

                    continue

                actual_content = await read_file_safe(
                    file_mcp,
                    file_path
                )

                if actual_content is None:

                    print(
                        f"✗ COULD NOT READ | "
                        f"{file_path}"
                    )

                    verification_failed = True

                    continue

                if actual_content != expected_content:

                    print(
                        f"✗ CONTENT MISMATCH | "
                        f"{file_path}"
                    )

                    verification_failed = True

                    continue

                # Re-run syntax validation against the
                # actual content stored by the MCP server.
                valid_python, syntax_error = (
                    validate_python_content(
                        file_path,
                        actual_content
                    )
                )

                if not valid_python:

                    print(
                        f"✗ INVALID PYTHON | "
                        f"{file_path} | "
                        f"{syntax_error}"
                    )

                    verification_failed = True

                    continue

                print(
                    f"✓ VERIFIED | "
                    f"{file_path}"
                )

        else:

            print(
                "No changed files to verify."
            )

        # ======================================================
        # 21. UPDATE TASK STATUS
        # ======================================================

        print_separator(
            "TASK STATUS"
        )

        all_changes_applied = (
            len(file_changes) == successful_changes
        )

        implementation_successful = (
            not validation_failed
            and all_changes_applied
            and not verification_failed
        )

        if implementation_successful:

            target_status = "completed"

        else:

            target_status = "in_progress"

        print(
            f"\nTarget status: "
            f"{target_status.upper()}"
        )

        try:

            status_result = await mcp.call_tool(
                "update_task",
                {
                    "task_id": task_id,
                    "status": target_status
                }
            )

            status_items = parse_mcp_result(
                status_result
            )

            status_error = response_has_error(
                status_result
            )

            if status_error:

                print(
                    f"⚠ Could not update task status: "
                    f"{status_error}"
                )

                print(
                    "RAW STATUS RESPONSE:"
                )

                print_json(
                    status_items
                )

            else:

                updated_task = first_dict(
                    status_items
                )

                if updated_task:

                    print(
                        f"✓ TASK STATUS UPDATED | "
                        f"{updated_task.get('task_id')} | "
                        f"{updated_task.get('status')}"
                    )

                else:

                    print(
                        "⚠ MCP returned an unexpected "
                        "task-status response:"
                    )

                    print_json(
                        status_items
                    )

        except Exception as exc:

            print(
                f"⚠ Exception while updating "
                f"task status: {exc}"
            )

        # ======================================================
        # 22. STRUCTURED PLAN
        # ======================================================

        print_separator(
            "STRUCTURED PLAN"
        )

        print_json(
            implementation_plan
        )

        # ======================================================
        # 23. FINAL RESULT
        # ======================================================

        print_separator()

        if implementation_successful:

            print(
                "✓ Developer Agent successfully "
                "implemented and verified the task."
            )

        else:

            print(
                "⚠ Developer Agent completed its run, "
                "but implementation verification failed."
            )

    finally:

        # ======================================================
        # 24. DISCONNECT FILE MCP
        # ======================================================

        try:

            await file_mcp.disconnect()

        except Exception as exc:

            print(
                f"\n⚠ File MCP disconnect error: "
                f"{exc}"
            )

        # ======================================================
        # 25. DISCONNECT PROJECT MCP
        # ======================================================

        try:

            await mcp.disconnect()

        except Exception as exc:

            print(
                f"\n⚠ Project MCP disconnect error: "
                f"{exc}"
            )

    print(
        "\n" + "=" * 60
    )

    print(
        "DEVELOPER AGENT COMPLETED"
    )

    print(
        "=" * 60
    )


    return {
        "success": implementation_successful,
        "status": (
            "completed"
            if implementation_successful
            else "failed"
        ),
        "stage": "developer",
        "task_id": task_id,
        "task": selected_task.get("title", ""),
        "file_changes": file_changes,
        "implementation_plan": implementation_plan,
        "successful_changes": successful_changes,
        "validation_failed": validation_failed,
        "verification_failed": verification_failed,
        "task_status": target_status
    }


# ==============================================================
# INTERACTIVE ENTRY POINT
# ==============================================================

async def main():
    await run_developer()


if __name__ == "__main__":

    asyncio.run(main())
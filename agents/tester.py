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
You are the Testing Agent in an AI Student Project Manager.

Your job is to analyze ONE software development task,
inspect its ACTUAL IMPLEMENTATION, generate practical automated tests,
and verify those tests against the real source code.

You are given:
- project information
- selected task
- other project tasks
- complete project file structure
- relevant existing source files
- an extracted source-code symbol map

IMPORTANT:

The source code is the source of truth.

Never invent:
- functions
- classes
- methods
- endpoints
- modules
- import paths
- return types
- dependency functions

Before generating tests, verify every imported project symbol against
the provided source files and symbol map.

Return ONLY valid JSON.
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

            return item.get("error")

    return None


# ==============================================================
# PATH HELPERS
# ==============================================================


def normalize_path(path):

    if not isinstance(path, str):

        return ""

    path = path.replace(
        "\\",
        "/"
    ).strip()

    if path == ".":

        return "."

    return path.rstrip("/")


def is_safe_relative_path(path):

    if not isinstance(path, str):

        return False

    path = path.replace(
        "\\",
        "/"
    ).strip()

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

        items = parse_mcp_result(result)

        for item in items:

            if not isinstance(item, dict):

                continue

            item_path = normalize_path(
                item.get(
                    "path",
                    ""
                )
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
# FILE READING
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

        if not isinstance(item, dict):

            continue

        if item.get("error"):

            return None

        if "content" in item:

            return item.get(
                "content",
                ""
            )

    return None


async def read_files(
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
# PYTHON SOURCE ANALYSIS
# ==============================================================


def module_name_from_path(path):

    normalized = normalize_path(
        path
    )

    if not normalized.endswith(".py"):

        return None

    module = normalized[:-3]

    if module.endswith("/__init__"):

        module = module[:-9]

    module = module.replace(
        "/",
        "."
    )

    return module


def extract_python_symbols(
    file_path,
    content
):
    try:
        tree = ast.parse(
            content,
            filename=file_path
        )

    except SyntaxError as exc:

        return {
            "path": file_path,
            "module": module_name_from_path(
                file_path
            ),
            "syntax_error": str(exc),
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
            "routes": []
        }

    classes = []
    functions = []
    variables = []
    imports = []
    routes = []

    # ----------------------------------------------------------
    # Collect module-level variables
    # ----------------------------------------------------------

    def collect_target_names(target):
        names = []

        if isinstance(target, ast.Name):
            names.append(target.id)

        elif isinstance(
            target,
            (ast.Tuple, ast.List)
        ):
            for element in target.elts:
                names.extend(
                    collect_target_names(element)
                )

        return names

    for node in tree.body:

        if isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
                ast.AugAssign
            )
        ):

            if isinstance(
                node,
                ast.Assign
            ):
                for target in node.targets:
                    variables.extend(
                        collect_target_names(target)
                    )

            else:
                variables.extend(
                    collect_target_names(
                        node.target
                    )
                )

        elif isinstance(
            node,
            ast.Import
        ):
            for alias in node.names:

                if alias.asname:
                    variables.append(
                        alias.asname
                    )
                else:
                    variables.append(
                        alias.name.split(".")[0]
                    )

        elif isinstance(
            node,
            ast.ImportFrom
        ):
            for alias in node.names:

                if alias.name == "*":
                    continue

                variables.append(
                    alias.asname or alias.name
                )

    # ----------------------------------------------------------
    # Existing AST analysis
    # ----------------------------------------------------------

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.ClassDef
        ):

            methods = []

            for child in node.body:

                if isinstance(
                    child,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef
                    )
                ):
                    methods.append(
                        child.name
                    )

            classes.append(
                {
                    "name": node.name,
                    "methods": methods
                }
            )

        elif isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        ):

            functions.append(
                node.name
            )

        elif isinstance(
            node,
            ast.Import
        ):

            for alias in node.names:

                imports.append(
                    alias.name
                )

        elif isinstance(
            node,
            ast.ImportFrom
        ):

            module = node.module or ""

            for alias in node.names:

                imports.append(
                    f"{module}.{alias.name}"
                )

        elif isinstance(
            node,
            ast.Call
        ):

            if (
                isinstance(
                    node.func,
                    ast.Attribute
                )
                and node.func.attr in {
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch"
                }
            ):

                if node.args:

                    first_arg = node.args[0]

                    if (
                        isinstance(
                            first_arg,
                            ast.Constant
                        )
                        and isinstance(
                            first_arg.value,
                            str
                        )
                    ):

                        routes.append(
                            {
                                "method": (
                                    node.func.attr.upper()
                                ),
                                "path": first_arg.value
                            }
                        )

    return {
        "path": file_path,
        "module": module_name_from_path(
            file_path
        ),
        "syntax_error": None,
        "classes": classes,
        "functions": sorted(
            set(functions)
        ),
        "variables": sorted(
            set(variables)
        ),
        "imports": sorted(
            set(imports)
        ),
        "routes": routes
    }

def build_symbol_map(
    existing_files
):
    print("\n--- FILES USED FOR SYMBOL MAP ---")

    for file_data in existing_files:
        print(file_data["path"])

    symbol_map = []

    for file_data in existing_files:

        file_path = file_data["path"]

        if not file_path.endswith(".py"):

            continue

        symbols = extract_python_symbols(
            file_path,
            file_data["content"]
        )

        if file_path.endswith("models/database.py"):
            print("\nDATABASE SYMBOLS:")
            print(symbols)

        if symbols:

            symbol_map.append(
                symbols
            )

    return symbol_map


def display_symbol_map(
    symbol_map
):

    print_separator(
        "ACTUAL SOURCE SYMBOLS"
    )

    for module in symbol_map:

        print(
            f"\n--- {module['path']} ---"
        )

        print(
            f"Module: "
            f"{module.get('module')}"
        )

        if module.get(
            "syntax_error"
        ):

            print(
                f"⚠ Syntax error: "
                f"{module['syntax_error']}"
            )

            continue

        classes = module.get(
            "classes",
            []
        )

        if classes:

            print("Classes:")

            for cls in classes:

                print(
                    f"  • {cls['name']}"
                )

                for method in cls.get(
                    "methods",
                    []
                ):

                    print(
                        f"      - {method}"
                    )

        functions = module.get(
            "functions",
            []
        )

        if functions:

            print("Functions:")

            for function in functions:

                print(
                    f"  • {function}"
                )

        variables = module.get(
            "variables",
            []
        )

        if variables:

            print("Variables:")

            for variable in variables:

                print(
                    f"  • {variable}"
                )

        routes = module.get(
            "routes",
            []
        )

        if routes:

            print("Routes:")

            for route in routes:

                print(
                    f"  • "
                    f"{route['method']} "
                    f"{route['path']}"
                )


# ==============================================================
# TEST SOURCE VALIDATION
# ==============================================================


def validate_python_content(
    file_path,
    content
):

    try:

        tree = ast.parse(
            content,
            filename=file_path
        )

        return True, tree, None

    except SyntaxError as exc:

        message = (
            f"{exc.msg} "
            f"(line {exc.lineno}, "
            f"column {exc.offset})"
        )

        return False, None, message


def build_real_module_map(
    project_files
):

    modules = {}

    for path in project_files:

        module = module_name_from_path(
            path
        )

        if module:

            modules[module] = path

    return modules


def build_symbol_lookup(
    symbol_map
):
    lookup = {}

    for module in symbol_map:

        module_name = module.get(
            "module"
        )

        if not module_name:
            continue

        symbols = set(
            module.get(
                "functions",
                []
            )
        )

        # Include module-level variables.
        # Examples:
        # app = FastAPI()
        # router = APIRouter()
        # Base = declarative_base()
        # SessionLocal = sessionmaker(...)
        symbols.update(
            module.get(
                "variables",
                []
            )
        )

        # Include classes and their methods.
        for cls in module.get(
            "classes",
            []
        ):

            symbols.add(
                cls["name"]
            )

            for method in cls.get(
                "methods",
                []
            ):

                symbols.add(
                    f"{cls['name']}.{method}"
                )

        lookup[module_name] = symbols

    return lookup

def validate_test_imports(
    content,
    module_map,
    symbol_lookup
):

    """
    Validate project-local imports.

    Third-party imports such as pytest, fastapi,
    sqlalchemy and unittest.mock are allowed.
    """

    try:

        tree = ast.parse(
            content
        )

    except SyntaxError:

        return [
            "Test file contains invalid Python syntax."
        ]

    errors = []

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.ImportFrom
        ):

            module = node.module

            if not module:

                continue

            if node.level:

                continue

            if module in module_map:

                actual_symbols = symbol_lookup.get(
                    module,
                    set()
                )

                for alias in node.names:

                    imported_name = alias.name

                    if imported_name == "*":

                        continue

                    if imported_name not in actual_symbols:

                        errors.append(
                            f"Invalid project import: "
                            f"from {module} "
                            f"import {imported_name}"
                        )

    return errors


def validate_test_file(
    path,
    content,
    project_files,
    symbol_map
):

    errors = []

    if not path.startswith(
        "tests/"
    ):

        errors.append(
            "Test file must be inside tests/."
        )

    if not path.endswith(
        ".py"
    ):

        errors.append(
            "Generated test file must be Python."
        )

    if not is_safe_relative_path(
        path
    ):

        errors.append(
            "Unsafe test file path."
        )

    valid, tree, syntax_error = (
        validate_python_content(
            path,
            content
        )
    )

    if not valid:

        errors.append(
            f"Python syntax error: "
            f"{syntax_error}"
        )

        return errors

    module_map = build_real_module_map(
        project_files
    )

    symbol_lookup = build_symbol_lookup(
        symbol_map
    )

    errors.extend(
        validate_test_imports(
            content,
            module_map,
            symbol_lookup
        )
    )

    test_functions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        )
        and node.name.startswith(
            "test_"
        )
    ]

    if not test_functions:

        errors.append(
            "No pytest test_* functions found."
        )

    return errors


# ==============================================================
# MCP FILE CREATION
# ==============================================================


async def create_test_file(
    file_mcp,
    path,
    content
):

    try:

        result = await file_mcp.create_file(
            path,
            content
        )

    except Exception as exc:

        return False, str(exc)

    error = response_has_error(
        result
    )

    if error:

        return False, error

    return True, None


# ==============================================================
# CORE TESTING AGENT
# ==============================================================


async def run_testing_agent(
    project_id,
    task_id,
    project=None,
    tasks=None,
    selected_task=None,
    show_output=True
):

    """
    Public Testing Agent entry point.

    This function can be called directly by the Orchestrator.

    The interactive CLI below also calls this function.

    Parameters
    ----------
    project_id:
        Project ID.

    task_id:
        Task ID to test.

    project:
        Optional already-fetched project object.

    tasks:
        Optional already-fetched project tasks.

    selected_task:
        Optional already-selected task.

    show_output:
        Whether to print detailed progress.
    """

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

    try:

        # ======================================================
        # 1. GET PROJECT
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
                    "stage": "testing",
                    "status": "failed",
                    "task_id": task_id,
                    "error": "Project not found."
                }

            if project.get(
                "error"
            ):

                return {
                    "success": False,
                    "stage": "testing",
                    "status": "failed",
                    "task_id": task_id,
                    "error": project.get(
                        "error"
                    )
                }

        # ======================================================
        # 2. GET TASKS
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
                if isinstance(
                    item,
                    dict
                )
                and not item.get(
                    "error"
                )
            ]

        if not tasks:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "error": "No tasks found."
            }

        # ======================================================
        # 3. FIND SELECTED TASK
        # ======================================================

        if selected_task is None:

            selected_task = find_task(
                tasks,
                task_id
            )

        if not selected_task:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "error": (
                    f"Task not found: "
                    f"{task_id}"
                )
            }

        # ======================================================
        # 4. DISPLAY PROJECT / TASK
        # ======================================================

        if show_output:

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

            print_separator(
                "SELECTED TASK"
            )

            display_task(
                selected_task
            )

        # ======================================================
        # 5. DISCOVER PROJECT FILES
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
                f"{len(project_files)} "
                f"project files:"
            )

            for path in project_files:

                print(
                    f"  • {path}"
                )

        # ======================================================
        # 6. IDENTIFY RELEVANT FILES
        # ======================================================

        if show_output:

            print_separator(
                "IDENTIFYING RELEVANT FILES"
            )

        file_selection_prompt = f"""
Identify the smallest set of EXISTING files that need to be inspected
to test the selected task.

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

PROJECT FILES:

{json.dumps(project_files, indent=2)}

Return ONLY:

{{
    "relevant_files": [
        "exact/path"
    ]
}}

Rules:
- Only use exact paths from PROJECT FILES.
- Include implementation files.
- Include API files if endpoints are involved.
- Include service files if services are involved.
- Include schema/model files when relevant.
- Do not invent files.
"""

        file_selection_response = generate_response(
            file_selection_prompt
        )

        try:

            file_selection = json.loads(
                file_selection_response
            )

        except json.JSONDecodeError:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "error": (
                    "Invalid JSON while "
                    "identifying relevant files."
                )
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

        relevant_files = [
            normalize_path(path)
            for path in relevant_files
            if normalize_path(path)
            in project_files
        ]

        if show_output:

            print(
                "\nRelevant files:"
            )

            for path in relevant_files:

                print(
                    f"  • {path}"
                )

        # ======================================================
        # 7. READ SOURCE FILES
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
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "error": (
                    "No relevant source files "
                    "could be read."
                )
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
        # 8. BUILD ACTUAL SYMBOL MAP
        # ======================================================

        source_files_for_validation = await read_files(
            file_mcp,
            project_files
        )

        symbol_map = build_symbol_map(
            source_files_for_validation
        )

        if show_output:

            display_symbol_map(
                symbol_map
            )

        # ======================================================
        # 9. GENERATE TESTING PLAN
        # ======================================================

        if show_output:

            print_separator(
                "TESTING AGENT ANALYZING..."
            )

        testing_prompt = f"""
You are the Testing Agent.

Design tests ONLY for the selected task.

PROJECT:

{json.dumps(project, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

SOURCE FILES:

{json.dumps(existing_files, indent=2)}

ACTUAL SOURCE SYMBOL MAP:

{json.dumps(symbol_map, indent=2)}

Return ONLY valid JSON:

{{
    "task": "...",
    "testing_objective": "...",
    "test_cases": [
        {{
            "name": "...",
            "description": "...",
            "type": "unit|integration|validation|error",
            "expected_result": "..."
        }}
    ],
    "files_to_test": [],
    "test_files_to_create": [],
    "dependencies": [],
    "testing_steps": []
}}

CRITICAL RULES:

- Source code is the source of truth.
- Use only actual functions/classes/methods/endpoints.
- Do not invent APIs.
- Do not invent helper functions.
- Use exact module paths.
- If a dependency function is not present, do not import it.
- If an API endpoint exists, test its actual path.
- If an external service exists, mock the exact symbol used by the
  implementation.

IMPORTANT TEST FILE RULES:

- test_files_to_create must contain ONLY NEW test files.
- Every path in test_files_to_create must be inside tests/.
- Never select an existing file from PROJECT FILES as a file to create.
- Each test file must be specifically related to the selected task.
- Create separate test files when different implementation areas
  require substantially different tests.
- The planned test files must provide meaningful coverage of the
  selected task.
"""

        testing_response = generate_response(
            testing_prompt
        )

        if show_output:

            print(
                "\nRAW AI RESPONSE:"
            )

            print(
                testing_response
            )

        try:

            testing_plan = json.loads(
                testing_response
            )

        except json.JSONDecodeError:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "error": (
                    "AI returned invalid "
                    "testing-plan JSON."
                )
            }

        # ======================================================
        # 10. GENERATE TEST FILES
        # ======================================================

        if show_output:

            print_separator(
                "GENERATING AUTOMATED TESTS"
            )

        test_generation_prompt = f"""
You are the Test Implementation Agent.

Generate pytest files for the selected task.

PROJECT FILE STRUCTURE:

{json.dumps(project_files, indent=2)}

SELECTED TASK:

{json.dumps(selected_task, indent=2)}

ACTUAL SOURCE FILES:

{json.dumps(existing_files, indent=2)}

ACTUAL SOURCE SYMBOL MAP:

{json.dumps(symbol_map, indent=2)}

TESTING PLAN:

{json.dumps(testing_plan, indent=2)}

Return ONLY:

{{
    "test_file_changes": [
        {{
            "action": "create",
            "path": "tests/test_example.py",
            "content": "COMPLETE PYTHON FILE"
        }}
    ]
}}

ABSOLUTE RULES:

1. Every imported project module MUST exist in PROJECT FILE STRUCTURE.

2. Every imported project symbol MUST exist in ACTUAL SOURCE SYMBOL MAP.

3. Never write:
from models.database import get_db
unless get_db actually exists in models.database.

4. If get_db exists in api.endpoints, import it from api.endpoints.

5. Never invent parse_receipt_image or any other function.

6. If the actual source exposes:
    GeminiParser.parse_expense
test that actual interface instead.

7. Test actual FastAPI endpoints only.

8. Mock external API/network calls.

9. Never call real Gemini APIs.

10. Every test file must be valid pytest code.

11. Only create new test files.

12. Never overwrite an existing test file.

13. All test files must be inside tests/.

14. Return complete file contents.

15. Generate EVERY file listed in testing_plan.test_files_to_create.

16. Do not generate fewer test files than the testing plan specifies.

17. The generated file paths MUST exactly match the paths in
    testing_plan.test_files_to_create.

18. If a planned test file already exists in PROJECT FILE STRUCTURE,
    choose a NEW task-specific filename in the testing plan instead.
    Never overwrite existing tests.

19. Every generated test file must contain tests specifically related
    to the selected task.

20. Do not generate tests for unrelated existing functionality.
"""

        test_generation_response = generate_response(
            test_generation_prompt
        )

        if show_output:

            print(
                "\nRAW TEST GENERATION RESPONSE:"
            )

            print(
                test_generation_response
            )

        try:

            generated_tests = json.loads(
                test_generation_response
            )

        except json.JSONDecodeError:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "error": (
                    "Invalid JSON while "
                    "generating tests."
                )
            }

        test_file_changes = generated_tests.get(
            "test_file_changes",
            []
        )

        

        if not isinstance(
            test_file_changes,
            list
        ):

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "error": (
                    "Invalid test_file_changes."
                )
            }

        # ======================================================
        # VERIFY TEST GENERATION AGAINST TESTING PLAN
        # ======================================================

        planned_test_files = testing_plan.get(
            "test_files_to_create",
            []
        )

        if not isinstance(
            planned_test_files,
            list
        ):

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "error": (
                    "Testing plan contains an invalid "
                    "test_files_to_create field."
                )
            }

        planned_test_files = {
            normalize_path(path)
            for path in planned_test_files
            if isinstance(path, str)
        }

        generated_test_paths = {
            normalize_path(change.get("path", ""))
            for change in test_file_changes
            if isinstance(change, dict)
        }

        missing_planned_tests = (
            planned_test_files
            - generated_test_paths
        )

        unexpected_generated_tests = (
            generated_test_paths
            - planned_test_files
        )

        if missing_planned_tests:

            if show_output:

                print(
                    "\n✗ TEST GENERATION INCOMPLETE"
                )

                print(
                    "\nPlanned test files that were "
                    "not generated:"
                )

                for path in sorted(
                    missing_planned_tests
                ):

                    print(
                        f"  • {path}"
                    )

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "generated_test_files": sorted(
                    generated_test_paths
                ),
                "missing_planned_test_files": sorted(
                    missing_planned_tests
                ),
                "error": (
                    "Testing Agent failed to generate "
                    "all test files required by its "
                    "testing plan."
                )
            }

        if unexpected_generated_tests:

            if show_output:

                print(
                    "\n✗ UNPLANNED TEST FILES GENERATED"
                )

                for path in sorted(
                    unexpected_generated_tests
                ):

                    print(
                        f"  • {path}"
                    )

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "generated_test_files": sorted(
                    generated_test_paths
                ),
                "unexpected_test_files": sorted(
                    unexpected_generated_tests
                ),
                "error": (
                    "Testing Agent generated test files "
                    "that were not included in its "
                    "testing plan."
                )
            }

        # ======================================================
        # 11. VALIDATE GENERATED TESTS
        # ======================================================

        if show_output:

            print_separator(
                "VALIDATING GENERATED TESTS"
            )

        valid_test_changes = []

        seen_paths = set()

        for change in test_file_changes:

            if not isinstance(
                change,
                dict
            ):

                if show_output:

                    print(
                        "\n⚠ Invalid test "
                        "change object."
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

            if action != "create":

                if show_output:

                    print(
                        f"\n⚠ Invalid test action "
                        f"for {path}: "
                        f"{action}"
                    )

                continue

            if path in seen_paths:

                if show_output:

                    print(
                        f"\n⚠ Duplicate "
                        f"test path: "
                        f"{path}"
                    )

                continue

            seen_paths.add(
                path
            )

            if path in project_files:

                if show_output:

                    print(
                        f"\n⚠ REFUSED to overwrite "
                        f"existing file: "
                        f"{path}"
                    )

                continue

            if not isinstance(
                content,
                str
            ):

                if show_output:

                    print(
                        f"\n⚠ Invalid content: "
                        f"{path}"
                    )

                continue

            errors = validate_test_file(
                path,
                content,
                project_files,
                symbol_map
            )

            if errors:

                if show_output:

                    print(
                        f"\n✗ REJECTED | "
                        f"{path}"
                    )

                    for error in errors:

                        print(
                            f"   • {error}"
                        )

                continue

            if show_output:

                print(
                    f"\n✓ VALIDATED | "
                    f"{path}"
                )

            valid_test_changes.append(
                {
                    "action": "create",
                    "path": path,
                    "content": content
                }
            )

        if show_output:

            print(
                f"\n✓ Validated "
                f"{len(valid_test_changes)} "
                f"test files."
            )

        if not valid_test_changes:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "generated_test_files": [],
                "verified_test_files": [],
                "test_run": {
                    "executed": False,
                    "passed": False,
                    "pytest_exit_code": None
                },
                "error": (
                    "No valid tests survived "
                    "source-code validation."
                )
            }

        # ======================================================
        # 12. CREATE TEST FILES
        # ======================================================

        if show_output:

            print_separator(
                "CREATING TEST FILES"
            )

        successful_tests = []

        for change in valid_test_changes:

            success, error = await create_test_file(
                file_mcp,
                change["path"],
                change["content"]
            )

            if not success:

                if show_output:

                    print(
                        f"\n✗ FAILED | "
                        f"{change['path']} | "
                        f"{error}"
                    )

                continue

            if show_output:

                print(
                    f"✓ CREATED | "
                    f"{change['path']}"
                )

            successful_tests.append(
                change["path"]
            )

        if not successful_tests:

            return {
                "success": False,
                "stage": "testing",
                "status": "failed",
                "task_id": task_id,
                "testing_plan": testing_plan,
                "generated_test_files": [],
                "verified_test_files": [],
                "test_run": {
                    "executed": False,
                    "passed": False,
                    "pytest_exit_code": None
                },
                "error": (
                    "No test files could "
                    "be created."
                )
            }

        # ======================================================
        # 13. READ BACK CREATED TESTS
        # ======================================================

        if show_output:

            print_separator(
                "VERIFYING GENERATED TEST CONTENT"
            )

        verified_test_files = []

        project_files_with_tests = (
            project_files
            + successful_tests
        )

        for path in successful_tests:

            content = await read_file_safe(
                file_mcp,
                path
            )

            if content is None:

                if show_output:

                    print(
                        f"✗ COULD NOT READ | "
                        f"{path}"
                    )

                continue

            errors = validate_test_file(
                path,
                content,
                project_files_with_tests,
                symbol_map
            )

            if errors:

                if show_output:

                    print(
                        f"\n✗ INVALID AFTER "
                        f"CREATION | "
                        f"{path}"
                    )

                    for error in errors:

                        print(
                            f"   • {error}"
                        )

                continue

            if show_output:

                print(
                    f"\n✓ VERIFIED | "
                    f"{path}"
                )

                print(
                    f"\n--- {path} ---"
                )

                print(
                    content
                )

            verified_test_files.append(
                path
            )

        # ======================================================
        # 14. RUN TESTS
        # ======================================================

        if show_output:

            print_separator(
                "RUNNING AUTOMATED TESTS"
            )

        test_run_success = False

        pytest_executed = False

        pytest_output = ""

        pytest_exit_code = None

        if not verified_test_files:

            if show_output:

                print(
                    "\n⚠ No verified test "
                    "files available."
                )

        else:

            if show_output:

                print(
                    "\nTest files to execute:"
                )

                for path in verified_test_files:

                    print(
                        f"  • {path}"
                    )

                print(
                    "\nExecuting pytest..."
                )

            try:

                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        *verified_test_files,
                        "-v"
                    ],
                    capture_output=True,
                    text=True
                )

                pytest_executed = True

                pytest_exit_code = (
                    result.returncode
                )

                pytest_output = (
                    result.stdout
                    + "\n"
                    + result.stderr
                )

                if show_output:

                    print(
                        "\nPYTEST OUTPUT:"
                    )

                    print(
                        pytest_output
                    )

                if result.returncode == 0:

                    test_run_success = True

                    if show_output:

                        print(
                            "\n✓ ALL GENERATED "
                            "TESTS PASSED."
                        )

                else:

                    if show_output:

                        print(
                            "\n✗ GENERATED "
                            "TESTS FAILED."
                        )

                        print(
                            f"Pytest exit code: "
                            f"{result.returncode}"
                        )

            except Exception as exc:

                pytest_output = str(exc)

                if show_output:

                    print(
                        f"\n⚠ Failed to execute "
                        f"pytest: {exc}"
                    )

        # ======================================================
        # 15. STRUCTURED RESULT
        # ======================================================

        structured_result = {

            "success": test_run_success,

            "stage": "testing",

            "status": (
                "passed"
                if test_run_success
                else "failed"
            ),

            "task": selected_task.get(
                "title",
                ""
            ),

            "task_id": task_id,

            "testing_plan": testing_plan,

            "generated_test_files": (
                successful_tests
            ),

            "verified_test_files": (
                verified_test_files
            ),

            "test_run": {

                "executed": pytest_executed,

                "passed": test_run_success,

                "pytest_exit_code": (
                    pytest_exit_code
                )
            },

            "pytest_output": pytest_output
        }

        # ======================================================
        # 16. DISPLAY FINAL RESULT
        # ======================================================

        if show_output:

            print_separator(
                "FINAL TEST VERIFICATION"
            )

            print(
                f"\nGenerated test files: "
                f"{len(successful_tests)}"
            )

            print(
                f"Verified test files: "
                f"{len(verified_test_files)}"
            )

            print(
                f"Pytest executed: "
                f"{pytest_executed}"
            )

            print(
                f"Pytest passed: "
                f"{test_run_success}"
            )

            if test_run_success:

                print(
                    "\n✓ TESTING PASSED"
                )

            elif verified_test_files:

                print(
                    "\n⚠ TESTS GENERATED "
                    "BUT FAILED"
                )

            else:

                print(
                    "\n✗ TESTING COULD NOT "
                    "BE COMPLETED"
                )

            print_separator(
                "STRUCTURED TEST RESULT"
            )

            print_json(
                structured_result
            )

            print_separator()

            if test_run_success:

                print(
                    "Testing Agent successfully "
                    "generated, validated, verified, "
                    "and executed the automated tests."
                )

            else:

                print(
                    "Testing Agent completed its run, "
                    "but the implementation requires "
                    "attention before testing can be "
                    "considered successful."
                )

        return structured_result

    finally:

        try:

            await file_mcp.disconnect()

        except Exception:
            pass

        try:

            await project_mcp.disconnect()

        except Exception:
            pass


# ==============================================================
# INTERACTIVE CLI
# ==============================================================


async def main():

    print_separator(
        "TESTING AGENT"
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
        "\nEnter Task ID to test:\n> "
    ).strip()

    if not task_id:

        print(
            "\nTask ID cannot be empty."
        )

        return

    result = await run_testing_agent(
        project_id=project_id,
        task_id=task_id,
        show_output=True
    )

    if result.get("success"):

        print(
            "\n" + "=" * 60
        )

        print(
            "TESTING AGENT COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 60
        )

    else:

        print(
            "\n" + "=" * 60
        )

        print(
            "TESTING AGENT COMPLETED WITH FAILURES"
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
import os
import sys
import ast
import json
import re
import time
import threading
import traceback
import subprocess

from django.conf import settings

PROJECT_ROOT = os.path.join(settings.BASE_DIR, "..")
sys.path.insert(0, PROJECT_ROOT)

from openai import OpenAI

# OpenAI API configuration - read from root .env file
ROOT_ENV_PATH = os.path.join(os.path.dirname(PROJECT_ROOT), "..", ".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    try:
        with open(ROOT_ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    OPENAI_API_KEY = line.split("=", 1)[1].strip('"').strip("'")
                    break
    except Exception:
        pass

OPENAI_BASE_URL = "https://integrate.api.nvidia.com/v1"
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "deepseek-ai/deepseek-v4-pro-0813")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client = None


def get_openai_client():
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=OPENAI_BASE_URL,
            api_key=OPENAI_API_KEY,
            timeout=180.0,
            max_retries=2,
        )
    return _client


def generate_response(prompt: str, model_name=None) -> str:
    """Generate response using OpenAI API."""
    try:
        model_name = model_name or OPENAI_MODEL_NAME
        if model_name.startswith(("gemini-", "gemma-")):
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            return client.models.generate_content(model=model_name, contents=prompt).text
        if model_name in {
            "llama-3.3-70b-versatile",
            "llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
        }:
            client = OpenAI(
                base_url=GROQ_BASE_URL,
                api_key=os.getenv("GROQ_API_KEY"),
                timeout=180.0,
                max_retries=2,
            )
        else:
            client = get_openai_client()
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            top_p=0.95,
            max_tokens=8192,
            seed=42,
            extra_body={"chat_template_kwargs": {"thinking": False}},
            stream=False
        )
        return completion.choices[0].message.content
    except Exception as e:
        raise Exception(f"OpenAI API error: {e}")


from pipeline.models import PipelineRun
from tasks.models import Task
from projects.models import Project


MAX_RETRIES = 2
MAX_FILE_CONTENT = 8000


class PipelineStopped(Exception):
    """Raised when a user stops a running pipeline."""


def _raise_if_pipeline_stopped(pipeline):
    pipeline.refresh_from_db(fields=["stage"])
    if pipeline.stage == PipelineRun.Stage.FAILED:
        raise PipelineStopped()

# Helper functions for AST parsing and file tree building
def extract_python_symbols(source_code: str) -> dict:
    """Extract classes, functions, variables, imports from Python source."""
    symbols = {
        "classes": [],
        "functions": [],
        "variables": [],
        "imports": [],
    }
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)
            symbols["classes"].append({"name": node.name, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["functions"].append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols["variables"].append(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    symbols["imports"].append(alias.name)
            else:
                module = node.module or ""
                for alias in node.names:
                    symbols["imports"].append(f"{module}.{alias.name}")
    return symbols


def validate_python_syntax(source_code: str) -> tuple:
    """Validate Python syntax. Returns (is_valid, error_message)."""
    try:
        ast.parse(source_code)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def build_file_tree(files: dict) -> str:
    """Build a formatted file tree from a dict of filename -> content."""
    if not files:
        return "  (no files yet)"
    tree = {}
    for fname in sorted(files.keys()):
        parts = fname.split("/")
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = len(files[fname])

    lines = []
    def _walk(d, prefix=""):
        items = sorted(d.items(), key=lambda x: (isinstance(x[1], dict), x[0]))
        for i, (name, val) in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            if isinstance(val, dict):
                lines.append(f"{prefix}{connector}{name}/")
                _walk(val, prefix + ("    " if is_last else "│   "))
            else:
                lines.append(f"{prefix}{connector}{name} ({val}B)")
    _walk(tree)
    return "\n".join(lines)


def validate_imports(source_code: str, available_symbols: dict) -> list:
    """Check if imports reference symbols that exist in the project."""
    warnings = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return warnings

    all_names = set()
    for cls in available_symbols.get("classes", []):
        all_names.add(cls["name"])
        for m in cls.get("methods", []):
            all_names.add(m)
    for fn in available_symbols.get("functions", []):
        all_names.add(fn)
    for var in available_symbols.get("variables", []):
        all_names.add(var)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("."):
                for alias in node.names:
                    name = alias.name
                    if name != "*" and name not in all_names:
                        warnings.append(f"Import '{name}' from '{node.module}' may not exist in project")
    return warnings


def verify_file_content(filepath: str, content: str) -> dict:
    """Verify a generated file. Returns dict with valid, errors, warnings."""
    result = {"valid": True, "errors": [], "warnings": []}

    if not content or not content.strip():
        result["valid"] = False
        result["errors"].append("Empty file content")
        return result

    if filepath.endswith(".py"):
        is_valid, err = validate_python_syntax(content)
        if not is_valid:
            result["valid"] = False
            result["errors"].append(f"Syntax error: {err}")

    if filepath.endswith(".json"):
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            result["warnings"].append(f"Invalid JSON: {e.msg}")

    return result


def run_pipeline(project_id):
    thread = threading.Thread(target=_run_pipeline_worker, args=(project_id,), daemon=True)
    thread.start()


def _run_pipeline_worker(project_id):
    pipeline = None
    try:
        project = Project.objects.get(id=project_id)
        all_tasks = list(Task.objects.filter(project=project).order_by("id"))
        selected_model = project.ai_model or OPENAI_MODEL_NAME

        pipeline = PipelineRun.objects.create(
            project=project,
            stage=PipelineRun.Stage.PLANNING,
            total_tasks=0,
            completed_tasks=0,
        )

        pipeline.append_log(f"Pipeline started for project: {project.name}")
        pipeline.append_log(f"Description: {project.description}")

        # Planning belongs to the pipeline so the UI can show it and task creation
        # happens before the development stages begin.
        if not all_tasks:
            pipeline.append_log("[Planner] Creating an ordered implementation plan...")
            from ai_services.gemini_ai import plan_project

            plan = plan_project(
                f"{project.name}: {project.description or ''}",
                model_name=selected_model,
            )
            if not plan or not isinstance(plan.get("tasks"), list):
                planner_error = plan.get("error", "unknown planner error") if plan else "empty planner response"
                raise RuntimeError(f"Planner did not return a valid task plan: {planner_error}")

            for task_data in plan["tasks"]:
                Task.objects.create(
                    project=project,
                    title=task_data.get("title", "Untitled Task"),
                    description=task_data.get("description", ""),
                    priority=task_data.get("priority", "medium"),
                    status="todo",
                )
            all_tasks = list(Task.objects.filter(project=project).order_by("id"))
            pipeline.append_log(f"[Planner] Created {len(all_tasks)} tasks")
        else:
            pipeline.append_log(f"[Planner] Resuming existing plan with {len(all_tasks)} tasks")

        tasks = [task for task in all_tasks if task.status != "done"]
        pipeline.total_tasks = len(tasks)
        pipeline.save(update_fields=["total_tasks"])
        pipeline.append_log(f"Total tasks to process: {len(tasks)}")

        project_dir = os.path.join(PROJECT_ROOT, "generated_projects", f"project_{project.id}")
        os.makedirs(project_dir, exist_ok=True)

        project_files = {}

        for i, task in enumerate(tasks):
            _raise_if_pipeline_stopped(pipeline)
            task.status = "in_progress"
            task.save(update_fields=["status"])
            pipeline.current_task = task.title
            pipeline.save(update_fields=["current_task"])

            pipeline.append_log(f"\n{'='*60}")
            pipeline.append_log(f"TASK {i+1}/{len(tasks)}: {task.title}")
            pipeline.append_log(f"Priority: {task.priority}")
            pipeline.append_log(f"{'='*60}")

            task_completed = False
            last_error = None

            for attempt in range(MAX_RETRIES + 1):
                _raise_if_pipeline_stopped(pipeline)
                pipeline.append_log(
                    f"[AI] Using model: {selected_model}"
                )
                if attempt > 0:
                    pipeline.append_log(f"\n--- Retry attempt {attempt}/{MAX_RETRIES} ---")

                # DEVELOPER
                pipeline.stage = PipelineRun.Stage.DEVELOPING
                pipeline.save(update_fields=["stage"])
                pipeline.append_log("[Developer] Generating implementation...")

                try:
                    dev_result = _run_developer(
                        task, project, all_tasks, project_files, project_dir, pipeline,
                        previous_error=None if attempt == 0 else last_error,
                        model_name=selected_model,
                    )
                    _raise_if_pipeline_stopped(pipeline)
                    new_files = dev_result.get("files", {})
                    pipeline.append_log(f"[Developer] Generated {len(new_files)} files")

                    # Verify and write files
                    verification_errors = []
                    for fname, content in new_files.items():
                        if not content or not content.strip():
                            verification_errors.append(f"{fname}: empty content")
                            continue

                        vresult = verify_file_content(fname, content)
                        if not vresult["valid"]:
                            verification_errors.extend(
                                f"{fname}: {e}" for e in vresult["errors"]
                            )
                        for w in vresult.get("warnings", []):
                            pipeline.append_log(f"[Verify] Warning: {fname}: {w}")

                        project_files[fname] = content
                        _write_file(project_dir, fname, content)

                    if verification_errors:
                        last_error = "Verification errors: " + "; ".join(verification_errors)
                        pipeline.append_log(f"[Developer] {last_error}")
                        continue

                    # Validate imports for Python files
                    all_symbols = {"classes": [], "functions": [], "variables": []}
                    for fname, content in project_files.items():
                        if fname.endswith(".py"):
                            syms = extract_python_symbols(content)
                            all_symbols["classes"].extend(syms.get("classes", []))
                            all_symbols["functions"].extend(syms.get("functions", []))
                            all_symbols["variables"].extend(syms.get("variables", []))

                    for fname, content in new_files.items():
                        if fname.endswith(".py"):
                            import_warnings = validate_imports(content, all_symbols)
                            for w in import_warnings:
                                pipeline.append_log(f"[Verify] Import warning: {fname}: {w}")

                    last_error = None

                except Exception as e:
                    last_error = f"Developer error: {e}"
                    pipeline.append_log(f"[Developer] Error: {e}")
                    continue

                # TESTER
                pipeline.stage = PipelineRun.Stage.TESTING
                pipeline.save(update_fields=["stage"])
                pipeline.append_log("[Tester] Generating and running tests...")

                try:
                    _raise_if_pipeline_stopped(pipeline)
                    test_result = _run_tester(
                        task, project, all_tasks, project_files, project_dir, pipeline,
                        model_name=selected_model,
                    )
                    test_passed = test_result.get("passed", False)
                    pipeline.append_log(
                        f"[Tester] Tests {'PASSED' if test_passed else 'FAILED'}"
                    )

                    for fname, content in test_result.get("test_files", {}).items():
                        project_files[fname] = content
                        _write_file(project_dir, fname, content)

                except Exception as e:
                    pipeline.append_log(f"[Tester] Error: {e}")
                    test_result = {"passed": False, "test_output": str(e)}
                    test_passed = False

                # DEBUGGER (if tests failed)
                if not test_passed:
                    _raise_if_pipeline_stopped(pipeline)
                    pipeline.stage = PipelineRun.Stage.DEBUGGING
                    pipeline.save(update_fields=["stage"])
                    pipeline.append_log("[Debugger] Analyzing failures and fixing...")

                    try:
                        debug_result = _run_debugger(
                            task, project, project_files, project_dir,
                            test_result, pipeline, model_name=selected_model,
                        )
                        fixed = debug_result.get("fixed", False)
                        pipeline.append_log(f"[Debugger] Fix {'applied' if fixed else 'not applied'}")

                        for fname, content in debug_result.get("files", {}).items():
                            project_files[fname] = content
                            _write_file(project_dir, fname, content)

                        # Re-run tests after debug
                        if fixed:
                            pipeline.append_log("[Debugger] Re-running tests after fix...")
                            try:
                                rerun = _execute_pytest(project_dir)
                                pipeline.append_log(
                                    f"[Debugger] Re-run: {'PASSED' if rerun['passed'] else 'FAILED'}"
                                )
                                if rerun["passed"]:
                                    test_passed = True
                            except Exception:
                                pass

                    except Exception as e:
                        pipeline.append_log(f"[Debugger] Error: {e}")

                # REVIEWER
                _raise_if_pipeline_stopped(pipeline)
                pipeline.stage = PipelineRun.Stage.REVIEWING
                pipeline.save(update_fields=["stage"])
                pipeline.append_log("[Reviewer] Reviewing implementation...")
                review_approved = False

                try:
                    review = _run_reviewer(
                        task, project, project_files, project_dir, pipeline,
                        model_name=selected_model,
                    )
                    score = review.get("score", 0)
                    status = review.get("overall_status", "unknown")
                    review_approved = status == "approved"
                    pipeline.append_log(f"[Reviewer] Status: {status}, Score: {score}/10")

                    if review.get("findings"):
                        for f in review["findings"][:5]:
                            sev = f.get("severity", "?")
                            msg = f.get("message", "")
                            pipeline.append_log(f"  [{sev.upper()}] {msg}")

                except Exception as e:
                    pipeline.append_log(f"[Reviewer] Error: {e}")

                if test_passed and review_approved:
                    task_completed = True
                    break

                last_error = (
                    "Task acceptance failed: "
                    f"tests={'passed' if test_passed else 'failed'}, "
                    f"review={'approved' if review_approved else 'changes required'}"
                )
                pipeline.append_log(f"[Retry] {last_error}")

            if task_completed:
                task.status = "done"
                task.save(update_fields=["status"])
            else:
                pipeline.append_log(f"[Failed] Task '{task.title}' failed after {MAX_RETRIES + 1} attempts.")

            pipeline.completed_tasks = i + 1
            pipeline.save(update_fields=["completed_tasks"])
            if task_completed:
                pipeline.append_log(f"[Done] Task '{task.title}' completed.")
            else:
                pipeline.append_log(f"[Failed] Task '{task.title}' remains unfinished.")
            pipeline.flush_log()

        unfinished_tasks = Task.objects.filter(
            project=project,
            status__in=["todo", "in_progress"],
        ).count()

        # Generate project-level files
        pipeline.stage = (
            PipelineRun.Stage.FAILED
            if unfinished_tasks
            else PipelineRun.Stage.COMPLETED
        )
        pipeline.save(update_fields=["stage"])
        pipeline.append_log("\n[Finalizing] Generating project metadata...")

        try:
            _generate_project_readme(project, project_files, project_dir, selected_model)
        except Exception as e:
            pipeline.append_log(f"[Finalize] README generation failed: {e}")

        pipeline.append_log(f"\n{'='*60}")
        if unfinished_tasks:
            pipeline.append_log(
                f"PIPELINE FINISHED WITH {unfinished_tasks} UNFINISHED TASK(S)"
            )
        else:
            pipeline.append_log("PIPELINE COMPLETED SUCCESSFULLY")
        pipeline.append_log(f"Total files generated: {len(project_files)}")
        pipeline.append_log(f"{'='*60}")
        pipeline.flush_log()

    except PipelineStopped:
        if pipeline:
            pipeline.stage = PipelineRun.Stage.FAILED
            pipeline.error = "Pipeline stopped by user"
            pipeline.append_log("\n[Stopped] Pipeline stopped by user.")
            pipeline.save(update_fields=["stage", "error"])
    except Exception as e:
        tb = traceback.format_exc()
        try:
            if pipeline is None:
                pipeline = PipelineRun.objects.filter(project_id=project_id).first()
            if pipeline:
                pipeline.stage = PipelineRun.Stage.FAILED
                pipeline.error = str(e)
                pipeline.append_log(f"\nPIPELINE FAILED: {e}\n{tb}")
                pipeline.save(update_fields=["stage", "error"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Developer Agent
# ---------------------------------------------------------------------------

def _run_developer(task, project, all_tasks, existing_files, project_dir, pipeline,
                   previous_error=None, model_name=None):
    file_tree = build_file_tree(existing_files)
    total_files = len(existing_files)

    completed_tasks = [
        f"- {t.title}: {t.description}"
        for t in all_tasks if t.status == "done"
    ]
    pending_tasks = [
        f"- {t.title}: {t.description}"
        for t in all_tasks if t.status == "todo"
    ]

    files_section = ""
    if existing_files:
        files_section = "\nEXISTING PROJECT FILES:\n"
        for fname, content in existing_files.items():
            truncated = content[:MAX_FILE_CONTENT]
            if len(content) > MAX_FILE_CONTENT:
                truncated += f"\n... [truncated, {len(content)} total chars]"
            files_section += f"\n--- {fname} ({len(content)} chars) ---\n{truncated}\n"

    error_section = ""
    if previous_error:
        error_section = f"""
PREVIOUS ATTEMPT FAILED:
{previous_error}

You MUST fix this issue in your implementation. Pay special attention to:
- Valid Python syntax (no indentation errors, no undefined variables)
- Correct imports (only import what exists in the project files)
- Complete file content (not placeholders or "rest of code here")
"""

    prompt = f"""You are an expert senior software engineer generating production-quality code for a student project.

=== PROJECT ===
Name: {project.name}
Description: {project.description}

=== CURRENT TASK ===
Title: {task.title}
Description: {task.description}
Priority: {task.priority}

=== PROJECT STRUCTURE ({total_files} files) ===
{file_tree}

{files_section}

=== ALL PROJECT TASKS ===
Completed:
{chr(10).join(completed_tasks) if completed_tasks else "(none yet)"}

Current (THIS TASK): {task.title}

Remaining:
{chr(10).join(pending_tasks) if pending_tasks else "(none)"}

{error_section}

=== INSTRUCTIONS ===
Generate COMPLETE, WORKING implementation for the current task. You must:

1. **Create all necessary files** for this task - models, views, serializers, URLs, templates, components, config files, etc.
2. **Write COMPLETE code** - no placeholders, no "TODO", no "rest of code here", no "..." ellipsis
3. **Use correct imports** - only import from files that exist in the project
4. **Follow framework conventions** - Django models use Meta classes, Django views use proper patterns, React uses JSX, etc.
5. **Include all boilerplate** - __init__.py, manage.py, settings.py entries, requirements.txt, etc.
6. **Make files self-contained** - each file should be complete and functional

For each file, return the COMPLETE content as a string. Do not abbreviate or truncate.

Return ONLY valid JSON:
{{
    "files": {{
        "path/to/file.py": "COMPLETE FILE CONTENT HERE"
    }},
    "explanation": "Brief explanation of what was implemented"
}}

CRITICAL RULES:
- Every file path must be relative to the project root
- Every file MUST contain the COMPLETE implementation
- Python files MUST have valid syntax
- Include __init__.py for Python packages
- Do NOT include markdown or code blocks in the JSON values
- The JSON must be parseable by json.loads()

=== DJANGO-SPECIFIC RULES (follow strictly for any Django backend) ===
1. **Project layout**: Always use this exact layout:
   - backend/manage.py
   - backend/config/__init__.py
   - backend/config/settings.py  (ROOT_URLCONF = 'config.urls')
   - backend/config/urls.py
   - backend/config/wsgi.py
   - backend/apps/<appname>/__init__.py
   - backend/apps/<appname>/models.py
   - backend/apps/<appname>/views.py
   - backend/apps/<appname>/serializers.py
   - backend/apps/<appname>/urls.py
   - backend/apps/<appname>/apps.py
   - backend/apps/__init__.py
   - backend/requirements.txt
   - backend/pytest.ini

2. **INSTALLED_APPS**: Every Django app placed at backend/apps/<appname>/ MUST be listed as 'apps.<appname>' in INSTALLED_APPS. NEVER list a bare app name like 'calculator' or 'calculator_app' unless it has a matching top-level directory. Example:
   INSTALLED_APPS = [..., 'rest_framework', 'corsheaders', 'apps.calculator']

3. **AppConfig**: Each app's apps.py must set name = 'apps.<appname>' and the app's __init__.py must NOT set default_app_config unless needed.

4. **Database**: Use SQLite for development. The DATABASES setting should have a 'default' key with 'ENGINE' and 'NAME' keys. Use BASE_DIR from pathlib for the database path. Do not use f-strings for dictionary literals.

5. **SECRET_KEY**: Always read from environment: SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-key-change-in-prod')

6. **settings.py must include ALL required middleware** in this order:
   - corsheaders.middleware.CorsMiddleware (FIRST)
   - django.middleware.security.SecurityMiddleware
   - django.contrib.sessions.middleware.SessionMiddleware
   - django.middleware.common.CommonMiddleware
   - django.middleware.csrf.CsrfViewMiddleware
   - django.contrib.auth.middleware.AuthenticationMiddleware
   - django.contrib.messages.middleware.MessageMiddleware
   - django.middleware.clickjacking.XFrameOptionsMiddleware

7. **TEMPLATES**: Include the full TEMPLATES list with APP_DIRS=True and all context_processors.

8. **backend/pytest.ini**: Must contain:
   [pytest]
   DJANGO_SETTINGS_MODULE = config.settings
   pythonpath = backend

9. **tests/conftest.py**: Must set up Django before imports:
   import os, sys, django
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
   django.setup()

10. **React frontend**: Place at frontend/ with standard create-react-app or Vite structure. Never mix frontend files into backend/.

=== DJANGO VIEWS - CRITICAL RULES ===
For class-based views in Django:

1. **Simple class-based views** (recommended):
   from django.views import View
   from django.http import JsonResponse
   
   class HealthCheckView(View):
       def get(self, request, *args, **kwargs):
           return JsonResponse({{'status': 'healthy'}})

2. **URL configuration**:
   from django.urls import path
   from .views import HealthCheckView
   
   urlpatterns = [
       path('api/health/', HealthCheckView.as_view(), name='health-check'),
   ]

3. **DO NOT** wrap views with decorators that change the view_class
4. **DO NOT** create WrappedAPIView or similar wrapper classes
5. **DO NOT** use function wrappers unless you explicitly set `view_class` attribute
6. For function-based views, use `@require_http_methods` decorator from django.views.decorators.http
7. If using decorators, preserve the original view class by setting `view_class = YourView` on the function

=== IMPORTANT: Avoid f-string format specifier errors ===
When generating Python code, NEVER use f-strings with curly braces that contain dictionary literals or single-quoted content. This is a common syntax error:

  - DON'T: f"{{'key': 'value'}}"  - causes format specifier error
  - DON'T: f"{{'ENGINE': 'django.db.backends.sqlite3'}}" - causes format specifier error  
  - DON'T: f"{{some_dict}}" if some_dict contains single quotes
    - DO: Use regular strings: '{{"key": "value"}}' for JSON-like content
  - DO: Use proper Python dict syntax without f-strings: {{'key': 'value'}}
  - DO: If you must use f-strings, escape the braces: f"{{{{'key': 'value'}}}}"

For Django settings.py, NEVER wrap dictionary literals in f-strings. Write them directly:

  CORRECT:
    DATABASES = {{
        'default': {{
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }}
    }}

  INCORRECT (will cause syntax error):
    DATABASES = f"{{{{'default': {{{{'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}}}}}}}"

This is the #1 cause of syntax errors in generated code. Always write dictionary literals directly without f-string wrapping."""

    response = generate_response(prompt, model_name=model_name)
    result = _parse_json_response(response, "developer", model_name=model_name)

    if "error" in result:
        raise Exception(result["error"])

    return result


# ---------------------------------------------------------------------------
# Tester Agent
# ---------------------------------------------------------------------------

def _run_tester(task, project, all_tasks, project_files, project_dir, pipeline,
                model_name=None):
    source_files = {k: v for k, v in project_files.items() if not k.startswith("tests/")}
    test_files = {k: v for k, v in project_files.items() if k.startswith("tests/")}

    file_tree = build_file_tree(source_files)

    source_section = ""
    for fname, content in source_files.items():
        if fname.endswith(".py"):
            truncated = content[:MAX_FILE_CONTENT]
            source_section += f"\n--- {fname} ---\n{truncated}\n"
    source_section = source_section[:24000]

    prompt = f"""You are an expert QA engineer generating comprehensive test suites for a student project.

=== PROJECT ===
Name: {project.name}
Description: {project.description}

=== TASK BEING TESTED ===
Title: {task.title}
Description: {task.description}

=== SOURCE CODE ===
{source_section}

=== INSTRUCTIONS ===
Generate thorough pytest tests for the task above. Tests must:

1. **Test all functionality** described in the task
2. **Use correct imports** - import from the actual source files that exist
3. **Use pytest conventions** - test functions start with test_, use assertions
4. **Be runnable** - no syntax errors, correct module paths
5. **Cover edge cases** - test normal flow, error cases, boundary conditions
6. **Use fixtures** where appropriate for setup/teardown

IMPORTANT: You MUST import from the actual source modules. If a file is at tasks/models.py, import from tasks.models. Do NOT invent functions or classes that don't exist.

Return ONLY valid JSON:
{{
    "passed": true,
    "test_files": {{
        "tests/test_filename.py": "COMPLETE TEST FILE CONTENT"
    }},
    "test_summary": "Brief description of what was tested"
}}

CRITICAL RULES:
- Test files MUST be in the tests/ directory
- Imports MUST reference actual source files that exist
- Test function names MUST start with "test_"
- Include proper assertions (assert, pytest.raises, etc.)
- Do NOT use unittest style - use pytest style
- The JSON must be parseable by json.loads()

DJANGO TEST RULES (apply whenever the project uses Django):
1. Always generate tests/conftest.py if it does not already exist:
   import os, sys
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
   import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
   import django; django.setup()

2. Always generate backend/pytest.ini if it does not already exist:
   [pytest]
   DJANGO_SETTINGS_MODULE = config.settings
   pythonpath = backend

3. Django model tests MUST use @pytest.mark.django_db decorator.

4. For Django REST framework endpoint tests use rest_framework.test.APIClient.

5. Never import Django models at module level without calling django.setup() first.
   Always ensure conftest.py calls django.setup() before any model imports in test files.

6. Import apps as 'apps.<appname>.models' not '<appname>.models'.
   Example: from apps.calculator.models import Calculation
"""

    response = generate_response(prompt, model_name=model_name)
    result = _parse_json_response(response, "tester", model_name=model_name)

    if "error" in result:
        raise Exception(result["error"])

    # Write test files and run them
    test_files = result.get("test_files", {})
    if test_files and project_dir:
        for fname, content in test_files.items():
            _write_file(project_dir, fname, content)

        pytest_result = _execute_pytest(project_dir)
        result["passed"] = pytest_result["passed"]
        result["test_output"] = pytest_result["output"]

    return result


# ---------------------------------------------------------------------------
# Debugger Agent
# ---------------------------------------------------------------------------

def _run_debugger(task, project, project_files, project_dir, test_result, pipeline,
                  model_name=None):
    source_files = {k: v for k, v in project_files.items() if not k.startswith("tests/")}
    test_files = {k: v for k, v in project_files.items() if k.startswith("tests/")}

    source_section = ""
    for fname, content in source_files.items():
        if fname.endswith(".py"):
            truncated = content[:MAX_FILE_CONTENT]
            source_section += f"\n--- {fname} ---\n{truncated}\n"

    test_section = ""
    for fname, content in test_files.items():
        truncated = content[:MAX_FILE_CONTENT]
        test_section += f"\n--- {fname} ---\n{truncated}\n"

    test_output = test_result.get("test_output", "No output available")

    prompt = f"""You are an expert debugger fixing failing tests in a student project.

=== PROJECT ===
Name: {project.name}

=== TASK ===
Title: {task.title}
Description: {task.description}

=== SOURCE FILES ===
{source_section}

=== TEST FILES ===
{test_section}

=== TEST OUTPUT (FAILING) ===
{test_output}

=== INSTRUCTIONS ===
Analyze the test output and fix the source code to make tests pass.

Common issues to check:
1. Syntax errors in source or test files
2. Import errors (wrong module path, missing class/function)
3. Logic errors (wrong return value, wrong behavior)
4. Missing functionality (function not implemented)
5. Test import paths don't match source structure

Fix source, test, and project configuration files when the failure is in
those files. Do NOT rewrite everything from scratch.

DJANGO-SPECIFIC DIAGNOSIS (check these first for any Django error):

A. **RuntimeError: Model class ... doesn't declare an explicit app_label**
   Root cause: The app listed in INSTALLED_APPS does not match the actual app directory.
   Fix: Ensure INSTALLED_APPS contains 'apps.<appname>' (dotted path) and the app
   lives at backend/apps/<appname>/ with a valid AppConfig (name = 'apps.<appname>').

B. **ModuleNotFoundError on settings import / app not in INSTALLED_APPS**
   Fix: Verify backend/config/settings.py has INSTALLED_APPS = [..., 'apps.<appname>']
   and the directory backend/apps/<appname>/__init__.py exists.

C. **RuntimeError: populate() called before django.setup() / Model imported too early**
   Fix: tests/conftest.py must call django.setup() BEFORE any model imports.
   Correct conftest.py:
     import os, sys
     sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
     os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
     import django
     django.setup()

D. **DJANGO_SETTINGS_MODULE not set / ImportError on config.settings**
   Fix: Ensure backend/pytest.ini contains:
     [pytest]
     DJANGO_SETTINGS_MODULE = config.settings
     pythonpath = backend

E. **Import from wrong app path** (e.g., from calculator.models import X not found)
   Fix: Always import as from apps.<appname>.models import X

F. **Invalid format specifier error**
   Root cause: f-strings with curly braces inside single quotes like f"{{'key': 'value'}}" or f"{{'ENGINE': 'django.db.backends.sqlite3'}}"
   Fix: NEVER wrap dictionary literals in f-strings. Write dictionaries directly without f-string syntax. For Django settings, always use regular string quotes for dictionary keys and values, not f-strings.

Return ONLY valid JSON:
{{
    "fixed": true,
    "diagnosis": "What was wrong and how you fixed it",
    "files": {{
        "path/to/fixed_file.py": "COMPLETE FIXED FILE CONTENT"
    }},
}}

CRITICAL RULES:
- Return COMPLETE file content for each fixed file (not partial)
- Only fix files that actually have issues
- Ensure Python syntax is valid
- Ensure imports reference existing modules
- The JSON must be parseable by json.loads()
"""

    response = generate_response(prompt, model_name=model_name)
    result = _parse_json_response(response, "debugger", model_name=model_name)

    if "error" in result:
        raise Exception(result["error"])

    return result


# ---------------------------------------------------------------------------
# Reviewer Agent
# ---------------------------------------------------------------------------

def _run_reviewer(task, project, project_files, project_dir, pipeline,
                  model_name=None):
    source_files = {k: v for k, v in project_files.items() if not k.startswith("tests/")}

    file_tree = build_file_tree(project_files)

    source_section = ""
    for fname, content in source_files.items():
        truncated = content[:MAX_FILE_CONTENT]
        source_section += f"\n--- {fname} ({len(content)} chars) ---\n{truncated}\n"

    pytest_result = _execute_pytest(project_dir)
    test_output = pytest_result["output"]

    prompt = f"""You are a senior software engineer performing a code review for a student project.

=== PROJECT ===
Name: {project.name}
Description: {project.description}

=== PROJECT FILE TREE ===
{file_tree}

=== TASK REVIEWED ===
Title: {task.title}
Description: {task.description}

=== SOURCE CODE ===
{source_section}

=== TEST RESULTS ===
{"PASSED" if pytest_result["passed"] else "FAILED"}
{test_output[:3000]}

=== REVIEW CRITERIA ===
Evaluate the implementation on:
1. **Completeness** (0-2): Are all requirements from the task description met?
2. **Correctness** (0-2): Does the code work correctly? Are there bugs?
3. **Code Quality** (0-2): Is it readable, well-structured, following conventions?
4. **Error Handling** (0-2): Are errors handled gracefully?
5. **Best Practices** (0-2): Follows framework conventions, proper patterns?

Return ONLY valid JSON:
{{
    "overall_status": "approved|needs_changes",
    "score": <int 0-10>,
    "findings": [
        {{
            "severity": "critical|major|minor",
            "category": "security|performance|readability|correctness|completeness",
            "message": "<specific issue found>",
            "file": "<filename>",
            "suggestion": "<how to fix>"
        }}
    ],
    "strengths": ["<specific positive aspect>"],
    "test_assessment": "<evaluation of test quality>"
}}

Be specific and constructive. Do not include markdown or code blocks."""

    response = generate_response(prompt, model_name=model_name)
    result = _parse_json_response(response, "reviewer", model_name=model_name)

    if "error" in result:
        raise Exception(result["error"])

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(project_dir, relative_path, content):
    """Write a file to the project directory."""
    full_path = os.path.join(project_dir, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)


def _execute_pytest(project_dir):
    """Run pytest and return results."""
    try:
        env = os.environ.copy()
        python_paths = [project_dir]
        backend_dir = os.path.join(project_dir, "backend")
        if os.path.isdir(backend_dir):
            python_paths.insert(0, backend_dir)
        existing_python_path = env.get("PYTHONPATH")
        if existing_python_path:
            python_paths.append(existing_python_path)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        django_settings = _find_generated_settings_module(project_dir, backend_dir)
        if django_settings:
            django_settings = _create_test_settings_module(
                project_dir, backend_dir, django_settings
            )
            env["DJANGO_SETTINGS_MODULE"] = django_settings
        else:
            env.pop("DJANGO_SETTINGS_MODULE", None)

        # A generated full-stack project commonly keeps Python dependencies in
        # ``backend/requirements.txt``.  Installing only a root requirements
        # file leaves pytest unable to import Django apps (or DRF plugins) and
        # produces misleading settings/import errors.
        requirements_files = [os.path.join(project_dir, "requirements.txt")]
        if os.path.isdir(backend_dir):
            requirements_files.append(os.path.join(backend_dir, "requirements.txt"))

        for requirements in requirements_files:
            if not os.path.isfile(requirements):
                continue
            install = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", requirements, "-q"],
                cwd=os.path.dirname(requirements),
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if install.returncode != 0:
                return {"passed": False, "output": (install.stdout + "\n" + install.stderr).strip()}

        plugin_check = subprocess.run(
            [sys.executable, "-c", "import pytest_django"],
            capture_output=True,
            text=True,
            env=env,
        )
        if plugin_check.returncode != 0 and os.path.isdir(backend_dir):
            install_plugin = subprocess.run(
                [sys.executable, "-m", "pip", "install", "pytest-django", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if install_plugin.returncode != 0:
                return {"passed": False, "output": (install_plugin.stdout + "\n" + install_plugin.stderr).strip()}
        pytest_command = [sys.executable, "-m", "pytest", project_dir, "-x", "--tb=short", "-q"]
        if django_settings:
            # ``--ds`` takes precedence over a generated pytest.ini setting.
            # That keeps test execution isolated from a Docker/PostgreSQL
            # configuration which is not available to the pipeline worker.
            pytest_command[3:3] = [f"--ds={django_settings}"]
        root_pytest_config = os.path.join(project_dir, "pytest.ini")
        if os.path.isfile(root_pytest_config):
            pytest_command[3:3] = ["-c", root_pytest_config]
        proc = subprocess.run(
            pytest_command,
            capture_output=True, text=True, timeout=120,
            cwd=project_dir,
            env=env,
        )
        output = proc.stdout + "\n" + proc.stderr
        return {"passed": proc.returncode == 0, "output": output.strip()}
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Test execution timed out after 120 seconds"}
    except Exception as e:
        return {"passed": False, "output": f"Test execution error: {e}"}


def _find_generated_settings_module(project_dir, backend_dir):
    """Find generated Django settings without inheriting host Django settings."""
    config_files = [
        os.path.join(project_dir, "pytest.ini"),
        os.path.join(backend_dir, "pytest.ini"),
    ]
    for config_path in config_files:
        if not os.path.isfile(config_path):
            continue
        with open(config_path, "r", encoding="utf-8", errors="replace") as config_file:
            match = re.search(r"^\s*DJANGO_SETTINGS_MODULE\s*=\s*([^\s#]+)", config_file.read(), re.MULTILINE)
        if match:
            return match.group(1).strip()

    search_roots = [backend_dir, project_dir] if os.path.isdir(backend_dir) else [project_dir]
    for root in search_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {"node_modules", ".git", "__pycache__"}]
            if "settings.py" not in filenames:
                continue
            relative = os.path.relpath(os.path.join(dirpath, "settings.py"), root)
            parts = os.path.splitext(relative)[0].replace(os.sep, ".").split(".")
            if parts[-1] == "settings":
                return ".".join(parts)
    return None


def _create_test_settings_module(project_dir, backend_dir, django_settings):
    """Create SQLite-backed settings for generated Django project tests."""
    if not django_settings.endswith(".settings"):
        return django_settings

    package = django_settings.rsplit(".", 1)[0]
    relative_path = os.path.join(*package.split("."), "pipeline_test_settings.py")
    search_roots = [backend_dir, project_dir] if os.path.isdir(backend_dir) else [project_dir]

    for root in search_roots:
        settings_dir = os.path.dirname(os.path.join(root, relative_path))
        source_settings = os.path.join(settings_dir, "settings.py")
        if not os.path.isfile(source_settings):
            continue

        test_settings = os.path.join(settings_dir, "pipeline_test_settings.py")
        with open(test_settings, "w", encoding="utf-8") as settings_file:
            settings_file.write(
                "from .settings import *\n\n"
                "DATABASES = {\n"
                "    'default': {\n"
                "        'ENGINE': 'django.db.backends.sqlite3',\n"
                "        'NAME': ':memory:',\n"
                "    }\n"
                "}\n"
            )
        return f"{package}.pipeline_test_settings"

    return django_settings


def _generate_project_readme(project, project_files, project_dir, model_name=None):
    """Generate a README.md for the project."""
    file_tree = build_file_tree(project_files)

    file_list = "\n".join(f"- `{f}`" for f in sorted(project_files.keys()))

    prompt = f"""Generate a professional README.md for this student project.

Project: {project.name}
Description: {project.description}

Files in project:
{file_list}

Generate a README with these sections:
1. Project name and description
2. Features
3. Tech stack
4. Project structure
5. Installation instructions
6. Usage instructions
7. API endpoints (if applicable)

Return ONLY the markdown content of the README. No JSON wrapping."""

    try:
        response = generate_response(prompt, model_name=model_name)
        readme_content = response.strip()
        if readme_content.startswith("```"):
            lines = readme_content.splitlines()
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            readme_content = "\n".join(lines).strip()

        _write_file(project_dir, "README.md", readme_content)
    except Exception:
        pass


def _parse_json_response(response, agent_name, model_name=None):
    """Robustly parse JSON from LLM response."""
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from response
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Try to repair common JSON issues
            candidate = match.group()
            # Remove trailing commas before } or ]
            candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
            # Fix single quotes to double quotes
            candidate = candidate.replace("'", '"')
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Ask LLM to fix the JSON
    try:
        fix_prompt = f"""The following text was supposed to be valid JSON but has syntax errors.
Fix it and return ONLY the corrected valid JSON. No explanation, no markdown.

{text[:5000]}"""
        fixed_response = generate_response(fix_prompt, model_name=model_name).strip()
        if fixed_response.startswith("```"):
            lines = fixed_response.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fixed_response = "\n".join(lines).strip()
        return json.loads(fixed_response)
    except Exception:
        pass

    return {"error": f"Could not parse {agent_name} response", "raw": text[:500]}

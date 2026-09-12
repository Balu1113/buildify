import os
import sys
import ast
import json
import re
import time
import threading
import traceback
import subprocess
import shutil
import hashlib
from types import SimpleNamespace

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
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "nex-agi/nex-n2.5-pro:free")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    try:
        with open(ROOT_ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    OPENROUTER_API_KEY = line.split("=", 1)[1].strip('"').strip("'")
                    break
    except Exception:
        pass
LEGACY_MODEL_ALIASES = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-4-scout-17b-16e-instruct": "openai/gpt-oss-120b",
    "qwen/qwen3-32b": "openai/gpt-oss-120b",
    "moonshotai/kimi-k2-instruct": "openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "openai/gpt-oss-120b",
    "nvidia/nemotron-3-ultra": "nex-agi/nex-n2.5-pro:free",
    "nvidia/llama-3.1-nemotron-70b-instruct": "nex-agi/nex-n2.5-pro:free",
    "deepseek-ai/deepseek-v4-pro-0813": "nex-agi/nex-n2.5-pro:free",
    "deepseek/deepseek-chat-v3.1": "nex-agi/nex-n2.5-pro:free",
}

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


def _is_openrouter_model(model_name: str) -> bool:
    model_name = model_name.strip()
    if not model_name or model_name.startswith(("gemini-", "gemma-")):
        return False
    if model_name in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}:
        return False
    return "/" in model_name


def generate_response(prompt: str, model_name=None) -> str:
    """Generate response using the selected model provider."""
    try:
        model_name = model_name or OPENAI_MODEL_NAME
        model_name = LEGACY_MODEL_ALIASES.get(model_name, model_name)
        if model_name.startswith(("gemini-", "gemma-")):
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            return client.models.generate_content(model=model_name, contents=prompt).text
        if model_name in {
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        }:
            client = OpenAI(
                base_url=GROQ_BASE_URL,
                api_key=os.getenv("GROQ_API_KEY"),
                timeout=180.0,
                max_retries=2,
            )
        elif _is_openrouter_model(model_name):
            if not OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY is not set in the environment.")
            client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=OPENROUTER_API_KEY,
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
            stream=False,
        )
        return completion.choices[0].message.content
    except Exception as e:
        raise Exception(f"OpenAI API error: {e}")


from pipeline.models import PipelineRun
from tasks.models import Task
from projects.models import Project


# Stop after a small, bounded set of attempts so the user can switch models and retry.
MAX_RETRIES = 5
MAX_FILE_CONTENT = 8000
PROJECT_EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
HOST_DJANGO_PACKAGE = "student_project_manager"


QUALITY_GATE_ENV = "BUILDIFY_QUALITY_GATES"


def _task_acceptance_contract(task):
    """Build a structured, model-independent acceptance contract for every task."""
    description = (task.description or "").strip()
    project_name = getattr(getattr(task, "project", None), "name", None) or "generated_project"
    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", project_name.lower()).strip("_") or "generated_project"
    if safe_name[0].isdigit():
        safe_name = f"project_{safe_name}"
    generated_package = f"{safe_name}_backend"
    if generated_package.startswith(HOST_DJANGO_PACKAGE):
        generated_package = f"generated_{generated_package}"
    task_text = f"{task.title} {description}".lower()
    prohibited = [
        "Do not bypass, weaken, or remove tests to obtain a passing result.",
        "Do not commit real credentials, tokens, or private keys.",
    ]
    if any(keyword in task_text for keyword in ("frontend", "react", "javascript", "typescript", "browser")):
        prohibited.append("Do not use eval(), Function(), new Function(), or equivalent dynamic code execution.")
    if any(keyword in task_text for keyword in ("api", "backend", "deployment", "configuration")):
        prohibited.append("Do not hardcode deployment endpoints or disable authentication and authorization.")
    prohibited.append(f"Do not import or reference the Buildify host Django package: {HOST_DJANGO_PACKAGE}.")
    return {
        "version": 1,
        "task": {"id": getattr(task, "pk", None), "title": task.title, "description": description},
        "functional_requirements": [description] if description else [task.title],
        "non_functional_requirements": [
            "Preserve existing public behavior and project architecture.",
            "Use complete, maintainable implementation with appropriate error handling.",
        ],
        "security_requirements": [
            "Do not introduce arbitrary code execution, secret leakage, or unsafe input handling.",
            "Keep authentication, authorization, and user data scoped to the existing API contract.",
            "Generated projects must be independently runnable and must not import or reference the Buildify host application.",
        ],
        "required_files_components": [
            "All source files, components, configuration, and API changes necessary for the stated requirements.",
            f"For Django projects: use the deterministic independent package {generated_package} with manage.py, settings, URLs, WSGI/ASGI modules, apps, migrations, and dependencies.",
        ],
        "test_requirements": [
            "Test each stated functional requirement, important edge cases, and security-sensitive behavior.",
            "Tests must run against the actual generated project and existing APIs.",
        ],
        "reviewer_acceptance_criteria": [
            "All functional and contract requirements are implemented.",
            "Tests pass and no critical or major findings remain.",
            "Deterministic quality and security gates pass.",
            "Generated Django configuration resolves only within the generated project workspace.",
        ],
        "prohibited_approaches": prohibited,
    }


def _contract_text(contract):
    return json.dumps(contract, indent=2, ensure_ascii=True)


def _retry_context_text(retry_context):
    return json.dumps(retry_context or {}, indent=2, ensure_ascii=True)


def _quality_gate_config():
    configured = os.getenv(QUALITY_GATE_ENV, "all").strip().lower()
    if configured in {"", "all", "default"}:
        return {"dynamic_code", "secrets", "production_config", "hardcoded_urls"}
    return {item.strip() for item in configured.split(",") if item.strip()}


def _deterministic_quality_gates(files):
    """Run conservative, configurable source checks without rejecting ordinary words."""
    enabled = _quality_gate_config()
    violations = []
    for filepath, content in files.items():
        if not isinstance(content, str):
            continue
        normalized_path = filepath.replace("\\", "/")
        source_path = normalized_path.lower()
        filename = source_path.rsplit("/", 1)[-1]
        is_test = (
            source_path.startswith("tests/")
            or "/tests/" in source_path
            or "/__tests__/" in source_path
            or filename.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx"))
            or filename.endswith((".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"))
        )
        is_frontend = source_path.endswith((".js", ".jsx", ".ts", ".tsx"))
        is_code = source_path.endswith((".js", ".jsx", ".ts", ".tsx", ".py"))
        if "dynamic_code" in enabled and is_code and not is_test:
            patterns = [
                (r"(?<![\w$.])eval\s*\(", "dynamic eval"),
            ]
            if source_path.endswith(".py"):
                patterns.append((r"\bexec\s*\(", "dynamic exec"))
            if is_frontend:
                patterns.extend([
                    (r"\bnew\s+Function\s*\(", "dynamic Function constructor"),
                    (r"(?<![\w$.])Function\s*\(", "dynamic Function call"),
                ])
            for pattern, label in patterns:
                if re.search(pattern, content):
                    violations.append({
                        "severity": "critical",
                        "category": "security",
                        "file": filepath,
                        "issue": f"Detected {label} in executable frontend source.",
                        "why": "It permits arbitrary or uncontrolled code execution.",
                        "required_fix": "Replace it with explicit parsing or controlled allowlisted operations.",
                    })
        if "secrets" in enabled and not is_test:
            secret_pattern = re.compile(
                r"(?i)\b(?:secret|password|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
            )
            secret_matches = secret_pattern.finditer(content)
            real_secret = any(
                all(marker not in value.group(0).lower()
                    for marker in ("change-in-prod", "change_me", "placeholder", "your-", "example"))
                for value in secret_matches
            )
            if real_secret and "example" not in source_path:
                violations.append({
                    "severity": "critical",
                    "category": "security",
                    "file": filepath,
                    "issue": "A likely hardcoded secret or credential was detected.",
                    "why": "Credentials must not be committed to generated source.",
                    "required_fix": "Read the value from a deployment environment or secret manager.",
                })
        if "production_config" in enabled and source_path.endswith(("settings.py", ".env", ".env.production")):
            if re.search(r"(?m)^\s*DEBUG\s*=\s*True\b", content):
                violations.append({
                    "severity": "major",
                    "category": "configuration",
                    "file": filepath,
                    "issue": "DEBUG is enabled in a production-facing configuration.",
                    "why": "Debug output can disclose sensitive application details.",
                    "required_fix": "Read DEBUG from the environment with a secure production default.",
                })
            if re.search(r"(?m)^\s*CORS_ALLOW_ALL_ORIGINS\s*=\s*True\b", content):
                violations.append({
                    "severity": "major",
                    "category": "security",
                    "file": filepath,
                    "issue": "CORS allows every origin in configuration.",
                    "why": "Production APIs should restrict browser origins.",
                    "required_fix": "Configure an explicit environment-driven allowlist.",
                })
        if "hardcoded_urls" in enabled and is_frontend and not is_test:
            for url in re.findall(r"https?://[^\s'\"`]+", content):
                if not re.search(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/|$)", url):
                    violations.append({
                        "severity": "major",
                        "category": "configuration",
                        "file": filepath,
                        "issue": f"Hardcoded non-local API URL detected: {url}",
                        "why": "Deployment endpoints must be configurable.",
                        "required_fix": "Read the endpoint from the project's environment configuration.",
                    })
    return violations


def _blocking_findings(findings):
    return [
        finding for finding in (findings or [])
        if str(finding.get("severity", "")).lower() in {"critical", "major", "high"}
    ]


def _normalize_findings(findings):
    """Keep reviewer output compatible while enforcing the structured finding contract."""
    normalized = []
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        item["issue"] = item.get("issue") or item.get("message", "Unspecified reviewer finding")
        item["why"] = item.get("why") or "The reviewer did not explain the contract violation."
        item["required_fix"] = item.get("required_fix") or item.get("suggestion", "Address the finding.")
        normalized.append(item)
    return normalized


class PipelineStopped(Exception):
    """Raised when a user stops a running pipeline."""


def _raise_if_pipeline_stopped(pipeline):
    pipeline.refresh_from_db(fields=["stage"])
    if pipeline.stage == PipelineRun.Stage.FAILED:
        raise PipelineStopped()


def _load_project_files(project_dir):
    """Hydrate the agent context from the generated project on disk."""
    files = {}
    if not os.path.isdir(project_dir):
        return files
    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
        for filename in filenames:
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, project_dir).replace(os.sep, "/")
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    files[relative] = handle.read()
            except (UnicodeDecodeError, OSError):
                continue
    return files


def _project_python(project_dir):
    """Return the project-local Python, creating its environment on demand."""
    venv_dir = os.path.join(project_dir, ".venv")
    python_name = "Scripts\\python.exe" if os.name == "nt" else "bin/python"
    executable = os.path.join(venv_dir, python_name)
    if not os.path.exists(executable):
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True, timeout=180)
    return executable

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


def _is_package_initializer(filepath: str) -> bool:
    return filepath.replace("\\", "/").rsplit("/", 1)[-1] == "__init__.py"


def verify_file_content(filepath: str, content: str) -> dict:
    """Verify a generated file. Returns dict with valid, errors, warnings."""
    result = {"valid": True, "errors": [], "warnings": []}

    if not content.strip() and not _is_package_initializer(filepath):
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


def _validated_file_map(files, label):
    """Reject malformed agent file maps before they enter project state."""
    if files is None:
        raise ValueError(f"{label} returned no file map")
    if not isinstance(files, dict):
        raise ValueError(f"{label} returned {type(files).__name__}, expected an object")
    invalid = [path for path, content in files.items() if not isinstance(path, str) or not isinstance(content, str)]
    if invalid:
        raise ValueError(f"{label} returned non-string content for: {', '.join(map(str, invalid[:5]))}")
    return files


def _project_preflight(project_files):
    """Find cheap, deterministic file failures before invoking an agent."""
    failures = []
    for filepath, content in project_files.items():
        if not isinstance(content, str):
            failures.append(f"{filepath}: content is not text")
            continue
        if filepath.endswith(".py"):
            valid, error = validate_python_syntax(content)
            if not valid:
                failures.append(f"{filepath}: {error}")
        elif filepath.endswith(".json"):
            try:
                json.loads(content)
            except json.JSONDecodeError as error:
                failures.append(f"{filepath}: invalid JSON at line {error.lineno}: {error.msg}")
    return failures


def _repair_workspace(task, project, project_files, project_dir, pipeline, diagnostics, model_name,
                      acceptance_contract=None, retry_context=None):
    """Ask the Debugger to repair pipeline diagnostics and validate its patch."""
    repair_result = _run_debugger(
        task,
        project,
        project_files,
        project_dir,
        {"passed": False, "test_output": "Pipeline diagnostics:\n" + "\n".join(diagnostics)},
        pipeline,
        acceptance_contract=acceptance_contract or _task_acceptance_contract(task),
        retry_context=retry_context or {
            "attempt": 0,
            "test_failures": diagnostics,
            "unresolved_issues": diagnostics,
        },
        model_name=model_name,
    )
    if not repair_result.get("fixed", False):
        return False
    repair_files = _validated_file_map(repair_result.get("files", {}), "Debugger")
    for filepath, content in repair_files.items():
        verification = verify_file_content(filepath, content)
        if not verification["valid"]:
            raise ValueError(f"Debugger produced invalid {filepath}: {verification['errors']}")
        project_files[filepath] = content
        _write_file(project_dir, filepath, content)
    return True


def run_pipeline(project_id, pipeline_id=None):
    thread = threading.Thread(
        target=_run_pipeline_worker,
        args=(project_id, pipeline_id),
        daemon=True,
    )
    thread.start()


def _run_pipeline_worker(project_id, pipeline_id=None):
    pipeline = None
    try:
        project = Project.objects.get(id=project_id)
        all_tasks = list(Task.objects.filter(project=project).order_by("id"))
        selected_model = Project.LEGACY_MODEL_ALIASES.get(
            project.ai_model, project.ai_model
        ) or OPENAI_MODEL_NAME

        if pipeline_id:
            pipeline = PipelineRun.objects.get(id=pipeline_id, project=project)
            if pipeline.finalization_state == PipelineRun.FinalizationState.ACCEPTED:
                pipeline.append_log("[Finalization] Project already accepted; no work rerun")
                return
            pipeline.error = ""
            pipeline.save(update_fields=["error"])
        else:
            pipeline = PipelineRun.objects.create(
                project=project,
                stage=PipelineRun.Stage.PLANNING,
                total_tasks=0,
                completed_tasks=0,
            )

        pipeline.append_log(f"Pipeline started for project: {project.name}")
        pipeline.append_log(f"Description: {project.description}")
        project_dir = os.path.join(PROJECT_ROOT, "generated_projects", f"project_{project.id}")

        # Planning belongs to the pipeline so the UI can show it and task creation
        # happens before the development stages begin.
        if not all_tasks:
            if os.path.isdir(project_dir):
                shutil.rmtree(project_dir, ignore_errors=True)
                pipeline.append_log("[Workspace] Removed stale output before fresh planning")
            pipeline.append_log("[Planner] Creating an ordered implementation plan...")
            from ai_services.gemini_ai import plan_project

            plan = plan_project(
                f"{project.name}: {project.description or ''}",
                model_name=selected_model,
            )
            if not plan or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
                planner_error = plan.get("error", "empty or invalid task plan") if plan else "empty planner response"
                raise RuntimeError(
                    f"Planner failed using selected model '{selected_model}': {planner_error}"
                )

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

        pipeline.append_log(f"[Agents] Using selected model only: {selected_model}")

        tasks = [task for task in all_tasks if task.status != "done"]
        pipeline.total_tasks = len(all_tasks)
        pipeline.completed_tasks = sum(1 for task in all_tasks if task.status == "done")
        pipeline.save(update_fields=["total_tasks", "completed_tasks"])
        pipeline.append_log(f"Total tasks to process: {len(tasks)}")

        os.makedirs(project_dir, exist_ok=True)

        project_files = _load_project_files(project_dir)
        pipeline.append_log(
            f"[Workspace] Hydrated {len(project_files)} existing files from generated project"
        )

        for i, task in enumerate(tasks):
            _raise_if_pipeline_stopped(pipeline)
            diagnostics = _project_preflight(project_files)
            if diagnostics:
                pipeline.stage = PipelineRun.Stage.DEBUGGING
                pipeline.save(update_fields=["stage"])
                pipeline.append_log(
                    f"[Preflight] Found {len(diagnostics)} existing file failure(s) before task '{task.title}'"
                )
                for diagnostic in diagnostics[:10]:
                    pipeline.append_log(f"[Preflight] {diagnostic}")
                try:
                    repaired = _repair_workspace(
                        task, project, project_files, project_dir, pipeline,
                        diagnostics, selected_model,
                    )
                    remaining = _project_preflight(project_files)
                    if repaired and not remaining:
                        pipeline.append_log("[Preflight] Debugger repaired all detected file failures")
                    elif remaining:
                        pipeline.append_log(
                            f"[Preflight] {len(remaining)} failure(s) remain after repair"
                        )
                        pipeline.append_log("[Preflight] Blocking task processing until the workspace is repaired")
                        task.status = "todo"
                        task.save(update_fields=["status"])
                        break
                except Exception as error:
                    pipeline.append_log(f"[Preflight] Repair error: {error}")
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
            acceptance_contract = _task_acceptance_contract(task)
            retry_context = {
                "original_task": acceptance_contract["task"],
                "acceptance_contract": acceptance_contract,
                "attempt": 0,
                "implementation_files": {},
                "test_files": {},
                "debugger_files": {},
                "files_changed": [],
                "test_failures": [],
                "debugger_analysis": [],
                "reviewer_findings": [],
                "unresolved_issues": [],
            }
            pipeline.append_log(
                f"[Acceptance] Functional: {len(acceptance_contract['functional_requirements'])}; "
                f"security: {len(acceptance_contract['security_requirements'])}; "
                f"tests: {len(acceptance_contract['test_requirements'])}"
            )

            for attempt in range(MAX_RETRIES + 1):
                _raise_if_pipeline_stopped(pipeline)
                retry_context["attempt"] = attempt
                pipeline.append_log(
                    f"[AI] Using model: {selected_model} | task {i + 1}/{len(tasks)} | "
                    f"attempt {attempt + 1}/{MAX_RETRIES + 1}"
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
                        acceptance_contract=acceptance_contract,
                        retry_context=retry_context,
                        attempt=attempt,
                        model_name=selected_model,
                    )
                    _raise_if_pipeline_stopped(pipeline)
                    new_files = _validated_file_map(dev_result.get("files"), "Developer")
                    pipeline.append_log(f"[Developer] Generated {len(new_files)} files")

                    candidate_files = dict(project_files)
                    candidate_files.update(new_files)
                    retry_context["implementation_files"] = dict(new_files)
                    retry_context["files_changed"] = sorted(new_files)
                    quality_violations = _deterministic_quality_gates(candidate_files)
                    if quality_violations:
                        last_error = (
                            "Deterministic quality gates failed: "
                            + "; ".join(item["issue"] for item in quality_violations)
                        )
                        retry_context["unresolved_issues"] = quality_violations
                        pipeline.append_log(f"[Developer] {last_error}")
                        pipeline.append_log(f"[Quality] {len(quality_violations)} blocking violation(s)")
                        continue

                    # Verify and write files
                    verification_errors = []
                    for fname, content in new_files.items():
                        if (
                            not content or not content.strip()
                        ) and not _is_package_initializer(fname):
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

                    retry_context["implementation_files"] = {
                        fname: project_files[fname] for fname in new_files
                    }
                    retry_context["files_changed"] = sorted(new_files)

                    if verification_errors:
                        last_error = "Verification errors: " + "; ".join(verification_errors)
                        pipeline.append_log(f"[Developer] {last_error}")
                        pipeline.stage = PipelineRun.Stage.DEBUGGING
                        pipeline.save(update_fields=["stage"])
                        pipeline.append_log("[Debugger] Repairing developer validation failures...")
                        try:
                            _repair_workspace(
                                task, project, project_files, project_dir, pipeline,
                                verification_errors, selected_model,
                            )
                        except Exception as repair_error:
                            pipeline.append_log(f"[Debugger] Repair error: {repair_error}")
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
                    retry_context["unresolved_issues"] = [{
                        "severity": "major",
                        "category": "implementation",
                        "issue": last_error,
                        "why": "The Developer stage did not produce a valid implementation.",
                        "required_fix": "Resolve the reported developer error and return complete files.",
                    }]
                    pipeline.append_log(f"[Developer] Error: {e}")
                    pipeline.stage = PipelineRun.Stage.DEBUGGING
                    pipeline.save(update_fields=["stage"])
                    pipeline.append_log("[Debugger] Repairing developer exception...")
                    try:
                        _repair_workspace(
                            task, project, project_files, project_dir, pipeline,
                            [last_error], selected_model,
                        )
                    except Exception as repair_error:
                        pipeline.append_log(f"[Debugger] Repair error: {repair_error}")
                    continue

                # TESTER
                pipeline.stage = PipelineRun.Stage.TESTING
                pipeline.save(update_fields=["stage"])
                pipeline.append_log("[Tester] Generating and running tests...")

                try:
                    _raise_if_pipeline_stopped(pipeline)
                    test_result = _run_tester(
                        task, project, all_tasks, project_files, project_dir, pipeline,
                        acceptance_contract=acceptance_contract,
                        retry_context=retry_context,
                        attempt=attempt,
                        model_name=selected_model,
                    )
                    test_passed = test_result.get("passed", False)
                    pipeline.append_log(
                        f"[Tester] Tests {'PASSED' if test_passed else 'FAILED'}"
                    )
                    retry_context["test_failures"] = [] if test_passed else [
                        test_result.get("test_output", "No test output available")
                    ]

                    test_files = _validated_file_map(test_result.get("test_files", {}), "Tester")
                    retry_context["test_files"] = dict(test_files)
                    retry_context["files_changed"] = sorted(
                        set(retry_context["files_changed"]) | set(test_files)
                    )
                    for fname, content in test_files.items():
                        project_files[fname] = content
                        _write_file(project_dir, fname, content)

                except Exception as e:
                    pipeline.append_log(f"[Tester] Error: {e}")
                    test_result = {"passed": False, "test_output": str(e)}
                    test_passed = False
                    retry_context["test_failures"] = [str(e)]
                    retry_context["unresolved_issues"] = [{
                        "severity": "major",
                        "category": "testing",
                        "issue": str(e),
                        "why": "The test stage did not complete successfully.",
                        "required_fix": "Repair the test or implementation failure and rerun the suite.",
                    }]
                    pipeline.stage = PipelineRun.Stage.DEBUGGING
                    pipeline.save(update_fields=["stage"])
                    pipeline.append_log("[Debugger] Repairing tester failure...")
                    try:
                        _repair_workspace(
                            task, project, project_files, project_dir, pipeline,
                            [f"Tester error: {e}"], selected_model,
                        )
                    except Exception as repair_error:
                        pipeline.append_log(f"[Debugger] Repair error: {repair_error}")

                # DEBUGGER (if tests failed)
                if not test_passed:
                    _raise_if_pipeline_stopped(pipeline)
                    pipeline.stage = PipelineRun.Stage.DEBUGGING
                    pipeline.save(update_fields=["stage"])
                    pipeline.append_log("[Debugger] Analyzing failures and fixing...")

                    try:
                        debug_result = _run_debugger(
                            task, project, project_files, project_dir,
                            test_result, pipeline,
                            acceptance_contract=acceptance_contract,
                            retry_context=retry_context,
                            attempt=attempt,
                            model_name=selected_model,
                        )
                        fixed = debug_result.get("fixed", False)
                        retry_context["debugger_analysis"] = [
                            debug_result.get("diagnosis", "No debugger diagnosis returned")
                        ]
                        pipeline.append_log(f"[Debugger] Fix {'applied' if fixed else 'not applied'}")

                        debug_files = _validated_file_map(debug_result.get("files", {}), "Debugger")
                        retry_context["debugger_files"] = dict(debug_files)
                        retry_context["files_changed"] = sorted(
                            set(retry_context["files_changed"]) | set(debug_files)
                        )
                        for fname, content in debug_files.items():
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
                        acceptance_contract=acceptance_contract,
                        retry_context=retry_context,
                        attempt=attempt,
                        model_name=selected_model,
                    )
                    score = review.get("score", 0)
                    status = review.get("overall_status", "unknown")
                    reviewer_findings = _normalize_findings(review.get("findings", []))
                    review["findings"] = reviewer_findings
                    retry_context["reviewer_findings"] = reviewer_findings
                    quality_violations = _deterministic_quality_gates(project_files)
                    blocking_findings = _blocking_findings(reviewer_findings)
                    review_approved = (
                        status == "approved"
                        and not blocking_findings
                        and not quality_violations
                    )
                    retry_context["unresolved_issues"] = blocking_findings + quality_violations
                    pipeline.append_log(f"[Reviewer] Status: {status}, Score: {score}/10")
                    pipeline.append_log(
                        f"[Quality] {'PASSED' if not quality_violations else 'FAILED'}; "
                        f"unresolved findings: {len(blocking_findings)}"
                    )

                    if review.get("findings"):
                        for f in review["findings"][:5]:
                            sev = f.get("severity", "?")
                            msg = f.get("issue", f.get("message", ""))
                            pipeline.append_log(f"  [{sev.upper()}] {msg}")

                except Exception as e:
                    pipeline.append_log(f"[Reviewer] Error: {e}")
                    pipeline.stage = PipelineRun.Stage.DEBUGGING
                    pipeline.save(update_fields=["stage"])
                    pipeline.append_log("[Debugger] Repairing reviewer/configuration failure...")
                    try:
                        _repair_workspace(
                            task, project, project_files, project_dir, pipeline,
                            [f"Reviewer error: {e}"], selected_model,
                        )
                    except Exception as repair_error:
                        pipeline.append_log(f"[Debugger] Repair error: {repair_error}")

                if test_passed and review_approved:
                    task_completed = True
                    break

                last_error = (
                    "Task acceptance failed: "
                    f"tests={'passed' if test_passed else 'failed'}, "
                    f"review={'approved' if review_approved else 'changes required'}, "
                    f"unresolved issues={len(retry_context['unresolved_issues'])}"
                )
                retry_context["unresolved_issues"] = retry_context["unresolved_issues"] or [
                    {"issue": last_error, "severity": "major"}
                ]
                pipeline.append_log(f"[Retry] {last_error}")

            if task_completed:
                task.status = "done"
                task.save(update_fields=["status"])
            else:
                pipeline.stage = PipelineRun.Stage.FAILED
                pipeline.error = (
                    f"Task '{task.title}' failed after {MAX_RETRIES + 1} attempts with model '{selected_model}'. "
                    "Please select another model and retry."
                )
                pipeline.save(update_fields=["stage", "error"])
                pipeline.append_log(f"[Failed] Task '{task.title}' failed after {MAX_RETRIES + 1} attempts.")
                pipeline.append_log(
                    "[FailureContext] " + _retry_context_text(retry_context)
                )
                pipeline.append_log(f"[Stopped] {pipeline.error}")
                raise PipelineStopped()

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

        if unfinished_tasks:
            pipeline.finalization_state = PipelineRun.FinalizationState.PENDING
            pipeline.stage = PipelineRun.Stage.FAILED
            pipeline.error = "Tasks remain unfinished; finalization is pending"
            pipeline.save(update_fields=["stage", "error", "finalization_state"])
            pipeline.append_log("[Finalization] Deferred until all tasks are complete")
            return

        pipeline.append_log("\n[Finalizing] Running complete project acceptance...")
        accepted = _run_finalization(
            pipeline, project, all_tasks, project_files, project_dir, selected_model
        )
        if accepted:
            pipeline.append_log("[Finalizing] Generating project metadata...")
            try:
                _generate_project_readme(project, project_files, project_dir, selected_model)
            except Exception as error:
                pipeline.append_log(f"[Finalize] README generation failed: {error}")
            pipeline.stage = PipelineRun.Stage.COMPLETED
            pipeline.error = ""
            pipeline.save(update_fields=["stage", "error"])
        else:
            pipeline.stage = PipelineRun.Stage.FAILED
            pipeline.error = pipeline.error or "Generated project failed final acceptance"
            pipeline.save(update_fields=["stage", "error"])

        pipeline.append_log(f"\n{'='*60}")
        if unfinished_tasks or not accepted:
            pipeline.append_log(
                "PIPELINE FINISHED WITHOUT ACCEPTANCE"
            )
        else:
            pipeline.append_log("PIPELINE COMPLETED SUCCESSFULLY")
        pipeline.append_log(f"Total files generated: {len(project_files)}")
        pipeline.append_log(f"{'='*60}")
        pipeline.flush_log()

    except PipelineStopped:
        if pipeline:
            pipeline.stage = PipelineRun.Stage.FAILED
            pipeline.error = pipeline.error or "Pipeline stopped by user"
            pipeline.append_log(f"\n[Stopped] {pipeline.error}")
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
                   previous_error=None, acceptance_contract=None, retry_context=None,
                   attempt=0, model_name=None):
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

    if acceptance_contract is None:
        acceptance_contract = _task_acceptance_contract(task)
    if retry_context is None:
        retry_context = {"attempt": attempt}

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

=== ACCEPTANCE CONTRACT ===
{_contract_text(acceptance_contract)}

=== RETRY CONTEXT ===
{_retry_context_text(retry_context)}

=== INSTRUCTIONS ===
Generate COMPLETE, WORKING implementation for the current task. For retry
attempt {attempt + 1}, modify the current implementation and explicitly resolve
EVERY unresolved issue, test failure, and reviewer finding in RETRY CONTEXT.
Do not blindly regenerate the task from scratch. You must:

DJANGO PROJECT ISOLATION:
- If Django is required, derive a unique lowercase Python package name from the
    project name (for example, <safe_project_name>_backend), and use it consistently
    in manage.py, settings.py, urls.py, wsgi.py, and asgi.py.
- Never use or import the Buildify host package {HOST_DJANGO_PACKAGE}, its settings,
    URLs, apps, database, environment, or project name.
- The generated project must run independently from its own root with its own
    requirements.txt and database configuration.

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
1. **Project layout**: Use this layout with a unique generated package name,
    never a host-application package:
   - backend/manage.py
    - backend/<generated_package>/__init__.py
    - backend/<generated_package>/settings.py
    - backend/<generated_package>/urls.py
    - backend/<generated_package>/wsgi.py
    - backend/<generated_package>/asgi.py
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

    The default SQLite NAME must be BASE_DIR / 'db.sqlite3'. Do not read
    DATABASE_NAME or replace this path with ':memory:'. The pipeline runs
    pytest against the project's real settings, so tests must not assume a
    separate pipeline settings module or a different database path.

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
    DJANGO_SETTINGS_MODULE = <generated_package>.settings
   pythonpath = backend

9. **tests/conftest.py**: Must set up Django before imports:
   import os, sys, django
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', '<generated_package>.settings')
   django.setup()

10. **React frontend**: Place at frontend/ with standard create-react-app or Vite structure. Never mix frontend files into backend/.

11. **Mobile compatibility**: Frontend pages must be responsive from 320px
    through desktop widths. Use flexible layouts, readable touch-sized controls,
    responsive tables or cards, and viewport-safe typography. Do not require
    horizontal scrolling for the primary workflow.

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
                acceptance_contract=None, retry_context=None, attempt=0,
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

    acceptance_contract = acceptance_contract or _task_acceptance_contract(task)
    retry_context = retry_context or {"attempt": attempt}

    prompt = f"""You are an expert QA engineer generating comprehensive test suites for a student project.

=== PROJECT ===
Name: {project.name}
Description: {project.description}

=== TASK BEING TESTED ===
Title: {task.title}
Description: {task.description}

=== ACCEPTANCE CONTRACT ===
{_contract_text(acceptance_contract)}

=== RETRY CONTEXT ===
{_retry_context_text(retry_context)}

=== SOURCE CODE ===
{source_section}

=== INSTRUCTIONS ===
Generate thorough pytest tests for the task above. Tests must:

1. **Test all functionality** described in the task and every acceptance-contract requirement
2. **Use correct imports** - import from the actual source files that exist
3. **Use pytest conventions** - test functions start with test_, use assertions
4. **Be runnable** - no syntax errors, correct module paths
5. **Cover edge cases** - test normal flow, error cases, boundary conditions
6. **Use fixtures** where appropriate for setup/teardown
7. **Test security and edge cases**, including invalid input, authorization boundaries,
   configuration errors, and prohibited approaches identified by the contract

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
    import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', '<generated_package>.settings')
   import django; django.setup()

2. Always generate backend/pytest.ini if it does not already exist:
   [pytest]
    DJANGO_SETTINGS_MODULE = <generated_package>.settings
   pythonpath = backend

3. Django model tests MUST use @pytest.mark.django_db decorator.

4. For Django REST framework endpoint tests use rest_framework.test.APIClient.

5. Never import Django models at module level without calling django.setup() first.
   Always ensure conftest.py calls django.setup() before any model imports in test files.

6. Import apps as 'apps.<appname>.models' not '<appname>.models'.
   Example: from apps.calculator.models import Calculation

7. Tests must load the project's normal settings module and must not set
    DATABASE_NAME=:memory: or create a competing settings override. The
    configured development database remains BASE_DIR / 'db.sqlite3'; Django's
    test database handling provides test isolation.
"""

    generation_started = time.monotonic()
    response = generate_response(prompt, model_name=model_name)
    pipeline.append_log(
        f"[Tester] Model generation duration: {time.monotonic() - generation_started:.1f}s"
    )
    result = _parse_json_response(response, "tester", model_name=model_name)

    if "error" in result:
        raise Exception(result["error"])

    # Write test files and run them
    test_files = _validated_file_map(result.get("test_files", {}), "Tester")
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
                  acceptance_contract=None, retry_context=None, attempt=0,
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

    acceptance_contract = acceptance_contract or _task_acceptance_contract(task)
    retry_context = retry_context or {"attempt": attempt}
    test_output = test_result.get("test_output", "No output available")

    prompt = f"""You are an expert debugger fixing failing tests in a student project.

=== PROJECT ===
Name: {project.name}

=== TASK ===
Title: {task.title}
Description: {task.description}

=== ACCEPTANCE CONTRACT ===
{_contract_text(acceptance_contract)}

=== RETRY CONTEXT ===
{_retry_context_text(retry_context)}

=== SOURCE FILES ===
{source_section}

=== TEST FILES ===
{test_section}

=== TEST OUTPUT, STACK TRACE, AND FAILURES ===
{test_output}

=== INSTRUCTIONS ===
Analyze the failing tests, stack traces, reviewer findings, and acceptance contract.
Fix the actual source, test, or project configuration
failure. This may be a preflight scan before tests run. Inspect the complete file
tree and repair malformed, missing, inconsistent, or incompatible files instead
of only suppressing the reported error. Return complete replacement file contents.
Make targeted changes and resolve every applicable item in RETRY CONTEXT; do not
rewrite unrelated parts of the project.

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
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', '<generated_package>.settings')
     import django
     django.setup()

D. **DJANGO_SETTINGS_MODULE not set / ImportError on generated settings**
   Fix: Ensure backend/pytest.ini contains:
     [pytest]
    DJANGO_SETTINGS_MODULE = <generated_package>.settings
     pythonpath = backend

E. **Database path differs between settings and tests**
    Fix: Use the project's normal settings module. The default SQLite database
    must remain BASE_DIR / 'db.sqlite3'; do not add DATABASE_NAME=:memory: or
    create pipeline-specific settings to hide a configuration mismatch.

F. **Import from wrong app path** (e.g., from calculator.models import X not found)
   Fix: Always import as from apps.<appname>.models import X

G. **Invalid format specifier error**
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
                  acceptance_contract=None, retry_context=None, attempt=0,
                  model_name=None):
    source_files = {k: v for k, v in project_files.items() if not k.startswith("tests/")}

    file_tree = build_file_tree(project_files)

    source_section = ""
    for fname, content in source_files.items():
        truncated = content[:MAX_FILE_CONTENT]
        source_section += f"\n--- {fname} ({len(content)} chars) ---\n{truncated}\n"

    pytest_result = _execute_pytest(project_dir)
    test_output = pytest_result["output"]

    acceptance_contract = acceptance_contract or _task_acceptance_contract(task)
    retry_context = retry_context or {"attempt": attempt}

    prompt = f"""You are a senior software engineer performing a code review for a student project.

=== PROJECT ===
Name: {project.name}
Description: {project.description}

=== PROJECT FILE TREE ===
{file_tree}

=== TASK REVIEWED ===
Title: {task.title}
Description: {task.description}

=== ACCEPTANCE CONTRACT ===
{_contract_text(acceptance_contract)}

=== RETRY CONTEXT ===
{_retry_context_text(retry_context)}

=== SOURCE CODE ===
{source_section}

=== TEST RESULTS ===
{"PASSED" if pytest_result["passed"] else "FAILED"}
{test_output[:3000]}

=== REVIEW CRITERIA ===
Evaluate the implementation against the acceptance contract and task on:
1. **Completeness** (0-2): Are all requirements from the task description met?
2. **Correctness** (0-2): Does the code work correctly? Are there bugs?
3. **Code Quality** (0-2): Is it readable, well-structured, following conventions?
4. **Error Handling** (0-2): Are errors handled gracefully?
5. **Best Practices** (0-2): Follows framework conventions, proper patterns?
6. **Configuration and mobile compatibility**: Confirm Django uses the
    project's configured BASE_DIR / 'db.sqlite3' default without a hidden
    DATABASE_NAME=:memory: override, and confirm frontend workflows remain
    usable at mobile widths with responsive layouts and touch-sized controls.
7. Every finding must explain why it violates the acceptance contract and state
    the required fix. A critical or major contract violation requires
    "overall_status": "changes_required".

Return ONLY valid JSON:
{{
    "overall_status": "approved|needs_changes",
    "score": <int 0-10>,
    "findings": [
        {{
            "severity": "critical|major|minor",
            "category": "security|performance|readability|correctness|completeness|configuration|testing|architecture",
            "file": "<filename>",
            "issue": "<specific issue found>",
            "why": "<why this violates the acceptance contract>",
            "required_fix": "<required fix>",
            "message": "<specific issue found>",
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
        started_at = time.monotonic()
        project_python = _project_python(project_dir)
        python_paths = [project_dir]
        backend_dir = os.path.join(project_dir, "backend")
        if os.path.isdir(backend_dir):
            python_paths.insert(0, backend_dir)
        env = _generated_environment(project_dir, python_paths)
        django_descriptor = _discover_generated_django(project_dir)
        django_settings = django_descriptor.get("settings_module")
        if django_settings:
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

        install_time = 0.0
        for requirements in requirements_files:
            if not os.path.isfile(requirements):
                continue
            with open(requirements, "rb") as requirements_file:
                requirements_hash = hashlib.sha256(requirements_file.read()).hexdigest()
            marker = os.path.join(project_dir, ".pipeline", "requirements", f"{hashlib.sha256(requirements.encode()).hexdigest()}.sha256")
            cached_hash = None
            if os.path.isfile(marker):
                with open(marker, "r", encoding="ascii") as marker_file:
                    cached_hash = marker_file.read().strip()
            if cached_hash != requirements_hash:
                install_started = time.monotonic()
                install = subprocess.run(
                    [project_python, "-m", "pip", "install", "-r", requirements, "-q"],
                    cwd=os.path.dirname(requirements),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env,
                )
                if install.returncode != 0:
                    return {"passed": False, "output": (install.stdout + "\n" + install.stderr).strip()}
                os.makedirs(os.path.dirname(marker), exist_ok=True)
                with open(marker, "w", encoding="ascii") as marker_file:
                    marker_file.write(requirements_hash)
                install_time = time.monotonic() - install_started
            else:
                install_time = 0.0

        plugin_check = subprocess.run(
            [project_python, "-c", "import pytest_django"],
            capture_output=True,
            text=True,
            env=env,
        )
        if plugin_check.returncode != 0 and os.path.isdir(backend_dir):
            install_plugin = subprocess.run(
                [project_python, "-m", "pip", "install", "pytest-django", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if install_plugin.returncode != 0:
                return {"passed": False, "output": (install_plugin.stdout + "\n" + install_plugin.stderr).strip()}
        pytest_command = [project_python, "-m", "pytest", project_dir, "-x", "--tb=short", "-q"]
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
        duration = time.monotonic() - started_at
        return {
            "passed": proc.returncode == 0,
            "output": f"[pipeline] pytest duration: {duration:.1f}s; dependency install: {install_time:.1f}s\n{output.strip()}",
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Test execution timed out after 120 seconds"}
    except Exception as e:
        return {"passed": False, "output": f"Test execution error: {e}"}


def _generated_environment(project_dir, roots):
    """Create a subprocess environment that cannot inherit host Django config."""
    env = os.environ.copy()
    for key in tuple(env):
        if (
            key == "DJANGO_SETTINGS_MODULE"
            or key.startswith("DJANGO_")
            or key.startswith("DATABASE_")
            or key in {"DATABASE_URL", "SECRET_KEY", "DJANGO_SECRET_KEY", "ROOT_URLCONF"}
        ):
            env.pop(key, None)
    env["PIPELINE_LOCAL"] = "1"
    env["DATABASE_ENGINE"] = "sqlite3"
    env["DJANGO_ALLOWED_HOSTS"] = "localhost,127.0.0.1"
    env["PYTHONPATH"] = os.pathsep.join(
        [root for root in roots if root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return env


def _generated_project_reference_violations(project_dir):
    """Find host-application references only inside the generated workspace."""
    violations = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
        for filename in files:
            path = os.path.join(root, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, 1):
                        if HOST_DJANGO_PACKAGE in line:
                            relative = os.path.relpath(path, project_dir).replace(os.sep, "/")
                            violations.append(
                                f"{relative}:{line_number} references host package {HOST_DJANGO_PACKAGE}"
                            )
                            break
            except OSError:
                continue
    return violations


def _discover_generated_django(project_dir):
    """Discover and validate a generated Django project without importing host modules."""
    candidates = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
        if "manage.py" in files:
            candidates.append(os.path.join(root, "manage.py"))
    if not candidates:
        return {"manage_path": None, "errors": ["Generated Django manage.py is missing"]}

    manage_path = sorted(candidates)[0]
    backend_dir = os.path.dirname(manage_path)
    try:
        with open(manage_path, "r", encoding="utf-8", errors="replace") as handle:
            manage_source = handle.read()
    except OSError as error:
        return {"manage_path": manage_path, "errors": [f"Cannot read manage.py: {error}"]}

    match = re.search(
        r"DJANGO_SETTINGS_MODULE\s*['\"]?\s*\]\s*=\s*['\"]([^'\"]+)['\"]",
        manage_source,
    )
    if not match:
        match = re.search(
            r"DJANGO_SETTINGS_MODULE['\"]?\s*,\s*['\"]([^'\"]+)['\"]",
            manage_source,
        )
    settings_module = match.group(1).strip() if match else None
    errors = []
    if not settings_module:
        errors.append("manage.py does not define DJANGO_SETTINGS_MODULE")
    elif settings_module == HOST_DJANGO_PACKAGE or settings_module.startswith(f"{HOST_DJANGO_PACKAGE}."):
        errors.append(f"manage.py points to host settings module {settings_module}")

    settings_path = None
    package_root = None
    if settings_module and re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", settings_module):
        parts = settings_module.split(".")
        for root in (backend_dir, project_dir):
            candidate = os.path.join(root, *parts[:-1], f"{parts[-1]}.py")
            if os.path.isfile(candidate):
                settings_path = candidate
                package_root = root
                break
    if not settings_path:
        errors.append(f"Generated settings module {settings_module or '(missing)'} cannot be resolved inside the workspace")
    else:
        package_path = os.path.dirname(settings_path)
        if not os.path.isfile(os.path.join(package_path, "__init__.py")):
            errors.append(f"Generated Django package is missing __init__.py: {package_path}")
        for required in ("urls.py", "wsgi.py", "asgi.py"):
            if not os.path.isfile(os.path.join(package_path, required)):
                errors.append(f"Generated Django package is missing {required}")

    return {
        "manage_path": manage_path,
        "backend_dir": backend_dir,
        "settings_module": settings_module,
        "settings_path": settings_path,
        "package_root": package_root,
        "errors": errors,
    }


def _validate_project_locally(project_dir):
    """Run the generated app's own backend and frontend build gates."""
    checks = []
    project_files = []
    if os.path.isdir(project_dir):
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
            project_files.extend(os.path.join(root, name) for name in files)
    checks.append({
        "name": "Project structure",
        "passed": bool(project_files),
        "output": "Generated workspace is present" if project_files else "Generated workspace is empty or missing",
    })
    host_references = _generated_project_reference_violations(project_dir)
    checks.append({
        "name": "Generated-project isolation",
        "passed": not host_references,
        "output": "\n".join(host_references) or "No Buildify host application references found",
    })

    django_project = _discover_generated_django(project_dir)
    manage_path = django_project.get("manage_path")
    if manage_path:
        try:
            python = _project_python(project_dir)
            backend_dir = django_project["backend_dir"]
            package_root = django_project.get("package_root") or backend_dir
            env = _generated_environment(project_dir, [backend_dir, package_root])
            if django_project.get("settings_module"):
                env["DJANGO_SETTINGS_MODULE"] = django_project["settings_module"]
            dependency_paths = [
                os.path.join(backend_dir, "requirements.txt"),
                os.path.join(project_dir, "requirements.txt"),
            ]
            for requirements in dependency_paths:
                if os.path.isfile(requirements):
                    install = subprocess.run(
                        [python, "-m", "pip", "install", "-r", requirements, "-q"],
                        cwd=os.path.dirname(requirements), env=env,
                        capture_output=True, text=True, timeout=300,
                    )
                    if install.returncode != 0:
                        checks.append({
                            "name": "Backend dependency installation",
                            "passed": False,
                            "output": (install.stdout + install.stderr).strip(),
                        })
            for error in django_project.get("errors", []):
                checks.append({"name": "Generated Django project discovery", "passed": False, "output": error})
            python_files = []
            for root, dirs, files in os.walk(backend_dir):
                dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
                python_files.extend(os.path.join(root, name) for name in files if name.endswith(".py"))
            compile_result = subprocess.run(
                [python, "-m", "py_compile", *python_files],
                cwd=backend_dir, env=env, capture_output=True, text=True, timeout=180,
            )
            checks.append({"name": "Python compilation", "passed": compile_result.returncode == 0, "output": (compile_result.stdout + compile_result.stderr).strip()})
            if not django_project.get("errors"):
                settings_import = subprocess.run(
                    [python, "-c", f"import {django_project['settings_module']}"],
                    cwd=backend_dir, env=env, capture_output=True,
                    text=True, timeout=180,
                )
                checks.append({
                    "name": "Generated settings import",
                    "passed": settings_import.returncode == 0,
                    "output": (settings_import.stdout + settings_import.stderr).strip(),
                })
                for name, command in (
                    ("Django settings import and system check", [python, manage_path, "check"]),
                    ("Django migrations", [python, manage_path, "migrate", "--noinput"]),
                    ("Django migration check", [python, manage_path, "makemigrations", "--check", "--dry-run"]),
                ):
                    result = subprocess.run(
                        command, cwd=backend_dir, env=env, capture_output=True,
                        text=True, timeout=180,
                    )
                    checks.append({"name": name, "passed": result.returncode == 0, "output": (result.stdout + result.stderr).strip()})
        except Exception as error:
            checks.append({"name": "Django validation", "passed": False, "output": str(error)})
    else:
        checks.extend({"name": "Generated Django project discovery", "passed": False, "output": error} for error in django_project.get("errors", []))

    package_paths = []
    frontend_directories = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in PROJECT_EXCLUDED_DIRS]
        if os.path.basename(root).lower() in {"frontend", "react_frontend", "web"}:
            frontend_directories.append(root)
        if "package.json" in files:
            package_paths.append(os.path.join(root, "package.json"))

    frontend_required = any(
        os.path.basename(path).lower() in {"frontend", "react_frontend", "web"}
        for path in frontend_directories
    ) or any(
        "react" in (open(path, encoding="utf-8", errors="replace").read(4000).lower())
        for path in package_paths
    )
    if frontend_required and not package_paths:
        checks.append({"name": "Frontend package.json", "passed": False, "output": "React frontend detected or required, but package.json is missing"})

    if manage_path:
        dependency_paths = [
            os.path.join(os.path.dirname(manage_path), "requirements.txt"),
            os.path.join(project_dir, "requirements.txt"),
        ]
        if not any(os.path.isfile(path) for path in dependency_paths):
            checks.append({"name": "Backend dependency file", "passed": False, "output": "Django manage.py found but no requirements.txt exists in the generated backend or root"})

    npm = "npm.cmd" if os.name == "nt" else "npm"
    env = _generated_environment(project_dir, [project_dir])
    for package_path in package_paths:
        package_dir = os.path.dirname(package_path)
        try:
            lockfile = os.path.join(package_dir, "package-lock.json")
            if not os.path.isfile(lockfile):
                lock_result = subprocess.run([npm, "install", "--package-lock-only", "--ignore-scripts"], cwd=package_dir, env=env, capture_output=True, text=True, timeout=300)
                if lock_result.returncode != 0:
                    checks.append({"name": "Frontend lockfile generation", "passed": False, "output": (lock_result.stdout + lock_result.stderr).strip()})
                    continue
            install = subprocess.run([npm, "ci"], cwd=package_dir, env=env, capture_output=True, text=True, timeout=300)
            if install.returncode != 0:
                checks.append({"name": "Frontend dependency install", "passed": False, "output": (install.stdout + install.stderr).strip()})
                continue
            package = json.loads(open(package_path, encoding="utf-8").read())
            if "react" in json.dumps(package).lower():
                frontend_dir = os.path.dirname(package_path)
                source_dir = os.path.join(frontend_dir, "src")
                entrypoints = {
                    "index.js", "index.jsx", "index.ts", "index.tsx",
                    "main.js", "main.jsx", "main.ts", "main.tsx",
                }
                source_files = set(os.listdir(source_dir)) if os.path.isdir(source_dir) else set()
                checks.append({
                    "name": "Frontend structure",
                    "passed": bool(source_files & entrypoints),
                    "output": "React source entrypoint found" if source_files & entrypoints else "React package has no src entrypoint",
                })
            if "build" not in package.get("scripts", {}):
                checks.append({"name": "Frontend build", "passed": True, "output": "No build script declared"})
                continue
            build = subprocess.run([npm, "run", "build"], cwd=package_dir, env=env, capture_output=True, text=True, timeout=300)
            checks.append({"name": "Frontend build", "passed": build.returncode == 0, "output": (build.stdout + build.stderr).strip()})
        except Exception as error:
            checks.append({"name": "Frontend validation", "passed": False, "output": str(error)})

    if not checks:
        checks.append({"name": "Project entrypoint", "passed": False, "output": "No Django manage.py or frontend package.json found"})
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def _acceptance_findings(acceptance):
    """Convert every failed acceptance check into actionable repair findings."""
    findings = []
    severity_by_check = {
        "Generated-project isolation": "critical",
        "Generated settings import": "critical",
        "Django settings import and system check": "critical",
        "Django system check": "critical",
        "Django migrations": "major",
        "Django migration check": "major",
        "Generated Django project discovery": "critical",
        "Project entrypoint": "critical",
        "Backend dependency file": "major",
        "Frontend package.json": "major",
        "Frontend structure": "major",
    }
    repair_by_check = {
        "Generated-project isolation": "Remove host-application imports and configuration from the generated workspace.",
        "Generated Django project discovery": "Create an independent generated package and point manage.py to its settings module.",
        "Generated settings import": "Repair the generated settings package and its dependencies without importing Buildify modules.",
        "Django settings import and system check": "Fix the generated Django settings, installed apps, URLs, and dependencies.",
        "Django migrations": "Add or repair generated app migrations and database configuration.",
        "Django migration check": "Create consistent migrations for the generated applications.",
        "Backend dependency file": "Add a complete generated backend requirements.txt.",
        "Frontend package.json": "Add the generated React frontend package.json and scripts.",
        "Frontend structure": "Restore the generated frontend entrypoint and source structure.",
    }
    for check in acceptance.get("checks", []):
        if check.get("passed"):
            continue
        output = check.get("output", "")
        affected = None
        path_match = re.search(r"(?:[A-Za-z]:)?[^\s:]+\.(?:py|js|jsx|ts|tsx|json)", output)
        module_match = re.search(r"No module named ['\"]?([^'\"\s]+)", output)
        if path_match:
            affected = path_match.group(0)
        elif module_match:
            affected = module_match.group(1)
        findings.append({
            "check_name": check.get("name", "Unknown acceptance check"),
            "failure_type": "process_failure" if "timed out" in output.lower() else "validation_failure",
            "exact_error": output,
            "affected_path_or_module": affected,
            "severity": severity_by_check.get(check.get("name"), "major"),
            "recommended_repair": repair_by_check.get(
                check.get("name"),
                "Repair the generated workspace for this check and rerun all acceptance checks.",
            ),
        })
    return findings


FINALIZATION_REPAIR_ATTEMPTS = 3


def _run_finalization(pipeline, project, all_tasks, project_files, project_dir, selected_model):
    """Run complete acceptance and bounded targeted repairs on the current workspace."""
    if pipeline.finalization_state == PipelineRun.FinalizationState.ACCEPTED:
        pipeline.append_log("[Finalization] Already accepted; preserving generated workspace")
        return True

    pipeline.finalization_state = PipelineRun.FinalizationState.RUNNING
    pipeline.finalization_attempts = 0
    pipeline.finalization_error = ""
    pipeline.save(update_fields=["finalization_state", "finalization_attempts", "finalization_error"])

    retry_context = {
        "original_task": {
            "title": "Project finalization",
            "description": project.description or "Validate and finalize the generated project",
        },
        "acceptance_contract": {
            "reviewer_acceptance_criteria": [
                "Every final acceptance check passes in the isolated generated workspace.",
                "No generated file references the Buildify host application.",
            ],
            "prohibited_approaches": [
                f"Do not import or reference {HOST_DJANGO_PACKAGE}.",
                "Do not repair failures by modifying the Buildify host application.",
            ],
        },
        "test_failures": [],
        "debugger_analysis": [],
        "reviewer_findings": [],
        "unresolved_issues": [],
        "attempt": 0,
    }

    for attempt in range(1, FINALIZATION_REPAIR_ATTEMPTS + 1):
        pipeline.finalization_attempts = attempt
        pipeline.stage = PipelineRun.Stage.DEBUGGING
        pipeline.save(update_fields=["stage", "finalization_attempts"])
        pipeline.append_log(
            f"[Finalization] Attempt {attempt}/{FINALIZATION_REPAIR_ATTEMPTS}: "
            "running all acceptance checks"
        )
        try:
            acceptance = _validate_project_locally(project_dir)
        except Exception as error:
            acceptance = {
                "passed": False,
                "checks": [{
                    "name": "Final acceptance execution",
                    "passed": False,
                    "output": f"{type(error).__name__}: {error}",
                }],
            }
        for check in acceptance["checks"]:
            pipeline.append_log(
                f"[Acceptance] {check['name']}: {'PASSED' if check['passed'] else 'FAILED'}"
            )
            if not check["passed"]:
                pipeline.append_log(f"[Acceptance] {check['output'][-2000:]}")

        if acceptance["passed"]:
            pipeline.finalization_state = PipelineRun.FinalizationState.ACCEPTED
            pipeline.finalization_error = ""
            pipeline.save(update_fields=["finalization_state", "finalization_error", "stage"])
            pipeline.append_log("[Finalization] All acceptance checks passed")
            return True

        findings = _acceptance_findings(acceptance)
        retry_context["attempt"] = attempt
        retry_context["reviewer_findings"] = findings
        retry_context["unresolved_issues"] = findings
        retry_context["test_failures"] = [finding["exact_error"] for finding in findings]
        pipeline.append_log(f"[Finalization] {len(findings)} structured failure finding(s)")
        for finding in findings:
            pipeline.append_log(
                f"  [{finding['severity'].upper()}] {finding['check_name']}: "
                f"{finding['recommended_repair']}"
            )

        if attempt == FINALIZATION_REPAIR_ATTEMPTS:
            pipeline.finalization_state = PipelineRun.FinalizationState.FAILED
            pipeline.finalization_error = json.dumps(findings, indent=2)
            pipeline.stage = PipelineRun.Stage.FAILED
            pipeline.error = "Finalization failed after bounded repair attempts"
            pipeline.save(update_fields=[
                "finalization_state", "finalization_error", "stage", "error",
            ])
            pipeline.append_log("[Finalization] Repair limit reached; workspace remains resumable")
            pipeline.append_log("[FinalizationContext] " + _retry_context_text(retry_context))
            return False

        diagnostics = [
            f"{finding['check_name']}: {finding['exact_error']}"
            for finding in findings
        ]
        try:
            repaired = _repair_workspace(
                all_tasks[-1] if all_tasks else SimpleNamespace(
                    title="Project finalization", description=project.description or ""
                ),
                project,
                project_files,
                project_dir,
                pipeline,
                diagnostics,
                selected_model,
                acceptance_contract=retry_context["acceptance_contract"],
                retry_context=retry_context,
            )
        except Exception as error:
            repaired = False
            retry_context["debugger_analysis"] = [f"{type(error).__name__}: {error}"]
            pipeline.append_log(f"[Finalization] Repair error: {error}")
        pipeline.append_log(
            f"[Finalization] Targeted repair {'applied' if repaired else 'not applied'}; "
            "the next attempt will rerun every check"
        )

    return False


def _find_generated_settings_module(project_dir, backend_dir):
    """Compatibility wrapper for the single isolation-safe Django discovery path."""
    return _discover_generated_django(project_dir).get("settings_module")


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
    if not isinstance(response, str) or not response.strip():
        return {"error": f"{agent_name} model response was empty"}
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

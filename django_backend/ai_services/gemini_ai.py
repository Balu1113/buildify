import os
import sys
import ast
import json
import re
import threading
import signal
from typing import Iterable, Optional
from contextlib import contextmanager

from django.conf import settings

sys.path.insert(0, os.path.join(settings.BASE_DIR, ".."))

from google import genai
from openai import OpenAI


API_KEY = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
MODEL_NAME = settings.GEMINI_MODEL_NAME
FALLBACK_MODEL_NAMES = os.getenv("GEMINI_FALLBACK_MODELS", "")

# API timeout for Gemini calls (must be less than gunicorn's 30-second worker timeout)
GEMINI_TIMEOUT_SECONDS = 20

_client = None
_model_context = threading.local()
LEGACY_MODEL_ALIASES = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-4-scout-17b-16e-instruct": "openai/gpt-oss-120b",
    "qwen/qwen3-32b": "openai/gpt-oss-120b",
    "moonshotai/kimi-k2-instruct": "openai/gpt-oss-120b",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "openai/gpt-oss-120b",
}


class TimeoutError(Exception):
    """Raised when an operation exceeds its timeout."""
    pass


class GeminiAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _gemini_error(error: Exception) -> GeminiAPIError:
    provider_status = getattr(error, "status_code", None)
    if provider_status is None:
        provider_status = getattr(error, "code", None)
    if hasattr(provider_status, "value"):
        provider_status = provider_status.value
    message = str(error).strip() or error.__class__.__name__
    return GeminiAPIError(message, provider_status)


@contextmanager
def _timeout_guard(seconds: int):
    """Context manager that enforces a timeout using threading."""
    result = {"timed_out": False}
    
    def timeout_handler():
        result["timed_out"] = True
    
    # Use signal.alarm on Unix-like systems
    if hasattr(signal, "alarm"):
        def alarm_handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds} seconds")
        
        old_handler = signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # On Windows or if signal.alarm is not available, just yield without timeout
        # This is not ideal but prevents breaking on Windows
        yield


def get_client():
    global _client
    if _client is None:
        if not API_KEY:
            raise ValueError("GEMINI_API_KEY is not set.")
        _client = genai.Client(api_key=API_KEY)
    return _client


def _configured_models() -> Iterable[str]:
    """Return the primary model followed by unique configured fallbacks."""
    candidates = [MODEL_NAME, *FALLBACK_MODEL_NAMES.split(",")]
    seen = set()
    for candidate in candidates:
        model = (candidate or "").strip()
        if model and model not in seen:
            seen.add(model)
            yield model


def set_model_attempt(attempt: int) -> None:
    """Prefer a different model for each pipeline retry in the current thread."""
    _model_context.attempt = max(0, attempt)


def _models_for_current_attempt() -> list[str]:
    """Rotate configured models so a retry does not begin with an exhausted one."""
    models = list(_configured_models())
    if not models:
        return models
    offset = getattr(_model_context, "attempt", 0) % len(models)
    return models[offset:] + models[:offset]


def current_model_order() -> list[str]:
    """Expose the active model order for safe pipeline diagnostics."""
    return _models_for_current_attempt()


def _should_try_fallback(error: Exception) -> bool:
    """Only move on for provider/model availability failures, not bad requests."""
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if hasattr(status_code, "value"):
        status_code = status_code.value
    if status_code in {404, 408, 429, 500, 502, 503, 504}:
        return True

    message = str(error).lower()
    retryable_markers = (
        "resource_exhausted",
        "rate limit",
        "quota",
        "too many requests",
        "model not found",
        "model is not available",
        "service unavailable",
        "temporarily unavailable",
        "deadline exceeded",
        "timed out",
    )
    return any(marker in message for marker in retryable_markers)


def _generate_content(contents):
    """Generate content, falling back when the current model is exhausted."""
    client = get_client()
    models = _models_for_current_attempt()
    if not models:
        raise ValueError("GEMINI_MODEL_NAME is not set.")

    failures = []
    for index, model in enumerate(models):
        try:
            with _timeout_guard(GEMINI_TIMEOUT_SECONDS):
                response = client.models.generate_content(model=model, contents=contents)
            if not response.text:
                raise GeminiAPIError(f"Gemini model '{model}' returned an empty response.")
            return response.text
        except TimeoutError as error:
            # Timeout occurred; treat as a retriable failure
            api_error = GeminiAPIError(str(error), 504)
            failures.append(f"{model}: timeout")
            if index == len(models) - 1:
                raise api_error from error
        except Exception as error:
            api_error = _gemini_error(error)
            failures.append(f"{model}: {api_error}")
            if index == len(models) - 1 or not _should_try_fallback(error):
                raise GeminiAPIError("; ".join(failures), api_error.status_code) from error

    raise GeminiAPIError("All configured Gemini models failed.")


def generate_response(prompt: str, model_name: Optional[str] = None) -> str:
    try:
        if model_name:
            model_name = LEGACY_MODEL_ALIASES.get(model_name, model_name)
            if not model_name.startswith(("gemini-", "gemma-")):
                base_url = (
                    "https://api.groq.com/openai/v1"
                    if model_name in {
                        "openai/gpt-oss-120b",
                        "openai/gpt-oss-20b",
                    }
                    else "https://integrate.api.nvidia.com/v1"
                )
                api_key = (
                    os.getenv("GROQ_API_KEY")
                    if base_url.startswith("https://api.groq")
                    else os.getenv("OPENAI_API_KEY")
                )
                completion = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    timeout=GEMINI_TIMEOUT_SECONDS,
                    max_retries=1,
                ).chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1,
                    max_tokens=8192,
                )
                return completion.choices[0].message.content
            with _timeout_guard(GEMINI_TIMEOUT_SECONDS):
                response = get_client().models.generate_content(model=model_name, contents=prompt)
            return response.text
        return _generate_content(prompt)
    except TimeoutError as error:
        raise GeminiAPIError(f"API request timed out: {error}", 504) from error
    except Exception as error:
        raise _gemini_error(error) from error


def generate_image_response(prompt: str, image_content: bytes, mime_type: str) -> str:
    try:
        return _generate_content(
            [
                prompt,
                {"inline_data": {"mime_type": mime_type, "data": image_content}},
            ]
        )
    except Exception as error:
        raise _gemini_error(error) from error


# ---------------------------------------------------------------------------
# AST Utilities
# ---------------------------------------------------------------------------

def extract_python_symbols(source_code: str) -> dict:
    """Extract classes, functions, variables, imports from Python source."""
    symbols = {
        "classes": [],
        "functions": [],
        "variables": [],
        "imports": [],
        "routes": [],
    }
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
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
        # Detect Flask/Django/FastAPI route decorators
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    attr = getattr(func, "attr", "") or getattr(func, "id", "")
                    if attr in ("route", "get", "post", "put", "delete", "patch"):
                        symbols["routes"].append({
                            "function": node.name,
                            "method": attr,
                        })
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


# ---------------------------------------------------------------------------
# Expense / Priority utilities
# ---------------------------------------------------------------------------

def parse_expense_text(text: str) -> Optional[dict]:
    prompt = f"""Extract expense details from this text:

{text}

Return ONLY valid JSON with exactly these keys:
{{
    "amount": <float>,
    "merchant": "<string>",
    "category": "<string>"
}}

Do not include markdown, code blocks, or explanations."""
    try:
        response_text = generate_response(prompt).strip()
        clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Error parsing expense text: {e}")
        return None


def parse_receipt_image(image_content: bytes, mime_type: str = "image/jpeg") -> Optional[dict]:
    prompt = """Analyze this receipt image and extract the expense information.

Return ONLY valid JSON with exactly these keys:
{{
    "amount": <float>,
    "merchant": "<string>",
    "category": "<string>"
}}

Rules:
- amount must be the final/total amount paid
- merchant must be the store/business name
- category should be a simple category such as Food, Transport, Shopping, Utilities, Healthcare, Entertainment, or Other
- Do not include markdown or explanations."""
    try:
        response_text = generate_image_response(prompt, image_content, mime_type).strip()
        clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Error parsing receipt image: {e}")
        return None


def suggest_task_priority(title: str, description: str = "") -> str:
    prompt = f"""You are an AI task management assistant.

Analyze this task and determine its priority.

Task title: {title}
Task description: {description or 'No description provided'}

Choose exactly one priority: high, medium, or low.
Return ONLY the priority word."""
    try:
        response = generate_response(prompt).strip().lower()
        if response in {"high", "medium", "low"}:
            return response
        return "medium"
    except Exception as e:
        print(f"Error suggesting task priority: {e}")
        return "medium"


# ---------------------------------------------------------------------------
# Project Planning
# ---------------------------------------------------------------------------

def plan_project(description: str, model_name: Optional[str] = None) -> Optional[dict]:
    prompt = f"""You are a senior software architect and project planner.

Given this project idea, create a comprehensive development plan:

Project Idea: {description}

Your task breakdown must be specific, actionable, and ordered by dependency. Each task should produce working, testable code. Think about:
- What tech stack is appropriate (prefer Python/Django for backend, React/Vue for frontend, SQLite for DB)
- What models/tables are needed
- What API endpoints are needed
- What frontend pages/components are needed
- What configuration files are needed (requirements.txt, manage.py, etc.)
- Authentication, testing, documentation

Break it into 6-10 practical development tasks. Order them so each task builds on the previous.

Return ONLY valid JSON:
{{
    "project_name": "<descriptive name>",
    "project_description": "<1-2 sentence description>",
    "tech_stack": ["<technology1>", "<technology2>"],
    "tasks": [
        {{
            "title": "<specific task title>",
            "description": "<detailed description of what to implement, including specific files, models, endpoints, or components to create>",
            "priority": "high|medium|low",
            "files_expected": ["<list of files this task should create>"]
        }}
    ]
}}

Rules:
- First task must create a runnable project scaffold before feature work: backend
    manage.py, settings, urls, wsgi/asgi, requirements, and, when a frontend is
    required, frontend package.json with a working dev/start script and source entrypoint.
    The scaffold must be startable independently before later feature tasks build on it.
- Each subsequent task should add specific functionality
- Last tasks should handle testing, polish, and documentation
- Be specific about what files and code each task produces
- Do NOT include markdown or code blocks"""
    try:
        response_text = generate_response(prompt, model_name=model_name).strip()
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text, flags=re.IGNORECASE).strip()
        try:
            plan = json.loads(clean_json)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", clean_json, flags=re.DOTALL)
            if not match:
                raise ValueError("Planner response did not contain a JSON object")
            plan = json.loads(match.group(0))
        if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
            raise ValueError("Planner response did not contain a non-empty tasks list")
        return plan
    except Exception as e:
        print(f"Error planning project: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Code Review
# ---------------------------------------------------------------------------

def review_code(source_files: dict, test_results: str = "") -> Optional[dict]:
    files_text = "\n\n".join(
        f"=== {filename} ===\n{content}" for filename, content in source_files.items()
    )

    test_results_section = f"Test results:\n{test_results}" if test_results else ""
    prompt = f"""You are a senior software engineer performing a thorough code review.

Review the following source files for a student project:

{files_text}

{test_results_section}

Evaluate:
1. Correctness - Does the code work as intended?
2. Completeness - Are all features fully implemented?
3. Code quality - Is it readable, well-structured, following conventions?
4. Error handling - Are errors handled gracefully?
5. Security - Are there any security concerns?
6. Performance - Any obvious performance issues?
7. Best practices - Follows language/framework conventions?

Return ONLY valid JSON:
{{
    "overall_status": "approved|needs_changes",
    "score": <int 0-10>,
    "findings": [
        {{
            "severity": "critical|major|minor",
            "category": "security|performance|readability|correctness|completeness",
            "message": "<specific description of the issue>",
            "file": "<filename>",
            "suggestion": "<how to fix it>"
        }}
    ],
    "strengths": ["<specific positive aspect of the code>"],
    "test_assessment": "<evaluation of test coverage and quality>"
}}

Be specific and constructive. Do not include markdown or code blocks."""
    try:
        response_text = generate_response(prompt).strip()
        clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Error reviewing code: {e}")
        return None


# ---------------------------------------------------------------------------
# Project Modification
# ---------------------------------------------------------------------------

def modify_project(source_files: dict, modification: str, model_name: Optional[str] = None) -> Optional[dict]:
    files_text = "\n\n".join(
        f"=== {filename} ===\n{content}" for filename, content in source_files.items()
    )

    prompt = f"""You are a software engineer AI assistant.

The user has an existing project with these files:

{files_text}

The user wants this modification:
{modification}

Apply the modification to the project. Return ONLY valid JSON:
{{
    "summary": "<string describing what you changed>",
    "files": {{
        "<filename>": "<new full content of the file>"
    }},
    "new_files": {{
        "<filename>": "<content of any new files to create>"
    }},
    "deleted_files": ["<list of filenames to delete>"]
}}

Rules:
- For files you did NOT modify, do NOT include them in "files"
- Only include genuinely new files in "new_files"
- Return complete file contents, not diffs
- Do not include markdown or code blocks outside the JSON"""
    try:
        response_text = generate_response(prompt, model_name=model_name).strip()
        clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
        return json.loads(clean_json)
    except GeminiAPIError:
        raise
    except json.JSONDecodeError as error:
        raise GeminiAPIError(f"AI returned invalid JSON: {error.msg}", 502) from error
    except Exception as e:
        raise GeminiAPIError(f"AI modification response could not be processed: {e}", 502) from e


def project_chat(source_files: dict, message: str, conversation=None, apply_changes=False, model_name: Optional[str] = None) -> Optional[dict]:
    """Advise on a generated project and optionally return an explicit change set."""
    files_text = "\n\n".join(
        f"=== {filename} ===\n{content[:12000]}" for filename, content in source_files.items()
    )
    history_text = json.dumps(conversation or [], ensure_ascii=True)[-12000:]
    prompt = f"""You are a senior product engineer, UX strategist, and software architect.

You are advising on an existing generated project. Inspect its actual files before
making claims. The user asks:
{message}

Conversation so far:
{history_text}

Current project files:
{files_text}

Provide useful, concrete product advice. When asked to compare competitors, do not
invent private facts or claim live market data. Compare against recognizable market
patterns and common capabilities of relevant products, label assumptions, and focus
on differentiated opportunities the project can realistically build.

Return ONLY valid JSON:
{{
  "answer": "Clear direct response to the user",
  "project_assessment": "What the current project already does and where it is weak",
  "competitor_patterns": [
    {{"pattern": "Capability common in comparable products", "user_value": "Why it matters", "assumption": "What is assumed"}}
  ],
  "recommendations": [
    {{"title": "Feature or improvement", "priority": "high|medium|low", "impact": "Expected user or business impact", "effort": "small|medium|large", "reason": "Why it fits this project"}}
  ],
  "next_steps": ["Ordered implementation steps"],
  "change_plan": ["Files/components that would need changes"],
  "files": {{}},
  "new_files": {{}},
  "deleted_files": [],
  "changes_applied": {str(bool(apply_changes)).lower()}
}}

Rules:
- Do not claim a change was applied unless apply_changes is true and files are returned.
- If apply_changes is false, return an empty change set and recommendations only.
- If apply_changes is true, return complete file contents only for files that need changes.
- Preserve existing APIs, authentication, project isolation, and persistence.
- Never reference or import the Buildify host application.
- Do not include markdown outside the JSON."""
    try:
        response_text = generate_response(prompt, model_name=model_name).strip()
        clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
        result = json.loads(clean_json)
        if not isinstance(result, dict):
            raise ValueError("AI chat response was not an object")
        if not apply_changes:
            result["files"] = {}
            result["new_files"] = {}
            result["deleted_files"] = []
            result["changes_applied"] = False
        return result
    except GeminiAPIError:
        raise
    except json.JSONDecodeError as error:
        raise GeminiAPIError(f"AI chat returned invalid JSON: {error.msg}", 502) from error
    except Exception as error:
        raise GeminiAPIError(f"AI chat response could not be processed: {error}", 502) from error

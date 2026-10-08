import os
import ast
import json
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import shutil
import hashlib

from django.conf import settings
from django.core import signing
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

from django.http import HttpResponse
from django.db import close_old_connections

from . import gemini_ai
from projects.models import GeneratedFile, Project
from projects.runtime import (
    ensure_project_python,
    generated_env,
    install_python_dependencies,
    requirements_ready,
)
from projects.storage import (
    delete_generated_file,
    load_project_files,
    materialize_project,
    normalize_file_path,
    persist_workspace,
    save_generated_file,
)

PYTHON = sys.executable

PROJECTS_DIR = settings.GENERATED_PROJECTS_DIR

_running_processes = {}

_preview_jobs = {}
_preview_jobs_lock = threading.Lock()

# Runtime repair is intentionally bounded. A generated project must never enter
# an unbounded LLM/restart loop because of a persistent environment failure.
_auto_repair_jobs = {}
_auto_repair_jobs_lock = threading.Lock()
_auto_repair_fingerprints = {}
MAX_AUTO_REPAIRS_PER_ERROR = 3
MAX_AUTO_REPAIR_FILES = 15
MAX_AUTO_REPAIR_LOG_CHARS = 15000

PREVIEW_TOKEN_SALT = "buildify.generated-preview"
PREVIEW_TOKEN_MAX_AGE = 60 * 60


def _resolve_project(project_id):
    value = str(project_id)
    if value.startswith("project_"):
        value = value.removeprefix("project_")
    if not value.isdigit():
        return None
    return Project.objects.filter(pk=int(value)).first()


def _preview_cookie_name(project_id):
    return f"buildify_preview_{project_id}"


def _issue_preview_token(request, project):
    """Create a short-lived, project-scoped token for an iframe preview."""
    return signing.dumps(
        {"project_id": project.pk, "user_id": request.user.pk},
        salt=PREVIEW_TOKEN_SALT,
    )


def _has_preview_access(request, project):
    token = request.GET.get("preview_token") or request.COOKIES.get(
        _preview_cookie_name(project.pk)
    )
    if not token:
        return False
    try:
        payload = signing.loads(
            token,
            salt=PREVIEW_TOKEN_SALT,
            max_age=PREVIEW_TOKEN_MAX_AGE,
        )
    except signing.BadSignature:
        return False
    return payload.get("project_id") == project.pk


def _attach_preview_cookie(request, response, project):
    """Authorize subsequent preview/iframe requests via a scoped cookie.

    Every successful run response refreshes the cookie with a freshly signed
    token, so sessions stay valid past the token TTL and the iframe works
    without appending ``preview_token`` to each URL.
    """
    response.set_cookie(
        _preview_cookie_name(project.pk),
        _issue_preview_token(request, project),
        max_age=PREVIEW_TOKEN_MAX_AGE,
        httponly=True,
        secure=request.is_secure(),
        samesite="Lax",
        path="/",
    )
    return response


def _preview_runtime_script(project_id):
    """Route generated frontend API calls through this project's preview proxy."""
    proxy_prefix = f"/api/ai/generated/project_{project_id}/preview"
    return f"""<script>
(() => {{
  const proxyPrefix = {json.dumps(proxy_prefix)};
  // Generated apps with a router must use this as their basename so routes
  // resolve while the preview is embedded under the Buildify origin.
  window.__BUILDIFY_PREVIEW_BASENAME__ = proxyPrefix + "/";
  try {{
    if (!window.location.pathname.startsWith(proxyPrefix)) {{
      history.replaceState(
        history.state,
        "",
        proxyPrefix + window.location.pathname + window.location.search + window.location.hash
      );
    }}
  }} catch (_) {{}}
  const rewrite = (value) => {{
    if (typeof value !== "string") return value;
    try {{
      const url = new URL(value, window.location.origin);
      const isLocal = url.origin === window.location.origin || /^(localhost|127\\.0\\.0\\.1)$/.test(url.hostname);
      if (isLocal && (url.pathname === "/api" || url.pathname.startsWith("/api/"))) {{
        if (url.pathname.startsWith(proxyPrefix)) return value;
        return proxyPrefix + url.pathname + url.search + url.hash;
      }}
    }} catch (_) {{}}
    return value;
  }};
  const originalFetch = window.fetch;
  if (originalFetch) window.fetch = (input, init) => originalFetch(rewrite(input), init);
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
    return originalOpen.call(this, method, rewrite(url), ...rest);
  }};
}})();</script>"""


def _inject_preview_runtime(response_body, content_type, project_id):
    if "text/html" not in content_type.lower():
        return response_body
    try:
        page = response_body.decode("utf-8")
    except UnicodeDecodeError:
        return response_body
    script = _preview_runtime_script(project_id)
    if "</head>" in page.lower():
        return re.sub(r"</head>", f"{script}</head>", page, count=1, flags=re.IGNORECASE).encode("utf-8")
    return f"{script}{page}".encode("utf-8")


def _project_workspace(project_id, materialize=False):
    project = _resolve_project(project_id)

    if project is None:
        return None, None

    project_dir = os.path.join(
        PROJECTS_DIR,
        f"project_{project.pk}",
    )

    persisted = load_project_files(project)

    if not persisted and os.path.isdir(project_dir):
        persisted = persist_workspace(project, project_dir)

    if materialize:
        existing_job = _get_preview_job(project.pk)

        preserve_workspace = existing_job and existing_job.get(
            "status"
        ) in {
            "preparing",
            "ready",
            "running",
        }

        if not preserve_workspace:
            materialize_project(
                project,
                project_dir,
                clear=True,
            )

    return project, project_dir


def _format_command(command):
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return " ".join(subprocess.list2cmdline([part]) for part in command)


def _terminal_agent_snapshot(project_id, project_dir, process_info=None):
    """Return safe command and output details for the generated app console."""
    processes = []
    for info in (process_info or {}).get("processes", []):
        process = info["proc"]
        processes.append({
            "script": info["script"],
            "command": info["command_display"],
            "cwd": info["cwd"],
            "port": info["port"],
            "pid": process.pid,
            "status": "running" if process.poll() is None else "stopped",
            "exit_code": process.poll(),
            "output": "".join(info["output"][-100:]),
        })

    return {
        "project_dir": project_dir,
        "processes": processes,
        "manual_commands": [
            {
                "label": info["script"],
                "command": info["command_display"],
                "cwd": info["cwd"],
            }
            for info in (process_info or {}).get("processes", [])
        ],
    }


def _port_is_available(port):
    """True when nothing is listening on this port on any interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False


def _find_free_port(exclude=None):
    exclude = exclude or set()
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in exclude:
            return port
    raise RuntimeError("Could not find a free port for the generated project")


def _detect_port_from_files(project_dir):
    py_files = []
    for fname in os.listdir(project_dir):
        if fname.endswith(".py"):
            py_files.append(fname)
    for fname in py_files:
        fpath = os.path.join(project_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            port_match = re.search(r"(?:port|PORT)\s*[=:]\s*(\d{4,5})", content)
            if port_match:
                return int(port_match.group(1))
        except Exception:
            pass
    return None


def _get_run_command(project_dir, script, port=None):
    if script.endswith("manage.py"):
        req_dir = _get_requirements_dir(project_dir, script)

        if not req_dir:
            req_dir = os.path.dirname(
                os.path.join(project_dir, script)
            )

        if req_dir:
            req_file = os.path.join(
                req_dir,
                "requirements.txt",
            )

            if not os.path.exists(req_file):
                with open(req_file, "w") as f:
                    f.write("django\n")

        # Install into the project-local virtualenv so the generated app can
        # never upgrade Django/DRF inside the Buildify interpreter.
        try:
            project_python = ensure_project_python(project_dir)
        except Exception as error:
            raise RuntimeError(f"Could not create the generated project virtualenv: {error}")

        ok, message = install_python_dependencies(project_dir)
        if not ok:
            raise RuntimeError(message)

        # Create generated project's static directory
        os.makedirs(
            os.path.join(
                project_dir,
                "static",
            ),
            exist_ok=True,
        )

        manage_py = os.path.join(req_dir, "manage.py")

        migration_env = generated_env()
        migration_env["PYTHONDONTWRITEBYTECODE"] = "1"

        settings_module = _detect_settings_module(project_dir, manage_py)

        if settings_module:
            migration_env["DJANGO_SETTINGS_MODULE"] = settings_module

        print(f"[Buildify] Django migration cwd: {req_dir}", flush=True)
        print(f"[Buildify] Django manage.py: {manage_py}", flush=True)

        try:
            migrate_result = subprocess.run(
                [
                    project_python,
                    manage_py,
                    "migrate",
                    "--noinput",
                ],
                cwd=req_dir,
                env=migration_env,
                timeout=120,
                text=True,
                capture_output=True,
                check=False,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            print(
                f"[Buildify] Generated Django migration stdout:\n"
                f"{migrate_result.stdout}",
                flush=True,
            )

            print(
                f"[Buildify] Generated Django migration stderr:\n"
                f"{migrate_result.stderr}",
                flush=True,
            )

            if migrate_result.returncode != 0:
                raise RuntimeError(
                    "Generated Django migrations failed with "
                    f"exit code {migrate_result.returncode}"
                )

        except Exception as error:
            print(
                f"[Buildify] Generated Django migration error: {error}",
                flush=True,
            )
            raise

        return [
            project_python,
            script,
            "runserver",
            f"0.0.0.0:{port or 0}",
            "--noreload",
        ]
    if script.endswith(".py"):
        project_python = ensure_project_python(project_dir)
        ok, message = install_python_dependencies(project_dir)
        if not ok:
            raise RuntimeError(message)
        return [project_python, script]
    
    if script.endswith("package.json"):
        package_dir = os.path.dirname(os.path.join(project_dir, script))
        package_path = os.path.join(package_dir, "package.json")
        
        
        try:
            with open(package_path, "r", encoding="utf-8") as package_file:
                package = json.load(package_file)
        except (OSError, json.JSONDecodeError):
            package = {}

        scripts = package.get("scripts", {})
        script_name = "dev" if "dev" in scripts else "start" if "start" in scripts else None
        if not script_name:
            raise RuntimeError(
                f"{package_path} has no runnable 'dev' or 'start' script"
            )

        npm_command = "npm.cmd" if os.name == "nt" else "npm"

        command = [npm_command, "run", script_name]

        if port and script_name == "dev":
            # Vite-style dev servers accept these flags. A CRA "start" script
            # would choke on them; it reads PORT from the environment instead.
            command.extend(["--", "--host", "127.0.0.1", "--port", str(port)])
        return command
    return [PYTHON, script]


def _ensure_node_dependencies(project_dir, script):
    """Validate the frontend and return its package directory."""
    if not script.endswith("package.json"):
        return None

    npm_command = "npm.cmd" if os.name == "nt" else "npm"

    if shutil.which(npm_command) is None:
        return {
            "status": "environment-unavailable",
            "severity": "user-action-required",
            "error": "npm_unavailable",
            "message": "Node.js/npm is not available in the Buildify execution environment.",
        }

    package_dir = os.path.dirname(os.path.join(project_dir, script))
    package_path = os.path.join(package_dir, "package.json")

    if not os.path.exists(package_path):
        return {
            "status": "not-ready",
            "severity": "user-action-required",
            "error": "package_json_missing",
            "message": "Frontend package.json was not found.",
        }

    try:
        with open(package_path, "r", encoding="utf-8") as package_file:
            package = json.load(package_file)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "status": "not-ready",
            "severity": "user-action-required",
            "error": "invalid_package_json",
            "message": f"Unable to read package.json: {error}",
        }

    scripts = package.get("scripts", {})

    print(
        f"[Buildify] FRONTEND package.json: {package_path}",
        flush=True,
    )

    print(
        f"[Buildify] FRONTEND scripts: {scripts}",
        flush=True,
    )

    print(
        f"[Buildify] FRONTEND package name: {package.get('name')}",
        flush=True,
    )

    if "dev" not in scripts and "start" not in scripts:
        return {
            "status": "not-ready",
            "severity": "user-action-required",
            "error": "frontend_script_missing",
            "message": "Frontend package.json does not contain a dev or start script.",
        }

    return package_dir


def _get_preview_job(project_id):
    with _preview_jobs_lock:
        job = _preview_jobs.get(project_id)

    return dict(job) if job else None

def _preview_state_path(project_dir):
    state_dir = os.path.join(
        project_dir,
        ".buildify",
    )

    os.makedirs(
        state_dir,
        exist_ok=True,
    )

    return os.path.join(
        state_dir,
        "frontend_status.json",
    )


def _write_preview_state(project_dir, state):
    state_path = _preview_state_path(project_dir)

    temp_path = f"{state_path}.tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as state_file:
        json.dump(
            state,
            state_file,
        )

    os.replace(
        temp_path,
        state_path,
    )


def _read_preview_state(project_dir):
    state_path = _preview_state_path(project_dir)

    if not os.path.exists(state_path):
        return None

    try:
        with open(
            state_path,
            "r",
            encoding="utf-8",
        ) as state_file:
            return json.load(state_file)
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None
    
def _append_preview_output(project_id, line):
    with _preview_jobs_lock:
        job = _preview_jobs.get(project_id)
        if job is not None:
            job.setdefault("output", []).append(line)
            job["output"] = job["output"][-200:]


def _get_auto_repair_job(project_id):
    with _auto_repair_jobs_lock:
        job = _auto_repair_jobs.get(project_id)
    return dict(job) if job else None


def _set_auto_repair_job(project_id, **updates):
    with _auto_repair_jobs_lock:
        job = _auto_repair_jobs.setdefault(project_id, {})
        job.update(updates)
        return dict(job)


def _auto_repair_project(project_id, project_dir, output, attempt_number=1):
    """Ask the existing code-modification service for a bounded runtime fix with progressive escalation."""
    close_old_connections()
    try:
        project = _resolve_project(project_id)
        if project is None:
            raise RuntimeError("Project no longer exists")

        source_files = load_project_files(project)
        if not source_files:
            raise RuntimeError("No generated source files are available to repair")

        diagnosis = output[-MAX_AUTO_REPAIR_LOG_CHARS:]

        # Progressive escalation strategy based on attempt number
        if attempt_number == 1:
            strategy = "CONSERVATIVE: Make minimal changes, preserve all features, fix obvious issues only (syntax errors, missing imports, simple typos). Do not restructure code."
        elif attempt_number == 2:
            strategy = "TARGETED: Focus on specific error patterns:\\n  - Python: ImportError, ModuleNotFoundError, SyntaxError, IndentationError, AttributeError\\n  - Django: ImproperlyConfigured, AppRegistryNotReady, migration issues, settings errors\\n  - React/JS: ReferenceError, TypeError, hooks rules violations, missing dependencies\\n  - Runtime: Port already in use, EADDRINUSE, address already in use\\n  - Dependency: npm install failures, missing package.json, node_modules issues\\n  Apply targeted fixes for the detected error category."
        else:  # attempt_number >= 3
            strategy = "AGGRESSIVE: May restructure code, add missing files, change configurations, add fallback handling. Consider alternative implementations if the current approach is fundamentally flawed."

        request_text = f"""You are the Auto Bug Detection Agent and Solver.
A runtime error occurred when running the generated application.

=== ATTEMPT {attempt_number} OF {MAX_AUTO_REPAIRS_PER_ERROR} ===
ESCALATION STRATEGY: {strategy}

=== RUNTIME ERROR & CRASH LOGS ===
{diagnosis}
=== END RUNTIME ERROR & CRASH LOGS ===

Debug and solve the issue:
1. DIAGNOSE: Analyze the exact error and stack trace from the output above (e.g. unhandled exception, syntax error, missing import, port mismatch, undefined React variable/hook, route definition error, Django settings issue).
2. PINPOINT & SOLVE: Identify the root cause and provide the complete, working content for the affected files.
3. PRESERVE: Preserve existing functionality, models, authentication, and design. Do not strip features merely to suppress an error.
4. RETURN: Return complete file contents, not diffs, and include a clear summary of what bug was found and how you fixed it."""

        result = gemini_ai.modify_project(
            source_files,
            request_text,
            model_name=project.ai_model,
        ) or {}

        candidate_files = {
            **(result.get("files") or {}),
            **(result.get("new_files") or {}),
        }
        if len(candidate_files) > MAX_AUTO_REPAIR_FILES:
            raise RuntimeError("Auto-repair proposed too many file changes")

        changed_files = []
        for path, content in candidate_files.items():
            try:
                safe_path = normalize_file_path(path)
            except ValueError:
                continue
            if safe_path.endswith((".lock", ".env")) or "/.env" in safe_path:
                continue
            if not isinstance(content, str):
                continue
            if source_files.get(safe_path) == content:
                continue
            # Validate Python syntax if modifying a python file
            if safe_path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as syntax_err:
                    print(
                        f"[AutoRepair] Proposed file {safe_path} has syntax error: {syntax_err}",
                        flush=True,
                    )
                    continue
            save_generated_file(project, safe_path, content)
            changed_files.append(safe_path)

        if not changed_files:
            raise RuntimeError(
                result.get("summary") or "No safe source changes were proposed"
            )

        materialize_project(project, project_dir, clear=True)
        with _preview_jobs_lock:
            _preview_jobs[project_id] = {
                "status": "ready",
                "severity": "ready",
                "stage": "auto_repair",
                "message": "Auto-repair completed. Restarting the application.",
                "attempt_number": attempt_number,
                "max_attempts": MAX_AUTO_REPAIRS_PER_ERROR,
            }
        _set_auto_repair_job(
            project_id,
            status="ready",
            stage="auto_repair",
            message="Auto-repair applied. Restarting the generated project...",
            changed_files=changed_files,
            summary=result.get("summary", "Applied an automatic runtime repair."),
            attempt_number=attempt_number,
            max_attempts=MAX_AUTO_REPAIRS_PER_ERROR,
        )
    except Exception as error:
        _set_auto_repair_job(
            project_id,
            status="failed",
            stage="auto_repair",
            message="Auto-repair could not resolve the runtime error.",
            error=str(error),
            attempt_number=attempt_number,
            max_attempts=MAX_AUTO_REPAIRS_PER_ERROR,
        )
    finally:
        close_old_connections()


def _start_auto_repair(project_id, project_dir, output):
    """Schedule one repair attempt for a distinct runtime failure with attempt tracking."""
    output = output[-MAX_AUTO_REPAIR_LOG_CHARS:]
    fingerprint = hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()
    existing = _get_auto_repair_job(project_id)
    if existing and existing.get("fingerprint") == fingerprint:
        return existing
    with _auto_repair_jobs_lock:
        project_fingerprints = _auto_repair_fingerprints.setdefault(project_id, {})
        attempts = project_fingerprints.get(fingerprint, 0)
        if attempts >= MAX_AUTO_REPAIRS_PER_ERROR:
            return {
                "status": "failed",
                "stage": "auto_repair",
                "message": f"Maximum auto-repair attempts ({MAX_AUTO_REPAIRS_PER_ERROR}) reached for this error.",
                "error": "Repeated runtime error after maximum automatic repair attempts.",
                "output": output,
                "attempt_number": attempts + 1,
                "max_attempts": MAX_AUTO_REPAIRS_PER_ERROR,
            }
        # Increment attempt count
        attempt_number = attempts + 1
        project_fingerprints[fingerprint] = attempt_number
        # Create fingerprint with attempt suffix for job tracking
        attempt_fingerprint = f"{fingerprint}_attempt{attempt_number}"

    job = _set_auto_repair_job(
        project_id,
        status="repairing",
        stage="auto_repair",
        message=f"Runtime error detected. Auto Bug Detection & Fix agent is analyzing it (attempt {attempt_number}/{MAX_AUTO_REPAIRS_PER_ERROR})...",
        fingerprint=attempt_fingerprint,
        output=output,
        changed_files=[],
        attempt_number=attempt_number,
        max_attempts=MAX_AUTO_REPAIRS_PER_ERROR,
    )
    thread = threading.Thread(
        target=_auto_repair_project,
        args=(project_id, project_dir, output, attempt_number),
        daemon=True,
    )
    thread.start()
    return job


def _start_frontend_preparation(project_id, project_dir, script):
    """Start dependency preparation (Python venv + npm) in an OS process."""

    node_modules_dir = None
    if script:
        node_modules_dir = os.path.join(
            os.path.dirname(os.path.join(project_dir, script)),
            "node_modules",
        )

    # ---------------------------------------------------------
    # Mark as preparing BEFORE starting worker
    # ---------------------------------------------------------
    state = {
        "status": "preparing",
        "severity": "in-progress",
        "error": None,
        "stage": "preparing",
        "message": "Installing project dependencies (Python and npm).",
    }
    if node_modules_dir:
        state["package_dir"] = os.path.dirname(node_modules_dir)

    _write_preview_state(
        project_dir,
        state,
    )

    with _preview_jobs_lock:
        _preview_jobs[project_id] = state

    try:
        command = [PYTHON, "-m", "ai_services.preview_worker", project_dir]
        if script:
            command.append(script)

        process = subprocess.Popen(
            command,
            cwd=os.path.dirname(
                os.path.dirname(
                    os.path.abspath(__file__)
                )
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )

        print(
            f"[Buildify] Started frontend preparation worker "
            f"PID={process.pid} for project {project_id}",
            flush=True,
        )

        return state

    except Exception as error:
        state = {
            "status": "failed",
            "severity": "error",
            "stage": "npm_install",
            "error": str(error),
            "message": "Failed to start frontend preparation.",
        }

        _write_preview_state(
            project_dir,
            state,
        )

        with _preview_jobs_lock:
            _preview_jobs[project_id] = state

        return state


def _monitor_generated_processes(project_id, project_dir):
    """Watch a running generated app even when the browser is not polling."""
    while True:
        time.sleep(2)
        info = _running_processes.get(project_id)
        if not info:
            return
        stopped = [
            process_info for process_info in info["processes"]
            if process_info["proc"].poll() is not None
        ]
        if not stopped:
            continue
        output = "\n".join(
            "".join(process_info["output"][-100:])
            for process_info in info["processes"]
        )
        exit_code = stopped[0]["proc"].poll()
        _stop_process(project_id)
        _start_auto_repair(
            project_id,
            project_dir,
            output or f"Generated process exited with code {exit_code}",
        )
        return


def _start_process(project_id, project_dir, script):
    if project_id in _running_processes:
        _stop_process(project_id)

    scripts = [script]
    frontend_script = script if script.endswith("package.json") else None
    backend_script = None

    for candidate in (
        "manage.py",
        os.path.join("backend", "manage.py"),
        os.path.join("server", "manage.py"),
    ):
        if os.path.exists(os.path.join(project_dir, candidate)):
            backend_script = candidate
            break

    if frontend_script and backend_script:
        scripts = [backend_script, frontend_script]

    # ---------------------------------------------------------
    # Dependency preparation (Python venv + npm)
    # ---------------------------------------------------------
    job = _get_preview_job(project_id)

    if job and job.get("status") == "preparing":
        return None, {
            "status": "preparing",
            "severity": "in-progress",
            "error": None,
            "stage": job.get("stage", "preparing"),
            "message": job.get("message")
            or "Installing project dependencies (Python and npm).",
        }

    node_modules_missing = False
    if frontend_script:
        node_modules_missing = not os.path.isdir(
            os.path.join(
                os.path.dirname(os.path.join(project_dir, frontend_script)),
                "node_modules",
            )
        )
    python_deps_missing = bool(backend_script) and not requirements_ready(project_dir)

    if python_deps_missing or node_modules_missing:
        if job and job.get("status") in {
            # Permanent environment problems: do not spin on them.
            "environment-unavailable",
            "not-ready",
        }:
            return None, job

        # "failed" states (pip/npm errors) fall through and retry on the
        # next Run click; markers only exist after a successful install.
        job = _start_frontend_preparation(
            project_id,
            project_dir,
            frontend_script,
        )

        return None, {
            "status": "preparing",
            "severity": "in-progress",
            "error": None,
            "stage": job.get("stage", "preparing"),
            "message": "Installing project dependencies (Python and npm).",
        }

    processes = []
    frontend_info = None
    used_ports = set()

    try:
        for current_script in scripts:
            file_port = (
                _detect_port_from_files(project_dir)
                if current_script == backend_script
                else None
            )

            port = file_port if file_port and _port_is_available(file_port) else None
            if port is None:
                port = _find_free_port(used_ports)
            used_ports.add(port)

            cmd = _get_run_command(
                project_dir,
                current_script,
                port,
            )

            env = generated_env()
            env["PORT"] = str(port)
            env["FLASK_RUN_PORT"] = str(port)
            env["FLASK_APP"] = "app.py"
            env["PYTHONDONTWRITEBYTECODE"] = "1"

            # Never allow Buildify's Django settings to leak
            # into the generated project.
            env.pop("DJANGO_SETTINGS_MODULE", None)

            if current_script.endswith("manage.py"):
                settings_module = _detect_settings_module(
                    project_dir,
                    current_script,
                )

                if settings_module:
                    env["DJANGO_SETTINGS_MODULE"] = settings_module

            cwd = project_dir
            script_dir = os.path.dirname(current_script)

            if current_script.endswith("package.json"):
                cwd = os.path.dirname(
                    os.path.join(project_dir, current_script)
                )

            elif current_script.endswith(".py") and script_dir:
                cwd = os.path.join(
                    project_dir,
                    script_dir,
                )

                cmd[1] = os.path.basename(current_script)

            python_paths = [cwd]

            for source_dir in ("backend", "src"):
                source_path = os.path.join(
                    project_dir,
                    source_dir,
                )

                if (
                    os.path.isdir(source_path)
                    and source_path not in python_paths
                ):
                    python_paths.append(source_path)

            existing_python_path = env.get("PYTHONPATH")

            if existing_python_path:
                python_paths.append(existing_python_path)

            env["PYTHONPATH"] = os.pathsep.join(
                python_paths
            )

            popen_kwargs = {
                "cwd": cwd,
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
                "creationflags": getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            }

            if os.name == "posix":
                # Own session/process group so stopping can terminate npm's
                # and the dev server's grandchildren; otherwise orphaned
                # children keep writing to the workspace during materialize.
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(
                cmd,
                **popen_kwargs,
            )

            output_lines = []

            def reader(process=proc, lines=output_lines):
                for line in iter(
                    process.stdout.readline,
                    "",
                ):
                    lines.append(line)

            thread = threading.Thread(
                target=reader,
                daemon=True,
            )

            thread.start()

            info = {
                "proc": proc,
                "port": port,
                "script": current_script,
                "output": output_lines,
                "thread": thread,
                "cwd": cwd,
                "command_display": _format_command(cmd),
            }

            processes.append(info)

            if (
                frontend_script
                and current_script == frontend_script
            ):
                frontend_info = info

    except Exception as error:
        for info in processes:
            try:
                _terminate_process_tree(info["proc"])
            except Exception:
                pass

        return None, str(error)

    _running_processes[project_id] = {
        "processes": processes,
        "port": (
            frontend_info["port"]
            if frontend_info
            else processes[0]["port"]
        ),
        "pid": (
            frontend_info["proc"].pid
            if frontend_info
            else processes[0]["proc"].pid
        ),
        "started_at": time.time(),
    }

    threading.Thread(
        target=_monitor_generated_processes,
        args=(project_id, project_dir),
        daemon=True,
    ).start()

    return {
        "port": _running_processes[project_id]["port"],
        "pid": _running_processes[project_id]["pid"],
    }, None

def _detect_settings_module(project_dir, manage_script):
    """Read the generated manage.py setting without importing Buildify settings."""
    manage_path = os.path.join(project_dir, manage_script)
    try:
        with open(manage_path, "r", encoding="utf-8", errors="replace") as manage_file:
            source = manage_file.read()
    except OSError:
        return None
    match = re.search(
        r"DJANGO_SETTINGS_MODULE\s*['\"]?\s*\]\s*=\s*['\"]([^'\"]+)['\"]",
        source,
    ) or re.search(
        r"DJANGO_SETTINGS_MODULE['\"]?\s*,\s*['\"]([^'\"]+)['\"]",
        source,
    )
    return match.group(1) if match else None


def _wait_for_port(port, process, timeout=60):
    deadline = time.time() + timeout

    while time.time() < deadline:
        # Process already exited
        if process.poll() is not None:
            return False

        try:
            with socket.create_connection(
                ("127.0.0.1", port),
                timeout=0.5,
            ):
                return True

        except OSError:
            time.sleep(0.25)

    return False


def _terminate_process_tree(proc, timeout=5):
    """Terminate a generated process and any children in its group.

    ``npm run``/``vite`` and Django's runserver reloader spawn grandchildren;
    killing only the direct child leaves orphans that hold ports and keep
    writing into the workspace. On POSIX the process runs in its own session
    (see ``_start_process``), so signaling the process group reaches them.
    """
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
    else:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass


def _stop_process(project_id):
    info = _running_processes.pop(project_id, None)
    if not info:
        return False
    for process_info in info["processes"]:
        try:
            _terminate_process_tree(process_info["proc"])
        except Exception:
            pass
    return True


@api_view(["GET"])
def list_projects(request):
    projects = []
    for project in Project.objects.all().order_by("id"):
        files = load_project_files(project)
        projects.append({
            "id": f"project_{project.pk}",
            "name": project.name,
            "path": os.path.join(PROJECTS_DIR, f"project_{project.pk}"),
            "files": _serialized_project_files(project),
            "file_count": len(files),
        })

    return Response(projects)


@api_view(["GET"])
def project_files(request, project_id):
    project, project_dir = _project_workspace(project_id)
    if project is None:
        return Response(
            {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )

    files = _serialized_project_files(project)
    return Response({"project_id": project_id, "files": files})


@api_view(["GET"])
def read_file(request, project_id):
    file_path = request.query_params.get("file_path")
    if not file_path:
        return Response({"error": "file_path parameter required"}, status=status.HTTP_400_BAD_REQUEST)

    project, project_dir = _project_workspace(project_id)
    if project is None:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
    try:
        file_path = normalize_file_path(file_path)
    except ValueError:
        return Response({"error": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST)
    full_path = os.path.normpath(os.path.join(project_dir, file_path))

    if not full_path.startswith(os.path.normpath(project_dir)):
        return Response(
            {"error": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST
        )

    persisted_files = load_project_files(project)
    if file_path not in persisted_files:
        return Response(
            {"error": "File not found"}, status=status.HTTP_404_NOT_FOUND
        )

    content = persisted_files[file_path]

    return Response({"path": file_path, "content": content})


@api_view(["POST"])
def run_project(request, project_id):
    # First resolve the project WITHOUT rebuilding/clearing
    # its runtime workspace.
    project, project_dir = _project_workspace(
        project_id,
        materialize=False,
    )

    if project is None:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # A fresh run supersedes any previous auto-repair outcome. Without this,
    # run_status keeps returning the stale "failed" repair job on every poll,
    # so the frontend would stop polling (and hide the preview) even though
    # the newly started app is running.
    existing_repair = _get_auto_repair_job(project_id)
    if existing_repair and existing_repair.get("status") != "repairing":
        with _auto_repair_jobs_lock:
            _auto_repair_jobs.pop(project_id, None)

    # If this project already has a preview process, reuse it.
    if project_id in _running_processes:
        info = _running_processes[project_id]

        if all(
            process_info["proc"].poll() is None
            for process_info in info["processes"]
        ):
            return _attach_preview_cookie(request, Response({
                "status": "running",
                "port": info["port"],
                "pid": info["pid"],
                "preview_token": _issue_preview_token(request, project),
                "pids": [
                    process_info["proc"].pid
                    for process_info in info["processes"]
                ],
                "message": f"Already running on port {info['port']}",
            }), project)

        _running_processes.pop(project_id, None)

    # Only materialize when we actually need a fresh runtime workspace.
    preview_job = _get_preview_job(project_id)

    if not preview_job or preview_job.get("status") not in {
        "preparing",
        "ready",
    }:
        materialize_project(
            project,
            project_dir,
            clear=True,
        )

    run_script = _find_run_script(project_dir)

    if not run_script:
        return Response(
            {
                "error": (
                    "No runnable script found "
                    "(main.py, app.py, manage.py, or package.json)"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    result, error = _start_process(
        project_id,
        project_dir,
        run_script,
    )

    if error:
        if isinstance(error, dict):
            return Response(
                error,
                status=(
                    status.HTTP_200_OK
                    if error.get("status") in {
                        "preparing",
                        "not-ready",
                        "environment-unavailable",
                    }
                    else status.HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        return Response(
            {
                "error": (
                    f"Failed to start process: {error}"
                )
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    time.sleep(0.5)

    proc_info = _running_processes.get(project_id)

    if not proc_info:
        return Response(
            {
                "error": "Preview process information was lost"
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    for process_info in proc_info["processes"]:
        process_info["thread"].join(timeout=0.2)

    stopped = [
        process_info
        for process_info in proc_info["processes"]
        if process_info["proc"].poll() is not None
    ]

    if stopped:
        process_info = stopped[0]
        exit_code = process_info["proc"].poll()
        output = "".join(
            process_info["output"][-30:]
        )

        _stop_process(project_id)

        repair_job = _start_auto_repair(
            project_id,
            project_dir,
            output or f"Process exited with code {exit_code}",
        )
        if repair_job.get("status") in {"repairing", "ready"}:
            return Response(repair_job)

        return Response(
            {
                "error": f"Process exited with code {exit_code}",
                "output": output,
                "terminal": _terminal_agent_snapshot(
                    project_id,
                    project_dir,
                    {
                        "processes": [process_info]
                    },
                ),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not _wait_for_port(
        result["port"],
        proc_info["processes"][-1]["proc"],
    ):
        output = "\n".join(
            "".join(
                process_info["output"][-100:]
            )
            for process_info in proc_info["processes"]
        )

        _stop_process(project_id)

        repair_job = _start_auto_repair(
            project_id,
            project_dir,
            output or f"Preview port {result['port']} did not become reachable",
        )
        if repair_job.get("status") in {"repairing", "ready"}:
            return Response(repair_job)

        return Response(
            {
                "error": (
                    "Preview process started but "
                    f"port {result['port']} "
                    "did not become reachable"
                ),
                "output": output[-4000:],
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return _attach_preview_cookie(request, Response({
        "status": "running",
        "port": result["port"],
        "pid": result["pid"],
        "preview_token": _issue_preview_token(request, project),
        "pids": [
            process_info["proc"].pid
            for process_info in proc_info["processes"]
        ],
        "message": (
            f"App running on port {result['port']}"
        ),
        "terminal": _terminal_agent_snapshot(
            project_id,
            project_dir,
            proc_info,
        ),
    }), project)

@api_view(["POST"])
def stop_project(request, project_id):
    stopped = _stop_process(project_id)
    if stopped:
        return Response({"status": "stopped", "message": "Process terminated"})
    return Response({"status": "not_running", "message": "No running process found"})


@api_view(["GET"])
def run_status(request, project_id):
    project, project_dir = _project_workspace(
        project_id,
        materialize=False,
    )

    if project is None:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    repair_job = _get_auto_repair_job(project_id)
    if repair_job:
        if repair_job.get("status") == "repairing":
            return Response({
                **repair_job,
                "output": repair_job.get("output", ""),
            })
        if repair_job.get("status") == "failed":
            return Response(repair_job)
        if repair_job.get("status") == "ready":
            ready_snapshot = dict(repair_job)
            with _auto_repair_jobs_lock:
                _auto_repair_jobs.pop(project_id, None)
            return Response(ready_snapshot)

    filesystem_job = _read_preview_state(
        project_dir
    )

    if filesystem_job:
        with _preview_jobs_lock:
            _preview_jobs[project_id] = filesystem_job
    if project_id not in _running_processes:
        job = _get_preview_job(project_id)

        if job:
            if job.get("status") == "preparing":
                return Response(job)

            if job.get("status") == "ready":
                project, project_dir = _project_workspace(
                    project_id,
                    materialize=False,
                )

                if project is None:
                    return Response(
                        {"error": "Project not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                run_script = _find_run_script(project_dir)

                if not run_script:
                    return Response({
                        "status": "failed",
                        "error": "No runnable script found",
                    })

                result, error = _start_process(
                    project_id,
                    project_dir,
                    run_script,
                )

                if error:
                    if isinstance(error, dict):
                        return Response(error)

                    return Response({
                        "status": "failed",
                        "error": str(error),
                    })

                return Response({
                    "status": "starting",
                    "port": result["port"],
                    "pid": result["pid"],
                    "message": "Frontend dependencies are ready. Starting the application...",
                })

            return Response(job)

        return Response({
            "status": "not_running"
        })

    info = _running_processes[project_id]

    stopped = [
        process_info
        for process_info in info["processes"]
        if process_info["proc"].poll() is not None
    ]

    if stopped:
        poll = stopped[0]["proc"].poll()
        output = "\n".join(
            "".join(process_info["output"][-100:])
            for process_info in stopped
        )
        _stop_process(project_id)

        repair_job = _start_auto_repair(
            project_id,
            project_dir,
            output or f"Process exited with code {poll}",
        )
        if repair_job.get("status") in {"repairing", "ready"}:
            return Response(repair_job)

        return Response({
            "status": "stopped",
            "exit_code": poll,
        })

    # Refresh the preview cookie on every running poll so an active session
    # never hits the signed-token expiry while the app is up.
    return _attach_preview_cookie(request, Response({
        "status": "running",
        "port": info["port"],
        "pid": info["pid"],
        "pids": [
            process_info["proc"].pid
            for process_info in info["processes"]
        ],
        "terminal": _terminal_agent_snapshot(
            project_id,
            os.path.join(
                PROJECTS_DIR,
                str(project_id),
            ),
            info,
        ),
    }), project)

@api_view(["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@permission_classes([AllowAny])
def preview_project(request, project_id, preview_path=""):
    """
    Proxy requests from the Buildify browser to the generated
    project's frontend or backend process.
    """

    project, project_dir = _project_workspace(
        project_id,
        materialize=False,
    )

    if project is None:
        return Response(
            {"error": "Project not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    process_info = _running_processes.get(project_id)

    if not process_info:
        # Report the actionable state before the auth check so a user opening
        # preview for a project that was never successfully started sees
        # "start it first" instead of a bare 403.
        return Response(
            {
                "error": (
                    "Preview is not running. "
                    "Start the project from the dashboard to open its preview."
                ),
                "status": "not_running",
            },
            status=status.HTTP_409_CONFLICT,
        )

    if not _has_preview_access(request, project):
        return Response(
            {"error": "A valid preview token is required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ---------------------------------------------------------
    # Find generated backend and frontend processes
    # ---------------------------------------------------------
    backend_process = None
    frontend_process = None

    for info in process_info["processes"]:
        if info["script"].endswith("package.json"):
            frontend_process = info
        else:
            # manage.py, main.py, app.py — anything that is not the frontend.
            backend_process = info

    # ---------------------------------------------------------
    # Clean preview path
    # ---------------------------------------------------------
    preview_path = preview_path.lstrip("/")

    # ---------------------------------------------------------
    # Determine whether request belongs to backend or frontend
    # ---------------------------------------------------------
    is_backend_request = (
        preview_path == "api"
        or preview_path.startswith("api/")
    )

    if is_backend_request:
        target_process = backend_process
    else:
        # Prefer the frontend dev server; fall back to the backend for
        # Python-only projects that serve their own pages.
        target_process = frontend_process or backend_process

    if target_process is None:
        return Response(
            {
                "error": (
                    "Generated backend process is not running."
                    if is_backend_request
                    else "No generated process is running."
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )

    target_port = target_process["port"]

    # ---------------------------------------------------------
    # Build target URL
    # ---------------------------------------------------------
    target_url = (
        f"http://127.0.0.1:{target_port}/"
        f"{preview_path}"
    )

    if request.META.get("QUERY_STRING"):
        forwarded_pairs = [
            (key, value)
            for key, value in parse_qsl(
                request.META["QUERY_STRING"], keep_blank_values=True
            )
            # Never leak Buildify's own preview token to the generated app.
            if key != "preview_token"
        ]
        if forwarded_pairs:
            target_url += f"?{urlencode(forwarded_pairs)}"

    # ---------------------------------------------------------
    # Forward required headers
    # ---------------------------------------------------------
    headers = {}

    for header_name in (
        "Content-Type",
        "Accept",
        "User-Agent",
        "Authorization",
    ):
        value = request.META.get(
            f"HTTP_{header_name.upper().replace('-', '_')}"
        )

        if value:
            headers[header_name] = value

    body = (
        request.body
        if request.method not in {"GET", "HEAD"}
        else None
    )

    proxy_request = Request(
        target_url,
        data=body,
        headers=headers,
        method=request.method,
    )

    # ---------------------------------------------------------
    # Forward request to generated process
    # ---------------------------------------------------------
    try:
        with urlopen(
            proxy_request,
            timeout=30,
        ) as upstream:

            response_body = _inject_preview_runtime(
                upstream.read(),
                upstream.headers.get("Content-Type", "text/plain"),
                project.pk,
            )

            content_type = upstream.headers.get(
                "Content-Type",
                "text/plain",
            )

            response = HttpResponse(
                response_body,
                status=upstream.status,
                content_type=content_type,
            )

            for header_name in (
                "Cache-Control",
                "ETag",
                "Last-Modified",
            ):
                value = upstream.headers.get(header_name)

                if value:
                    response[header_name] = value

            # The token in the initial iframe URL is exchanged for a scoped
            # cookie so generated asset and API requests remain authorized.
            # The cookie must be visible at the site root because preview
            # assets are also served for root-level requests dispatched by
            # the host catch-all view.
            response.set_cookie(
                _preview_cookie_name(project.pk),
                request.GET.get("preview_token") or request.COOKIES.get(
                    _preview_cookie_name(project.pk)
                ),
                max_age=PREVIEW_TOKEN_MAX_AGE,
                httponly=True,
                secure=request.is_secure(),
                samesite="Lax",
                path="/",
            )

            return response

    except HTTPError as error:
        try:
            response_body = error.read()
        except Exception:
            response_body = str(error).encode()

        return HttpResponse(
            response_body,
            status=error.code,
            content_type=error.headers.get(
                "Content-Type",
                "text/plain",
            ),
        )

    except URLError as error:
        return Response(
            {
                "error": "Unable to connect to preview process",
                "detail": str(error.reason),
                "port": target_port,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except Exception as error:
        return Response(
            {
                "error": "Preview proxy failed",
                "detail": str(error),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    
@api_view(["POST"])
def modify_project(request, project_id):
    project, project_dir = _project_workspace(project_id)
    if project is None:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    modification = request.data.get("modification")
    if not modification:
        return Response({"error": "modification parameter required"}, status=status.HTTP_400_BAD_REQUEST)

    source_files = load_project_files(project)
    model_name = request.data.get("model")

    try:
        result = gemini_ai.modify_project(source_files, modification, model_name=model_name)
    except gemini_ai.GeminiAPIError as error:
        is_rate_limited = error.status_code == 429 or "resource_exhausted" in str(error).lower()
        if is_rate_limited:
            return Response(
                {
                    "error": "AI provider rate limit exceeded",
                    "code": "rate_limit_exceeded",
                    "detail": str(error),
                    "model": gemini_ai.MODEL_NAME,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response(
            {
                "error": "AI provider request failed",
                "code": "ai_provider_error",
                "detail": str(error),
                "model": gemini_ai.MODEL_NAME,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if not result:
        return Response({"error": "AI modification failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    changed_files = []
    all_files = result.get("files", {})
    for fname, content in all_files.items():
        save_generated_file(project, fname, content)
        changed_files.append(fname)

    new_files = result.get("new_files", {})
    for fname, content in new_files.items():
        save_generated_file(project, fname, content)
        changed_files.append(fname)

    for fname in result.get("deleted_files", []):
        delete_generated_file(project, fname)
        changed_files.append(f"deleted:{fname}")

    files = _serialized_project_files(project)
    return Response({
        "summary": result.get("summary", ""),
        "changed_files": changed_files,
        "files": files,
    })


@api_view(["POST"])
def project_chat(request, project_id):
    """Chat about a persisted generated project, with optional explicit application of changes."""
    project, _ = _project_workspace(project_id)
    if project is None:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    message = str(request.data.get("message", "")).strip()
    if not message:
        return Response({"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST)
    conversation = request.data.get("conversation", [])
    if not isinstance(conversation, list):
        return Response({"error": "conversation must be a list"}, status=status.HTTP_400_BAD_REQUEST)
    apply_changes = bool(request.data.get("apply_changes", False))
    model_name = request.data.get("model")

    try:
        result = gemini_ai.project_chat(
            load_project_files(project),
            message,
            conversation=conversation[-20:],
            apply_changes=apply_changes,
            model_name=model_name,
        )
    except gemini_ai.GeminiAPIError as error:
        return Response(
            {
                "error": str(error),
                "detail": str(error),
                "code": "ai_provider_error",
            },
            status=error.status_code if isinstance(error.status_code, int) and 400 <= error.status_code <= 599 else status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as error:
        return Response(
            {
                "error": "Project modification failed",
                "detail": str(error),
                "code": "project_chat_error",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if not result:
        return Response({"error": "Project chat failed"}, status=status.HTTP_502_BAD_GATEWAY)

    changed_files = []
    if apply_changes:
        for filename, content in (result.get("files") or {}).items():
            try:
                save_generated_file(project, filename, content)
            except ValueError as error:
                return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
            changed_files.append(filename)
        for filename, content in (result.get("new_files") or {}).items():
            try:
                save_generated_file(project, filename, content)
            except ValueError as error:
                return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
            changed_files.append(filename)
        for filename in result.get("deleted_files") or []:
            try:
                delete_generated_file(project, filename)
            except ValueError as error:
                return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
            changed_files.append(f"deleted:{filename}")

    result["changed_files"] = changed_files
    result["files"] = _serialized_project_files(project)
    result["changes_applied"] = bool(apply_changes and changed_files)
    return Response(result)


@api_view(["PUT"])
def save_file(request, project_id):
    project, project_dir = _project_workspace(project_id)
    if project is None:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    file_path = request.data.get("file_path")
    content = request.data.get("content")
    if not file_path or content is None:
        return Response({"error": "file_path and content required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        file_path = normalize_file_path(file_path)
    except ValueError:
        return Response({"error": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST)
    save_generated_file(project, file_path, content)

    files = _serialized_project_files(project)
    return Response({"status": "saved", "path": file_path, "files": files})


def _serialized_project_files(project):
    return [
        {
            "path": item.path,
            "size": len(item.content.encode("utf-8")),
            "lines": item.line_count,
            "added_lines": item.added_lines,
            "removed_lines": item.removed_lines,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in GeneratedFile.objects.filter(project=project).only(
            "path", "content", "updated_at", "line_count", "added_lines", "removed_lines"
        )
    ]


def _find_run_script(project_dir):
    package_candidates = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in {"node_modules", ".git", ".venv", "__pycache__"}]
        if "package.json" in files:
            package_candidates.append(os.path.relpath(os.path.join(root, "package.json"), project_dir))
    for package_path in sorted(package_candidates):
        try:
            with open(os.path.join(project_dir, package_path), encoding="utf-8") as package_file:
                package = json.load(package_file)
        except (OSError, json.JSONDecodeError):
            continue
        scripts = package.get("scripts", {})
        if "dev" in scripts or "start" in scripts:
            return package_path

    if os.path.exists(os.path.join(project_dir, "manage.py")):
        return "manage.py"
    if os.path.exists(os.path.join(project_dir, "main.py")):
        return "main.py"
    if os.path.exists(os.path.join(project_dir, "app.py")):
        return "app.py"
    if os.path.exists(os.path.join(project_dir, "package.json")):
        return "package.json"

    for sub in ["backend", "server", "src", "app"]:
        sub_path = os.path.join(project_dir, sub)
        if os.path.isdir(sub_path):
            for name in ["manage.py", "main.py", "app.py"]:
                if os.path.exists(os.path.join(sub_path, name)):
                    return os.path.join(sub, name)
            if os.path.exists(os.path.join(sub_path, "package.json")):
                return os.path.join(sub, "package.json")

    for fname in os.listdir(project_dir):
        if fname.endswith(".py") and not fname.startswith("test_"):
            return fname

    return None


def _get_requirements_dir(project_dir, script):
    if os.path.exists(os.path.join(project_dir, "requirements.txt")):
        return project_dir
    script_dir = os.path.dirname(os.path.join(project_dir, script))
    if os.path.exists(os.path.join(script_dir, "requirements.txt")):
        return script_dir
    return None

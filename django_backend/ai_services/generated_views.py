import os
import json
import re
import socket
import subprocess
import sys
import threading
import time

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from . import gemini_ai

PYTHON = sys.executable

PROJECTS_DIR = settings.GENERATED_PROJECTS_DIR

_running_processes = {}


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


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
            req_dir = os.path.dirname(os.path.join(project_dir, script))
        if req_dir:
            req_file = os.path.join(req_dir, "requirements.txt")
            if not os.path.exists(req_file):
                with open(req_file, "w") as f:
                    f.write("django\n")
            try:
                subprocess.run(
                    [PYTHON, "-m", "pip", "install", "-r", req_file, "-q"],
                    cwd=req_dir,
                    timeout=120,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                pass
        return [PYTHON, script, "runserver", f"127.0.0.1:{port or 0}", "--noreload"]
    if script.endswith(".py"):
        req_dir = _get_requirements_dir(project_dir, script)
        if req_dir:
            req_file = os.path.join(req_dir, "requirements.txt")
            if os.path.exists(req_file):
                try:
                    subprocess.run(
                        [PYTHON, "-m", "pip", "install", "-r", req_file, "-q"],
                        cwd=req_dir,
                        timeout=120,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception:
                    pass
        return [PYTHON, script]
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
        if port:
            command.extend(["--", "--host", "127.0.0.1", "--port", str(port)])
        return command
    return [PYTHON, script]


def _ensure_node_dependencies(project_dir, script):
    if not script.endswith("package.json"):
        return None

    package_dir = os.path.dirname(os.path.join(project_dir, script))
    if os.path.isdir(os.path.join(package_dir, "node_modules")):
        return None

    npm_command = "npm.cmd" if os.name == "nt" else "npm"
    try:
        result = subprocess.run(
            [npm_command, "install"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"Unable to install JavaScript dependencies: {error}"

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "npm install failed").strip()
        return f"Unable to install JavaScript dependencies: {details[-1000:]}"
    return None


def _start_process(project_id, project_dir, script):
    if project_id in _running_processes:
        _stop_process(project_id)

    scripts = [script]
    frontend_script = script if script.endswith("package.json") else None
    backend_script = None
    for candidate in ("manage.py", os.path.join("backend", "manage.py"), os.path.join("server", "manage.py")):
        if os.path.exists(os.path.join(project_dir, candidate)):
            backend_script = candidate
            break
    if frontend_script and backend_script:
        scripts = [backend_script, frontend_script]

    processes = []
    frontend_info = None
    try:
        for current_script in scripts:
            file_port = _detect_port_from_files(project_dir) if current_script == backend_script else None
            port = file_port or _find_free_port()
            dependency_error = _ensure_node_dependencies(project_dir, current_script)
            if dependency_error:
                raise RuntimeError(dependency_error)

            cmd = _get_run_command(project_dir, current_script, port)
            env = os.environ.copy()
            env["PORT"] = str(port)
            env["FLASK_RUN_PORT"] = str(port)
            env["FLASK_APP"] = "app.py"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env.pop("DJANGO_SETTINGS_MODULE", None)
            if current_script.endswith("manage.py"):
                settings_module = _detect_settings_module(project_dir, current_script)
                if settings_module:
                    env["DJANGO_SETTINGS_MODULE"] = settings_module

            cwd = project_dir
            script_dir = os.path.dirname(current_script)
            if current_script.endswith("package.json"):
                cwd = os.path.dirname(os.path.join(project_dir, current_script))
            elif current_script.endswith(".py") and script_dir:
                cwd = os.path.join(project_dir, script_dir)
                cmd[1] = os.path.basename(current_script)

            python_paths = [cwd]
            for source_dir in ("backend", "src"):
                source_path = os.path.join(project_dir, source_dir)
                if os.path.isdir(source_path) and source_path not in python_paths:
                    python_paths.append(source_path)
            existing_python_path = env.get("PYTHONPATH")
            if existing_python_path:
                python_paths.append(existing_python_path)
            env["PYTHONPATH"] = os.pathsep.join(python_paths)

            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output_lines = []

            def reader(process=proc, lines=output_lines):
                for line in iter(process.stdout.readline, ""):
                    lines.append(line)

            thread = threading.Thread(target=reader, daemon=True)
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
            if frontend_script and current_script == frontend_script:
                frontend_info = info
    except Exception as error:
        for info in processes:
            info["proc"].terminate()
        return None, str(error)

    _running_processes[project_id] = {
        "processes": processes,
        "port": frontend_info["port"] if frontend_info else processes[0]["port"],
        "pid": frontend_info["proc"].pid if frontend_info else processes[0]["proc"].pid,
        "started_at": time.time(),
    }
    return {"port": _running_processes[project_id]["port"], "pid": _running_processes[project_id]["pid"]}, None


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


def _wait_for_port(port, process, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _stop_process(project_id):
    info = _running_processes.pop(project_id, None)
    if not info:
        return False
    for process_info in info["processes"]:
        proc = process_info["proc"]
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass
    return True


@api_view(["GET"])
def list_projects(request):
    if not os.path.exists(PROJECTS_DIR):
        return Response([])

    projects = []
    for name in sorted(os.listdir(PROJECTS_DIR)):
        path = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(path):
            files = _list_files(path)
            projects.append({
                "id": name,
                "name": name.replace("project_", "Project "),
                "path": path,
                "files": files,
                "file_count": len(files),
            })

    return Response(projects)


@api_view(["GET"])
def project_files(request, project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return Response(
            {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )

    files = _list_files(project_dir)
    return Response({"project_id": project_id, "files": files})


@api_view(["GET"])
def read_file(request, project_id):
    file_path = request.query_params.get("file_path")
    if not file_path:
        return Response({"error": "file_path parameter required"}, status=status.HTTP_400_BAD_REQUEST)

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    full_path = os.path.normpath(os.path.join(project_dir, file_path))

    if not full_path.startswith(os.path.normpath(project_dir)):
        return Response(
            {"error": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST
        )

    if not os.path.exists(full_path):
        return Response(
            {"error": "File not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return Response(
            {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({"path": file_path, "content": content})


@api_view(["POST"])
def run_project(request, project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return Response(
            {"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if project_id in _running_processes:
        info = _running_processes[project_id]
        if all(process_info["proc"].poll() is None for process_info in info["processes"]):
            return Response({
                "status": "running",
                "port": info["port"],
                "pid": info["pid"],
                "pids": [process_info["proc"].pid for process_info in info["processes"]],
                "message": f"Already running on port {info['port']}",
            })
        else:
            _running_processes.pop(project_id, None)

    run_script = _find_run_script(project_dir)
    if not run_script:
        return Response(
            {"error": "No runnable script found (main.py, app.py, manage.py, or package.json)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result, error = _start_process(project_id, project_dir, run_script)
    if error:
        return Response(
            {"error": f"Failed to start process: {error}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    time.sleep(0.5)

    proc_info = _running_processes.get(project_id)
    if proc_info:
        for process_info in proc_info["processes"]:
            process_info["thread"].join(timeout=3)
        stopped = [process_info for process_info in proc_info["processes"] if process_info["proc"].poll() is not None]
        if stopped:
            process_info = stopped[0]
            exit_code = process_info["proc"].poll()
            output = "".join(process_info["output"][-30:])
            _stop_process(project_id)
            return Response(
                {
                    "error": f"Process exited with code {exit_code}",
                    "output": output,
                    "terminal": _terminal_agent_snapshot(
                        project_id, project_dir, {"processes": [process_info]}
                    ),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not _wait_for_port(result["port"], proc_info["processes"][-1]["proc"]):
            output = "\n".join(
                "".join(process_info["output"][-30:])
                for process_info in proc_info["processes"]
            )
            _stop_process(project_id)
            return Response(
                {
                    "error": f"Preview process started but port {result['port']} did not become reachable",
                    "output": output[-4000:],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    return Response({
        "status": "running",
        "port": result["port"],
        "pid": result["pid"],
        "pids": [process_info["proc"].pid for process_info in proc_info["processes"]],
        "message": f"App running on port {result['port']}",
        "terminal": _terminal_agent_snapshot(project_id, project_dir, proc_info),
    })


@api_view(["POST"])
def stop_project(request, project_id):
    stopped = _stop_process(project_id)
    if stopped:
        return Response({"status": "stopped", "message": "Process terminated"})
    return Response({"status": "not_running", "message": "No running process found"})


@api_view(["GET"])
def run_status(request, project_id):
    if project_id not in _running_processes:
        return Response({"status": "not_running"})

    info = _running_processes[project_id]
    stopped = [process_info for process_info in info["processes"] if process_info["proc"].poll() is not None]
    if stopped:
        poll = stopped[0]["proc"].poll()
        _stop_process(project_id)
        return Response({"status": "stopped", "exit_code": poll})

    return Response({
        "status": "running",
        "port": info["port"],
        "pid": info["pid"],
        "pids": [process_info["proc"].pid for process_info in info["processes"]],
        "terminal": _terminal_agent_snapshot(
            project_id, os.path.join(PROJECTS_DIR, project_id), info
        ),
    })


@api_view(["POST"])
def modify_project(request, project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    modification = request.data.get("modification")
    if not modification:
        return Response({"error": "modification parameter required"}, status=status.HTTP_400_BAD_REQUEST)

    source_files = {}
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "node_modules", ".git", ".venv"}]
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, project_dir)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    source_files[rel_path] = f.read()
            except Exception:
                pass

    try:
        result = gemini_ai.modify_project(source_files, modification)
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
        fpath = os.path.join(project_dir, fname)
        os.makedirs(os.path.dirname(fpath) if os.path.dirname(fpath) else project_dir, exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        changed_files.append(fname)

    new_files = result.get("new_files", {})
    for fname, content in new_files.items():
        fpath = os.path.join(project_dir, fname)
        os.makedirs(os.path.dirname(fpath) if os.path.dirname(fpath) else project_dir, exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        changed_files.append(fname)

    for fname in result.get("deleted_files", []):
        fpath = os.path.join(project_dir, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            changed_files.append(f"deleted:{fname}")

    files = _list_files(project_dir)
    return Response({
        "summary": result.get("summary", ""),
        "changed_files": changed_files,
        "files": files,
    })


@api_view(["PUT"])
def save_file(request, project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    file_path = request.data.get("file_path")
    content = request.data.get("content")
    if not file_path or content is None:
        return Response({"error": "file_path and content required"}, status=status.HTTP_400_BAD_REQUEST)

    full_path = os.path.normpath(os.path.join(project_dir, file_path))
    if not full_path.startswith(os.path.normpath(project_dir)):
        return Response({"error": "Invalid path"}, status=status.HTTP_400_BAD_REQUEST)

    os.makedirs(os.path.dirname(full_path) if os.path.dirname(full_path) else project_dir, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    files = _list_files(project_dir)
    return Response({"status": "saved", "path": file_path, "files": files})


def _list_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "node_modules", ".git", ".venv"}]
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root)
            size = os.path.getsize(full_path)
            files.append({"path": rel_path, "size": size})
    return sorted(files, key=lambda x: x["path"])


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

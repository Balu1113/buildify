"""Shared helpers for running generated (child) projects.

Stdlib-only on purpose: imported by the pipeline service, the preview views,
and the dependency-preparation worker (`python -m ai_services.preview_worker`),
which must not import Django.
"""

import hashlib
import os
import subprocess
import sys

REQUIREMENTS_MARKER_DIR = os.path.join(".pipeline", "requirements")


def ensure_project_python(project_dir):
    """Return the project-local Python, creating its virtualenv on demand."""
    venv_dir = os.path.join(project_dir, ".venv")
    python_name = "Scripts\\python.exe" if os.name == "nt" else "bin/python"
    executable = os.path.join(venv_dir, python_name)
    if not os.path.exists(executable):
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True,
            timeout=180,
        )
    return executable


def generated_env(roots=None):
    """Copy of the host environment with Buildify/Django config stripped out.

    Generated projects must never see the host DATABASE_URL, secret key, or
    settings module: their own settings fall back to SQLite defaults instead.
    """
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
    python_paths = [root for root in (roots or []) if root]
    if python_paths:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            python_paths + ([existing] if existing else [])
        )
    return env


def find_requirements_files(project_dir):
    """Locate requirements.txt files for the generated backend (root or subdir)."""
    candidates = [project_dir]
    for name in ("backend", "server", "api"):
        sub = os.path.join(project_dir, name)
        if os.path.isdir(sub):
            candidates.append(sub)
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "__pycache__"}]
        if "manage.py" in files:
            candidates.append(root)
            break
    seen = set()
    found = []
    for candidate in candidates:
        req = os.path.join(candidate, "requirements.txt")
        if req not in seen and os.path.isfile(req):
            seen.add(req)
            found.append(req)
    return found


def _requirements_marker_path(project_dir, requirements_path):
    # Same key/content scheme as pipeline.service._execute_pytest so both
    # the pipeline test runner and the preview share one install cache.
    key = hashlib.sha256(requirements_path.encode()).hexdigest()
    return os.path.join(project_dir, REQUIREMENTS_MARKER_DIR, f"{key}.sha256")


def _file_hash(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def requirements_ready(project_dir):
    """True when the venv exists and every requirements.txt matches its marker."""
    python_name = "Scripts\\python.exe" if os.name == "nt" else "bin/python"
    if not os.path.exists(os.path.join(project_dir, ".venv", python_name)):
        return False
    requirements_files = find_requirements_files(project_dir)
    if not requirements_files:
        return True
    for requirements in requirements_files:
        marker = _requirements_marker_path(project_dir, requirements)
        try:
            if not os.path.isfile(marker):
                return False
            with open(marker, "r", encoding="ascii") as marker_file:
                if marker_file.read().strip() != _file_hash(requirements):
                    return False
        except OSError:
            return False
    return True


def install_python_dependencies(project_dir, timeout=300):
    """Create the project venv and pip-install its requirements (cached by hash).

    Returns (ok, message). Safe to call repeatedly: unchanged requirements are
    skipped via sha256 marker files shared with the pipeline test runner.
    """
    try:
        python = ensure_project_python(project_dir)
    except Exception as error:
        return False, f"Could not create the Python environment: {error}"

    for requirements in find_requirements_files(project_dir):
        marker = _requirements_marker_path(project_dir, requirements)
        try:
            expected = _file_hash(requirements)
            if os.path.isfile(marker):
                with open(marker, "r", encoding="ascii") as marker_file:
                    if marker_file.read().strip() == expected:
                        continue
            result = subprocess.run(
                [python, "-m", "pip", "install", "-r", requirements, "-q"],
                cwd=os.path.dirname(requirements),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=generated_env(),
            )
            if result.returncode != 0:
                output = (result.stdout + "\n" + result.stderr).strip()
                return False, f"pip install failed for {os.path.relpath(requirements, project_dir)}:\n{output[-4000:]}"
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="ascii") as marker_file:
                marker_file.write(expected)
        except subprocess.TimeoutExpired:
            return False, f"pip install timed out after {timeout} seconds for {os.path.relpath(requirements, project_dir)}"
        except OSError as error:
            return False, f"pip install error: {error}"
    return True, "Python dependencies are ready."

import difflib
import hashlib
import os

from django.db import transaction

from .models import GeneratedFile, Project


EXCLUDED_WORKSPACE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    # Install markers and runtime state: must survive materialize clears so
    # dependency installs are not repeated and restart recovery keeps working.
    ".pipeline",
    ".buildify",
}


def normalize_file_path(path):
    normalized = str(path).replace("\\", "/").lstrip("/")
    if not normalized or normalized == "." or normalized.startswith("../") or "/../" in normalized:
        raise ValueError("Invalid generated file path")
    return normalized


def project_id_from_workspace(project_dir):
    name = os.path.basename(os.path.normpath(project_dir))
    if not name.startswith("project_"):
        raise ValueError("Workspace is not tied to a persisted project identifier")
    return int(name.removeprefix("project_"))


def line_stats(previous_content, content):
    """Return (line_count, added_lines, removed_lines) for a write.

    ``previous_content`` is None for a brand-new file: every line counts as
    added. Unchanged rewrites report a zero diff.
    """
    new_lines = content.splitlines()
    if previous_content is None:
        return len(new_lines), len(new_lines), 0
    old_lines = previous_content.splitlines()
    added = removed = 0
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return len(new_lines), added, removed


@transaction.atomic
def save_generated_file(project, path, content):
    path = normalize_file_path(path)
    content = str(content)
    previous = (
        GeneratedFile.objects.filter(project=project, path=path)
        .values_list("content", flat=True)
        .first()
    )
    line_count, added_lines, removed_lines = line_stats(previous, content)
    GeneratedFile.objects.update_or_create(
        project=project,
        path=path,
        defaults={
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "line_count": line_count,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
        },
    )
    return path


def delete_generated_file(project, path):
    GeneratedFile.objects.filter(project=project, path=normalize_file_path(path)).delete()


def load_project_files(project):
    return {
        item.path: item.content
        for item in GeneratedFile.objects.filter(project=project).only("path", "content")
    }


def _clear_workspace(directory):
    """Delete workspace contents while preserving excluded dirs at any depth.

    ``node_modules``/``.venv`` live inside subdirectories (e.g. ``frontend/``),
    so a top-level-only exclusion would delete them on every clear — forcing a
    full reinstall and racing with lingering dev-server children, which aborts
    materialization with ENOTEMPTY. Recurse instead, keep excluded subtrees,
    and tolerate concurrent writers rather than failing the whole operation.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if name in EXCLUDED_WORKSPACE_DIRS:
            continue
        path = os.path.join(directory, name)
        if os.path.isdir(path) and not os.path.islink(path):
            _clear_workspace(path)
            try:
                os.rmdir(path)
            except OSError:
                # Still holds a preserved dir (node_modules, .venv, ...) or a
                # concurrently recreated entry; leaving it is safe because
                # materialization rewrites every persisted file afterwards.
                pass
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def materialize_project(project, project_dir, clear=False):
    files = load_project_files(project)
    if clear and os.path.isdir(project_dir):
        _clear_workspace(project_dir)
    os.makedirs(project_dir, exist_ok=True)
    for relative_path, content in files.items():
        full_path = os.path.join(project_dir, *relative_path.split("/"))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(content)
    return files


def persist_workspace(project, project_dir):
    if not os.path.isdir(project_dir):
        return load_project_files(project)
    persisted = {}
    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name not in EXCLUDED_WORKSPACE_DIRS]
        for filename in filenames:
            full_path = os.path.join(root, filename)
            relative_path = os.path.relpath(full_path, project_dir).replace(os.sep, "/")
            try:
                with open(full_path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            save_generated_file(project, relative_path, content)
            persisted[relative_path] = content
    return persisted

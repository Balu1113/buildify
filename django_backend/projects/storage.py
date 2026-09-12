import hashlib
import os
import shutil

from django.db import transaction

from .models import GeneratedFile, Project


EXCLUDED_WORKSPACE_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


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


@transaction.atomic
def save_generated_file(project, path, content):
    path = normalize_file_path(path)
    content = str(content)
    GeneratedFile.objects.update_or_create(
        project=project,
        path=path,
        defaults={
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
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


def materialize_project(project, project_dir, clear=False):
    files = load_project_files(project)
    if clear and os.path.isdir(project_dir):
        for name in os.listdir(project_dir):
            if name not in EXCLUDED_WORKSPACE_DIRS:
                path = os.path.join(project_dir, name)
                shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
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

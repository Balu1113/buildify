import json
import os
import subprocess
import sys


def write_state(project_dir, state):
    state_dir = os.path.join(
        project_dir,
        ".buildify",
    )

    os.makedirs(
        state_dir,
        exist_ok=True,
    )

    state_path = os.path.join(
        state_dir,
        "frontend_status.json",
    )

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


def ensure_frontend_dependencies(project_dir, script):
    package_dir = os.path.dirname(
        os.path.join(
            project_dir,
            script,
        )
    )

    package_path = os.path.join(
        package_dir,
        "package.json",
    )

    if not os.path.exists(package_path):
        write_state(
            project_dir,
            {
                "status": "failed",
                "severity": "error",
                "stage": "npm_install",
                "error": "package_json_missing",
                "message": "Frontend package.json was not found.",
            },
        )
        return 1

    try:
        with open(
            package_path,
            "r",
            encoding="utf-8",
        ) as package_file:
            package = json.load(package_file)
    except Exception as error:
        write_state(
            project_dir,
            {
                "status": "failed",
                "severity": "error",
                "stage": "npm_install",
                "error": str(error),
                "message": "Unable to read package.json.",
            },
        )
        return 1

    scripts = package.get(
        "scripts",
        {},
    )

    if "dev" not in scripts and "start" not in scripts:
        write_state(
            project_dir,
            {
                "status": "failed",
                "severity": "error",
                "stage": "npm_install",
                "error": "frontend_script_missing",
                "message": (
                    "Frontend package.json does not contain "
                    "a dev or start script."
                ),
            },
        )
        return 1

    node_modules_dir = os.path.join(
        package_dir,
        "node_modules",
    )

    # ---------------------------------------------------------
    # Already installed
    # ---------------------------------------------------------
    if os.path.isdir(node_modules_dir):
        print(
            f"[Buildify Worker] node_modules already exists: "
            f"{node_modules_dir}",
            flush=True,
        )

        write_state(
            project_dir,
            {
                "status": "ready",
                "severity": "ready",
                "error": None,
                "stage": "dependencies_installed",
                "message": (
                    "Frontend dependencies are already installed."
                ),
                "package_dir": package_dir,
            },
        )

        return 0

    print(
        f"[Buildify Worker] Starting npm install for "
        f"{package.get('name', 'frontend')}",
        flush=True,
    )

    write_state(
        project_dir,
        {
            "status": "preparing",
            "severity": "in-progress",
            "error": None,
            "stage": "npm_install",
            "message": (
                "Installing React frontend dependencies."
            ),
            "package_dir": package_dir,
        },
    )

    npm_command = (
        "npm.cmd"
        if os.name == "nt"
        else "npm"
    )

    result = subprocess.run(
        [
            npm_command,
            "install",
            "--include=dev",
            "--no-audit",
            "--no-fund",
        ],
        cwd=package_dir,
        text=True,
    )

    if result.returncode != 0:
        write_state(
            project_dir,
            {
                "status": "failed",
                "severity": "error",
                "stage": "npm_install",
                "error": (
                    f"npm install exited with code "
                    f"{result.returncode}"
                ),
                "message": (
                    "Failed to install frontend dependencies."
                ),
                "package_dir": package_dir,
            },
        )

        return result.returncode

    if not os.path.isdir(node_modules_dir):
        write_state(
            project_dir,
            {
                "status": "failed",
                "severity": "error",
                "stage": "npm_install",
                "error": (
                    "node_modules directory was not created "
                    "after npm install."
                ),
                "message": (
                    "npm install completed but dependencies "
                    "were not created."
                ),
                "package_dir": package_dir,
            },
        )

        return 1

    print(
        f"[Buildify Worker] npm install completed.",
        flush=True,
    )

    print(
        f"[Buildify Worker] node_modules: "
        f"{node_modules_dir}",
        flush=True,
    )

    write_state(
        project_dir,
        {
            "status": "ready",
            "severity": "ready",
            "error": None,
            "stage": "dependencies_installed",
            "message": (
                "Frontend dependencies are ready."
            ),
            "package_dir": package_dir,
        },
    )

    return 0


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python -m ai_services.preview_worker "
            "<project_dir> <script>",
            flush=True,
        )
        return 2

    return ensure_frontend_dependencies(
        sys.argv[1],
        sys.argv[2],
    )


if __name__ == "__main__":
    raise SystemExit(main())
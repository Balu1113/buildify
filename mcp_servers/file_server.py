from mcp.server.fastmcp import FastMCP
from pathlib import Path


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP("Student Project File Manager")


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# SECURITY HELPER
# ============================================================

def safe_path(file_path: str) -> Path:
    """
    Resolve a file path while preventing access outside
    the project directory.
    """

    path = (PROJECT_ROOT / file_path).resolve()

    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError(
            "Access denied: file is outside the project directory."
        )

    return path


# ============================================================
# LIST FILES
# ============================================================

@mcp.tool()
def list_files(directory: str = ".") -> list:
    """
    Recursively list all files and directories inside the project.

    directory:
        Relative directory path inside the project.
    """

    path = safe_path(directory)

    if not path.exists():
        return {
            "error": f"Directory not found: {directory}"
        }

    if not path.is_dir():
        return {
            "error": f"Not a directory: {directory}"
        }

    results = []

    for item in sorted(
        path.rglob("*"),
        key=lambda p: str(p)
    ):

        relative_path = item.relative_to(PROJECT_ROOT)

        results.append({
            "name": item.name,
            "path": str(relative_path),
            "type": "directory" if item.is_dir() else "file"
        })

    return results
# ============================================================
# READ FILE
# ============================================================

@mcp.tool()
def read_file(file_path: str) -> dict:
    """
    Read the contents of a project file.
    """

    path = safe_path(file_path)

    if not path.exists():
        return {
            "error": f"File not found: {file_path}"
        }

    if not path.is_file():
        return {
            "error": f"Not a file: {file_path}"
        }

    try:

        content = path.read_text(
            encoding="utf-8"
        )

        return {
            "path": file_path,
            "content": content
        }

    except UnicodeDecodeError:

        return {
            "error": "File is not a UTF-8 text file."
        }


# ============================================================
# CREATE FILE
# ============================================================

@mcp.tool()
def create_file(
    file_path: str,
    content: str
) -> dict:
    """
    Create a new project file.

    The tool will not overwrite an existing file.
    """

    path = safe_path(file_path)

    if path.exists():
        return {
            "error": (
                f"File already exists: {file_path}. "
                "Use update_file instead."
            )
        }

    try:

        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        path.write_text(
            content,
            encoding="utf-8"
        )

        return {
            "success": True,
            "path": file_path,
            "message": "File created successfully."
        }

    except Exception as exc:

        return {
            "error": str(exc)
        }

# ============================================================
# UPDATE FILE
# ============================================================

@mcp.tool()
def update_file(
    file_path: str,
    content: str
) -> dict:
    """
    Update an existing project file.
    """

    path = safe_path(file_path)

    if not path.exists():
        return {
            "error": f"File not found: {file_path}"
        }

    if not path.is_file():
        return {
            "error": f"Not a file: {file_path}"
        }

    try:

        path.write_text(
            content,
            encoding="utf-8"
        )

        return {
            "success": True,
            "path": file_path,
            "message": "File updated successfully."
        }

    except Exception as exc:

        return {
            "error": str(exc)
        }

# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run()

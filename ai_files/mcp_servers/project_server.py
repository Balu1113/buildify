from mcp.server.fastmcp import FastMCP
from typing import Optional
import sqlite3
import uuid


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP("Student Project Manager")


# ============================================================
# DATABASE
# ============================================================

DB_PATH = "project_manager.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = get_connection()

    cursor = conn.cursor()

    # --------------------------------------------------------
    # Projects table
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # --------------------------------------------------------
    # Tasks table
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (project_id)
                REFERENCES projects(project_id)
        )
    """)

    conn.commit()
    conn.close()


# Initialize database when MCP server starts
init_database()


# ============================================================
# CREATE PROJECT
# ============================================================

@mcp.tool()
def create_project(
    name: str,
    description: str
) -> dict:
    """
    Create a new student project.
    """

    project_id = str(uuid.uuid4())[:8]

    project = {
        "project_id": project_id,
        "name": name,
        "description": description,
        "status": "planning"
    }

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO projects (
            project_id,
            name,
            description,
            status
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            project_id,
            name,
            description,
            "planning"
        )
    )

    conn.commit()
    conn.close()

    return project


# ============================================================
# GET PROJECT
# ============================================================

@mcp.tool()
def get_project(
    project_id: str
) -> dict:
    """
    Retrieve a project by its ID.
    """

    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            project_id,
            name,
            description,
            status
        FROM projects
        WHERE project_id = ?
        """,
        (project_id,)
    ).fetchone()

    conn.close()

    if not row:

        return {
            "error": "Project not found"
        }

    return dict(row)


# ============================================================
# CREATE TASK
# ============================================================

@mcp.tool()
def create_task(
    project_id: str,
    title: str,
    description: str,
    priority: str = "medium"
) -> dict:
    """
    Create a task for a project.
    """

    conn = get_connection()

    # --------------------------------------------------------
    # Check project exists
    # --------------------------------------------------------

    project = conn.execute(
        """
        SELECT project_id
        FROM projects
        WHERE project_id = ?
        """,
        (project_id,)
    ).fetchone()

    if not project:

        conn.close()

        return {
            "error": "Project not found"
        }

    # --------------------------------------------------------
    # Generate task ID
    # --------------------------------------------------------

    task_id = str(uuid.uuid4())[:8]

    task = {
        "task_id": task_id,
        "project_id": project_id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "todo"
    }

    # --------------------------------------------------------
    # Insert task
    # --------------------------------------------------------

    conn.execute(
        """
        INSERT INTO tasks (
            task_id,
            project_id,
            title,
            description,
            priority,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            project_id,
            title,
            description,
            priority,
            "todo"
        )
    )

    conn.commit()
    conn.close()

    return task


# ============================================================
# LIST TASKS
# ============================================================

@mcp.tool()
def list_tasks(
    project_id: str
) -> list:
    """
    List all tasks belonging to a project.
    """

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            task_id,
            project_id,
            title,
            description,
            priority,
            status
        FROM tasks
        WHERE project_id = ?
        """,
        (project_id,)
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# UPDATE TASK
# ============================================================

@mcp.tool()
def update_task(
    task_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None
) -> dict:
    """
    Update one or more fields of an existing task.
    """

    conn = get_connection()

    # --------------------------------------------------------
    # Find task
    # --------------------------------------------------------

    row = conn.execute(
        """
        SELECT
            task_id,
            project_id,
            title,
            description,
            priority,
            status
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,)
    ).fetchone()

    if not row:

        conn.close()

        return {
            "error": "Task not found"
        }

    # --------------------------------------------------------
    # Build update dynamically
    # --------------------------------------------------------

    updates = []
    values = []

    if status is not None:

        updates.append(
            "status = ?"
        )

        values.append(status)

    if priority is not None:

        updates.append(
            "priority = ?"
        )

        values.append(priority)

    if title is not None:

        updates.append(
            "title = ?"
        )

        values.append(title)

    if description is not None:

        updates.append(
            "description = ?"
        )

        values.append(description)

    # --------------------------------------------------------
    # Nothing to update
    # --------------------------------------------------------

    if not updates:

        conn.close()

        return dict(row)

    # --------------------------------------------------------
    # Execute UPDATE
    # --------------------------------------------------------

    values.append(task_id)

    query = f"""
        UPDATE tasks
        SET {", ".join(updates)}
        WHERE task_id = ?
    """

    conn.execute(
        query,
        values
    )

    conn.commit()

    # --------------------------------------------------------
    # Retrieve updated task
    # --------------------------------------------------------

    updated_row = conn.execute(
        """
        SELECT
            task_id,
            project_id,
            title,
            description,
            priority,
            status
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,)
    ).fetchone()

    conn.close()

    if not updated_row:

        return {
            "error": "Task could not be retrieved after update"
        }

    return dict(updated_row)


# ============================================================
# DELETE TASK
# ============================================================

@mcp.tool()
def delete_task(
    task_id: str
) -> dict:
    """
    Delete an existing task.
    """

    conn = get_connection()

    # --------------------------------------------------------
    # Find task first
    # --------------------------------------------------------

    row = conn.execute(
        """
        SELECT
            task_id,
            project_id,
            title,
            description,
            priority,
            status
        FROM tasks
        WHERE task_id = ?
        """,
        (task_id,)
    ).fetchone()

    if not row:

        conn.close()

        return {
            "error": "Task not found"
        }

    deleted_task = dict(row)

    # --------------------------------------------------------
    # Delete task
    # --------------------------------------------------------

    conn.execute(
        """
        DELETE FROM tasks
        WHERE task_id = ?
        """,
        (task_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "deleted_task": deleted_task
    }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    mcp.run()
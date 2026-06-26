import sqlite3
import sys
from fastmcp import FastMCP

mcp = FastMCP("SQLite-Jobs-Service")

# Default DB path - override via command line arg when run standalone,
# e.g. `python db_server.py path/to/jobs_d1.db`
DB_PATH = "jobs_d1.db"


def _connect():
    """Open a connection to the configured database."""
    return sqlite3.connect(DB_PATH)


@mcp.tool
def query_db(sql_query: str) -> list[dict]:
    """
    Execute a read-only SQL query (SELECT) against the jobs SQLite database
    and return the results as a list of dictionaries (column_name -> value).
    """
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def update_tech_stack(source_id: int, tech_stack: str) -> dict:
    """
    Update the tech_stack column for a single job row, identified by
    source_id. tech_stack should be a comma-separated string of
    technologies, e.g. "Python, Django, PostgreSQL".

    Returns a dict indicating success/failure and how many rows were affected.
    """
    try:
        with _connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
                (tech_stack, source_id),
            )
            conn.commit()
            return {
                "success": True,
                "source_id": source_id,
                "rows_affected": cursor.rowcount,
            }
    except Exception as e:
        return {"success": False, "source_id": source_id, "error": str(e)}


@mcp.tool
def get_untagged_jobs(limit: int = 10, offset: int = 0) -> list[dict]:
    """
    Fetch a batch of jobs that do not yet have a tech_stack value.
    Returns a list of dicts with source_id, job_title, company, and
    description, limited to `limit` rows starting at `offset`
    (for pagination/batching).
    """
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT source_id, job_title, company, description
                FROM jobs
                WHERE tech_stack IS NULL OR tech_stack = ''
                ORDER BY source_id
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def count_untagged_jobs() -> dict:
    """
    Return the total count of jobs that still need a tech_stack value.
    Useful for the calling client to know how many batches are needed.
    """
    try:
        with _connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM jobs WHERE tech_stack IS NULL OR tech_stack = ''"
            )
            count = cursor.fetchone()[0]
            return {"untagged_count": count}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # Allow overriding the DB path: python db_server.py path/to/jobs_d1.db
    if len(sys.argv) > 1:
        DB_PATH = sys.argv[1]
    mcp.run()

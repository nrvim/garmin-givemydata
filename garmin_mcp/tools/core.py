"""Schema inspection and read-only SQL access."""

import json
import logging
from contextlib import closing

from ..db import get_connection, query, query_readonly

# Keep the original logger name so existing logging config still applies.
log = logging.getLogger("garmin_mcp.server")


def garmin_schema() -> str:
    """Show all tables, their columns, and row counts."""
    with closing(get_connection()) as conn:
        tables = query(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        )
        result = {}
        for t in tables:
            table_name = t["name"]
            if not table_name.isidentifier():
                continue
            cols = query(conn, f"PRAGMA table_info([{table_name}])")
            row_count = query(conn, f"SELECT COUNT(*) AS cnt FROM [{table_name}]")[0]["cnt"]
            result[table_name] = {
                "columns": [c["name"] for c in cols],
                "row_count": row_count,
            }
        return json.dumps(result, indent=2)


def garmin_query(sql: str, limit: int = 1000) -> str:
    """Run a read-only SELECT query against the Garmin database.

    The database is opened in SQLite read-only mode at the engine level,
    so writes, ATTACH, and schema changes are impossible regardless of
    the SQL content.  Results are capped at *limit* rows (default 1000).
    """
    try:
        clamped = max(1, min(limit, 10000))
        rows = query_readonly(sql, limit=clamped)
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        log.exception("garmin_query failed")
        return json.dumps({"error": "Query failed. Check that your SQL is a valid SELECT statement."})

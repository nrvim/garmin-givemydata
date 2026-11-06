"""Database location, connections and generic query helpers."""

import sqlite3
from pathlib import Path
from typing import Any, Optional


def _default_db_path() -> str:
    """Find the database using the same logic as the CLI."""
    import os

    env_dir = os.environ.get("GARMIN_DATA_DIR")
    if env_dir:
        return str(Path(env_dir) / "garmin.db")

    cwd = Path.cwd()
    if (cwd / "garmin.db").exists() or (cwd / ".env").exists() or (cwd / "garmin_givemydata.py").exists():
        return str(cwd / "garmin.db")

    home_dir = Path.home() / ".garmin-givemydata"
    home_dir.mkdir(parents=True, exist_ok=True)
    return str(home_dir / "garmin.db")


DB_PATH = _default_db_path()


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a sqlite3 connection with WAL mode and Row factory enabled."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def query(conn: sqlite3.Connection, sql: str, params: Any = None) -> list[dict]:
    """Execute *sql* with optional *params* and return results as a list of dicts."""
    cursor = conn.execute(sql, params or [])
    return [dict(row) for row in cursor.fetchall()]


def query_readonly(sql: str, params: Any = None, limit: int = 1000) -> list[dict]:
    """Execute a read-only query against the database.

    Opens the database in SQLite read-only mode (``?mode=ro`` URI),
    which enforces read-only at the engine level — no writes, no
    PRAGMA changes, regardless of the SQL content.  Additionally
    blocks ATTACH/DETACH to prevent filesystem side-effects.
    """
    # Block ATTACH/DETACH before opening any connection — these can
    # create zero-byte files on disk even in read-only mode.
    check = sql.strip().upper()
    if "ATTACH" in check or "DETACH" in check:
        raise PermissionError("ATTACH and DETACH are not permitted.")

    ro_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro_conn.row_factory = sqlite3.Row
    try:
        clamped = max(1, min(limit if isinstance(limit, int) else 1000, 10000))
        ro_conn.execute("PRAGMA busy_timeout = 5000")
        cursor = ro_conn.execute(sql, params or [])
        rows = [dict(row) for row in cursor.fetchmany(clamped)]
        return rows
    finally:
        ro_conn.close()

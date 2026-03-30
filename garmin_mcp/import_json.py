"""
Import script: loads garmin_data_for_ai.json into the SQLite database.

Uses save_to_db() to route each dataset to the correct table.

Usage:
    python -m garmin_mcp.import_json [json_path]

If json_path is omitted, defaults to garmin_data_for_ai.json in the project root.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from garmin_mcp.db import get_connection, init_db, save_to_db

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_JSON_PATH = PROJECT_ROOT / "garmin_data_for_ai.json"


def _log_sync(conn, sync_type: str, count: int, status: str = "ok", error: str = None):
    conn.execute(
        """
        INSERT INTO sync_log (sync_date, sync_type, records_upserted, status, error)
        VALUES (?, ?, ?, ?, ?)
        """,
        (datetime.now(timezone.utc).isoformat(), sync_type, count, status, error),
    )
    conn.commit()


def main(json_path: str = None):
    path = Path(json_path) if json_path else DEFAULT_JSON_PATH
    if not path.exists():
        print(f"ERROR: JSON file not found: {path}")
        sys.exit(1)

    print(f"Loading {path} ({path.stat().st_size / 1_048_576:.1f} MB)...")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    data = payload.get("data", {})
    print("JSON loaded. Connecting to database...")

    conn = get_connection()
    init_db(conn)
    print("Schema initialized.\n")

    total = 0
    for endpoint_name, endpoint_data in data.items():
        n = save_to_db(conn, endpoint_name, endpoint_data)
        if n > 0:
            print(f"  {endpoint_name}: {n} records")
            total += n

    _log_sync(conn, "json_import", total)
    conn.close()

    print(f"\nImport complete. Total: {total} records")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(arg)

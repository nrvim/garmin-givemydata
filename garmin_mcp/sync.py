"""
Incremental sync module for Garmin MCP server.

Fetches today's and yesterday's data from Garmin Connect and saves it
directly to SQLite via save_to_db().
"""

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from garmin_mcp.db import get_connection, init_db, save_to_db

logger = logging.getLogger(__name__)


def incremental_sync(target_date: str = None) -> dict:
    """Fetch today's data from Garmin and save directly to the database.

    Parameters
    ----------
    target_date:
        ISO date string (``YYYY-MM-DD``) to treat as "today".  Defaults to
        the actual current date.

    Returns
    -------
    dict
        Summary with keys: ``status``, ``target_date``, ``yesterday``,
        ``records`` (per-endpoint counts), ``total_upserted``.
    """
    from garmin_client import GarminClient

    today = target_date or date.today().isoformat()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    PROJECT_DIR = Path(__file__).parent.parent
    PROFILE_DIR = PROJECT_DIR / "browser_profile_stealth"

    # Load .env if present
    import os

    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    email = os.environ.get("GARMIN_EMAIL", "")
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        return {
            "status": "error",
            "message": "Credentials not found. Run ./setup.sh or set GARMIN_EMAIL and GARMIN_PASSWORD.",
        }

    # Open DB connection for direct writes
    conn = get_connection()
    init_db(conn)

    counts = {}

    def on_batch(endpoint_name, data, cal_date=None):
        n = save_to_db(conn, endpoint_name, data, cal_date=cal_date)
        if n > 0:
            counts[endpoint_name] = counts.get(endpoint_name, 0) + n

    client = GarminClient(
        email=email,
        password=password,
        profile_dir=PROFILE_DIR,
    )

    logger.info("Starting incremental sync for %s (+ %s)", today, yesterday)

    try:
        if not client.login():
            return {"status": "error", "message": "Login failed"}

        client.fetch_all(
            target_date=today,
            start_date=yesterday,
            end_date=today,
            on_batch=on_batch,
        )
    finally:
        client.close()

    # Log the sync
    sync_ts = datetime.now(timezone.utc).isoformat()
    total = sum(counts.values())
    conn.execute(
        "INSERT INTO sync_log (sync_date, sync_type, records_upserted, status) VALUES (?, ?, ?, ?)",
        (sync_ts, "incremental_sync", total, "ok"),
    )
    conn.commit()
    conn.close()

    logger.info("Incremental sync complete. Total records upserted: %d", total)

    return {
        "status": "ok",
        "target_date": today,
        "yesterday": yesterday,
        "records": counts,
        "total_upserted": total,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arg_date = sys.argv[1] if len(sys.argv) > 1 else None
    result = incremental_sync(target_date=arg_date)
    print(result)

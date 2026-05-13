"""
Incremental sync module for Garmin MCP server.

Fetches today's and yesterday's data from Garmin Connect and saves it
directly to SQLite via save_to_db().
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from garmin_mcp.db import DB_PATH, get_connection, init_db, save_to_db

logger = logging.getLogger(__name__)


def _parse_trackpoints_for_activities(conn, activity_ids):
    """Parse trackpoints from already-downloaded FIT archives."""
    from .parse_activity_files import parse_trackpoints_from_directory

    if not activity_ids:
        return 0

    fit_dir = Path(DB_PATH).parent / "fit"

    if not fit_dir.exists():
        logger.debug("No FIT directory found, skipping trackpoints")
        return 0

    logger.info("Processing trackpoints for %d activities...", len(activity_ids))

    # Parse trackpoints from FIT files for these specific activities
    parsed_data = parse_trackpoints_from_directory(fit_dir, list(activity_ids))

    total_trackpoints = 0
    for activity_id, trackpoints in parsed_data:
        if trackpoints:
            count = save_to_db(conn, "activity_trackpoints", trackpoints, cal_date=str(activity_id))
            total_trackpoints += count
            logger.debug("Activity %s: %d trackpoints", activity_id, count)

    if total_trackpoints > 0:
        logger.info("Trackpoints processed: %d total points", total_trackpoints)

    return total_trackpoints


def incremental_sync(
    target_date: str = None, start_date: str = None, save_raw: bool = False, parse_trackpoints: bool = True
) -> dict:
    """Fetch today's data from Garmin and save directly to the database.

    Parameters
    ----------
    target_date:
        ISO date string (``YYYY-MM-DD``) to treat as "today".  Defaults to
        the actual current date.
    start_date:
        ISO date string (``YYYY-MM-DD``) for the beginning of the fetch range.
        Defaults to yesterday (incremental). Set to an early date for full-history sync.
    save_raw:
        Whether to save raw JSON responses under the ``debug/raw`` directory
        (next to ``browser_profile``).
    parse_trackpoints:
        Whether to parse activity trackpoints from downloaded FIT files and
        store them in ``activity_trackpoints``.

    Returns
    -------
    dict
        Summary with keys: ``status``, ``target_date``, ``start_date``,
        ``records`` (per-endpoint counts), ``total_upserted``.
    """
    from garmin_client import GarminClient

    today = target_date or date.today().isoformat()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    if start_date is not None:
        try:
            parsed_start = date.fromisoformat(start_date)
        except ValueError:
            return {
                "status": "error",
                "message": f"start_date must be YYYY-MM-DD, got: {start_date!r}",
            }
        if parsed_start > date.fromisoformat(today):
            return {
                "status": "error",
                "message": f"start_date ({start_date}) must be on or before target_date ({today})",
            }
    effective_start = start_date or yesterday
    is_backfill = start_date is not None and start_date != yesterday

    PROJECT_DIR = Path(__file__).parent.parent
    PROFILE_DIR = PROJECT_DIR / "browser_profile"

    # When launched as an MCP server, the host's CWD may be a system path
    # with no write access (e.g. C:\Windows\System32 on Windows). SeleniumBase
    # creates downloaded_files/ relative to CWD, which then crashes the sync
    # with PermissionError. Move into PROJECT_DIR. See issue #35.
    os.chdir(str(PROJECT_DIR))

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

    # Build set of already-fetched activity IDs so fetch_all() skips them
    existing = conn.execute("SELECT DISTINCT activity_id FROM activity_splits").fetchall()
    known_activity_ids = {row[0] for row in existing}
    if known_activity_ids:
        logger.info("Skipping %d activities with existing details", len(known_activity_ids))

    counts = {}

    def on_batch(endpoint_name, data, cal_date=None):
        n = save_to_db(conn, endpoint_name, data, cal_date=cal_date)
        if n > 0:
            counts[endpoint_name] = counts.get(endpoint_name, 0) + n
        # Track newly fetched activity details so later requests skip them
        if endpoint_name == "activity_splits" and cal_date:
            try:
                known_activity_ids.add(int(cal_date))
            except (ValueError, TypeError):
                pass

    SESSION_FILE = PROJECT_DIR / "garmin_session.json"
    client = GarminClient(
        email=email,
        password=password,
        profile_dir=PROFILE_DIR,
        headless=True,
        session_file=SESSION_FILE,
    )

    sync_label = "backfill" if is_backfill else "incremental sync"
    logger.info("Starting %s for %s (from %s)", sync_label, today, effective_start)

    try:
        if not client.login():
            return {"status": "error", "message": "Login failed"}

        client.fetch_all(
            target_date=today,
            start_date=effective_start,
            end_date=today,
            on_batch=on_batch,
            known_activity_ids=known_activity_ids,
            save_raw=save_raw,
        )

        # Parse trackpoints from local FIT files when explicitly requested.
        if parse_trackpoints:
            trackpoint_count = _parse_trackpoints_for_activities(conn, known_activity_ids)
            if trackpoint_count > 0:
                counts["activity_trackpoints"] = trackpoint_count

    finally:
        client.close()

    # Log the sync
    sync_ts = datetime.now(timezone.utc).isoformat()
    total = sum(counts.values())
    conn.execute(
        "INSERT INTO sync_log (sync_date, sync_type, records_upserted, status) VALUES (?, ?, ?, ?)",
        (sync_ts, "backfill" if is_backfill else "incremental_sync", total, "ok"),
    )
    conn.commit()
    conn.close()

    logger.info("%s complete. Total records upserted: %d", sync_label.capitalize(), total)

    return {
        "status": "ok",
        "target_date": today,
        "start_date": effective_start,
        "records": counts,
        "total_upserted": total,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Sync data from Garmin Connect into the local SQLite database.",
        epilog="Example: python -m garmin_mcp.sync --start-date 2018-01-01 (full history backfill)",
    )
    parser.add_argument("target_date", nargs="?", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--start-date", help="YYYY-MM-DD start of range (default: yesterday)")
    args = parser.parse_args()
    result = incremental_sync(target_date=args.target_date, start_date=args.start_date)
    print(result)

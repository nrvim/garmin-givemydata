"""garmin_sync and the background sync machinery (state, lock, timeout, freshness)."""

import json
import logging
import threading
from contextlib import closing
from datetime import date

from ..db import get_connection, query

# Keep the original logger name so existing logging config still applies.
log = logging.getLogger("garmin_mcp.server")


_sync_lock = threading.Lock()


_sync_state: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
}


SYNC_TIMEOUT_SEC = 600


def _start_background_sync() -> dict:
    """Start the browser-based sync in a daemon thread; return immediately.

    The sync takes ~2 minutes, but most MCP clients (e.g. Claude Desktop)
    time out at ~60s, so a synchronous result is unreachable. Returning
    immediately lets the caller poll status via garmin_sync(refresh=False).
    See issue #35.
    """
    import concurrent.futures
    from datetime import datetime, timezone

    if not _sync_lock.acquire(blocking=False):
        return {
            "status": "in_progress",
            "started_at": _sync_state["started_at"],
            "message": "A sync is already running. Check back with garmin_sync(refresh=False).",
        }

    started_at = datetime.now(timezone.utc).isoformat()
    _sync_state.update(running=True, started_at=started_at, finished_at=None, last_result=None)

    def _bg():
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            from ..sync import incremental_sync

            future = pool.submit(incremental_sync)
            try:
                _sync_state["last_result"] = future.result(timeout=SYNC_TIMEOUT_SEC)
            except concurrent.futures.TimeoutError:
                log.warning("sync exceeded %ds, abandoning", SYNC_TIMEOUT_SEC)
                _sync_state["last_result"] = {
                    "status": "error",
                    "error": f"Sync exceeded the {SYNC_TIMEOUT_SEC}s timeout. The browser may be hung; check server logs.",
                }
                pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            log.exception("sync failed")
            _sync_state["last_result"] = {
                "status": "error",
                "error": "Sync failed. Check server logs.",
            }
        finally:
            pool.shutdown(wait=False)
            _sync_state.update(
                running=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            _sync_lock.release()

    try:
        threading.Thread(target=_bg, daemon=True, name="garmin-sync").start()
    except RuntimeError:
        # Thread creation failed (resource exhaustion). Release the lock and
        # surface the failure so the caller doesn't silently see "started"
        # for a sync that will never run.
        _sync_state.update(running=False)
        _sync_lock.release()
        log.exception("failed to start garmin-sync thread")
        return {
            "status": "error",
            "error": "Failed to start sync thread (resource exhaustion). Check server logs.",
        }

    return {
        "status": "started",
        "started_at": started_at,
        "message": "Sync running in background (~2 min). Check back with garmin_sync(refresh=False).",
    }


def _get_data_freshness() -> dict:
    """Return data freshness info from the database."""
    from datetime import datetime, timezone

    today = str(date.today())
    with closing(get_connection()) as conn:
        freshness = query(
            conn,
            """SELECT 'daily_summary' AS source, MAX(calendar_date) AS latest FROM daily_summary
               UNION ALL SELECT 'sleep', MAX(calendar_date) FROM sleep
               UNION ALL SELECT 'hrv', MAX(calendar_date) FROM hrv
               UNION ALL SELECT 'activity', MAX(DATE(start_time_local)) FROM activity
                          WHERE start_time_local IS NOT NULL
               ORDER BY latest DESC""",
        )

        last_sync = query(
            conn,
            """SELECT sync_date, sync_type, records_upserted, status
               FROM sync_log ORDER BY created_at DESC LIMIT 1""",
        )

        latest_date = freshness[0]["latest"] if freshness and freshness[0]["latest"] else None

        # Calculate how long ago the last sync was
        last_sync_ago = None
        if last_sync and last_sync[0].get("sync_date"):
            try:
                sync_dt = datetime.fromisoformat(last_sync[0]["sync_date"])
                now = datetime.now(timezone.utc)
                if sync_dt.tzinfo is None:
                    sync_dt = sync_dt.replace(tzinfo=timezone.utc)
                delta = now - sync_dt
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    last_sync_ago = f"{int(delta.total_seconds() / 60)} minutes ago"
                elif hours < 24:
                    last_sync_ago = f"{hours:.1f} hours ago"
                else:
                    last_sync_ago = f"{delta.days} days ago"
            except (ValueError, TypeError):
                pass

        return {
            "today": today,
            "latest_data_date": latest_date,
            "is_stale": latest_date is None or latest_date < today,
            "freshness_by_table": {r["source"]: r["latest"] for r in freshness},
            "last_sync": last_sync[0] if last_sync else None,
            "last_sync_ago": last_sync_ago,
        }


def garmin_sync(refresh: bool = True) -> str:
    """Sync the latest data from Garmin Connect.

    The sync runs in the background (~2 minutes). The first call returns
    immediately with status "started"; follow up with garmin_sync(refresh=False)
    after ~2 minutes to see the final result. This avoids MCP client timeouts
    (Claude Desktop ~60s) that previously made synchronous sync unusable.

    Set refresh=False to just check the current state and last sync result
    without triggering a new sync.

    Use this when:
    - You just finished a run/ride and want to see the new data
    - You want to make sure today's health data is loaded
    - The data looks outdated
    """
    status = _get_data_freshness()
    status["sync_state"] = dict(_sync_state)

    if not refresh:
        if status["is_stale"] and not _sync_state["running"]:
            status["hint"] = "Data is not current. Call garmin_sync() to refresh."
        return json.dumps(status, indent=2, default=str)

    status["sync"] = _start_background_sync()
    return json.dumps(status, indent=2, default=str)

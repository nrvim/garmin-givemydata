"""
Garmin MCP server — exposes health and activity data via FastMCP tools.
"""

import json
import logging
import threading
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from .db import get_connection, init_db, query, query_readonly

log = logging.getLogger(__name__)

mcp = FastMCP("garmin")

# Ensure all tables exist on startup
_conn = get_connection()
init_db(_conn)
_conn.close()


# ---------------------------------------------------------------------------
# garmin_schema
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_schema() -> str:
    """Show all tables, their columns, and row counts."""
    conn = get_connection()
    try:
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
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_query
# ---------------------------------------------------------------------------


@mcp.tool()
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


# ---------------------------------------------------------------------------
# garmin_health_summary
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_health_summary(start_date: str = "", end_date: str = "", days: int = 7) -> str:
    """Health overview for a date range.

    If start_date/end_date are omitted the most recent *days* days are used.
    Returns averages for steps, HR, stress, body battery, SpO2, respiration,
    calories (daily_summary), sleep metrics (sleep table), and training
    readiness score.
    """
    if not end_date:
        end_date = str(date.today())
    if not start_date:
        start_date = str(date.today() - timedelta(days=days - 1))

    conn = get_connection()
    try:
        daily_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(total_steps), 0)              AS avg_steps,
                ROUND(AVG(resting_heart_rate), 1)       AS avg_resting_hr,
                ROUND(AVG(average_stress_level), 1)     AS avg_stress,
                ROUND(AVG(body_battery_highest), 1)     AS avg_body_battery_high,
                ROUND(AVG(body_battery_lowest), 1)      AS avg_body_battery_low,
                ROUND(AVG(average_spo2), 1)             AS avg_spo2,
                ROUND(AVG(avg_waking_respiration), 1)   AS avg_respiration,
                ROUND(AVG(total_kilocalories), 0)       AS avg_calories,
                ROUND(AVG(active_kilocalories), 0)      AS avg_active_calories,
                ROUND(AVG(floors_ascended), 1)          AS avg_floors,
                ROUND(AVG(moderate_intensity_minutes + vigorous_intensity_minutes), 0) AS avg_intensity_minutes
            FROM daily_summary
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        sleep_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(sleep_time_seconds) / 3600.0, 2)         AS avg_sleep_hours,
                ROUND(AVG(deep_sleep_seconds) / 60.0, 0)           AS avg_deep_min,
                ROUND(AVG(light_sleep_seconds) / 60.0, 0)          AS avg_light_min,
                ROUND(AVG(rem_sleep_seconds) / 60.0, 0)            AS avg_rem_min,
                ROUND(AVG(awake_sleep_seconds) / 60.0, 0)          AS avg_awake_min,
                ROUND(AVG(average_hr_sleep), 1)                    AS avg_sleeping_hr
            FROM sleep
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        tr_rows = query(
            conn,
            """
            SELECT ROUND(AVG(score), 1) AS avg_training_readiness
            FROM training_readiness
            WHERE calendar_date BETWEEN ? AND ?
            """,
            [start_date, end_date],
        )

        endurance_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(overall_score), 1) AS avg_endurance_score,
                ROUND(AVG(vo2_max_precise), 1) AS avg_vo2_max
            FROM endurance_score
            WHERE calendar_date BETWEEN ? AND ?
              AND overall_score IS NOT NULL
            """,
            [start_date, end_date],
        )

        hill_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(overall_score), 1) AS avg_hill_score,
                ROUND(AVG(endurance_score), 1) AS avg_hill_endurance,
                ROUND(AVG(strength_score), 1) AS avg_hill_strength
            FROM hill_score
            WHERE calendar_date BETWEEN ? AND ?
              AND overall_score IS NOT NULL
            """,
            [start_date, end_date],
        )

        race_rows = query(
            conn,
            """
            SELECT
                ROUND(AVG(time_5k), 0) AS avg_time_5k_sec,
                ROUND(AVG(time_10k), 0) AS avg_time_10k_sec,
                ROUND(AVG(time_half_marathon), 0) AS avg_time_half_sec,
                ROUND(AVG(time_marathon), 0) AS avg_time_marathon_sec
            FROM race_predictions
            WHERE calendar_date BETWEEN ? AND ?
              AND time_5k IS NOT NULL
            """,
            [start_date, end_date],
        )

        result = {
            "period": {"start_date": start_date, "end_date": end_date},
            "daily": daily_rows[0] if daily_rows else {},
            "sleep": sleep_rows[0] if sleep_rows else {},
            "training_readiness": tr_rows[0] if tr_rows else {},
            "endurance": endurance_rows[0] if endurance_rows else {},
            "hill_score": hill_rows[0] if hill_rows else {},
            "race_predictions": race_rows[0] if race_rows else {},
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_activities
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_activities(
    activity_type: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 20,
) -> str:
    """List activities with optional filters by type and date range.

    Returns key fields: name, type, date, duration_min, distance_km,
    calories, avg_hr, elevation, power, training_load, location.
    """
    conditions = []
    params: list = []

    if activity_type:
        conditions.append("LOWER(activity_type) = LOWER(?)")
        params.append(activity_type)
    if start_date:
        conditions.append("DATE(start_time_local) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("DATE(start_time_local) <= ?")
        params.append(end_date)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT
            activity_name                               AS name,
            activity_type                               AS type,
            start_time_local                            AS date,
            ROUND(duration_seconds / 60.0, 1)           AS duration_min,
            ROUND(distance_meters / 1000.0, 2)          AS distance_km,
            calories,
            ROUND(average_hr, 0)                        AS avg_hr,
            ROUND(elevation_gain, 0)                    AS elevation_gain_m,
            ROUND(avg_power, 0)                         AS avg_power_w,
            ROUND(training_load, 1)                     AS training_load,
            location_name                               AS location
        FROM activity
        {where_clause}
        ORDER BY start_time_local DESC
        LIMIT ?
    """

    conn = get_connection()
    try:
        rows = query(conn, sql, params)
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_trends
# ---------------------------------------------------------------------------

_TREND_METRICS = {
    "resting_hr": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(resting_heart_rate), 1)",
        "not_null": "resting_heart_rate IS NOT NULL",
        "date_col": "calendar_date",
    },
    "stress": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(average_stress_level), 1)",
        "not_null": "average_stress_level IS NOT NULL",
        "date_col": "calendar_date",
    },
    "steps": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(total_steps), 0)",
        "not_null": "total_steps IS NOT NULL",
        "date_col": "calendar_date",
    },
    "sleep_hours": {
        "table": "sleep",
        "expr": "ROUND(AVG(sleep_time_seconds) / 3600.0, 2)",
        "not_null": "sleep_time_seconds IS NOT NULL",
        "date_col": "calendar_date",
    },
    "body_battery": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(body_battery_highest), 1)",
        "not_null": "body_battery_highest IS NOT NULL",
        "date_col": "calendar_date",
    },
    "spo2": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(average_spo2), 1)",
        "not_null": "average_spo2 IS NOT NULL",
        "date_col": "calendar_date",
    },
    "training_readiness": {
        "table": "training_readiness",
        "expr": "ROUND(AVG(score), 1)",
        "not_null": "score IS NOT NULL",
        "date_col": "calendar_date",
    },
    "floors": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(floors_ascended), 1)",
        "not_null": "floors_ascended IS NOT NULL",
        "date_col": "calendar_date",
    },
    "calories": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(total_kilocalories), 0)",
        "not_null": "total_kilocalories IS NOT NULL",
        "date_col": "calendar_date",
    },
    "active_minutes": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(moderate_intensity_minutes + vigorous_intensity_minutes), 0)",
        "not_null": "moderate_intensity_minutes IS NOT NULL",
        "date_col": "calendar_date",
    },
    "respiration": {
        "table": "daily_summary",
        "expr": "ROUND(AVG(avg_waking_respiration), 1)",
        "not_null": "avg_waking_respiration IS NOT NULL",
        "date_col": "calendar_date",
    },
    "weight": {
        "table": "weight",
        "expr": "ROUND(AVG(weight), 2)",
        "not_null": "weight IS NOT NULL",
        "date_col": "calendar_date",
    },
    "hrv": {
        "table": "hrv",
        "expr": "ROUND(AVG(weekly_avg), 1)",
        "not_null": "weekly_avg IS NOT NULL",
        "date_col": "calendar_date",
    },
    "endurance_score": {
        "table": "endurance_score",
        "expr": "ROUND(AVG(overall_score), 1)",
        "not_null": "overall_score IS NOT NULL",
        "date_col": "calendar_date",
    },
    "hill_score": {
        "table": "hill_score",
        "expr": "ROUND(AVG(overall_score), 1)",
        "not_null": "overall_score IS NOT NULL",
        "date_col": "calendar_date",
    },
    "race_5k": {
        "table": "race_predictions",
        "expr": "ROUND(AVG(time_5k), 0)",
        "not_null": "time_5k IS NOT NULL",
        "date_col": "calendar_date",
    },
    "race_10k": {
        "table": "race_predictions",
        "expr": "ROUND(AVG(time_10k), 0)",
        "not_null": "time_10k IS NOT NULL",
        "date_col": "calendar_date",
    },
}


@mcp.tool()
def garmin_trends(metric: str, period: str = "month") -> str:
    """Return trend data for a metric aggregated by week or month.

    Supported metrics: resting_hr, stress, steps, sleep_hours, body_battery,
    spo2, training_readiness, floors, calories, active_minutes, respiration,
    weight, hrv, endurance_score, hill_score, race_5k, race_10k.
    period: 'week' or 'month'.
    """
    if metric not in _TREND_METRICS:
        return json.dumps({"error": f"Unknown metric '{metric}'. Choose from: {', '.join(_TREND_METRICS)}"})

    if period not in ("week", "month"):
        return json.dumps({"error": "period must be 'week' or 'month'."})

    cfg = _TREND_METRICS[metric]

    if period == "week":
        group_expr = "strftime('%Y-W%W', {date_col})".format(**cfg)
    else:
        group_expr = "strftime('%Y-%m', {date_col})".format(**cfg)

    sql = f"""
        SELECT
            {group_expr} AS period,
            {cfg["expr"]} AS value,
            COUNT(*) AS data_points
        FROM {cfg["table"]}
        WHERE {cfg["not_null"]}
        GROUP BY {group_expr}
        ORDER BY period
    """

    conn = get_connection()
    try:
        rows = query(conn, sql)
        return json.dumps({"metric": metric, "period": period, "data": rows}, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_sync
# ---------------------------------------------------------------------------


_sync_lock = threading.Lock()


def _run_incremental_sync() -> dict:
    """Run the browser-based sync in a thread. Internal helper."""
    import concurrent.futures

    def _go():
        from .sync import incremental_sync

        return incremental_sync()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_go)
    try:
        return future.result(timeout=300)
    except concurrent.futures.TimeoutError:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=False)


def _get_data_freshness() -> dict:
    """Return data freshness info from the database."""
    from datetime import datetime, timezone

    today = str(date.today())
    conn = get_connection()
    try:
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
    finally:
        conn.close()


def _do_sync() -> dict:
    """Acquire the lock and sync. Returns sync result or error dict."""
    if not _sync_lock.acquire(blocking=False):
        return {"status": "error", "error": "A sync is already in progress. Try again later."}
    try:
        return {"status": "success", "result": _run_incremental_sync()}
    except Exception as exc:
        log.exception("sync failed")
        return {"status": "error", "error": "Sync failed. Check server logs."}
    finally:
        _sync_lock.release()


@mcp.tool()
def garmin_sync(refresh: bool = True) -> str:
    """Sync the latest data from Garmin Connect.

    Always shows when the last sync happened before doing anything.
    Set refresh=False to just check the status without syncing.

    Use this when:
    - You just finished a run/ride and want to see the new data
    - You want to make sure today's health data is loaded
    - The data looks outdated
    """
    status = _get_data_freshness()

    if not refresh:
        if status["is_stale"]:
            status["hint"] = "Data is not current. Call garmin_sync() to refresh."
        return json.dumps(status, indent=2, default=str)

    sync_result = _do_sync()
    status["sync"] = sync_result

    # Refresh freshness info after sync
    if sync_result.get("status") == "success":
        status.update(_get_data_freshness())
        status["sync"] = sync_result

    return json.dumps(status, indent=2, default=str)


# ---------------------------------------------------------------------------
# garmin_today
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_today() -> str:
    """Complete snapshot of today's health: daily summary, last night's sleep,
    training readiness, HRV status, body battery, and most recent activity.
    Ideal as conversation context — call this first to ground any health question.
    """
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    conn = get_connection()
    try:
        daily = query(
            conn,
            """SELECT total_steps, resting_heart_rate, average_stress_level,
                      max_stress_level, body_battery_highest, body_battery_lowest,
                      body_battery_at_wake, average_spo2, lowest_spo2,
                      avg_waking_respiration, total_kilocalories, active_kilocalories,
                      moderate_intensity_minutes, vigorous_intensity_minutes,
                      floors_ascended, sedentary_seconds, active_seconds
               FROM daily_summary WHERE calendar_date = ?""",
            [today],
        )

        sleep = query(
            conn,
            """SELECT ROUND(sleep_time_seconds / 3600.0, 2) AS sleep_hours,
                      ROUND(deep_sleep_seconds / 60.0, 0) AS deep_min,
                      ROUND(light_sleep_seconds / 60.0, 0) AS light_min,
                      ROUND(rem_sleep_seconds / 60.0, 0) AS rem_min,
                      ROUND(awake_sleep_seconds / 60.0, 0) AS awake_min,
                      average_spo2, lowest_spo2, avg_sleep_stress,
                      sleep_score_feedback, sleep_score_insight
               FROM sleep WHERE calendar_date = ?""",
            [today],
        )

        tr = query(
            conn,
            """SELECT score, level, feedback_short,
                      hrv_factor_percent, hrv_factor_feedback, hrv_weekly_average,
                      sleep_history_factor_percent, sleep_history_factor_feedback,
                      stress_history_factor_percent, stress_history_factor_feedback,
                      acwr_factor_percent, acwr_factor_feedback
               FROM training_readiness WHERE calendar_date = ?""",
            [today],
        )

        hrv = query(
            conn,
            """SELECT weekly_avg, last_night_avg, last_night_5min_high,
                      status, baseline_low, baseline_upper
               FROM hrv WHERE calendar_date = ?""",
            [today],
        )

        last_activity = query(
            conn,
            """SELECT activity_name AS name, activity_type AS type,
                      start_time_local AS date,
                      ROUND(duration_seconds / 60.0, 1) AS duration_min,
                      ROUND(distance_meters / 1000.0, 2) AS distance_km,
                      ROUND(average_hr, 0) AS avg_hr,
                      ROUND(training_load, 1) AS training_load,
                      location_name AS location
               FROM activity ORDER BY start_time_local DESC LIMIT 1""",
        )

        fitness = query(
            conn,
            """SELECT chronological_age, fitness_age
               FROM fitness_age WHERE calendar_date = ?""",
            [today],
        )

        ts = query(
            conn,
            """SELECT status, acute_load, chronic_load
               FROM training_status WHERE calendar_date = ?""",
            [today],
        )

        result = {
            "date": today,
            "daily": daily[0] if daily else {},
            "last_night_sleep": sleep[0] if sleep else {},
            "training_readiness": tr[0] if tr else {},
            "training_status": ts[0] if ts else {},
            "hrv": hrv[0] if hrv else {},
            "fitness_age": fitness[0] if fitness else {},
            "last_activity": last_activity[0] if last_activity else {},
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_activity_detail
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_activity_detail(activity_id: int = 0, last: bool = False) -> str:
    """Deep-dive into a single activity.

    Pass activity_id, or set last=True for the most recent activity.
    Returns the activity summary plus splits, HR zones, weather, and
    exercise sets (if available).
    """
    conn = get_connection()
    try:
        if last or activity_id == 0:
            rows = query(conn, "SELECT activity_id FROM activity ORDER BY start_time_local DESC LIMIT 1")
            if not rows:
                return json.dumps({"error": "No activities found."})
            activity_id = rows[0]["activity_id"]

        activity = query(
            conn,
            """SELECT activity_id, activity_name, activity_type, start_time_local,
                      ROUND(duration_seconds / 60.0, 1) AS duration_min,
                      ROUND(distance_meters / 1000.0, 2) AS distance_km,
                      calories, ROUND(average_hr, 0) AS avg_hr, ROUND(max_hr, 0) AS max_hr,
                      ROUND(elevation_gain, 0) AS elevation_gain_m,
                      ROUND(avg_power, 0) AS avg_power_w,
                      ROUND(training_load, 1) AS training_load,
                      aerobic_training_effect, anaerobic_training_effect,
                      vo2max_value, ROUND(avg_cadence, 0) AS avg_cadence,
                      ROUND(avg_respiration, 1) AS avg_respiration,
                      location_name
               FROM activity WHERE activity_id = ?""",
            [activity_id],
        )
        if not activity:
            return json.dumps({"error": f"Activity {activity_id} not found."})

        splits = query(
            conn,
            """SELECT split_number, ROUND(distance_meters, 0) AS distance_m,
                      ROUND(duration_seconds, 0) AS duration_sec,
                      ROUND(average_speed, 3) AS avg_speed,
                      ROUND(average_hr, 0) AS avg_hr, ROUND(max_hr, 0) AS max_hr,
                      ROUND(elevation_gain, 1) AS elev_gain,
                      ROUND(avg_cadence, 0) AS avg_cadence
               FROM activity_splits WHERE activity_id = ?
               ORDER BY split_number""",
            [activity_id],
        )

        hr_zones = query(
            conn,
            """SELECT ROUND(zone1_seconds / 60.0, 1) AS zone1_min,
                      ROUND(zone2_seconds / 60.0, 1) AS zone2_min,
                      ROUND(zone3_seconds / 60.0, 1) AS zone3_min,
                      ROUND(zone4_seconds / 60.0, 1) AS zone4_min,
                      ROUND(zone5_seconds / 60.0, 1) AS zone5_min
               FROM activity_hr_zones WHERE activity_id = ?""",
            [activity_id],
        )

        weather = query(
            conn,
            """SELECT temperature, apparent_temperature, humidity,
                      wind_speed, wind_direction, weather_type
               FROM activity_weather WHERE activity_id = ?""",
            [activity_id],
        )

        exercise_sets = query(
            conn,
            """SELECT set_number, exercise_name, exercise_category,
                      reps, weight, ROUND(duration_seconds, 0) AS duration_sec
               FROM activity_exercise_sets WHERE activity_id = ?
               ORDER BY set_number""",
            [activity_id],
        )

        dynamics = query(
            conn,
            """SELECT avg_gct, avg_gct_balance, avg_vert_osc, avg_vert_ratio, avg_stride_len
               FROM running_dynamics WHERE activity_id = ?""",
            [activity_id],
        )

        result = {
            "activity": activity[0],
            "splits": splits if splits else [],
            "hr_zones": hr_zones[0] if hr_zones else {},
            "weather": weather[0] if weather else {},
            "exercise_sets": [s for s in exercise_sets if s.get("exercise_name")] if exercise_sets else [],
            "running_dynamics": dynamics[0] if dynamics else {},
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_sleep
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_sleep(start_date: str = "", days: int = 7) -> str:
    """Per-night sleep breakdown with stages, SpO2, stress, and Garmin feedback.

    Returns each night individually (not averages) for pattern analysis.
    """
    if not start_date:
        start_date = str(date.today() - timedelta(days=days - 1))
    end_date = str(date.today())

    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      ROUND(sleep_time_seconds / 3600.0, 2) AS total_hours,
                      ROUND(deep_sleep_seconds / 60.0, 0) AS deep_min,
                      ROUND(light_sleep_seconds / 60.0, 0) AS light_min,
                      ROUND(rem_sleep_seconds / 60.0, 0) AS rem_min,
                      ROUND(awake_sleep_seconds / 60.0, 0) AS awake_min,
                      awake_count,
                      CASE WHEN sleep_time_seconds > 0
                           THEN ROUND(deep_sleep_seconds * 100.0 / sleep_time_seconds, 1)
                           ELSE 0 END AS deep_pct,
                      CASE WHEN sleep_time_seconds > 0
                           THEN ROUND(rem_sleep_seconds * 100.0 / sleep_time_seconds, 1)
                           ELSE 0 END AS rem_pct,
                      average_spo2, lowest_spo2,
                      average_hr_sleep AS avg_hr,
                      average_respiration AS avg_resp,
                      avg_sleep_stress,
                      sleep_score_feedback AS feedback,
                      sleep_score_insight AS insight
               FROM sleep
               WHERE calendar_date BETWEEN ? AND ?
               ORDER BY calendar_date""",
            [start_date, end_date],
        )
        return json.dumps({"period": {"start": start_date, "end": end_date}, "nights": rows}, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_training_load  (CTL / ATL / TSB)
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_training_load() -> str:
    """Compute professional training periodization metrics from activity history.

    Returns:
    - CTL (Chronic Training Load, 42-day EWMA) — long-term fitness proxy
    - ATL (Acute Training Load, 7-day EWMA) — short-term fatigue
    - TSB (Training Stress Balance = CTL - ATL) — form / readiness
    - Weekly volume summary (hours, km, sessions, load)
    - Training load distribution by sport
    """
    conn = get_connection()
    try:
        activities = query(
            conn,
            """SELECT DATE(start_time_local) AS activity_date,
                      activity_type,
                      COALESCE(training_load, 0) AS load,
                      ROUND(duration_seconds / 3600.0, 2) AS hours,
                      ROUND(distance_meters / 1000.0, 2) AS km
               FROM activity
               WHERE start_time_local IS NOT NULL
               ORDER BY start_time_local""",
        )
        if not activities:
            return json.dumps({"error": "No activities found."})

        # Build daily load map
        daily_load: dict[str, float] = {}
        for a in activities:
            d = a["activity_date"]
            daily_load[d] = daily_load.get(d, 0) + (a["load"] or 0)

        # Date range from first activity to today
        first_date = date.fromisoformat(activities[0]["activity_date"])
        today = date.today()
        days_range = (today - first_date).days + 1

        # Compute EWMA
        ctl = 0.0
        atl = 0.0
        ctl_decay = 2.0 / (42 + 1)
        atl_decay = 2.0 / (7 + 1)
        timeline = []

        for i in range(days_range):
            d = str(first_date + timedelta(days=i))
            load = daily_load.get(d, 0)
            ctl = ctl * (1 - ctl_decay) + load * ctl_decay
            atl = atl * (1 - atl_decay) + load * atl_decay
            # Only emit weekly points + last 14 days for conciseness
            remaining = days_range - i
            if remaining <= 14 or i % 7 == 0:
                timeline.append(
                    {
                        "date": d,
                        "ctl": round(ctl, 1),
                        "atl": round(atl, 1),
                        "tsb": round(ctl - atl, 1),
                    }
                )

        # Weekly volume (last 12 weeks)
        twelve_weeks_ago = str(today - timedelta(weeks=12))
        weekly = query(
            conn,
            """SELECT strftime('%%Y-W%%W', start_time_local) AS week,
                      COUNT(*) AS sessions,
                      ROUND(SUM(duration_seconds) / 3600.0, 1) AS hours,
                      ROUND(SUM(distance_meters) / 1000.0, 1) AS km,
                      ROUND(SUM(COALESCE(training_load, 0)), 0) AS total_load,
                      GROUP_CONCAT(DISTINCT activity_type) AS sports
               FROM activity
               WHERE start_time_local >= ?
               GROUP BY week ORDER BY week""",
            [twelve_weeks_ago],
        )

        # Load by sport (all time)
        by_sport = query(
            conn,
            """SELECT activity_type AS sport,
                      COUNT(*) AS sessions,
                      ROUND(SUM(duration_seconds) / 3600.0, 1) AS total_hours,
                      ROUND(SUM(distance_meters) / 1000.0, 1) AS total_km,
                      ROUND(SUM(COALESCE(training_load, 0)), 0) AS total_load,
                      ROUND(AVG(COALESCE(training_load, 0)), 0) AS avg_load_per_session
               FROM activity
               GROUP BY activity_type
               ORDER BY total_load DESC""",
        )

        current = timeline[-1] if timeline else {}
        result = {
            "current": {
                "date": current.get("date"),
                "ctl_fitness": current.get("ctl"),
                "atl_fatigue": current.get("atl"),
                "tsb_form": current.get("tsb"),
                "interpretation": (
                    "FRESH — ready to race/test"
                    if current.get("tsb", 0) > 15
                    else "OPTIMAL — good training balance"
                    if current.get("tsb", 0) > 0
                    else "FATIGUED — absorbing training load"
                    if current.get("tsb", 0) > -15
                    else "OVERREACHING — need recovery"
                ),
            },
            "timeline": timeline,
            "weekly_volume_12w": weekly,
            "load_by_sport": by_sport,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_compare
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_compare(
    period1_start: str,
    period1_end: str,
    period2_start: str,
    period2_end: str,
) -> str:
    """Side-by-side comparison of two date ranges across all health metrics.

    Useful for week-over-week, month-over-month, or year-over-year analysis.
    Returns deltas and percentage changes for every metric.
    """
    conn = get_connection()
    try:

        def _fetch_period(start: str, end: str) -> dict:
            daily = query(
                conn,
                """SELECT ROUND(AVG(total_steps),0) AS steps,
                          ROUND(AVG(resting_heart_rate),1) AS rhr,
                          ROUND(AVG(average_stress_level),1) AS stress,
                          ROUND(AVG(body_battery_highest),1) AS bb_high,
                          ROUND(AVG(body_battery_lowest),1) AS bb_low,
                          ROUND(AVG(average_spo2),1) AS spo2,
                          ROUND(AVG(avg_waking_respiration),1) AS respiration,
                          ROUND(AVG(total_kilocalories),0) AS calories,
                          ROUND(AVG(active_kilocalories),0) AS active_cal,
                          ROUND(AVG(floors_ascended),1) AS floors,
                          ROUND(AVG(moderate_intensity_minutes + vigorous_intensity_minutes),0) AS intensity_min
                   FROM daily_summary WHERE calendar_date BETWEEN ? AND ?""",
                [start, end],
            )
            sleep = query(
                conn,
                """SELECT ROUND(AVG(sleep_time_seconds)/3600.0,2) AS sleep_hrs,
                          ROUND(AVG(deep_sleep_seconds)/60.0,0) AS deep_min,
                          ROUND(AVG(rem_sleep_seconds)/60.0,0) AS rem_min,
                          ROUND(AVG(avg_sleep_stress),1) AS sleep_stress
                   FROM sleep WHERE calendar_date BETWEEN ? AND ?""",
                [start, end],
            )
            tr = query(
                conn,
                """SELECT ROUND(AVG(score),1) AS readiness
                   FROM training_readiness WHERE calendar_date BETWEEN ? AND ?""",
                [start, end],
            )
            hrv = query(
                conn,
                """SELECT ROUND(AVG(weekly_avg),1) AS hrv_avg
                   FROM hrv WHERE calendar_date BETWEEN ? AND ?""",
                [start, end],
            )
            acts = query(
                conn,
                """SELECT COUNT(*) AS sessions,
                          ROUND(SUM(duration_seconds)/3600.0,1) AS hours,
                          ROUND(SUM(COALESCE(training_load,0)),0) AS load
                   FROM activity WHERE DATE(start_time_local) BETWEEN ? AND ?""",
                [start, end],
            )
            return {
                "period": f"{start} to {end}",
                **(daily[0] if daily else {}),
                **(sleep[0] if sleep else {}),
                **(tr[0] if tr else {}),
                **(hrv[0] if hrv else {}),
                **(acts[0] if acts else {}),
            }

        p1 = _fetch_period(period1_start, period1_end)
        p2 = _fetch_period(period2_start, period2_end)

        # Compute deltas
        deltas = {}
        for key in p1:
            if key == "period":
                continue
            v1 = p1.get(key)
            v2 = p2.get(key)
            if v1 is not None and v2 is not None and isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                diff = round(v2 - v1, 2)
                pct = round((diff / v1) * 100, 1) if v1 != 0 else None
                deltas[key] = {"period1": v1, "period2": v2, "delta": diff, "pct_change": pct}

        return json.dumps({"period1": p1, "period2": p2, "changes": deltas}, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_records
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_records() -> str:
    """All personal records (PRs) with activity details and dates."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT pr.display_name AS activity,
                      pr.activity_type AS sport,
                      pr.pr_type,
                      pr.value,
                      pr.pr_date,
                      a.activity_name,
                      a.location_name AS location
               FROM personal_record pr
               LEFT JOIN activity a ON pr.activity_id = a.activity_id
               ORDER BY pr.pr_date DESC""",
        )

        # Translate pr_type codes to human-readable names
        pr_names = {
            "1": "Longest Activity (min)",
            "2": "Fastest 1 km (sec)",
            "3": "Fastest 5K (sec)",
            "4": "Fastest 10K (sec)",
            "7": "Longest Distance (m)",
            "8": "Longest Ride (m)",
            "9": "Most Elevation (m)",
            "10": "Best 20-min Power (W)",
            "11": "Longest Climb (m)",
            "12": "Best Half Marathon (sec)",
            "13": "Best Marathon (sec)",
            "14": "Best Triathlon (sec)",
            "15": "Best VO2max",
            "16": "Lowest RHR",
            "17": "Longest Swim (m)",
            "18": "Fastest 100m Swim (sec)",
            "20": "Fastest 400m Swim (sec)",
            "22": "Fastest 1000m Swim (sec)",
            "23": "Fastest 1500m Swim (sec)",
        }

        for r in rows:
            code = str(r.get("pr_type", ""))
            r["record_name"] = pr_names.get(code, f"Type {code}")

        return json.dumps(rows, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_fitness_age
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_fitness_age(period: str = "month") -> str:
    """Fitness age vs chronological age trajectory over time.

    Shows the gap between biological fitness and real age, aggregated by
    week or month.  A widening gap means you're getting fitter relative
    to your age; a narrowing gap means fitness is declining.
    """
    if period not in ("week", "month"):
        return json.dumps({"error": "period must be 'week' or 'month'."})

    group_expr = "strftime('%Y-W%W', calendar_date)" if period == "week" else "strftime('%Y-%m', calendar_date)"

    conn = get_connection()
    try:
        rows = query(
            conn,
            f"""SELECT {group_expr} AS period,
                       ROUND(AVG(chronological_age), 1) AS chrono_age,
                       ROUND(AVG(fitness_age), 1) AS fitness_age,
                       ROUND(AVG(chronological_age) - AVG(fitness_age), 1) AS gap_years,
                       ROUND(MIN(fitness_age), 1) AS best_fitness_age
                FROM fitness_age
                WHERE fitness_age IS NOT NULL
                GROUP BY {group_expr}
                ORDER BY period""",
        )

        current = rows[-1] if rows else {}
        best = min(rows, key=lambda r: r["fitness_age"]) if rows else {}

        result = {
            "current": {
                "period": current.get("period"),
                "fitness_age": current.get("fitness_age"),
                "chrono_age": current.get("chrono_age"),
                "gap": current.get("gap_years"),
            },
            "all_time_best": {
                "period": best.get("period"),
                "fitness_age": best.get("best_fitness_age"),
            },
            "timeline": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_hrv — enriched with baseline context and status streaks
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_hrv(days: int = 30) -> str:
    """HRV (Heart Rate Variability) with clinical context.

    Unlike raw HRV numbers, this returns your personal baseline range,
    how many consecutive days you've been BALANCED vs UNBALANCED,
    trend direction, and whether current values are above/below baseline.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, weekly_avg, last_night_avg,
                      last_night_5min_high, status, baseline_low, baseline_upper
               FROM hrv WHERE calendar_date >= ? ORDER BY calendar_date""",
            [start],
        )
        if not rows:
            return json.dumps({"error": "No HRV data found."})

        # Compute status streak (consecutive days of current status)
        current_status = rows[-1]["status"]
        streak = 0
        for r in reversed(rows):
            if r["status"] == current_status:
                streak += 1
            else:
                break

        # Trend: compare last 7 days vs prior 7 days
        avgs = [r["weekly_avg"] for r in rows if r["weekly_avg"] is not None]
        if len(avgs) >= 14:
            recent_7 = sum(avgs[-7:]) / 7
            prior_7 = sum(avgs[-14:-7]) / 7
            trend_pct = round((recent_7 - prior_7) / prior_7 * 100, 1) if prior_7 else 0
            trend = "improving" if trend_pct > 3 else "declining" if trend_pct < -3 else "stable"
        elif len(avgs) >= 2:
            trend_pct = 0.0
            trend = "insufficient data"
        else:
            trend_pct = 0.0
            trend = "insufficient data"

        latest = rows[-1]
        result = {
            "current": {
                "date": latest["calendar_date"],
                "weekly_avg": latest["weekly_avg"],
                "last_night_avg": latest["last_night_avg"],
                "last_night_5min_high": latest["last_night_5min_high"],
                "status": latest["status"],
                "baseline_low": latest["baseline_low"],
                "baseline_upper": latest["baseline_upper"],
                "position": (
                    "ABOVE baseline"
                    if latest["weekly_avg"]
                    and latest["baseline_upper"]
                    and latest["weekly_avg"] > latest["baseline_upper"]
                    else "BELOW baseline"
                    if latest["weekly_avg"] and latest["baseline_low"] and latest["weekly_avg"] < latest["baseline_low"]
                    else "WITHIN baseline"
                ),
            },
            "status_streak": {"status": current_status, "consecutive_days": streak},
            "trend": {"direction": trend, "pct_change_7d": trend_pct},
            "daily": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_body_battery — charge/drain patterns with sleep correlation
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_body_battery(days: int = 14) -> str:
    """Body battery with charge efficiency and drain analysis.

    Returns per-day values enriched with: how much you charged overnight
    vs how much you drained during the day, wake-up charge level,
    and whether sleep quality (deep sleep) correlated with better charging.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT d.calendar_date,
                      d.body_battery_highest AS high,
                      d.body_battery_lowest AS low,
                      d.body_battery_at_wake AS at_wake,
                      d.body_battery_during_sleep AS sleep_charge,
                      d.body_battery_highest - d.body_battery_lowest AS daily_range,
                      s.deep_sleep_seconds,
                      ROUND(s.sleep_time_seconds / 3600.0, 2) AS sleep_hours,
                      s.avg_sleep_stress
               FROM daily_summary d
               LEFT JOIN sleep s ON d.calendar_date = s.calendar_date
               WHERE d.calendar_date >= ?
               ORDER BY d.calendar_date""",
            [start],
        )

        # Flag critical days (wake < 40 or low < 15)
        critical_days = [
            r["calendar_date"]
            for r in rows
            if (r["at_wake"] is not None and r["at_wake"] < 40) or (r["low"] is not None and r["low"] < 15)
        ]

        # Average wake value
        wakes = [r["at_wake"] for r in rows if r["at_wake"] is not None]
        avg_wake = round(sum(wakes) / len(wakes), 1) if wakes else None

        result = {
            "summary": {
                "avg_wake_battery": avg_wake,
                "critical_days_count": len(critical_days),
                "critical_days": critical_days,
            },
            "daily": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_stress — time-in-zone breakdown, not just averages
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_stress(days: int = 14) -> str:
    """Stress with time-in-zone breakdown (low/medium/high).

    Goes beyond the average — shows how many hours per day you spent
    in each stress zone, plus max stress spikes and the stress qualifier.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      average_stress_level AS avg_stress,
                      max_stress_level AS max_stress,
                      ROUND(low_stress_seconds / 3600.0, 1) AS low_stress_hrs,
                      ROUND(medium_stress_seconds / 3600.0, 1) AS med_stress_hrs,
                      ROUND(high_stress_seconds / 3600.0, 1) AS high_stress_hrs,
                      stress_qualifier
               FROM daily_summary
               WHERE calendar_date >= ? AND average_stress_level IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        # Averages across period
        avg_vals = [r["avg_stress"] for r in rows if r["avg_stress"] is not None]
        high_hrs = [r["high_stress_hrs"] for r in rows if r["high_stress_hrs"] is not None]

        result = {
            "summary": {
                "period_avg_stress": round(sum(avg_vals) / len(avg_vals), 1) if avg_vals else None,
                "avg_daily_high_stress_hrs": round(sum(high_hrs) / len(high_hrs), 1) if high_hrs else None,
                "highest_day": max(rows, key=lambda r: r["avg_stress"] or 0)["calendar_date"] if rows else None,
                "lowest_day": min(rows, key=lambda r: r["avg_stress"] or 999)["calendar_date"] if rows else None,
            },
            "daily": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_heart_rate — RHR trend with 7-day moving avg context
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_heart_rate(days: int = 30) -> str:
    """Resting heart rate with trend analysis and anomaly detection.

    Returns daily RHR plus a rolling 7-day average. Flags days where RHR
    jumped >5 bpm above your 7-day average (a sign of illness, overtraining,
    or poor recovery per sports science literature).
    """
    # Fetch extra days for the rolling average
    start = str(date.today() - timedelta(days=days + 7))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, resting_heart_rate AS rhr,
                      min_heart_rate AS min_hr, max_heart_rate AS max_hr
               FROM daily_summary
               WHERE calendar_date >= ? AND resting_heart_rate IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )
        if not rows:
            return json.dumps({"error": "No heart rate data found."})

        # Compute 7-day rolling average and flag anomalies
        output = []
        for i, r in enumerate(rows):
            window = [rows[j]["rhr"] for j in range(max(0, i - 6), i + 1) if rows[j]["rhr"]]
            avg_7d = round(sum(window) / len(window), 1) if window else None
            rhr = r["rhr"]
            elevated = rhr and avg_7d and (rhr - avg_7d > 5)
            output.append(
                {
                    "date": r["calendar_date"],
                    "rhr": rhr,
                    "min_hr": r["min_hr"],
                    "max_hr": r["max_hr"],
                    "avg_7d": avg_7d,
                    "elevated": elevated,
                }
            )

        # Trim to requested days
        cutoff = str(date.today() - timedelta(days=days - 1))
        output = [r for r in output if r["date"] >= cutoff]

        elevated_days = [r["date"] for r in output if r.get("elevated")]
        rhrs = [r["rhr"] for r in output if r["rhr"]]

        result = {
            "summary": {
                "current_rhr": output[-1]["rhr"] if output else None,
                "period_avg": round(sum(rhrs) / len(rhrs), 1) if rhrs else None,
                "period_min": min(rhrs) if rhrs else None,
                "period_max": max(rhrs) if rhrs else None,
                "elevated_days": elevated_days,
            },
            "daily": output,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_spo2 — with clinical threshold flags
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_spo2(days: int = 14) -> str:
    """Blood oxygen (SpO2) with clinical threshold analysis.

    Flags days where average SpO2 dropped below 95% (clinical concern)
    or nocturnal lows dropped below 80% (possible sleep apnea indicator).
    Includes both daily_summary and dedicated spo2 table data.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      average_spo2 AS avg_spo2,
                      lowest_spo2 AS min_spo2,
                      latest_spo2 AS latest,
                      CASE WHEN average_spo2 < 95 THEN 1 ELSE 0 END AS below_normal,
                      CASE WHEN lowest_spo2 < 80 THEN 1 ELSE 0 END AS critical_low
               FROM daily_summary
               WHERE calendar_date >= ? AND average_spo2 IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        avgs = [r["avg_spo2"] for r in rows if r["avg_spo2"]]
        below_count = sum(1 for r in rows if r["below_normal"])
        critical_count = sum(1 for r in rows if r["critical_low"])

        result = {
            "summary": {
                "period_avg": round(sum(avgs) / len(avgs), 1) if avgs else None,
                "days_below_95pct": below_count,
                "days_with_critical_low": critical_count,
                "recommendation": (
                    "URGENT: Frequent critical lows — consider a sleep apnea screening"
                    if critical_count > 3
                    else "WATCH: Consistently below 95% — monitor and consult if persistent"
                    if below_count > len(rows) * 0.5
                    else "NORMAL"
                ),
            },
            "daily": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_body_composition — weight trend with context
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_body_composition() -> str:
    """Weight, BMI, and body composition history with trend analysis."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT timestamp,
                      calendar_date,
                      ROUND(weight / 1000.0, 1) AS weight_kg,
                      ROUND(bmi, 1) AS bmi,
                      ROUND(body_fat, 1) AS body_fat_pct,
                      ROUND(body_water, 1) AS body_water_pct,
                      ROUND(bone_mass / 1000.0, 2) AS bone_mass_kg,
                      ROUND(muscle_mass / 1000.0, 1) AS muscle_mass_kg,
                      source
               FROM weight
               WHERE weight IS NOT NULL
               ORDER BY timestamp DESC""",
        )
        if not rows:
            return json.dumps({"error": "No weight data found."})

        latest = rows[0]
        result = {
            "latest": latest,
            "total_entries": len(rows),
            "history": rows,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_devices — connected hardware
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_devices() -> str:
    """Connected Garmin devices with type and last sync time."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT display_name, device_type, last_sync
               FROM device ORDER BY last_sync DESC""",
        )
        return json.dumps(rows, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_week_summary — current week vs goals
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_week_summary() -> str:
    """Current week's health totals vs goals, with daily breakdown.

    Shows steps, intensity minutes, floors, and calories for each day
    of the current week, plus totals vs weekly targets.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    start = str(monday)
    end = str(today)

    conn = get_connection()
    try:
        days = query(
            conn,
            """SELECT calendar_date,
                      total_steps, daily_step_goal,
                      moderate_intensity_minutes + vigorous_intensity_minutes AS intensity_min,
                      intensity_minutes_goal,
                      floors_ascended, floors_ascended_goal,
                      total_kilocalories, active_kilocalories,
                      resting_heart_rate, average_stress_level,
                      body_battery_highest, body_battery_lowest
               FROM daily_summary
               WHERE calendar_date BETWEEN ? AND ?
               ORDER BY calendar_date""",
            [start, end],
        )

        activities = query(
            conn,
            """SELECT activity_name AS name, activity_type AS type,
                      ROUND(duration_seconds / 60.0, 1) AS duration_min,
                      ROUND(distance_meters / 1000.0, 2) AS distance_km,
                      ROUND(training_load, 0) AS load
               FROM activity
               WHERE DATE(start_time_local) BETWEEN ? AND ?
               ORDER BY start_time_local""",
            [start, end],
        )

        # Compute totals
        total_steps = sum(d["total_steps"] or 0 for d in days)
        total_intensity = sum(d["intensity_min"] or 0 for d in days)
        total_floors = sum(d["floors_ascended"] or 0 for d in days)
        step_goal = (days[0]["daily_step_goal"] or 0) * 7 if days else 0
        intensity_goal = (days[0]["intensity_minutes_goal"] or 0) if days else 0

        result = {
            "week": f"{start} to {end}",
            "days_elapsed": len(days),
            "totals": {
                "steps": total_steps,
                "step_goal_weekly": step_goal,
                "step_pct": round(total_steps / step_goal * 100, 0) if step_goal else None,
                "intensity_min": total_intensity,
                "intensity_goal_weekly": intensity_goal,
                "intensity_pct": round(total_intensity / intensity_goal * 100, 0) if intensity_goal else None,
                "floors": round(total_floors, 1),
            },
            "activities_this_week": activities,
            "daily": days,
        }
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_recovery — post-activity recovery signature (unique)
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_recovery(days_after: int = 3) -> str:
    """Analyze how your body recovers after hard training sessions.

    For each activity with training_load > 80, shows RHR and HRV for
    the following days. Reveals your personal recovery curve and
    identifies which sports/intensities hit you hardest.

    This is unique — no other Garmin MCP computes recovery signatures.
    """
    conn = get_connection()
    try:
        activities = query(
            conn,
            """SELECT activity_id, activity_name, activity_type,
                      DATE(start_time_local) AS activity_date,
                      ROUND(training_load, 0) AS load,
                      ROUND(duration_seconds / 60.0, 0) AS duration_min,
                      ROUND(average_hr, 0) AS avg_hr
               FROM activity
               WHERE training_load > 80 AND start_time_local IS NOT NULL
               ORDER BY start_time_local DESC
               LIMIT 20""",
        )
        if not activities:
            return json.dumps({"error": "No high-load activities found."})

        results = []
        for a in activities:
            d = a["activity_date"]
            recovery_days = []
            for offset in range(days_after + 1):
                check = str(date.fromisoformat(d) + timedelta(days=offset))
                row = query(
                    conn,
                    """SELECT d.resting_heart_rate AS rhr, h.weekly_avg AS hrv,
                              d.body_battery_at_wake AS bb_wake, d.average_stress_level AS stress
                       FROM daily_summary d
                       LEFT JOIN hrv h ON d.calendar_date = h.calendar_date
                       WHERE d.calendar_date = ?""",
                    [check],
                )
                if row:
                    recovery_days.append({"day": f"+{offset}", "date": check, **row[0]})

            # Compute recovery delta
            if len(recovery_days) >= 2 and recovery_days[0].get("rhr") and recovery_days[-1].get("rhr"):
                rhr_delta = recovery_days[-1]["rhr"] - recovery_days[0]["rhr"]
            else:
                rhr_delta = None

            results.append(
                {
                    "activity": a["activity_name"],
                    "type": a["activity_type"],
                    "date": d,
                    "load": a["load"],
                    "duration_min": a["duration_min"],
                    "avg_hr": a["avg_hr"],
                    "rhr_delta_after": rhr_delta,
                    "recovery": recovery_days,
                }
            )

        # Aggregate: avg recovery by sport type
        by_sport: dict[str, list] = {}
        for r in results:
            sport = r["type"]
            if sport not in by_sport:
                by_sport[sport] = []
            if r["rhr_delta_after"] is not None:
                by_sport[sport].append(r["rhr_delta_after"])

        sport_summary = {
            sport: {
                "avg_rhr_impact": round(sum(deltas) / len(deltas), 1),
                "sessions": len(deltas),
            }
            for sport, deltas in by_sport.items()
            if deltas
        }

        return json.dumps(
            {
                "recovery_by_sport": sport_summary,
                "sessions": results,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_training_status — productive / detraining / recovery / etc
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_training_status(days: int = 90) -> str:
    """Training status history (Productive, Recovery, Detraining, Unproductive, etc).

    Shows how Garmin classified your training state each day, with a
    breakdown of how many days you spent in each status and when
    transitions happened. Useful for spotting detraining before it deepens.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, status, acute_load, chronic_load
               FROM training_status
               WHERE calendar_date >= ?
               ORDER BY calendar_date""",
            [start],
        )

        # Count days per status
        counts: dict[str, int] = {}
        for r in rows:
            s = r["status"] or "UNKNOWN"
            counts[s] = counts.get(s, 0) + 1

        # Detect transitions (status changes)
        transitions = []
        prev = None
        for r in rows:
            s = r["status"] or "UNKNOWN"
            if s != prev and prev is not None:
                transitions.append({"date": r["calendar_date"], "from": prev, "to": s})
            prev = s

        current = rows[-1]["status"] if rows else None

        return json.dumps(
            {
                "current_status": current,
                "days_in_status": counts,
                "transitions": transitions[-10:],
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_workouts — workout library and schedule
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_workouts() -> str:
    """Workout library and upcoming schedule.

    Returns saved workouts (training plans, custom workouts) and any
    scheduled workout dates. Useful for understanding planned vs executed training.
    """
    conn = get_connection()
    try:
        workouts = query(
            conn,
            """SELECT workout_id, workout_name, sport_type,
                      created_date, updated_date
               FROM workouts
               ORDER BY updated_date DESC""",
        )

        schedule = query(
            conn,
            """SELECT calendar_date, raw_json
               FROM workout_schedule
               ORDER BY calendar_date DESC""",
        )

        plans = query(
            conn,
            """SELECT id, raw_json FROM training_plans""",
        )

        return json.dumps(
            {
                "workout_library": workouts,
                "scheduled": schedule,
                "training_plans": plans,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_badges — achievements and milestones
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_badges() -> str:
    """Earned badges and achievements with dates.

    Tracks milestones like distance PRs, consistency streaks, and
    special event completions. Shows progression over time.
    """
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT badge_name, badge_category, earned_date, earned_number
               FROM earned_badges
               ORDER BY earned_date DESC""",
        )

        # Group by category
        by_category: dict[str, list] = {}
        for r in rows:
            cat = r["badge_category"] or "general"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(r)

        return json.dumps(
            {
                "total_badges": len(rows),
                "badges": rows,
                "by_category": {k: len(v) for k, v in by_category.items()},
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_hydration — fluid intake tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_hydration(days: int = 30) -> str:
    """Daily hydration intake vs goals.

    Tracks fluid intake, compares against Garmin's calculated goal
    (which factors in activity, weather, and body weight), and flags
    days with significant under-hydration.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      goal_ml, intake_ml,
                      CASE WHEN goal_ml > 0
                           THEN ROUND(intake_ml * 100.0 / goal_ml, 0)
                           ELSE NULL END AS pct_of_goal
               FROM hydration
               WHERE calendar_date >= ?
               ORDER BY calendar_date""",
            [start],
        )

        tracked = [r for r in rows if r["intake_ml"] and r["intake_ml"] > 0]

        return json.dumps(
            {
                "days_tracked": len(tracked),
                "days_total": len(rows),
                "data": rows if tracked else [],
                "note": "No hydration data logged" if not tracked else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_respiration — breathing rate trends
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_respiration(days: int = 14) -> str:
    """Waking respiration rate with min/max range.

    Elevated respiration at rest can indicate illness, stress, or
    cardiovascular strain. Normal adult range is 12-20 breaths/min.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      avg_waking_respiration AS avg_waking,
                      highest_respiration AS max_resp,
                      lowest_respiration AS min_resp
               FROM daily_summary
               WHERE calendar_date >= ? AND avg_waking_respiration IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        avgs = [r["avg_waking"] for r in rows if r["avg_waking"]]
        elevated = [r["calendar_date"] for r in rows if r["avg_waking"] and r["avg_waking"] > 20]

        return json.dumps(
            {
                "summary": {
                    "period_avg": round(sum(avgs) / len(avgs), 1) if avgs else None,
                    "elevated_days": elevated,
                },
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_intensity_minutes — moderate + vigorous with goal tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_intensity_minutes(days: int = 30) -> str:
    """Weekly intensity minutes vs the WHO-recommended 150 min/week.

    Breaks down moderate vs vigorous minutes (vigorous counts double per
    WHO guidelines). Shows weekly totals and goal attainment.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT strftime('%%Y-W%%W', calendar_date) AS week,
                      SUM(moderate) AS moderate_min,
                      SUM(vigorous) AS vigorous_min,
                      SUM(moderate + vigorous) AS total_min,
                      SUM(moderate + vigorous * 2) AS who_equivalent_min,
                      MAX(goal) AS weekly_goal
               FROM intensity_minutes
               WHERE calendar_date >= ?
               GROUP BY week
               ORDER BY week""",
            [start],
        )

        return json.dumps(
            {
                "who_target": "150 min/week (moderate) or 75 min/week (vigorous)",
                "weekly": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_floors — floors climbed with goal tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_floors(days: int = 14) -> str:
    """Daily floors climbed vs goal, with ascent/descent breakdown."""
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      ROUND(ascended, 1) AS floors_up,
                      ROUND(descended, 1) AS floors_down,
                      ROUND(goal, 0) AS goal,
                      CASE WHEN goal > 0
                           THEN ROUND(ascended * 100.0 / goal, 0)
                           ELSE NULL END AS pct_of_goal
               FROM floors
               WHERE calendar_date >= ?
               ORDER BY calendar_date""",
            [start],
        )

        ups = [r["floors_up"] for r in rows if r["floors_up"]]
        goal_met = sum(1 for r in rows if r["pct_of_goal"] and r["pct_of_goal"] >= 100)

        return json.dumps(
            {
                "summary": {
                    "avg_floors_day": round(sum(ups) / len(ups), 1) if ups else None,
                    "days_goal_met": goal_met,
                    "days_total": len(rows),
                },
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_steps — daily steps with goal and streak tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_steps(days: int = 14) -> str:
    """Daily step count with goal attainment and streaks.

    Shows steps per day, percentage of goal, and identifies the longest
    consecutive streak of meeting your step goal.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT d.calendar_date,
                      d.total_steps AS steps,
                      d.daily_step_goal AS goal,
                      ROUND(d.total_distance_meters / 1000.0, 2) AS distance_km,
                      CASE WHEN d.daily_step_goal > 0
                           THEN ROUND(d.total_steps * 100.0 / d.daily_step_goal, 0)
                           ELSE NULL END AS pct_of_goal
               FROM daily_summary d
               WHERE d.calendar_date >= ? AND d.total_steps IS NOT NULL
               ORDER BY d.calendar_date""",
            [start],
        )

        steps_list = [r["steps"] for r in rows if r["steps"]]
        goal_met_days = sum(1 for r in rows if r["pct_of_goal"] and r["pct_of_goal"] >= 100)

        # Longest goal streak
        streak = 0
        max_streak = 0
        for r in rows:
            if r["pct_of_goal"] and r["pct_of_goal"] >= 100:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        return json.dumps(
            {
                "summary": {
                    "avg_steps": round(sum(steps_list) / len(steps_list), 0) if steps_list else None,
                    "days_goal_met": goal_met_days,
                    "days_total": len(rows),
                    "longest_goal_streak": max_streak,
                    "best_day": max(rows, key=lambda r: r["steps"] or 0)["calendar_date"] if rows else None,
                },
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_calories — energy balance tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_calories(days: int = 14) -> str:
    """Daily calorie breakdown: total, active, BMR, and consumed (if logged).

    Combines daily_summary calorie data with the dedicated calories table
    for a complete energy picture.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date,
                      ROUND(total_kilocalories, 0) AS total_cal,
                      ROUND(active_kilocalories, 0) AS active_cal,
                      ROUND(bmr_kilocalories, 0) AS bmr_cal,
                      ROUND(remaining_kilocalories, 0) AS remaining_cal
               FROM daily_summary
               WHERE calendar_date >= ? AND total_kilocalories IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        # Check dedicated calories table for consumed data
        consumed = query(
            conn,
            """SELECT calendar_date, consumed, remaining
               FROM calories
               WHERE calendar_date >= ? AND consumed > 0
               ORDER BY calendar_date""",
            [start],
        )

        totals = [r["total_cal"] for r in rows if r["total_cal"]]
        actives = [r["active_cal"] for r in rows if r["active_cal"]]

        return json.dumps(
            {
                "summary": {
                    "avg_total_cal": round(sum(totals) / len(totals), 0) if totals else None,
                    "avg_active_cal": round(sum(actives) / len(actives), 0) if actives else None,
                },
                "daily": rows,
                "food_log": consumed if consumed else [],
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_blood_pressure — if tracked via compatible device
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_blood_pressure(days: int = 90) -> str:
    """Blood pressure readings (systolic/diastolic/pulse) if tracked.

    Requires a compatible Garmin blood pressure monitor. Flags readings
    outside normal ranges (>140/90 mmHg per AHA guidelines).
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, systolic, diastolic, pulse
               FROM blood_pressure
               WHERE calendar_date >= ?
               ORDER BY calendar_date""",
            [start],
        )

        flagged = [
            r for r in rows if (r["systolic"] and r["systolic"] >= 140) or (r["diastolic"] and r["diastolic"] >= 90)
        ]

        return json.dumps(
            {
                "total_readings": len(rows),
                "elevated_readings": len(flagged),
                "data": rows,
                "note": "No blood pressure data recorded" if not rows else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_goals — active goals and progress
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_goals() -> str:
    """Active fitness goals and their current progress."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT goal_id, goal_type, goal_value, raw_json
               FROM goals""",
        )
        return json.dumps(
            {
                "total_goals": len(rows),
                "goals": rows,
                "note": "No goals set" if not rows else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_challenges — active and completed challenges
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_challenges() -> str:
    """Garmin Connect challenges (active and completed)."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT id, challenge_type, raw_json
               FROM challenges""",
        )
        return json.dumps(
            {
                "total_challenges": len(rows),
                "challenges": rows,
                "note": "No challenges found" if not rows else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_user_profile — athlete profile info
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_user_profile() -> str:
    """User profile and settings stored in Garmin Connect."""
    conn = get_connection()
    try:
        rows = query(conn, "SELECT key, raw_json FROM user_profile")
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["raw_json"]) if r["raw_json"] else None
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["raw_json"]
        return json.dumps(result, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_race_predictions — predicted finish times with trend
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_race_predictions(days: int = 30) -> str:
    """Predicted race finish times (5K, 10K, half marathon, marathon).

    Shows daily predictions with human-readable times and trend direction.
    A rising prediction time means declining fitness; falling means improving.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, time_5k, time_10k,
                      time_half_marathon, time_marathon
               FROM race_predictions
               WHERE calendar_date >= ? AND time_5k IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        def _fmt_time(secs: float | None) -> str | None:
            if not secs:
                return None
            m, s = divmod(int(secs), 60)
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

        for r in rows:
            r["time_5k_fmt"] = _fmt_time(r["time_5k"])
            r["time_10k_fmt"] = _fmt_time(r["time_10k"])
            r["time_half_fmt"] = _fmt_time(r["time_half_marathon"])
            r["time_marathon_fmt"] = _fmt_time(r["time_marathon"])

        # Trend: first vs last 5K prediction
        if len(rows) >= 2:
            first_5k = rows[0]["time_5k"]
            last_5k = rows[-1]["time_5k"]
            delta = last_5k - first_5k
            trend = "IMPROVING (faster)" if delta < -10 else "DECLINING (slower)" if delta > 10 else "STABLE"
        else:
            delta = 0
            trend = "insufficient data"

        latest = rows[-1] if rows else {}

        return json.dumps(
            {
                "latest": {
                    "date": latest.get("calendar_date"),
                    "5k": latest.get("time_5k_fmt"),
                    "10k": latest.get("time_10k_fmt"),
                    "half_marathon": latest.get("time_half_fmt"),
                    "marathon": latest.get("time_marathon_fmt"),
                },
                "trend": {"direction": trend, "5k_delta_sec": round(delta)},
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_endurance_score — endurance and VO2max tracking
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_endurance_score(days: int = 30) -> str:
    """Endurance score and VO2max with classification and trend."""
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, overall_score, classification,
                      vo2_max_precise
               FROM endurance_score
               WHERE calendar_date >= ? AND overall_score IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        scores = [r["overall_score"] for r in rows if r["overall_score"]]
        if len(scores) >= 2:
            trend = (
                "improving" if scores[-1] > scores[0] + 10 else "declining" if scores[-1] < scores[0] - 10 else "stable"
            )
        else:
            trend = "insufficient data"

        return json.dumps(
            {
                "latest": rows[-1] if rows else {},
                "trend": trend,
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_hill_score — hill/climb fitness
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_hill_score(days: int = 30) -> str:
    """Hill score with endurance and strength sub-scores."""
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, overall_score,
                      endurance_score, strength_score
               FROM hill_score
               WHERE calendar_date >= ? AND overall_score IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )
        return json.dumps(
            {
                "latest": rows[-1] if rows else {},
                "daily": rows,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_vo2max — VO2max history by sport
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_vo2max() -> str:
    """VO2max estimates from activities and the dedicated vo2max table.

    Pulls from both the activity-level VO2max estimates and the
    standalone vo2max tracking table.
    """
    conn = get_connection()
    try:
        # Dedicated table
        vo2_table = query(
            conn,
            """SELECT calendar_date, sport, value
               FROM vo2max
               WHERE value IS NOT NULL
               ORDER BY calendar_date DESC""",
        )

        # From activities
        vo2_activities = query(
            conn,
            """SELECT DATE(start_time_local) AS date, activity_type,
                      vo2max_value, activity_name
               FROM activity
               WHERE vo2max_value IS NOT NULL AND start_time_local IS NOT NULL
               ORDER BY start_time_local DESC""",
        )

        return json.dumps(
            {
                "from_vo2max_table": vo2_table,
                "from_activities": vo2_activities,
                "note": "No VO2max data" if not vo2_table and not vo2_activities else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_health_snapshot — on-demand health measurements
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_health_snapshot() -> str:
    """On-demand health snapshot readings (2-minute wrist measurements).

    These are manual measurements taken via the watch's Health Snapshot
    feature, capturing HR, HRV, SpO2, stress, and respiration simultaneously.
    """
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, raw_json
               FROM health_snapshot
               ORDER BY calendar_date DESC""",
        )

        parsed = []
        for r in rows:
            entry = {"date": r["calendar_date"]}
            if r["raw_json"]:
                try:
                    entry["data"] = json.loads(r["raw_json"])
                except (json.JSONDecodeError, TypeError):
                    entry["data"] = r["raw_json"]
            parsed.append(entry)

        return json.dumps(
            {
                "total_snapshots": len(parsed),
                "snapshots": parsed,
                "note": "No health snapshots taken" if not parsed else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_gear — equipment tracking (shoes, bikes, etc)
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_gear() -> str:
    """Tracked gear/equipment (shoes, bikes, etc) with usage stats."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT gear_id, gear_type, display_name,
                      brand, model, date_begin
               FROM gear""",
        )
        return json.dumps(
            {
                "total_gear": len(rows),
                "gear": rows,
                "note": "No gear tracked" if not rows else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_daily_events — notable daily events
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_daily_events(days: int = 7) -> str:
    """Daily events detected by your Garmin (stress spikes, body battery events, etc)."""
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, raw_json
               FROM daily_events
               WHERE calendar_date >= ?
               ORDER BY calendar_date DESC""",
            [start],
        )

        parsed = []
        for r in rows:
            entry = {"date": r["calendar_date"]}
            if r["raw_json"]:
                try:
                    entry["events"] = json.loads(r["raw_json"])
                except (json.JSONDecodeError, TypeError):
                    entry["events"] = r["raw_json"]
            parsed.append(entry)

        return json.dumps(parsed, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_activity_types — all known activity type definitions
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_activity_types() -> str:
    """All Garmin activity type definitions with IDs and parent categories."""
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT type_id, type_key, parent_type_id
               FROM activity_types
               ORDER BY type_key""",
        )
        return json.dumps(rows, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_hr_zones — heart rate zone definitions
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_hr_zones() -> str:
    """Heart rate zone definitions configured in your Garmin profile."""
    conn = get_connection()
    try:
        rows = query(conn, "SELECT id, raw_json FROM hr_zones")
        parsed = []
        for r in rows:
            entry = {"id": r["id"]}
            if r["raw_json"]:
                try:
                    entry["zones"] = json.loads(r["raw_json"])
                except (json.JSONDecodeError, TypeError):
                    entry["zones"] = r["raw_json"]
            parsed.append(entry)
        return json.dumps(parsed, indent=2, default=str)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")

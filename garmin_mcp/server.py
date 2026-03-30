"""
Garmin MCP server — exposes health and activity data via FastMCP tools.
"""

import json
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from .db import get_connection, init_db, query

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
            cols = query(conn, f"PRAGMA table_info({table_name})")
            row_count = query(conn, f"SELECT COUNT(*) AS cnt FROM {table_name}")[0][
                "cnt"
            ]
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
def garmin_query(sql: str) -> str:
    """Run a custom SELECT query against the Garmin database. Only SELECT statements are allowed."""
    normalized = sql.strip().lstrip(";").strip().upper()
    if not normalized.startswith("SELECT"):
        return json.dumps({"error": "Only SELECT statements are permitted."})
    conn = get_connection()
    try:
        rows = query(conn, sql)
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_health_summary
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_health_summary(
    start_date: str = "", end_date: str = "", days: int = 7
) -> str:
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
        return json.dumps(
            {
                "error": f"Unknown metric '{metric}'. Choose from: {', '.join(_TREND_METRICS)}"
            }
        )

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
        return json.dumps(
            {"metric": metric, "period": period, "data": rows}, indent=2, default=str
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# garmin_sync
# ---------------------------------------------------------------------------


@mcp.tool()
def garmin_sync() -> str:
    """Trigger an incremental sync to fetch the latest Garmin data."""
    try:
        from .sync import incremental_sync

        result = incremental_sync()
        return json.dumps(
            {"status": "success", "result": result}, indent=2, default=str
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")

"""Cross-domain overviews: health summary, today, week, trends and period comparison."""

import json
from datetime import date, timedelta

from ..db import get_connection, query


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
            """SELECT total_steps, resting_heart_rate, min_heart_rate, max_heart_rate,
                      average_stress_level, max_stress_level,
                      body_battery_highest, body_battery_lowest, body_battery_at_wake,
                      average_spo2, lowest_spo2, avg_waking_respiration,
                      total_kilocalories, active_kilocalories,
                      moderate_intensity_minutes, vigorous_intensity_minutes,
                      floors_ascended, sedentary_seconds, active_seconds,
                      highly_active_seconds, sleeping_seconds
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
            """SELECT score, level, feedback_short, feedback_long,
                      recovery_time, recovery_time_factor_percent, recovery_time_factor_feedback,
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

"""Daily health metrics: sleep, HRV, body battery, stress, heart rate, SpO2 and more."""

import json
from datetime import date, timedelta

from ..db import get_connection, query


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
                      ROUND(nap_time_seconds / 60.0, 0) AS nap_min,
                      ROUND(deep_sleep_seconds / 60.0, 0) AS deep_min,
                      ROUND(light_sleep_seconds / 60.0, 0) AS light_min,
                      ROUND(rem_sleep_seconds / 60.0, 0) AS rem_min,
                      ROUND(awake_sleep_seconds / 60.0, 0) AS awake_min,
                      ROUND(unmeasurable_sleep_seconds / 60.0, 0) AS unmeasurable_min,
                      awake_count,
                      CASE WHEN sleep_time_seconds > 0
                           THEN ROUND(deep_sleep_seconds * 100.0 / sleep_time_seconds, 1)
                           ELSE 0 END AS deep_pct,
                      CASE WHEN sleep_time_seconds > 0
                           THEN ROUND(rem_sleep_seconds * 100.0 / sleep_time_seconds, 1)
                           ELSE 0 END AS rem_pct,
                      average_spo2, lowest_spo2,
                      average_hr_sleep AS avg_hr,
                      resting_heart_rate,
                      body_battery_change,
                      average_respiration AS avg_resp,
                      lowest_respiration, highest_respiration,
                      avg_sleep_stress,
                      avg_skin_temp_deviation_c, avg_skin_temp_deviation_f,
                      sleep_score_feedback AS feedback,
                      sleep_score_insight AS insight,
                      sleep_need_minutes,
                      highest_spo2,
                      sleep_score_overall,
                      sleep_light_pct,
                      sleep_score_rem,
                      sleep_score_deep
               FROM sleep
               WHERE calendar_date BETWEEN ? AND ?
               ORDER BY calendar_date""",
            [start_date, end_date],
        )
        return json.dumps({"period": {"start": start_date, "end": end_date}, "nights": rows}, indent=2, default=str)
    finally:
        conn.close()


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
            """SELECT calendar_date, weekly_avg, last_night, last_night_avg,
                      last_night_5min_high, status, feedback_phrase,
                      baseline_low, baseline_upper, start_timestamp, end_timestamp
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
            """SELECT bb.calendar_date,
                      bb.highest AS high,
                      bb.lowest AS low,
                      bb.charged,
                      bb.drained,
                      bb.most_recent,
                      bb.at_wake,
                      bb.during_sleep AS sleep_charge,
                      bb.highest - bb.lowest AS daily_range,
                      s.deep_sleep_seconds,
                      ROUND(s.sleep_time_seconds / 3600.0, 2) AS sleep_hours,
                      s.avg_sleep_stress
               FROM body_battery bb
               LEFT JOIN sleep s ON bb.calendar_date = s.calendar_date
               WHERE bb.calendar_date >= ?
               ORDER BY bb.calendar_date""",
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
            """SELECT s.calendar_date,
                      s.avg_stress,
                      s.max_stress,
                      s.stress_qualifier,
                      ROUND(ds.low_stress_seconds / 3600.0, 1) AS low_stress_hrs,
                      ROUND(ds.medium_stress_seconds / 3600.0, 1) AS med_stress_hrs,
                      ROUND(ds.high_stress_seconds / 3600.0, 1) AS high_stress_hrs
               FROM stress s
               LEFT JOIN daily_summary ds ON s.calendar_date = ds.calendar_date
               WHERE s.calendar_date >= ? AND s.avg_stress IS NOT NULL
               ORDER BY s.calendar_date""",
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
            """SELECT hr.calendar_date, hr.resting_hr AS rhr,
                      hr.min_hr, hr.max_hr, hr.avg_hr,
                      hr.last_7day_avg_resting,
                      hr.last_7day_avg_resting AS avg_resting_heart_rate_7day,
                      ds.min_heart_rate AS ds_min_hr,
                      ds.max_heart_rate AS ds_max_hr,
                      ds.highly_active_seconds,
                      ds.sleeping_seconds
               FROM heart_rate hr
               LEFT JOIN daily_summary ds ON hr.calendar_date = ds.calendar_date
               WHERE hr.calendar_date >= ? AND hr.resting_hr IS NOT NULL
               ORDER BY hr.calendar_date""",
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
                    "avg_hr": r["avg_hr"],
                    "garmin_7d_avg": r["last_7day_avg_resting"],
                    "avg_resting_heart_rate_7day": r["avg_resting_heart_rate_7day"],
                    "computed_7d_avg": avg_7d,
                    "elevated": elevated,
                    "highly_active_seconds": r["highly_active_seconds"],
                    "sleeping_seconds": r["sleeping_seconds"],
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
                      avg_spo2, min_spo2, max_spo2,
                      events_below_threshold, duration_below_threshold_secs,
                      CASE WHEN avg_spo2 < 95 THEN 1 ELSE 0 END AS below_normal,
                      CASE WHEN min_spo2 < 80 THEN 1 ELSE 0 END AS critical_low
               FROM spo2
               WHERE calendar_date >= ? AND avg_spo2 IS NOT NULL
               ORDER BY calendar_date""",
            [start],
        )

        avgs = [r["avg_spo2"] for r in rows if r["avg_spo2"]]
        below_count = sum(1 for r in rows if r.get("below_normal"))
        critical_count = sum(1 for r in rows if r.get("critical_low"))

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
                      sweat_loss_ml, activity_intake_ml,
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
                      avg_waking, avg_sleep,
                      max_value AS max_resp,
                      min_value AS min_resp
               FROM respiration
               WHERE calendar_date >= ? AND avg_waking IS NOT NULL
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


def garmin_health_snapshot() -> str:
    """On-demand health snapshot readings (2-minute wrist measurements).

    These are manual measurements taken via the watch's Health Snapshot
    feature, capturing HR, HRV, SpO2, stress, and respiration simultaneously.
    """
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, activity_name, wellness_activity_type,
                      start_timestamp_local, end_timestamp_local, raw_json
               FROM health_snapshot
               ORDER BY calendar_date DESC""",
        )

        parsed = []
        for r in rows:
            entry = {
                "date": r["calendar_date"],
                "activity_name": r["activity_name"],
                "wellness_activity_type": r["wellness_activity_type"],
                "start": r["start_timestamp_local"],
                "end": r["end_timestamp_local"],
            }
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


def garmin_daily_events(days: int = 7) -> str:
    """Daily events detected by your Garmin (stress spikes, body battery events, etc)."""
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, activity_type, activity_sub_type,
                      start_timestamp_local, end_timestamp_local,
                      duration_seconds, device_id, raw_json
               FROM daily_events
               WHERE calendar_date >= ?
               ORDER BY calendar_date DESC""",
            [start],
        )

        parsed = []
        for r in rows:
            entry = {
                "date": r["calendar_date"],
                "activity_type": r["activity_type"],
                "activity_sub_type": r["activity_sub_type"],
                "start": r["start_timestamp_local"],
                "end": r["end_timestamp_local"],
                "duration_seconds": r["duration_seconds"],
                "device_id": r["device_id"],
            }
            if r["raw_json"]:
                try:
                    entry["events"] = json.loads(r["raw_json"])
                except (json.JSONDecodeError, TypeError):
                    entry["events"] = r["raw_json"]
            parsed.append(entry)

        return json.dumps(parsed, indent=2, default=str)
    finally:
        conn.close()


def garmin_wellness_activity(days: int = 30) -> str:
    """Wellness activity sessions detected by Garmin (yoga, breathwork, etc).

    These are non-sport wellness sessions tracked separately from regular
    activities, including start/end times and activity type.
    """
    start = str(date.today() - timedelta(days=days - 1))
    conn = get_connection()
    try:
        rows = query(
            conn,
            """SELECT calendar_date, activity_name, wellness_activity_type,
                      start_timestamp_local, end_timestamp_local
               FROM wellness_activity
               WHERE calendar_date >= ?
               ORDER BY calendar_date DESC""",
            [start],
        )
        return json.dumps(
            {
                "total": len(rows),
                "sessions": rows,
                "note": "No wellness activity data" if not rows else None,
            },
            indent=2,
            default=str,
        )
    finally:
        conn.close()

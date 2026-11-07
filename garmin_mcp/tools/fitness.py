"""Training load/status, performance metrics and body composition."""

import json
from contextlib import closing
from datetime import date, timedelta

from ..db import get_connection, query


def garmin_training_load() -> str:
    """Compute professional training periodization metrics from activity history.

    Returns:
    - CTL (Chronic Training Load, 42-day EWMA) — long-term fitness proxy
    - ATL (Acute Training Load, 7-day EWMA) — short-term fatigue
    - TSB (Training Stress Balance = CTL - ATL) — form / readiness
    - Weekly volume summary (hours, km, sessions, load)
    - Training load distribution by sport
    """
    with closing(get_connection()) as conn:
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


def garmin_fitness_age(period: str = "month") -> str:
    """Fitness age vs chronological age trajectory over time.

    Shows the gap between biological fitness and real age, aggregated by
    week or month.  A widening gap means you're getting fitter relative
    to your age; a narrowing gap means fitness is declining.
    """
    if period not in ("week", "month"):
        return json.dumps({"error": "period must be 'week' or 'month'."})

    group_expr = "strftime('%Y-W%W', calendar_date)" if period == "week" else "strftime('%Y-%m', calendar_date)"

    with closing(get_connection()) as conn:
        rows = query(
            conn,
            f"""SELECT {group_expr} AS period,
                       ROUND(AVG(chronological_age), 1) AS chrono_age,
                       ROUND(AVG(fitness_age), 1) AS fitness_age,
                       ROUND(AVG(achievable_fitness_age), 1) AS avg_achievable_fitness_age,
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


def garmin_body_composition() -> str:
    """Weight, BMI, and body composition history with trend analysis."""
    with closing(get_connection()) as conn:
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
                      metabolic_age, physique_rating, visceral_fat,
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


def garmin_recovery(days_after: int = 3) -> str:
    """Analyze how your body recovers after hard training sessions.

    For each activity with training_load > 80, shows RHR and HRV for
    the following days. Reveals your personal recovery curve and
    identifies which sports/intensities hit you hardest.

    This is unique — no other Garmin MCP computes recovery signatures.
    """
    with closing(get_connection()) as conn:
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


def garmin_training_status(days: int = 90) -> str:
    """Training status history (Productive, Recovery, Detraining, Unproductive, etc).

    Shows how Garmin classified your training state each day, with a
    breakdown of how many days you spent in each status and when
    transitions happened. Useful for spotting detraining before it deepens.
    """
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
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


def garmin_blood_pressure(days: int = 90) -> str:
    """Blood pressure readings (systolic/diastolic/pulse) if tracked.

    Requires a compatible Garmin blood pressure monitor. Flags readings
    outside normal ranges (>140/90 mmHg per AHA guidelines).
    """
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
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


def garmin_race_predictions(days: int = 30) -> str:
    """Predicted race finish times (5K, 10K, half marathon, marathon).

    Shows daily predictions with human-readable times and trend direction.
    A rising prediction time means declining fitness; falling means improving.
    """
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
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


def garmin_endurance_score(days: int = 30) -> str:
    """Endurance score and VO2max with classification and trend."""
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT calendar_date, overall_score, classification,
                      vo2_max, vo2_max_precise, feedback_phrase, contributors
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


def garmin_hill_score(days: int = 30) -> str:
    """Hill score with endurance and strength sub-scores."""
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT calendar_date, overall_score,
                      endurance_score, strength_score,
                      vo2_max, vo2_max_precise, feedback_phrase_id
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


def garmin_vo2max() -> str:
    """VO2max estimates from activities and the dedicated vo2max table.

    Pulls from both the activity-level VO2max estimates and the
    standalone vo2max tracking table.
    """
    with closing(get_connection()) as conn:
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


def garmin_load_focus(days: int = 28) -> str:
    """Training load distribution across aerobic and anaerobic zones.

    Shows how your training load is split between low aerobic, high aerobic,
    and anaerobic zones, plus a focus_status indicating whether your training
    distribution is optimal.
    """
    start = str(date.today() - timedelta(days=days - 1))
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT calendar_date, anaerobic, high_aerobic, low_aerobic, focus_status
               FROM load_focus
               WHERE calendar_date >= ?
               ORDER BY calendar_date""",
            [start],
        )
        return json.dumps(
            {
                "latest": rows[-1] if rows else {},
                "daily": rows,
                "note": "No load focus data" if not rows else None,
            },
            indent=2,
            default=str,
        )


def garmin_lactate_threshold() -> str:
    """Lactate threshold pace and heart rate by sport.

    The lactate threshold is the highest intensity you can sustain aerobically.
    Used to set training zones and pace targets for races.
    """
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT calendar_date, speed, heart_rate,
                      heart_rate_cycling, rowing_speed, heart_rate_rowing
               FROM lactate_threshold
               ORDER BY calendar_date DESC""",
        )
        return json.dumps(
            {
                "latest": rows[0] if rows else {},
                "history": rows,
                "note": "No lactate threshold data" if not rows else None,
            },
            indent=2,
            default=str,
        )

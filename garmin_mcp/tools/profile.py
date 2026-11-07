"""Devices, gear, workouts, badges, goals, challenges, user profile and HR zones."""

import json
from contextlib import closing

from ..db import get_connection, query


def garmin_devices() -> str:
    """Connected Garmin devices with type and last sync time."""
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT device_id, display_name, device_type, application_key,
                      last_sync, software_version, battery_status, battery_voltage
               FROM device ORDER BY last_sync DESC""",
        )
        return json.dumps(rows, indent=2, default=str)


def garmin_workouts() -> str:
    """Workout library and upcoming schedule.

    Returns saved workouts (training plans, custom workouts) and any
    scheduled workout dates. Useful for understanding planned vs executed training.
    """
    with closing(get_connection()) as conn:
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


def garmin_badges() -> str:
    """Earned badges and achievements with dates.

    Tracks milestones like distance PRs, consistency streaks, and
    special event completions. Shows progression over time.
    """
    with closing(get_connection()) as conn:
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


def garmin_goals() -> str:
    """Active fitness goals and their current progress."""
    with closing(get_connection()) as conn:
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


def garmin_challenges() -> str:
    """Garmin Connect challenges (active and completed)."""
    with closing(get_connection()) as conn:
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


def garmin_user_profile() -> str:
    """User profile and settings stored in Garmin Connect."""
    with closing(get_connection()) as conn:
        rows = query(conn, "SELECT key, raw_json FROM user_profile")
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["raw_json"]) if r["raw_json"] else None
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["raw_json"]
        return json.dumps(result, indent=2, default=str)


def garmin_gear() -> str:
    """Tracked gear/equipment (shoes, bikes, etc) with usage stats."""
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT gear_id, gear_type, display_name,
                      brand, model, date_begin,
                      distance_used_meters, duration_used_seconds, days_used,
                      status, max_usage_distance_meters
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


def garmin_hr_zones() -> str:
    """Heart rate zone definitions configured in your Garmin profile."""
    with closing(get_connection()) as conn:
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

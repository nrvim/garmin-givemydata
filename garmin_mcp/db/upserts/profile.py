"""Upserts for profile, gear, devices, goals, badges and workouts."""

import json
import sqlite3

from ._common import _upsert_raw_only


def upsert_earned_badges(conn: sqlite3.Connection, record: dict) -> None:
    badge_id = record.get("badgeId") or record.get("id")
    if not badge_id:
        return
    conn.execute(
        """INSERT OR REPLACE INTO earned_badges
           (badge_id, badge_key, badge_name, badge_category,
            earned_date, earned_number, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            badge_id,
            record.get("badgeKey"),
            record.get("badgeName") or record.get("displayName"),
            record.get("badgeCategoryName") or record.get("badgeCategory"),
            record.get("badgeEarnedDate") or record.get("earnedDate"),
            record.get("badgeEarnedNumber") or record.get("earnedNumber"),
            json.dumps(record),
        ),
    )


def upsert_workout_schedule(conn, record):
    d = record.get("calendarDate") or record.get("scheduleDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "workout_schedule", "calendar_date", record, d)


def upsert_workout(conn: sqlite3.Connection, record: dict) -> None:
    wid = record.get("workoutId")
    if not wid:
        return
    sport = record.get("sportType", {})
    sport_key = sport.get("sportTypeKey") if isinstance(sport, dict) else None
    conn.execute(
        """INSERT OR REPLACE INTO workouts
           (workout_id, workout_name, sport_type, created_date, updated_date, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            wid,
            record.get("workoutName"),
            sport_key,
            record.get("createdDate"),
            record.get("updateDate"),
            json.dumps(record),
        ),
    )


def upsert_personal_record(conn, record):
    conn.execute(
        """INSERT OR REPLACE INTO personal_record
           (id, display_name, activity_type, pr_type, value, pr_date, activity_id, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.get("id"),
            record.get("activityName"),
            record.get("activityType"),
            str(record.get("typeId")) if record.get("typeId") is not None else None,
            record.get("value"),
            (record.get("actStartDateTimeInGMTFormatted") or "")[:10] or None,
            record.get("activityId"),
            json.dumps(record),
        ),
    )


def upsert_device(conn, record):
    device_id = record.get("deviceId") or record.get("unitId")
    if device_id is None:
        return
    conn.execute(
        """INSERT OR REPLACE INTO device
           (device_id, display_name, device_type, application_key, last_sync,
            software_version, battery_status, battery_voltage, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            device_id,
            record.get("displayName"),
            record.get("deviceTypeSimpleName"),
            record.get("applicationKey"),
            record.get("lastSync"),
            record.get("softwareVersion"),
            record.get("batteryStatus"),
            record.get("batteryVoltage"),
            json.dumps(record),
        ),
    )


def upsert_gear(conn, record):
    g_id = record.get("uuid") or record.get("gearPk")
    if not g_id:
        return
    conn.execute(
        """INSERT OR REPLACE INTO gear
           (gear_id, gear_type, display_name, brand, model, date_begin,
            distance_used_meters, duration_used_seconds, days_used,
            status, max_usage_distance_meters, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(g_id),
            record.get("gearTypeName") or record.get("gearType"),
            record.get("displayName") or record.get("name"),
            record.get("customMakeModel") or record.get("brandName") or record.get("brand"),
            record.get("modelName") or record.get("model"),
            record.get("dateBegin") or record.get("firstUseDate"),
            record.get("distanceUsedMeters"),
            record.get("durationUsedSeconds"),
            record.get("daysUsed"),
            record.get("status"),
            record.get("maxUsageDistanceMeters"),
            json.dumps(record),
        ),
    )


def upsert_goals(conn, record):
    g_id = record.get("id") or record.get("goalId")
    if not g_id:
        return
    conn.execute(
        "INSERT OR REPLACE INTO goals (goal_id, goal_type, goal_value, raw_json) VALUES (?, ?, ?, ?)",
        (g_id, record.get("goalType"), record.get("goalValue"), json.dumps(record)),
    )


def upsert_user_profile(conn, key, record):
    conn.execute(
        "INSERT OR REPLACE INTO user_profile (key, raw_json) VALUES (?, ?)",
        (key, json.dumps(record)),
    )


def upsert_challenges(conn, record, challenge_type="adhoc"):
    conn.execute(
        "INSERT INTO challenges (challenge_type, raw_json) VALUES (?, ?)",
        (challenge_type, json.dumps(record)),
    )


def upsert_training_plans(conn, record):
    conn.execute("INSERT INTO training_plans (raw_json) VALUES (?)", (json.dumps(record),))


def upsert_hr_zones(conn, record):
    conn.execute("INSERT INTO hr_zones (raw_json) VALUES (?)", (json.dumps(record),))

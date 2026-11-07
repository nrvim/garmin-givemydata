"""save_to_db(): route fetched endpoint data to the matching upsert."""

import logging
import sqlite3
from typing import Any

from .upserts.activities import (
    upsert_activity,
    upsert_activity_exercise_sets,
    upsert_activity_hr_zones,
    upsert_activity_splits,
    upsert_activity_trackpoints,
    upsert_activity_trends,
    upsert_activity_types,
    upsert_activity_weather,
    upsert_running_dynamics,
)
from .upserts.daily import (
    upsert_body_battery,
    upsert_calories,
    upsert_daily_events,
    upsert_daily_movement,
    upsert_daily_summary,
    upsert_floors,
    upsert_health_snapshot,
    upsert_health_status,
    upsert_heart_rate,
    upsert_hrv,
    upsert_hrv_timeline,
    upsert_hydration,
    upsert_intensity_minutes,
    upsert_respiration,
    upsert_sleep,
    upsert_sleep_stats,
    upsert_spo2,
    upsert_steps,
    upsert_stress,
    upsert_wellness_activity,
)
from .upserts.fitness import (
    upsert_blood_pressure,
    upsert_endurance_score,
    upsert_fitness_age,
    upsert_hill_score,
    upsert_lactate_threshold,
    upsert_race_predictions,
    upsert_training_readiness,
    upsert_training_status,
    upsert_vo2max,
    upsert_weight,
)
from .upserts.profile import (
    upsert_challenges,
    upsert_device,
    upsert_earned_badges,
    upsert_gear,
    upsert_goals,
    upsert_hr_zones,
    upsert_personal_record,
    upsert_training_plans,
    upsert_user_profile,
    upsert_workout,
    upsert_workout_schedule,
)

# Keep the original logger name so existing logging config still applies.
log = logging.getLogger("garmin_mcp.db")


def _unwrap_gql_data(data):
    """Unwrap GraphQL response: {data: {scalarName: [...]}} -> [...]"""
    if not isinstance(data, dict):
        return data

    # Handle { data: { scalar: ... } }
    if "data" in data and isinstance(data["data"], dict):
        data = data["data"]

    # If it's a single-key dict, return the value (the actual scalar content)
    if len(data) == 1:
        inner = list(data.values())[0]
        return inner if inner is not None else []

    return data


def _ensure_list(data) -> list:
    """Coerce data to a list of records."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _extract_activity_records(data: Any) -> list[dict]:
    """Normalize activity payloads and drop wrapper/error objects."""
    if not data:
        return []
    if isinstance(data, list):
        return [rec for rec in data if isinstance(rec, dict) and rec.get("activityId")]
    if not isinstance(data, dict):
        return []
    if data.get("errors") and not data.get("data"):
        return []
    if isinstance(data.get("activityList"), list):
        return _extract_activity_records(data["activityList"])
    activities_for_day = data.get("ActivitiesForDay")
    if isinstance(activities_for_day, dict) and isinstance(activities_for_day.get("payload"), list):
        return _extract_activity_records(activities_for_day["payload"])
    if "data" in data:
        return _extract_activity_records(data["data"])
    if data.get("activityId"):
        return [data]
    return []


def _extract_weight_records(data: Any) -> list[dict]:
    """Normalize weight payloads from REST and GraphQL endpoints."""
    if not data:
        return []
    if isinstance(data, list):
        records: list[dict] = []
        for item in data:
            records.extend(_extract_weight_records(item))
        return records
    if not isinstance(data, dict):
        return []
    if data.get("errors") and not data.get("data"):
        return []
    if "data" in data:
        return _extract_weight_records(data["data"])
    if isinstance(data.get("dailyWeightSummaries"), list):
        records: list[dict] = []
        for summary in data["dailyWeightSummaries"]:
            if isinstance(summary, dict):
                records.extend(_extract_weight_records(summary.get("allWeightMetrics")))
        return records
    if isinstance(data.get("dateWeightList"), list):
        return _extract_weight_records(data["dateWeightList"])
    if isinstance(data.get("allWeightMetrics"), list):
        return _extract_weight_records(data["allWeightMetrics"])
    if any(key in data for key in ("weight", "calendarDate", "date")):
        return [data]
    return []


def _extract_calories_records(data: Any, cal_date: str = None) -> list[dict]:
    """Normalize calorie payloads from GraphQL and nutrition endpoints."""
    if not data:
        return []
    if isinstance(data, list):
        records: list[dict] = []
        for item in data:
            records.extend(_extract_calories_records(item, cal_date))
        return records
    if not isinstance(data, dict):
        return []
    if data.get("errors") and not data.get("data"):
        return []
    if "data" in data:
        return _extract_calories_records(data["data"], cal_date)

    record_date = data.get("calendarDate") or data.get("mealDate") or data.get("date") or cal_date
    if (
        any(
            key in data
            for key in (
                "totalKilocalories",
                "activeKilocalories",
                "bmrKilocalories",
                "consumedKilocalories",
                "remainingKilocalories",
            )
        )
        and record_date
    ):
        return [{**data, "calendarDate": record_date}]

    for key in ("mealSummaries", "meals", "dailyMeals", "items"):
        meals = data.get(key)
        if isinstance(meals, list):
            meal_calories = []
            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                value = meal.get("calories") or meal.get("kilocalories") or meal.get("totalKilocalories")
                if isinstance(value, (int, float)):
                    meal_calories.append(float(value))
            if meal_calories and record_date:
                return [{**data, "calendarDate": record_date, "consumedKilocalories": sum(meal_calories)}]

    return []


def save_to_db(conn: sqlite3.Connection, endpoint_name: str, data, cal_date: str = None) -> int:
    """Route fetched data to the correct table and upsert it.

    Parameters
    ----------
    conn : sqlite3.Connection
    endpoint_name : str
        The endpoint key from the fetch results (e.g. "daily_summary", "heart_rate",
        "gql_training_readiness", "activities", etc.)
    data : dict or list
        The raw data returned by the API.
    cal_date : str, optional
        The calendar date for daily endpoints (when not embedded in data).

    Returns
    -------
    int
        Number of records upserted.
    """
    if not data:
        return 0

    # Strip gql_ prefix for routing
    name = endpoint_name
    if name.startswith("gql_"):
        name = name[4:]
        data = _unwrap_gql_data(data)

    records = _ensure_list(data)
    count = 0

    try:
        if name == "daily_summary":
            for rec in records:
                upsert_daily_summary(conn, rec)
                count += 1

        elif name == "sleep":
            for rec in records:
                upsert_sleep(conn, rec)
                count += 1

        elif name == "heart_rate" or name == "heart_rate_detail":
            for rec in records:
                upsert_heart_rate(conn, rec, cal_date)
                count += 1

        elif name == "stress":
            for rec in records:
                upsert_stress(conn, rec, cal_date)
                count += 1

        elif name == "spo2":
            for rec in records:
                upsert_spo2(conn, rec, cal_date)
                count += 1

        elif name == "respiration":
            for rec in records:
                upsert_respiration(conn, rec, cal_date)
                count += 1

        elif name in ("body_battery_events", "body_battery_stress"):
            for rec in records:
                upsert_body_battery(conn, rec, cal_date)
                count += 1

        elif name == "steps":
            for rec in records:
                upsert_steps(conn, rec, cal_date)
                count += 1

        elif name == "floors":
            for rec in records:
                upsert_floors(conn, rec, cal_date)
                count += 1

        elif name == "intensity_minutes" or name == "intensity_minutes_weekly":
            for rec in records:
                upsert_intensity_minutes(conn, rec, cal_date)
                count += 1

        elif name == "hydration":
            for rec in records:
                upsert_hydration(conn, rec, cal_date)
                count += 1

        elif name == "fitness_age":
            for rec in records:
                upsert_fitness_age(conn, rec, cal_date)
                count += 1

        elif name == "daily_movement":
            for rec in records:
                upsert_daily_movement(conn, rec, cal_date)
                count += 1

        elif name == "wellness_activity":
            for rec in records:
                upsert_wellness_activity(conn, rec, cal_date)
                count += 1

        elif name in ("training_status_daily", "training_status_weekly", "training_status"):
            for rec in records:
                upsert_training_status(conn, rec, cal_date)
                count += 1

        elif name == "health_status" or name == "health_status_summary":
            # GraphQL healthStatusSummary returns a dict, not wrapped in a list
            if isinstance(data, dict) and "calendarDate" in data:
                upsert_health_status(conn, data, cal_date)
                count += 1
            else:
                for rec in records:
                    upsert_health_status(conn, rec, cal_date)
                    count += 1

        elif name == "daily_events":
            for rec in records:
                upsert_daily_events(conn, rec, cal_date)
                count += 1

        elif name.startswith("activity_trends"):
            # Extract activity type from name: activity_trends_running → running
            parts = name.split("_", 2)
            at = parts[2] if len(parts) > 2 else "all"
            for rec in records:
                upsert_activity_trends(conn, rec, at, cal_date)
                count += 1

        elif name.startswith("activity_stats"):
            parts = name.split("_", 2)
            at = parts[2] if len(parts) > 2 else "all"
            for rec in records:
                upsert_activity_trends(conn, rec, at, cal_date)
                count += 1

        elif name == "activities" or name == "activities_range":
            for rec in _extract_activity_records(data):
                upsert_activity(conn, rec)
                count += 1

        elif name in ("weight_range", "weight_latest", "weight", "weight_range_rest", "weight_first", "goal_weight"):
            for rec in _extract_weight_records(data):
                upsert_weight(conn, rec, cal_date)
                count += 1

        elif name in ("vo2max_trend", "vo2max_running"):
            for rec in records:
                upsert_vo2max(conn, rec, "RUNNING")
                count += 1

        elif name == "vo2max_cycling":
            for rec in records:
                upsert_vo2max(conn, rec, "CYCLING")
                count += 1

        elif name == "lactate_threshold":
            for rec in records:
                upsert_lactate_threshold(conn, rec)
                count += 1

        elif name in ("blood_pressure", "blood_pressure_rest"):
            for rec in records:
                upsert_blood_pressure(conn, rec)
                count += 1

        elif name in ("calories", "nutrition_meals"):
            for rec in _extract_calories_records(data, cal_date):
                upsert_calories(conn, rec)
                count += 1

        elif name == "sleep_stats":
            for rec in records:
                upsert_sleep_stats(conn, rec)
                count += 1

        elif name == "sleep_detail" or name == "sleep_summaries":
            for rec in records:
                upsert_sleep(conn, rec)
                count += 1

        elif name == "health_snapshot":
            for rec in records:
                upsert_health_snapshot(conn, rec)
                count += 1

        elif name == "workout_schedule":
            for rec in records:
                upsert_workout_schedule(conn, rec)
                count += 1

        elif name == "workouts":
            for rec in records:
                upsert_workout(conn, rec)
                count += 1

        elif name in ("hrv", "hrv_daily"):
            # HRV data may be nested: {hrvSummaries: [...]}
            hrv_records = records
            if len(records) == 1 and isinstance(records[0], dict):
                for v in records[0].values():
                    if isinstance(v, list):
                        hrv_records = v
                        break
            for rec in hrv_records:
                if not isinstance(rec, dict):
                    continue
                if rec.get("heartRateVariabilityScalar") is None and not any(
                    rec.get(k) for k in ("calendarDate", "startTimestampLocal", "weeklyAvg", "lastNight", "status")
                ):
                    continue
                if not rec.get("calendarDate") and not rec.get("startTimestampLocal"):
                    continue
                upsert_hrv(conn, rec)
                count += 1

        elif name == "training_readiness":
            for rec in records:
                upsert_training_readiness(conn, rec)
                count += 1

        elif name == "personal_records":
            conn.execute("DELETE FROM personal_record")
            for rec in records:
                upsert_personal_record(conn, rec)
                count += 1

        elif name in ("devices", "devices_historical", "last_used_device", "sensors"):
            for rec in records:
                upsert_device(conn, rec)
                count += 1

        elif name == "activity_types":
            for rec in records:
                upsert_activity_types(conn, rec)
                count += 1

        elif name in ("gear_list", "gear_types"):
            for rec in records:
                upsert_gear(conn, rec)
                count += 1

        elif name == "goals" or name == "user_goals":
            for rec in records:
                upsert_goals(conn, rec)
                count += 1

        elif name in ("personal_info", "user_settings", "social_profile", "user_profile_base"):
            upsert_user_profile(conn, name, data)
            count += 1

        elif name == "hr_zones":
            conn.execute("DELETE FROM hr_zones")
            for rec in records:
                upsert_hr_zones(conn, rec)
                count += 1

        elif name == "training_plans":
            conn.execute("DELETE FROM training_plans")
            for rec in records:
                upsert_training_plans(conn, rec)
                count += 1

        elif name.startswith("challenges_"):
            ctype = name.split("_", 1)[1]  # adhoc, badge, expeditions
            for rec in records:
                upsert_challenges(conn, rec, ctype)
                count += 1

        elif name in ("daily_summaries", "stats_daily"):
            # GraphQL daily summaries and REST stats_daily → merge into daily_summary
            for rec in records:
                upsert_daily_summary(conn, rec)
                count += 1

        elif name in (
            "daily_summaries_avg",
            "stats_averages",
            "daily_summaries_count",
            "sync_timestamp",
            "personal_record_types",
        ):
            # Metadata/averages — skip
            pass

        elif name == "endurance_score":
            for rec in records:
                upsert_endurance_score(conn, rec, cal_date)
                count += 1

        elif name == "hill_score":
            for rec in records:
                upsert_hill_score(conn, rec, cal_date)
                count += 1

        elif name == "race_predictions":
            for rec in records:
                upsert_race_predictions(conn, rec, cal_date)
                count += 1

        elif name == "earned_badges":
            conn.execute("DELETE FROM earned_badges")
            for rec in records:
                upsert_earned_badges(conn, rec)
                count += 1

        elif name == "activity_splits":
            # cal_date holds the activity_id for per-activity endpoints
            aid = int(cal_date) if cal_date else None
            if aid:
                count = upsert_activity_splits(conn, aid, data)

        elif name == "activity_trackpoints":
            # data should be a list of trackpoint tuples for the activity
            aid = int(cal_date) if cal_date else None
            if aid and isinstance(data, list):
                count = upsert_activity_trackpoints(conn, aid, data)

        elif name == "activity_hr_zones":
            aid = int(cal_date) if cal_date else None
            if aid:
                upsert_activity_hr_zones(conn, aid, data)
                count += 1

        elif name == "activity_weather":
            aid = int(cal_date) if cal_date else None
            if aid:
                upsert_activity_weather(conn, aid, data)
                count += 1

        elif name == "activity_details":
            # Detail endpoint has a different structure (summaryDTO, activityTypeDTO)
            # than the list endpoint. Don't overwrite the activity table wholesale —
            # it would null out fields the list endpoint populated. Update raw_json
            # plus the summaryDTO-derived columns, using COALESCE so a detail record
            # only fills in values without clobbering anything already set.
            for rec in records:
                aid = rec.get("activityId")
                if aid:
                    import json as _json

                    summary_dto = rec.get("summaryDTO") or {}
                    conn.execute(
                        """
                        UPDATE activity SET
                            raw_json = ?,
                            body_battery_change      = COALESCE(?, body_battery_change),
                            total_work_kcal          = COALESCE(?, total_work_kcal),
                            avg_grade_adjusted_speed = COALESCE(?, avg_grade_adjusted_speed),
                            activity_steps           = COALESCE(?, activity_steps),
                            activity_min_hr          = COALESCE(?, activity_min_hr),
                            direct_workout_feel      = COALESCE(?, direct_workout_feel),
                            direct_workout_rpe       = COALESCE(?, direct_workout_rpe)
                        WHERE activity_id = ?
                        """,
                        (
                            _json.dumps(rec),
                            summary_dto.get("differenceBodyBattery"),
                            summary_dto.get("totalWork"),
                            summary_dto.get("avgGradeAdjustedSpeed"),
                            summary_dto.get("steps"),
                            summary_dto.get("minHR"),
                            summary_dto.get("directWorkoutFeel"),
                            summary_dto.get("directWorkoutRpe"),
                            aid,
                        ),
                    )
                    # Extract running dynamics if present
                    upsert_running_dynamics(conn, aid, rec)
                    count += 1

        elif name == "hrv_timeline":
            for rec in records:
                upsert_hrv_timeline(conn, rec, cal_date)
                count += 1

        elif name == "activity_exercise_sets":
            aid = int(cal_date) if cal_date else None
            if aid:
                count = upsert_activity_exercise_sets(conn, aid, data)

        else:
            log.debug("save_to_db: no handler for endpoint '%s', skipping %d records", endpoint_name, len(records))

    except Exception as e:
        log.warning("save_to_db error for '%s': %s", endpoint_name, e)

    if count > 0:
        conn.commit()

    return count

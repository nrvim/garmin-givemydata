"""save_to_db(): route fetched endpoint data to the matching upsert."""

import json
import logging
import sqlite3
from typing import Any, Callable, Optional

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


# ---------------------------------------------------------------------------
# Handlers
#
# Each handler receives a _Ctx and increments ctx.count per stored record, so
# that when an upsert raises halfway through a batch, the records stored before
# it are still counted (and therefore committed), exactly as before.
# ---------------------------------------------------------------------------


class _Ctx:
    __slots__ = ("conn", "name", "data", "records", "cal_date", "count")

    def __init__(self, conn: sqlite3.Connection, name: str, data, records: list, cal_date):
        self.conn = conn
        self.name = name
        self.data = data
        self.records = records
        self.cal_date = cal_date
        self.count = 0


Handler = Callable[[_Ctx], None]


def _each(upsert) -> Handler:
    """upsert(conn, rec) for every record."""

    def handler(ctx: _Ctx) -> None:
        for rec in ctx.records:
            upsert(ctx.conn, rec)
            ctx.count += 1

    return handler


def _each_dated(upsert) -> Handler:
    """upsert(conn, rec, cal_date) for every record."""

    def handler(ctx: _Ctx) -> None:
        for rec in ctx.records:
            upsert(ctx.conn, rec, ctx.cal_date)
            ctx.count += 1

    return handler


def _each_with(upsert, *args) -> Handler:
    """upsert(conn, rec, *args) for every record."""

    def handler(ctx: _Ctx) -> None:
        for rec in ctx.records:
            upsert(ctx.conn, rec, *args)
            ctx.count += 1

    return handler


def _replace_all(table: str, upsert) -> Handler:
    """Snapshot endpoints: clear the table, then upsert(conn, rec) for every record."""

    def handler(ctx: _Ctx) -> None:
        ctx.conn.execute(f"DELETE FROM {table}")
        for rec in ctx.records:
            upsert(ctx.conn, rec)
            ctx.count += 1

    return handler


def _skip(ctx: _Ctx) -> None:
    """Metadata/averages endpoints that are intentionally not stored."""


def _activity_id(ctx: _Ctx):
    # Per-activity endpoints pass the activity_id in cal_date.
    return int(ctx.cal_date) if ctx.cal_date else None


def _handle_health_status(ctx: _Ctx) -> None:
    # GraphQL healthStatusSummary returns a dict, not wrapped in a list
    if isinstance(ctx.data, dict) and "calendarDate" in ctx.data:
        upsert_health_status(ctx.conn, ctx.data, ctx.cal_date)
        ctx.count += 1
    else:
        for rec in ctx.records:
            upsert_health_status(ctx.conn, rec, ctx.cal_date)
            ctx.count += 1


def _handle_activity_trends(ctx: _Ctx) -> None:
    # Extract activity type from name: activity_trends_running → running
    parts = ctx.name.split("_", 2)
    at = parts[2] if len(parts) > 2 else "all"
    for rec in ctx.records:
        upsert_activity_trends(ctx.conn, rec, at, ctx.cal_date)
        ctx.count += 1


def _handle_activities(ctx: _Ctx) -> None:
    for rec in _extract_activity_records(ctx.data):
        upsert_activity(ctx.conn, rec)
        ctx.count += 1


def _handle_weight(ctx: _Ctx) -> None:
    for rec in _extract_weight_records(ctx.data):
        upsert_weight(ctx.conn, rec, ctx.cal_date)
        ctx.count += 1


def _handle_calories(ctx: _Ctx) -> None:
    for rec in _extract_calories_records(ctx.data, ctx.cal_date):
        upsert_calories(ctx.conn, rec)
        ctx.count += 1


def _handle_hrv(ctx: _Ctx) -> None:
    # HRV data may be nested: {hrvSummaries: [...]}
    records = ctx.records
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
        upsert_hrv(ctx.conn, rec)
        ctx.count += 1


def _handle_user_profile(ctx: _Ctx) -> None:
    upsert_user_profile(ctx.conn, ctx.name, ctx.data)
    ctx.count += 1


def _handle_challenges(ctx: _Ctx) -> None:
    ctype = ctx.name.split("_", 1)[1]  # adhoc, badge, expeditions
    for rec in ctx.records:
        upsert_challenges(ctx.conn, rec, ctype)
        ctx.count += 1


def _handle_activity_splits(ctx: _Ctx) -> None:
    aid = _activity_id(ctx)
    if aid:
        ctx.count = upsert_activity_splits(ctx.conn, aid, ctx.data)


def _handle_activity_trackpoints(ctx: _Ctx) -> None:
    # data should be a list of trackpoint tuples for the activity
    aid = _activity_id(ctx)
    if aid and isinstance(ctx.data, list):
        ctx.count = upsert_activity_trackpoints(ctx.conn, aid, ctx.data)


def _handle_activity_exercise_sets(ctx: _Ctx) -> None:
    aid = _activity_id(ctx)
    if aid:
        ctx.count = upsert_activity_exercise_sets(ctx.conn, aid, ctx.data)


def _handle_activity_hr_zones(ctx: _Ctx) -> None:
    aid = _activity_id(ctx)
    if aid:
        upsert_activity_hr_zones(ctx.conn, aid, ctx.data)
        ctx.count += 1


def _handle_activity_weather(ctx: _Ctx) -> None:
    aid = _activity_id(ctx)
    if aid:
        upsert_activity_weather(ctx.conn, aid, ctx.data)
        ctx.count += 1


def _handle_activity_details(ctx: _Ctx) -> None:
    # Detail endpoint has a different structure (summaryDTO, activityTypeDTO)
    # than the list endpoint. Don't overwrite the activity table wholesale —
    # it would null out fields the list endpoint populated. Update raw_json
    # plus the summaryDTO-derived columns, using COALESCE so a detail record
    # only fills in values without clobbering anything already set.
    for rec in ctx.records:
        aid = rec.get("activityId")
        if aid:
            summary_dto = rec.get("summaryDTO") or {}
            ctx.conn.execute(
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
                    json.dumps(rec),
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
            upsert_running_dynamics(ctx.conn, aid, rec)
            ctx.count += 1


# ---------------------------------------------------------------------------
# Routing table: endpoint name (after stripping "gql_") → handler
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Handler] = {
    # Daily health
    "daily_summary": _each(upsert_daily_summary),
    "daily_summaries": _each(upsert_daily_summary),  # GraphQL daily summaries → daily_summary
    "stats_daily": _each(upsert_daily_summary),  # REST stats_daily → daily_summary
    "sleep": _each(upsert_sleep),
    "sleep_detail": _each(upsert_sleep),
    "sleep_summaries": _each(upsert_sleep),
    "sleep_stats": _each(upsert_sleep_stats),
    "heart_rate": _each_dated(upsert_heart_rate),
    "heart_rate_detail": _each_dated(upsert_heart_rate),
    "stress": _each_dated(upsert_stress),
    "spo2": _each_dated(upsert_spo2),
    "respiration": _each_dated(upsert_respiration),
    "body_battery_events": _each_dated(upsert_body_battery),
    "body_battery_stress": _each_dated(upsert_body_battery),
    "steps": _each_dated(upsert_steps),
    "floors": _each_dated(upsert_floors),
    "intensity_minutes": _each_dated(upsert_intensity_minutes),
    "intensity_minutes_weekly": _each_dated(upsert_intensity_minutes),
    "hydration": _each_dated(upsert_hydration),
    "daily_movement": _each_dated(upsert_daily_movement),
    "wellness_activity": _each_dated(upsert_wellness_activity),
    "daily_events": _each_dated(upsert_daily_events),
    "health_status": _handle_health_status,
    "health_status_summary": _handle_health_status,
    "health_snapshot": _each(upsert_health_snapshot),
    "hrv": _handle_hrv,
    "hrv_daily": _handle_hrv,
    "hrv_timeline": _each_dated(upsert_hrv_timeline),
    "calories": _handle_calories,
    "nutrition_meals": _handle_calories,
    # Fitness and body composition
    "fitness_age": _each_dated(upsert_fitness_age),
    "training_status": _each_dated(upsert_training_status),
    "training_status_daily": _each_dated(upsert_training_status),
    "training_status_weekly": _each_dated(upsert_training_status),
    "training_readiness": _each(upsert_training_readiness),
    "weight": _handle_weight,
    "weight_range": _handle_weight,
    "weight_latest": _handle_weight,
    "weight_range_rest": _handle_weight,
    "weight_first": _handle_weight,
    "goal_weight": _handle_weight,
    "vo2max_trend": _each_with(upsert_vo2max, "RUNNING"),
    "vo2max_running": _each_with(upsert_vo2max, "RUNNING"),
    "vo2max_cycling": _each_with(upsert_vo2max, "CYCLING"),
    "lactate_threshold": _each(upsert_lactate_threshold),
    "blood_pressure": _each(upsert_blood_pressure),
    "blood_pressure_rest": _each(upsert_blood_pressure),
    "endurance_score": _each_dated(upsert_endurance_score),
    "hill_score": _each_dated(upsert_hill_score),
    "race_predictions": _each_dated(upsert_race_predictions),
    # Activities
    "activities": _handle_activities,
    "activities_range": _handle_activities,
    "activity_details": _handle_activity_details,
    "activity_splits": _handle_activity_splits,
    "activity_trackpoints": _handle_activity_trackpoints,
    "activity_hr_zones": _handle_activity_hr_zones,
    "activity_weather": _handle_activity_weather,
    "activity_exercise_sets": _handle_activity_exercise_sets,
    "activity_types": _each(upsert_activity_types),
    # Profile, gear, workouts
    "workout_schedule": _each(upsert_workout_schedule),
    "workouts": _each(upsert_workout),
    "personal_records": _replace_all("personal_record", upsert_personal_record),
    "devices": _each(upsert_device),
    "devices_historical": _each(upsert_device),
    "last_used_device": _each(upsert_device),
    "sensors": _each(upsert_device),
    "gear_list": _each(upsert_gear),
    "gear_types": _each(upsert_gear),
    "goals": _each(upsert_goals),
    "user_goals": _each(upsert_goals),
    "personal_info": _handle_user_profile,
    "user_settings": _handle_user_profile,
    "social_profile": _handle_user_profile,
    "user_profile_base": _handle_user_profile,
    "hr_zones": _replace_all("hr_zones", upsert_hr_zones),
    "training_plans": _replace_all("training_plans", upsert_training_plans),
    "earned_badges": _replace_all("earned_badges", upsert_earned_badges),
    # Metadata/averages — intentionally not stored
    "daily_summaries_avg": _skip,
    "stats_averages": _skip,
    "daily_summaries_count": _skip,
    "sync_timestamp": _skip,
    "personal_record_types": _skip,
}

# Families of endpoints whose name carries a parameter (checked after exact names).
_PREFIX_HANDLERS: tuple[tuple[str, Handler], ...] = (
    ("activity_trends", _handle_activity_trends),
    ("activity_stats", _handle_activity_trends),
    ("challenges_", _handle_challenges),
)


def _resolve_handler(name: str) -> Optional[Handler]:
    handler = _HANDLERS.get(name)
    if handler is not None:
        return handler
    for prefix, prefix_handler in _PREFIX_HANDLERS:
        if name.startswith(prefix):
            return prefix_handler
    return None


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
        For per-activity endpoints it holds the activity_id.

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
    ctx = _Ctx(conn, name, data, records, cal_date)

    try:
        handler = _resolve_handler(name)
        if handler is None:
            log.debug("save_to_db: no handler for endpoint '%s', skipping %d records", endpoint_name, len(records))
        else:
            handler(ctx)
    except Exception as e:
        log.warning("save_to_db error for '%s': %s", endpoint_name, e)

    if ctx.count > 0:
        conn.commit()

    return ctx.count

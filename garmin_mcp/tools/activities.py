"""Activities, activity details, GPS trackpoints, activity types and personal records."""

import json
from contextlib import closing

from ..db import get_connection, query


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

    with closing(get_connection()) as conn:
        try:
            rows = query(conn, sql, params)
            return json.dumps(rows, indent=2, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})


def garmin_activity_detail(activity_id: int = 0, last: bool = False) -> str:
    """Deep-dive into a single activity.

    Pass activity_id, or set last=True for the most recent activity.
    Returns the activity summary plus splits, HR zones, weather, and
    exercise sets (if available).
    """
    with closing(get_connection()) as conn:
        if last or activity_id == 0:
            rows = query(conn, "SELECT activity_id FROM activity ORDER BY start_time_local DESC LIMIT 1")
            if not rows:
                return json.dumps({"error": "No activities found."})
            activity_id = rows[0]["activity_id"]

        activity = query(
            conn,
            """SELECT activity_id, activity_name, activity_type, start_time_local,
                      ROUND(duration_seconds / 60.0, 1) AS duration_min,
                      ROUND(elapsed_duration_seconds / 60.0, 1) AS elapsed_duration_min,
                      ROUND(moving_duration_seconds / 60.0, 1) AS moving_duration_min,
                      ROUND(distance_meters / 1000.0, 2) AS distance_km,
                      calories, ROUND(average_hr, 0) AS avg_hr, ROUND(max_hr, 0) AS max_hr,
                      ROUND(average_speed, 3) AS avg_speed_mps,
                      ROUND(max_speed, 3) AS max_speed_mps,
                      ROUND(elevation_gain, 0) AS elevation_gain_m,
                      ROUND(elevation_loss, 0) AS elevation_loss_m,
                      ROUND(min_elevation, 0) AS min_elevation_m,
                      ROUND(max_elevation, 0) AS max_elevation_m,
                      ROUND(avg_power, 0) AS avg_power_w,
                      ROUND(max_power, 0) AS max_power_w,
                      ROUND(norm_power, 0) AS norm_power_w,
                      ROUND(training_stress_score, 1) AS tss,
                      intensity_factor,
                      ROUND(training_load, 1) AS training_load,
                      aerobic_training_effect, anaerobic_training_effect,
                      vo2max_value,
                      ROUND(avg_cadence, 0) AS avg_cadence,
                      ROUND(max_cadence, 0) AS max_cadence,
                      ROUND(avg_respiration, 1) AS avg_respiration,
                      lap_count, location_name,
                      min_temperature, max_temperature,
                      body_battery_change, total_work_kcal,
                      ROUND(avg_grade_adjusted_speed, 3) AS avg_grade_adjusted_speed_mps,
                      activity_steps, activity_min_hr,
                      direct_workout_feel, direct_workout_rpe
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
                      ROUND(elevation_loss, 1) AS elev_loss,
                      ROUND(avg_cadence, 0) AS avg_cadence,
                      avg_swim_cadence, avg_swolf, total_strokes,
                      swim_stroke, num_active_lengths,
                      ROUND(normalized_power, 0) AS norm_power_w,
                      ROUND(avg_respiration_rate, 1) AS avg_resp,
                      ROUND(max_respiration_rate, 1) AS max_resp,
                      ROUND(calories, 0) AS calories
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

        # Garmin reports exercise-set weight in grams; surface it as kg.
        exercise_sets = query(
            conn,
            """SELECT set_number, exercise_name, exercise_category,
                      reps, ROUND(weight / 1000.0, 2) AS weight_kg,
                      ROUND(duration_seconds, 0) AS duration_sec
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
            # Keep actual exercise sets (named or at least categorised) and drop
            # empty REST rows. An ACTIVE set Garmin couldn't name still carries
            # reps/weight/duration worth surfacing.
            "exercise_sets": [s for s in exercise_sets if s.get("exercise_name") or s.get("exercise_category")]
            if exercise_sets
            else [],
            "running_dynamics": dynamics[0] if dynamics else {},
        }
        return json.dumps(result, indent=2, default=str)


def garmin_activity_trackpoints(activity_id: int, limit: int = 500, offset: int = 0) -> str:
    """GPS trackpoints for an activity — lat/lon, altitude, distance, speed,
    HR, cadence, power, temperature, in chronological order.

    Trackpoints are sampled ~1/second, so a 1-hour activity has ~3600 points.
    Pass `limit` and `offset` to page through them; the response includes
    `total_count` so callers know the full size.

    Best for: elevation profile, HR drift over time, GPS track inspection,
    pacing analysis, climb segmentation. For aggregate stats (splits, zones,
    weather), prefer garmin_activity_detail — much smaller output.
    """
    with closing(get_connection()) as conn:
        total_row = query(
            conn,
            "SELECT COUNT(*) AS n FROM activity_trackpoints WHERE activity_id = ?",
            [activity_id],
        )
        total = total_row[0]["n"] if total_row else 0
        if total == 0:
            return json.dumps(
                {
                    "activity_id": activity_id,
                    "total_count": 0,
                    "hint": "No trackpoints stored for this activity. Run "
                    "'garmin-givemydata --rebuild-trackpoints' to backfill from FIT files, "
                    "or 'garmin-givemydata' (which now parses trackpoints by default).",
                },
                indent=2,
            )

        points = query(
            conn,
            """SELECT seq, timestamp_utc, latitude, longitude, altitude_m,
                      distance_m, speed_mps, heart_rate_bpm, cadence,
                      power_w, temperature_c
               FROM activity_trackpoints
               WHERE activity_id = ?
               ORDER BY seq
               LIMIT ? OFFSET ?""",
            [activity_id, limit, offset],
        )
        return json.dumps(
            {
                "activity_id": activity_id,
                "total_count": total,
                "returned": len(points),
                "offset": offset,
                "trackpoints": points,
            },
            indent=2,
            default=str,
        )


def garmin_records() -> str:
    """All personal records (PRs) with activity details and dates."""
    with closing(get_connection()) as conn:
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


def garmin_activity_types() -> str:
    """All Garmin activity type definitions with IDs and parent categories."""
    with closing(get_connection()) as conn:
        rows = query(
            conn,
            """SELECT type_id, type_key, parent_type_id
               FROM activity_types
               ORDER BY type_key""",
        )
        return json.dumps(rows, indent=2, default=str)

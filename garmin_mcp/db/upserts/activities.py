"""Upserts for activities and per-activity detail tables."""

import json
import sqlite3


def upsert_running_dynamics(conn: sqlite3.Connection, aid: int, record: dict) -> None:
    # Running dynamics are usually in summaryDTO for activity details
    summary = record.get("summaryDTO") or record
    conn.execute(
        """INSERT OR REPLACE INTO running_dynamics
           (activity_id, avg_gct, avg_gct_balance, avg_vert_osc, avg_vert_ratio, avg_stride_len, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            aid,
            summary.get("groundContactTime"),
            summary.get("groundContactBalance"),
            summary.get("verticalOscillation"),
            summary.get("verticalRatio"),
            summary.get("strideLength"),
            json.dumps(record),
        ),
    )


def upsert_activity(conn: sqlite3.Connection, record: dict) -> None:
    if not isinstance(record, dict) or not record.get("activityId"):
        return

    activity_type_dict: dict = record.get("activityType") or {}
    activity_type_key: str | None = activity_type_dict.get("typeKey")
    activity_type_id: int | None = activity_type_dict.get("typeId")
    parent_type_id: int | None = activity_type_dict.get("parentTypeId")
    avg_cadence = (
        record.get("averageRunningCadenceInStepsPerMinute")
        or record.get("averageBikingCadenceInRevPerMinute")
        or record.get("averageCadence")
    )
    max_cadence = (
        record.get("maxRunningCadenceInStepsPerMinute")
        or record.get("maxBikingCadenceInRevPerMinute")
        or record.get("maxCadence")
    )
    # summaryDTO is present in activity_details records; flat list records lack it.
    # Use INSERT OR IGNORE + UPDATE (not INSERT OR REPLACE) so a flat-list record
    # arriving after a detailed record doesn't blank out the summaryDTO-only columns.
    # COALESCE preserves prior non-null values for those fields.
    summary: dict = record.get("summaryDTO") or {}
    activity_id = record.get("activityId")
    conn.execute("INSERT OR IGNORE INTO activity (activity_id) VALUES (?)", (activity_id,))
    conn.execute(
        """
        UPDATE activity SET
            activity_name = :activity_name,
            activity_type = :activity_type,
            activity_type_id = :activity_type_id,
            parent_type_id = :parent_type_id,
            start_time_local = :start_time_local,
            start_time_gmt = :start_time_gmt,
            duration_seconds = :duration_seconds,
            elapsed_duration_seconds = :elapsed_duration_seconds,
            moving_duration_seconds = :moving_duration_seconds,
            distance_meters = :distance_meters,
            calories = :calories,
            bmr_calories = :bmr_calories,
            average_hr = :average_hr,
            max_hr = :max_hr,
            average_speed = :average_speed,
            max_speed = :max_speed,
            elevation_gain = :elevation_gain,
            elevation_loss = :elevation_loss,
            min_elevation = :min_elevation,
            max_elevation = :max_elevation,
            avg_power = :avg_power,
            max_power = :max_power,
            norm_power = :norm_power,
            training_stress_score = :training_stress_score,
            intensity_factor = :intensity_factor,
            aerobic_training_effect = :aerobic_training_effect,
            anaerobic_training_effect = :anaerobic_training_effect,
            vo2max_value = :vo2max_value,
            avg_cadence = :avg_cadence,
            max_cadence = :max_cadence,
            avg_respiration = :avg_respiration,
            training_load = :training_load,
            moderate_intensity_minutes = :moderate_intensity_minutes,
            vigorous_intensity_minutes = :vigorous_intensity_minutes,
            start_latitude = :start_latitude,
            start_longitude = :start_longitude,
            end_latitude = :end_latitude,
            end_longitude = :end_longitude,
            location_name = :location_name,
            lap_count = :lap_count,
            water_estimated = :water_estimated,
            min_temperature = :min_temperature,
            max_temperature = :max_temperature,
            manufacturer = :manufacturer,
            device_id = :device_id,
            body_battery_change      = COALESCE(:body_battery_change, body_battery_change),
            total_work_kcal          = COALESCE(:total_work_kcal, total_work_kcal),
            avg_grade_adjusted_speed = COALESCE(:avg_grade_adjusted_speed, avg_grade_adjusted_speed),
            activity_steps           = COALESCE(:activity_steps, activity_steps),
            activity_min_hr          = COALESCE(:activity_min_hr, activity_min_hr),
            direct_workout_feel      = COALESCE(:direct_workout_feel, direct_workout_feel),
            direct_workout_rpe       = COALESCE(:direct_workout_rpe, direct_workout_rpe),
            raw_json = :raw_json
        WHERE activity_id = :activity_id
        """,
        {
            "activity_id": activity_id,
            "activity_name": record.get("activityName"),
            "activity_type": activity_type_key,
            "activity_type_id": activity_type_id,
            "parent_type_id": parent_type_id,
            "start_time_local": record.get("startTimeLocal"),
            "start_time_gmt": record.get("startTimeGMT"),
            "duration_seconds": record.get("duration"),
            "elapsed_duration_seconds": record.get("elapsedDuration"),
            "moving_duration_seconds": record.get("movingDuration"),
            "distance_meters": record.get("distance"),
            "calories": record.get("calories"),
            "bmr_calories": record.get("bmrCalories"),
            "average_hr": record.get("averageHR"),
            "max_hr": record.get("maxHR"),
            "average_speed": record.get("averageSpeed"),
            "max_speed": record.get("maxSpeed"),
            "elevation_gain": record.get("elevationGain"),
            "elevation_loss": record.get("elevationLoss"),
            "min_elevation": record.get("minElevation"),
            "max_elevation": record.get("maxElevation"),
            "avg_power": record.get("avgPower"),
            "max_power": record.get("maxPower"),
            "norm_power": record.get("normPower"),
            "training_stress_score": record.get("trainingStressScore"),
            "intensity_factor": record.get("intensityFactor"),
            "aerobic_training_effect": record.get("aerobicTrainingEffect"),
            "anaerobic_training_effect": record.get("anaerobicTrainingEffect"),
            "vo2max_value": record.get("vO2MaxValue"),
            "avg_cadence": avg_cadence,
            "max_cadence": max_cadence,
            "avg_respiration": record.get("avgRespirationRate"),
            "training_load": record.get("activityTrainingLoad"),
            "moderate_intensity_minutes": record.get("moderateIntensityMinutes"),
            "vigorous_intensity_minutes": record.get("vigorousIntensityMinutes"),
            "start_latitude": record.get("startLatitude"),
            "start_longitude": record.get("startLongitude"),
            "end_latitude": record.get("endLatitude"),
            "end_longitude": record.get("endLongitude"),
            "location_name": record.get("locationName"),
            "lap_count": record.get("lapCount"),
            "water_estimated": record.get("waterEstimated"),
            "min_temperature": record.get("minTemperature"),
            "max_temperature": record.get("maxTemperature"),
            "manufacturer": record.get("manufacturer"),
            "device_id": record.get("deviceId"),
            "body_battery_change": summary.get("differenceBodyBattery"),
            "total_work_kcal": summary.get("totalWork"),
            "avg_grade_adjusted_speed": summary.get("avgGradeAdjustedSpeed"),
            "activity_steps": summary.get("steps"),
            "activity_min_hr": summary.get("minHR"),
            "direct_workout_feel": summary.get("directWorkoutFeel"),
            "direct_workout_rpe": summary.get("directWorkoutRpe"),
            "raw_json": json.dumps(record),
        },
    )


def upsert_activity_splits(conn: sqlite3.Connection, activity_id: int, data) -> int:
    if not data:
        return 0
    splits = data if isinstance(data, list) else data.get("lapDTOs") or data.get("splitDTOs") or [data]
    count = 0
    for i, split in enumerate(splits):
        conn.execute(
            """INSERT OR REPLACE INTO activity_splits
               (activity_id, split_number, distance_meters, duration_seconds,
                average_speed, average_hr, max_hr, elevation_gain, elevation_loss,
                avg_cadence, avg_swim_cadence, avg_swolf, total_strokes,
                swim_stroke, num_active_lengths,
                normalized_power, avg_respiration_rate, max_respiration_rate,
                start_latitude, start_longitude, end_latitude, end_longitude,
                start_time_gmt, calories,
                left_pedal_smoothness, right_pedal_smoothness,
                left_torque_effectiveness, right_torque_effectiveness,
                surface_unpaved_pct, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                activity_id,
                i + 1,
                split.get("distance"),
                split.get("duration"),
                split.get("averageSpeed"),
                split.get("averageHR"),
                split.get("maxHR"),
                split.get("elevationGain"),
                split.get("elevationLoss"),
                split.get("averageRunCadence") or split.get("averageBikeCadence"),
                split.get("averageSwimCadence") or None,
                split.get("averageSWOLF") or None,
                split.get("totalNumberOfStrokes") or None,
                split.get("swimStroke"),
                split.get("numberOfActiveLengths") or None,
                split.get("normalizedPower"),
                split.get("avgRespirationRate"),
                split.get("maxRespirationRate"),
                split.get("startLatitude"),
                split.get("startLongitude"),
                split.get("endLatitude"),
                split.get("endLongitude"),
                split.get("startTimeGMT"),
                split.get("calories"),
                split.get("leftPedalSmoothness"),
                split.get("rightPedalSmoothness"),
                split.get("leftTorqueEffectiveness"),
                split.get("rightTorqueEffectiveness"),
                split.get("surfaceTypeUnpavedPercentage"),
                json.dumps(split),
            ),
        )
        count += 1
    return count


def upsert_activity_hr_zones(conn: sqlite3.Connection, activity_id: int, data) -> None:
    if not data:
        return
    zones = data if isinstance(data, list) else data.get("heartRateZones") or [data]
    zone_seconds = [None] * 5
    for z in zones:
        zone_num = z.get("zoneNumber")
        if zone_num and 1 <= zone_num <= 5:
            zone_seconds[zone_num - 1] = z.get("secsInZone")
    conn.execute(
        """INSERT OR REPLACE INTO activity_hr_zones
           (activity_id, zone1_seconds, zone2_seconds, zone3_seconds,
            zone4_seconds, zone5_seconds, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (activity_id, *zone_seconds, json.dumps(data)),
    )


def upsert_activity_weather(conn: sqlite3.Connection, activity_id: int, data) -> None:
    if not data:
        return
    record = data if isinstance(data, dict) else {}
    conn.execute(
        """INSERT OR REPLACE INTO activity_weather
           (activity_id, temperature, apparent_temperature, humidity,
            wind_speed, wind_direction, weather_type, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            activity_id,
            record.get("temp") or record.get("temperature"),
            record.get("apparentTemp") or record.get("apparentTemperature"),
            record.get("relativeHumidity") or record.get("humidity"),
            record.get("windSpeed"),
            record.get("windDirection"),
            record.get("weatherTypeDTO", {}).get("desc")
            if isinstance(record.get("weatherTypeDTO"), dict)
            else record.get("weatherType"),
            json.dumps(data),
        ),
    )


def upsert_activity_exercise_sets(conn: sqlite3.Connection, activity_id: int, data) -> int:
    if not data:
        return 0
    sets = data if isinstance(data, list) else data.get("exerciseSets") or [data]
    count = 0
    for i, s in enumerate(sets):
        # The Garmin API nests exercise details under an 'exercises' list within
        # each set. That list is a ranked set of candidate classifications, each
        # with a 'probability' — pick the most likely one rather than assuming
        # list order. Fall back to top-level keys for backward compatibility.
        exercises = s.get("exercises") or []
        best_exercise = max(exercises, key=lambda e: e.get("probability") or 0) if exercises else {}
        exercise_name = best_exercise.get("name") or s.get("exerciseName")
        exercise_category = best_exercise.get("category") or s.get("exerciseCategory")
        # repetitionCount can legitimately be 0 (e.g. a timed hold); only fall
        # back to 'reps' when the key is genuinely absent, not when it is 0.
        reps = s.get("repetitionCount")
        if reps is None:
            reps = s.get("reps")
        conn.execute(
            """INSERT OR REPLACE INTO activity_exercise_sets
               (activity_id, set_number, exercise_name, exercise_category,
                reps, weight, duration_seconds, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                activity_id,
                i + 1,
                exercise_name,
                exercise_category,
                reps,
                s.get("weight"),
                s.get("duration"),
                json.dumps(s),
            ),
        )
        count += 1
    return count


def upsert_activity_trackpoints(conn: sqlite3.Connection, activity_id: int, trackpoints: list) -> int:
    """Upsert trackpoints for an activity. Expects list of tuples: (seq, timestamp, lat, lon, alt, dist, speed, hr, cad, pwr, temp)"""
    if not trackpoints:
        return 0

    # Delete existing trackpoints for this activity
    conn.execute("DELETE FROM activity_trackpoints WHERE activity_id = ?", (activity_id,))

    # Insert new trackpoints
    conn.executemany(
        """
        INSERT INTO activity_trackpoints (
            activity_id, seq, timestamp_utc, latitude, longitude, altitude_m,
            distance_m, speed_mps, heart_rate_bpm, cadence, power_w, temperature_c
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(activity_id, *row) for row in trackpoints],
    )
    return len(trackpoints)


def upsert_activity_trends(conn, record, activity_type="all", cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        conn.execute(
            "INSERT OR REPLACE INTO activity_trends (calendar_date, activity_type, raw_json) VALUES (?, ?, ?)",
            (d, activity_type, json.dumps(record)),
        )


def upsert_activity_types(conn, record):
    t_id = record.get("typeId")
    if t_id is None:
        return
    conn.execute(
        "INSERT OR REPLACE INTO activity_types (type_id, type_key, parent_type_id, raw_json) VALUES (?, ?, ?, ?)",
        (t_id, record.get("typeKey"), record.get("parentTypeId"), json.dumps(record)),
    )

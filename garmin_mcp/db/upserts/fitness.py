"""Upserts for fitness, performance and body-composition metrics."""

import json
import sqlite3


def upsert_lactate_threshold(conn: sqlite3.Connection, record: dict) -> None:
    d = record.get("calendarDate")
    if not d:
        return
    d = str(d)[:10]
    conn.execute(
        """INSERT INTO lactate_threshold
           (calendar_date, speed, heart_rate, heart_rate_cycling, rowing_speed, heart_rate_rowing, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(calendar_date) DO UPDATE SET
             speed = COALESCE(excluded.speed, lactate_threshold.speed),
             heart_rate = COALESCE(excluded.heart_rate, lactate_threshold.heart_rate),
             heart_rate_cycling = COALESCE(excluded.heart_rate_cycling, lactate_threshold.heart_rate_cycling),
             rowing_speed = COALESCE(excluded.rowing_speed, lactate_threshold.rowing_speed),
             heart_rate_rowing = COALESCE(excluded.heart_rate_rowing, lactate_threshold.heart_rate_rowing),
             raw_json = excluded.raw_json""",
        (
            d,
            record.get("speed"),
            # Garmin's lactate threshold endpoint actually sends "hearRate" (missing 't')
            # in some firmware versions.  We check for both spellings.
            record.get("hearRate") or record.get("heartRate"),
            record.get("heartRateCycling"),
            record.get("rowSpeed"),
            record.get("heartRateRowing"),
            json.dumps(record),
        ),
    )


def upsert_training_readiness(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO training_readiness (
            calendar_date, score, level, feedback_short, feedback_long,
            recovery_time, recovery_time_factor_percent, recovery_time_factor_feedback,
            hrv_factor_percent, hrv_factor_feedback, hrv_weekly_average,
            sleep_history_factor_percent, sleep_history_factor_feedback,
            stress_history_factor_percent, stress_history_factor_feedback,
            acwr_factor_percent, acwr_factor_feedback, raw_json
        ) VALUES (
            :calendar_date, :score, :level, :feedback_short, :feedback_long,
            :recovery_time, :recovery_time_factor_percent, :recovery_time_factor_feedback,
            :hrv_factor_percent, :hrv_factor_feedback, :hrv_weekly_average,
            :sleep_history_factor_percent, :sleep_history_factor_feedback,
            :stress_history_factor_percent, :stress_history_factor_feedback,
            :acwr_factor_percent, :acwr_factor_feedback, :raw_json
        )
        """,
        {
            "calendar_date": record.get("calendarDate"),
            "score": record.get("score"),
            "level": record.get("level"),
            "feedback_short": record.get("feedbackShort"),
            "feedback_long": record.get("feedbackLong"),
            "recovery_time": record.get("recoveryTime"),
            "recovery_time_factor_percent": record.get("recoveryTimeFactorPercent"),
            "recovery_time_factor_feedback": record.get("recoveryTimeFactorFeedback"),
            "hrv_factor_percent": record.get("hrvFactorPercent"),
            "hrv_factor_feedback": record.get("hrvFactorFeedback"),
            "hrv_weekly_average": record.get("hrvWeeklyAverage"),
            "sleep_history_factor_percent": record.get("sleepHistoryFactorPercent"),
            "sleep_history_factor_feedback": record.get("sleepHistoryFactorFeedback"),
            "stress_history_factor_percent": record.get("stressHistoryFactorPercent"),
            "stress_history_factor_feedback": record.get("stressHistoryFactorFeedback"),
            "acwr_factor_percent": record.get("acwrFactorPercent"),
            "acwr_factor_feedback": record.get("acwrFactorFeedback"),
            "raw_json": json.dumps(record),
        },
    )


def upsert_fitness_age(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO fitness_age (calendar_date, chronological_age, fitness_age, achievable_fitness_age, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("chronologicalAge"),
            record.get("fitnessAge"),
            record.get("achievableFitnessAge"),
            json.dumps(record),
        ),
    )


def upsert_weight(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    from datetime import datetime

    d = cal_date or record.get("calendarDate")
    ts = record.get("date")

    # The "date" field from weight endpoints is a Unix timestamp in
    # milliseconds (e.g. 1743345400000).
    if isinstance(ts, (int, float)):
        # Garmin uses milliseconds; values > 1e10 are ms timestamps
        if ts > 1e10:
            actual_ts = int(ts)
            ts_seconds = ts / 1000
        else:
            actual_ts = int(ts * 1000)
            ts_seconds = ts
        if not d:
            d = datetime.fromtimestamp(ts_seconds).strftime("%Y-%m-%d")
    elif isinstance(ts, str) and ts[:4].isdigit() and "-" in ts:
        d = ts[:10]
        # Try to parse string date back to timestamp if missing
        try:
            actual_ts = int(datetime.fromisoformat(ts).timestamp() * 1000)
        except Exception:
            actual_ts = None
    else:
        actual_ts = None

    if not d:
        return
    d = str(d)[:10]

    # If we have no timestamp at all, we fall back to day-level resolution
    # but use a dummy timestamp to avoid primary key conflicts.
    if actual_ts is None:
        try:
            actual_ts = int(datetime.fromisoformat(d).timestamp() * 1000)
        except Exception:
            return

    source = record.get("sourceType") or record.get("source")

    conn.execute(
        """INSERT OR REPLACE INTO weight
           (timestamp, calendar_date, weight, bmi, body_fat, body_water, bone_mass, muscle_mass,
            metabolic_age, physique_rating, visceral_fat, source, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            actual_ts,
            d,
            record.get("weight"),
            record.get("bmi"),
            record.get("bodyFat"),
            record.get("bodyWater"),
            record.get("boneMass"),
            record.get("muscleMass"),
            record.get("metabolicAge"),
            record.get("physiqueRating"),
            record.get("visceralFat"),
            source,
            json.dumps(record),
        ),
    )


def upsert_vo2max(conn: sqlite3.Connection, record: dict, sport: str = "RUNNING") -> None:
    d = record.get("calendarDate") or record.get("date")
    val = record.get("vo2MaxPreciseValue") or record.get("value") or record.get("generic")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO vo2max (calendar_date, sport, value, raw_json) VALUES (?, ?, ?, ?)",
        (d, sport, val, json.dumps(record)),
    )


def upsert_blood_pressure(conn: sqlite3.Connection, record: dict) -> None:
    d = record.get("calendarDate") or record.get("date") or record.get("measurementTimestampLocal", "")[:10]
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO blood_pressure (calendar_date, systolic, diastolic, pulse, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("systolic"),
            record.get("diastolic"),
            record.get("pulse"),
            json.dumps(record),
        ),
    )


def upsert_endurance_score(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    contributors = record.get("contributors")
    conn.execute(
        """INSERT OR REPLACE INTO endurance_score
           (calendar_date, overall_score, classification, vo2_max, vo2_max_precise,
            feedback_phrase, contributors, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("overallScore"),
            record.get("classification"),
            record.get("vo2Max"),
            record.get("vo2MaxPreciseValue"),
            record.get("feedbackPhrase"),
            json.dumps(contributors) if contributors is not None else None,
            json.dumps(record),
        ),
    )


def upsert_hill_score(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO hill_score
           (calendar_date, overall_score, endurance_score, strength_score,
            vo2_max, vo2_max_precise, feedback_phrase_id, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("overallScore"),
            record.get("enduranceScore"),
            record.get("strengthScore"),
            record.get("vo2Max"),
            record.get("vo2MaxPreciseValue"),
            record.get("hillScoreFeedbackPhraseId"),
            json.dumps(record),
        ),
    )


def upsert_race_predictions(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO race_predictions
           (calendar_date, time_5k, time_10k, time_half_marathon, time_marathon, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("time5K") or record.get("time5k"),
            record.get("time10K") or record.get("time10k"),
            record.get("timeHalfMarathon") or record.get("timeHalf"),
            record.get("timeMarathon"),
            json.dumps(record),
        ),
    )


def upsert_training_status(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")

    # Extract from nested structure if present
    status = None
    acute = None
    chronic = None

    # Option 1: Top-level fields (rare in new API)
    status = record.get("trainingStatus") or record.get("status")

    # Option 2: Nested latestTrainingStatusData (common in modern API)
    # The keys inside latestTrainingStatusData are device IDs
    nested = record.get("latestTrainingStatusData")
    if isinstance(nested, dict) and nested:
        # Get the first device's data (usually there's only one primary)
        device_data = next(iter(nested.values()))
        if isinstance(device_data, dict):
            status = device_data.get("trainingStatusFeedbackPhrase") or device_data.get("trainingStatus")
            if not d:
                d = device_data.get("calendarDate")

            # Extract load
            acute_dto = device_data.get("acuteTrainingLoadDTO")
            if isinstance(acute_dto, dict):
                acute = acute_dto.get("dailyTrainingLoadAcute")
                chronic = acute_dto.get("dailyTrainingLoadChronic")

    if not d:
        return

    # Garmin's numeric codes do not match the old hard-coded enum guess.
    # Prefer the explicit phrase when Garmin provides it; otherwise preserve
    # the numeric code as-is instead of silently mislabeling the row.
    if isinstance(status, int):
        status = f"STATUS_{status}"

    conn.execute(
        """INSERT OR REPLACE INTO training_status (calendar_date, status, acute_load, chronic_load, raw_json)
           VALUES (?, ?, ?, ?, ?)""",
        (d, status, acute, chronic, json.dumps(record)),
    )

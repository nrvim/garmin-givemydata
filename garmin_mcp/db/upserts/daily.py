"""Upserts for daily health tables (keyed by calendar_date)."""

import json
import sqlite3
from typing import Any

from ._common import _mean_sample_values, _upsert_raw_only


def upsert_hrv_timeline(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate")
    if not d:
        return
    readings = record.get("hrvReadings")
    if not isinstance(readings, list):
        readings = record.get("hrvValues", [])
    conn.execute(
        "INSERT OR REPLACE INTO hrv_timeline (calendar_date, reading_count, raw_json) VALUES (?, ?, ?)",
        (d, len(readings) if isinstance(readings, list) else 0, json.dumps(record)),
    )


def upsert_daily_summary(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_summary (
            calendar_date, total_steps, daily_step_goal,
            total_distance_meters, total_kilocalories, active_kilocalories,
            bmr_kilocalories, remaining_kilocalories, highly_active_seconds,
            active_seconds, sedentary_seconds, sleeping_seconds,
            moderate_intensity_minutes, vigorous_intensity_minutes,
            intensity_minutes_goal, floors_ascended, floors_descended,
            floors_ascended_goal, min_heart_rate, max_heart_rate,
            resting_heart_rate, avg_resting_heart_rate_7day,
            average_stress_level, max_stress_level, low_stress_seconds,
            medium_stress_seconds, high_stress_seconds, stress_qualifier,
            body_battery_charged, body_battery_drained, body_battery_highest,
            body_battery_lowest, body_battery_most_recent, body_battery_at_wake,
            body_battery_during_sleep, average_spo2, lowest_spo2, latest_spo2,
            avg_waking_respiration, highest_respiration, lowest_respiration,
            source, raw_json
        ) VALUES (
            :calendar_date, :total_steps, :daily_step_goal,
            :total_distance_meters, :total_kilocalories, :active_kilocalories,
            :bmr_kilocalories, :remaining_kilocalories, :highly_active_seconds,
            :active_seconds, :sedentary_seconds, :sleeping_seconds,
            :moderate_intensity_minutes, :vigorous_intensity_minutes,
            :intensity_minutes_goal, :floors_ascended, :floors_descended,
            :floors_ascended_goal, :min_heart_rate, :max_heart_rate,
            :resting_heart_rate, :avg_resting_heart_rate_7day,
            :average_stress_level, :max_stress_level, :low_stress_seconds,
            :medium_stress_seconds, :high_stress_seconds, :stress_qualifier,
            :body_battery_charged, :body_battery_drained, :body_battery_highest,
            :body_battery_lowest, :body_battery_most_recent, :body_battery_at_wake,
            :body_battery_during_sleep, :average_spo2, :lowest_spo2, :latest_spo2,
            :avg_waking_respiration, :highest_respiration, :lowest_respiration,
            :source, :raw_json
        )
        """,
        {
            "calendar_date": record.get("calendarDate"),
            "total_steps": record.get("totalSteps"),
            "daily_step_goal": record.get("dailyStepGoal"),
            "total_distance_meters": record.get("totalDistanceMeters"),
            "total_kilocalories": record.get("totalKilocalories"),
            "active_kilocalories": record.get("activeKilocalories"),
            "bmr_kilocalories": record.get("bmrKilocalories"),
            "remaining_kilocalories": record.get("remainingKilocalories"),
            "highly_active_seconds": record.get("highlyActiveSeconds"),
            "active_seconds": record.get("activeSeconds"),
            "sedentary_seconds": record.get("sedentarySeconds"),
            "sleeping_seconds": record.get("sleepingSeconds"),
            "moderate_intensity_minutes": record.get("moderateIntensityMinutes"),
            "vigorous_intensity_minutes": record.get("vigorousIntensityMinutes"),
            "intensity_minutes_goal": record.get("intensityMinutesGoal"),
            "floors_ascended": record.get("floorsAscended"),
            "floors_descended": record.get("floorsDescended"),
            "floors_ascended_goal": record.get("floorsAscendedGoal"),
            "min_heart_rate": record.get("minHeartRate"),
            "max_heart_rate": record.get("maxHeartRate"),
            "resting_heart_rate": record.get("restingHeartRate"),
            "avg_resting_heart_rate_7day": record.get("averageRestingHeartRate"),
            "average_stress_level": record.get("averageStressLevel"),
            "max_stress_level": record.get("maxStressLevel"),
            "low_stress_seconds": record.get("lowStressSeconds"),
            "medium_stress_seconds": record.get("mediumStressSeconds"),
            "high_stress_seconds": record.get("highStressSeconds"),
            "stress_qualifier": record.get("stressQualifier"),
            "body_battery_charged": record.get("bodyBatteryChargedValue"),
            "body_battery_drained": record.get("bodyBatteryDrainedValue"),
            "body_battery_highest": record.get("bodyBatteryHighestValue"),
            "body_battery_lowest": record.get("bodyBatteryLowestValue"),
            "body_battery_most_recent": record.get("bodyBatteryMostRecentValue"),
            "body_battery_at_wake": record.get("bodyBatteryAtWakeTime"),
            "body_battery_during_sleep": record.get("bodyBatteryDuringSleep"),
            "average_spo2": record.get("averageSpo2"),
            "lowest_spo2": record.get("lowestSpo2"),
            "latest_spo2": record.get("latestSpo2"),
            "avg_waking_respiration": record.get("avgWakingRespirationValue"),
            "highest_respiration": record.get("highestRespirationValue"),
            "lowest_respiration": record.get("lowestRespirationValue"),
            "source": record.get("source"),
            "raw_json": json.dumps(record),
        },
    )
    upsert_calories_from_daily_summary(conn, record)
    upsert_body_battery_from_daily_summary(conn, record)


def upsert_body_battery_from_daily_summary(conn: sqlite3.Connection, record: dict) -> None:
    """Backfill body_battery aggregate columns from a daily_summary record.

    The body_battery_events endpoint only returns time-series data; the
    aggregates (highest/lowest/charged/drained/etc.) live in daily_summary.
    Mirrors upsert_calories_from_daily_summary.

    raw_json is intentionally not touched here so the events-endpoint
    time-series payload (when present) is preserved.
    """
    d = record.get("calendarDate")
    if not d:
        return
    charged = record.get("bodyBatteryChargedValue")
    drained = record.get("bodyBatteryDrainedValue")
    highest = record.get("bodyBatteryHighestValue")
    lowest = record.get("bodyBatteryLowestValue")
    most_recent = record.get("bodyBatteryMostRecentValue")
    at_wake = record.get("bodyBatteryAtWakeTime")
    during_sleep = record.get("bodyBatteryDuringSleep")
    if all(v is None for v in (charged, drained, highest, lowest, most_recent, at_wake, during_sleep)):
        return
    conn.execute(
        """
        INSERT INTO body_battery (calendar_date, charged, drained, highest, lowest, most_recent, at_wake, during_sleep)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(calendar_date) DO UPDATE SET
            charged      = COALESCE(excluded.charged,      body_battery.charged),
            drained      = COALESCE(excluded.drained,      body_battery.drained),
            highest      = COALESCE(excluded.highest,      body_battery.highest),
            lowest       = COALESCE(excluded.lowest,       body_battery.lowest),
            most_recent  = COALESCE(excluded.most_recent,  body_battery.most_recent),
            at_wake      = COALESCE(excluded.at_wake,      body_battery.at_wake),
            during_sleep = COALESCE(excluded.during_sleep, body_battery.during_sleep)
        """,
        (d, charged, drained, highest, lowest, most_recent, at_wake, during_sleep),
    )


def upsert_calories_from_daily_summary(conn: sqlite3.Connection, record: dict) -> None:
    d = record.get("calendarDate")
    total = record.get("totalKilocalories")
    active = record.get("activeKilocalories")
    bmr = record.get("bmrKilocalories")
    remaining = record.get("remainingKilocalories")
    if not d or all(v is None for v in (total, active, bmr, remaining)):
        return
    conn.execute(
        """
        INSERT INTO calories (calendar_date, total, active, bmr, consumed, remaining, raw_json)
        VALUES (?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(calendar_date) DO UPDATE SET
            total = excluded.total,
            active = excluded.active,
            bmr = excluded.bmr,
            remaining = COALESCE(excluded.remaining, calories.remaining),
            consumed = COALESCE(calories.consumed, excluded.consumed),
            raw_json = CASE
                WHEN calories.consumed IS NOT NULL THEN calories.raw_json
                ELSE excluded.raw_json
            END
        """,
        (
            d,
            total,
            active,
            bmr,
            remaining,
            json.dumps(record),
        ),
    )


def upsert_sleep(conn: sqlite3.Connection, record: dict) -> None:
    dto: dict[str, Any] = record.get("dailySleepDTO") or record
    sleep_seconds = dto.get("sleepTimeSeconds")
    if sleep_seconds is None:
        return
    calendar_date = dto.get("calendarDate") or record.get("date")
    avg_hr_sleep = (
        dto.get("averageHrSleep") or dto.get("avgSleepHR") or _mean_sample_values(record.get("sleepHeartRate"), "value")
    )
    # Multiple endpoints write to the same sleep row (REST sleep + GQL sleep_summaries +
    # GQL sleep_detail). They arrive in arbitrary order and carry different subsets of
    # fields. INSERT OR REPLACE would silently wipe out values set by a prior endpoint.
    # INSERT OR IGNORE + UPDATE lets each endpoint contribute what it knows while
    # COALESCE preserves non-null values already set by earlier writes.
    conn.execute("INSERT OR IGNORE INTO sleep (calendar_date) VALUES (?)", (calendar_date,))
    conn.execute(
        """
        UPDATE sleep SET
            sleep_time_seconds          = ?,
            nap_time_seconds            = ?,
            deep_sleep_seconds          = ?,
            light_sleep_seconds         = ?,
            rem_sleep_seconds           = ?,
            awake_sleep_seconds         = ?,
            unmeasurable_sleep_seconds  = ?,
            awake_count                 = ?,
            average_spo2                = ?,
            lowest_spo2                 = ?,
            average_hr_sleep            = ?,
            average_respiration         = ?,
            lowest_respiration          = ?,
            highest_respiration         = ?,
            avg_sleep_stress            = ?,
            sleep_score_feedback        = ?,
            sleep_score_insight         = ?,
            body_battery_change         = COALESCE(?, body_battery_change),
            resting_heart_rate          = COALESCE(?, resting_heart_rate),
            avg_skin_temp_deviation_c   = COALESCE(?, avg_skin_temp_deviation_c),
            avg_skin_temp_deviation_f   = COALESCE(?, avg_skin_temp_deviation_f),
            sleep_need_minutes          = COALESCE(?, sleep_need_minutes),
            highest_spo2                = COALESCE(?, highest_spo2),
            sleep_score_overall         = COALESCE(?, sleep_score_overall),
            sleep_light_pct             = COALESCE(?, sleep_light_pct),
            sleep_score_rem             = COALESCE(?, sleep_score_rem),
            sleep_score_deep            = COALESCE(?, sleep_score_deep),
            raw_json                    = ?
        WHERE calendar_date = ?
        """,
        (
            sleep_seconds,
            dto.get("napTimeSeconds"),
            dto.get("deepSleepSeconds"),
            dto.get("lightSleepSeconds"),
            dto.get("remSleepSeconds"),
            dto.get("awakeSleepSeconds"),
            dto.get("unmeasurableSleepSeconds"),
            dto.get("awakeSleepCount") or dto.get("awakeCount"),
            dto.get("averageSpO2Value"),
            dto.get("lowestSpO2Value"),
            avg_hr_sleep,
            dto.get("averageRespirationValue"),
            dto.get("lowestRespirationValue"),
            dto.get("highestRespirationValue"),
            dto.get("avgSleepStress"),
            dto.get("sleepScoreFeedback"),
            dto.get("sleepScoreInsight"),
            record.get("bodyBatteryChange"),
            record.get("restingHeartRate"),
            record.get("avgSkinTempDeviationC"),
            record.get("avgSkinTempDeviationF"),
            (dto.get("sleepNeed") or {}).get("actual")
            if isinstance(dto.get("sleepNeed"), dict)
            else dto.get("sleepNeed"),
            dto.get("highestSpO2Value"),
            # Guard against Garmin returning null for a specific score sub-dict
            # (e.g. {"sleepScores": {"overall": null}}) — happens on nights where
            # scoring failed but the rest of the structure is present.
            ((dto.get("sleepScores") or {}).get("overall") or {}).get("value"),
            ((dto.get("sleepScores") or {}).get("lightPercentage") or {}).get("value"),
            ((dto.get("sleepScores") or {}).get("remPercentage") or {}).get("value"),
            ((dto.get("sleepScores") or {}).get("deepPercentage") or {}).get("value"),
            json.dumps(record),
            calendar_date,
        ),
    )


def upsert_hrv(conn: sqlite3.Connection, record: dict) -> None:
    baseline = record.get("baseline")
    if isinstance(baseline, dict) and "baselineLowUpper" not in record:
        record = {
            **record,
            "baselineLowUpper": baseline.get("lowUpper"),
            "baselineBalancedUpper": baseline.get("balancedUpper"),
        }
    conn.execute(
        """
        INSERT OR REPLACE INTO hrv (
            calendar_date, weekly_avg, last_night, last_night_avg,
            last_night_5min_high, status, feedback_phrase, baseline_low, baseline_upper,
            start_timestamp, end_timestamp, raw_json
        ) VALUES (
            :calendar_date, :weekly_avg, :last_night, :last_night_avg,
            :last_night_5min_high, :status, :feedback_phrase, :baseline_low, :baseline_upper,
            :start_timestamp, :end_timestamp, :raw_json
        )
        """,
        {
            "calendar_date": record.get("calendarDate") or record.get("startTimestampLocal", "")[:10],
            "weekly_avg": record.get("weeklyAvg"),
            "last_night": record.get("lastNight"),
            "last_night_avg": record.get("lastNightAvg") or record.get("lastNight5MinHigh"),
            "last_night_5min_high": record.get("lastNight5MinHigh"),
            "status": record.get("status"),
            "feedback_phrase": record.get("feedbackPhrase"),
            "baseline_low": record.get("baselineLowUpper"),
            "baseline_upper": record.get("baselineBalancedUpper"),
            "start_timestamp": record.get("startTimestampLocal") or record.get("startTimestampGMT"),
            "end_timestamp": record.get("endTimestampLocal") or record.get("endTimestampGMT"),
            "raw_json": json.dumps(record),
        },
    )


def upsert_heart_rate(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    avg_hr = (
        record.get("averageHeartRate") or record.get("avgHR") or _mean_sample_values(record.get("heartRateValues"), 1)
    )
    # gql_heart_rate_detail also routes here but lacks lastSevenDaysAvgRestingHeartRate.
    # COALESCE preserves the value written by the REST endpoint.
    conn.execute("INSERT OR IGNORE INTO heart_rate (calendar_date) VALUES (?)", (d,))
    conn.execute(
        """
        UPDATE heart_rate SET
            resting_hr              = ?,
            min_hr                  = ?,
            max_hr                  = ?,
            avg_hr                  = ?,
            last_7day_avg_resting   = COALESCE(?, last_7day_avg_resting),
            raw_json                = ?
        WHERE calendar_date = ?
        """,
        (
            record.get("restingHeartRate") or record.get("restingHR"),
            record.get("minHeartRate") or record.get("minHR"),
            record.get("maxHeartRate") or record.get("maxHR"),
            avg_hr,
            record.get("lastSevenDaysAvgRestingHeartRate"),
            json.dumps(record),
            d,
        ),
    )


def upsert_stress(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO stress (calendar_date, avg_stress, max_stress, stress_qualifier, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("avgStressLevel") or record.get("averageStressLevel") or record.get("overallStressLevel"),
            record.get("maxStressLevel") or record.get("highStressDuration"),
            record.get("stressQualifier"),
            json.dumps(record),
        ),
    )


def upsert_spo2(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO spo2 "
        "(calendar_date, avg_spo2, min_spo2, max_spo2, events_below_threshold, duration_below_threshold_secs, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            d,
            record.get("averageSpo2") or record.get("averageSpO2"),
            record.get("lowestSpo2") or record.get("lowestSpO2"),
            record.get("latestSpo2") or record.get("latestSpO2"),
            record.get("numberOfEventsBelowThreshold"),
            record.get("durationOfEventsBelowThreshold"),
            json.dumps(record),
        ),
    )


def upsert_respiration(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    # avgSleepRespirationValue may be absent on same-day syncs (sleep not yet processed).
    # COALESCE preserves the value once it arrives without requiring a full re-sync.
    conn.execute("INSERT OR IGNORE INTO respiration (calendar_date) VALUES (?)", (d,))
    conn.execute(
        """
        UPDATE respiration SET
            avg_waking  = ?,
            avg_sleep   = COALESCE(?, avg_sleep),
            min_value   = ?,
            max_value   = ?,
            raw_json    = ?
        WHERE calendar_date = ?
        """,
        (
            record.get("avgWakingRespirationValue"),
            record.get("avgSleepRespirationValue"),
            record.get("lowestRespirationValue"),
            record.get("highestRespirationValue"),
            json.dumps(record),
            d,
        ),
    )


def upsert_body_battery(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    """Upsert a body_battery row from the events endpoint.

    The events payload only carries time-series data, not the per-day
    aggregate values (which live in daily_summary and are written via
    upsert_body_battery_from_daily_summary). Use COALESCE on every
    aggregate column so that calling this *after* the daily_summary path
    does not erase the aggregates with NULLs from the events payload.
    raw_json is always replaced with the latest events payload.
    """
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT INTO body_battery
           (calendar_date, charged, drained, highest, lowest, most_recent, at_wake, during_sleep, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(calendar_date) DO UPDATE SET
               charged      = COALESCE(excluded.charged,      body_battery.charged),
               drained      = COALESCE(excluded.drained,      body_battery.drained),
               highest      = COALESCE(excluded.highest,      body_battery.highest),
               lowest       = COALESCE(excluded.lowest,       body_battery.lowest),
               most_recent  = COALESCE(excluded.most_recent,  body_battery.most_recent),
               at_wake      = COALESCE(excluded.at_wake,      body_battery.at_wake),
               during_sleep = COALESCE(excluded.during_sleep, body_battery.during_sleep),
               raw_json     = excluded.raw_json
        """,
        (
            d,
            record.get("bodyBatteryChargedValue") or record.get("charged"),
            record.get("bodyBatteryDrainedValue") or record.get("drained"),
            record.get("bodyBatteryHighestValue") or record.get("highest"),
            record.get("bodyBatteryLowestValue") or record.get("lowest"),
            record.get("bodyBatteryMostRecentValue") or record.get("mostRecent") or record.get("most_recent"),
            record.get("bodyBatteryAtWakeTime") or record.get("atWake") or record.get("at_wake"),
            record.get("bodyBatteryDuringSleep") or record.get("duringSleep") or record.get("during_sleep"),
            json.dumps(record),
        ),
    )


def upsert_steps(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO steps (calendar_date, total_steps, goal, distance_meters, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("totalSteps") or record.get("steps"),
            record.get("dailyStepGoal") or record.get("stepGoal"),
            record.get("totalDistanceMeters") or record.get("totalDistance"),
            json.dumps(record),
        ),
    )


def upsert_floors(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO floors (calendar_date, ascended, descended, goal, raw_json) VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("floorsAscended"),
            record.get("floorsDescended"),
            record.get("floorsAscendedGoal") or record.get("floorGoal"),
            json.dumps(record),
        ),
    )


def upsert_intensity_minutes(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO intensity_minutes (calendar_date, moderate, vigorous, goal, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("moderateIntensityMinutes") or record.get("weeklyModerate"),
            record.get("vigorousIntensityMinutes") or record.get("weeklyVigorous"),
            record.get("intensityMinutesGoal") or record.get("weeklyGoal"),
            json.dumps(record),
        ),
    )


def upsert_hydration(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    # sweatLossInML / activityIntakeInML may be absent depending on endpoint variant.
    # COALESCE preserves values once written without requiring a full re-sync.
    conn.execute("INSERT OR IGNORE INTO hydration (calendar_date) VALUES (?)", (d,))
    conn.execute(
        """
        UPDATE hydration SET
            goal_ml             = ?,
            intake_ml           = ?,
            sweat_loss_ml       = COALESCE(?, sweat_loss_ml),
            activity_intake_ml  = COALESCE(?, activity_intake_ml),
            raw_json            = ?
        WHERE calendar_date = ?
        """,
        (
            record.get("goalInML") or record.get("baseGoalInML"),
            record.get("intakeInML") or record.get("valueInML"),
            record.get("sweatLossInML"),
            record.get("activityIntakeInML"),
            json.dumps(record),
            d,
        ),
    )


def upsert_calories(conn: sqlite3.Connection, record: dict) -> None:
    d = record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT INTO calories
           (calendar_date, total, active, bmr, consumed, remaining, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(calendar_date) DO UPDATE SET
               total = COALESCE(excluded.total, calories.total),
               active = COALESCE(excluded.active, calories.active),
               bmr = COALESCE(excluded.bmr, calories.bmr),
               consumed = COALESCE(excluded.consumed, calories.consumed),
               remaining = COALESCE(excluded.remaining, calories.remaining),
               raw_json = excluded.raw_json""",
        (
            d,
            record.get("totalKilocalories"),
            record.get("activeKilocalories"),
            record.get("bmrKilocalories"),
            record.get("consumedKilocalories"),
            record.get("remainingKilocalories"),
            json.dumps(record),
        ),
    )


def upsert_daily_movement(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "daily_movement", "calendar_date", record, d)


def upsert_wellness_activity(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO wellness_activity
           (calendar_date, activity_name, wellness_activity_type,
            start_timestamp_local, end_timestamp_local, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("activityName"),
            record.get("wellnessActivityType"),
            record.get("startTimestampLocal"),
            record.get("endTimestampLocal"),
            json.dumps(record),
        ),
    )


def upsert_health_status(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        conn.execute(
            "INSERT OR REPLACE INTO health_status (calendar_date, overall_status, raw_json) VALUES (?, ?, ?)",
            (d, record.get("overallStatus"), json.dumps(record)),
        )


def upsert_daily_events(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    # record may be a list of event objects; use the first non-rest event for scalars
    events = record if isinstance(record, list) else [record]
    primary = next((e for e in events if e.get("activityType")), events[0] if events else {})
    conn.execute(
        """INSERT OR REPLACE INTO daily_events
           (calendar_date, activity_type, activity_sub_type,
            start_timestamp_local, end_timestamp_local, duration_seconds, device_id, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d,
            primary.get("activityType"),
            primary.get("activitySubType"),
            primary.get("startTimestampLocal"),
            primary.get("endTimestampLocal"),
            primary.get("duration"),
            primary.get("deviceId"),
            json.dumps(record),
        ),
    )


def upsert_sleep_stats(conn, record):
    d = record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "sleep_stats", "calendar_date", record, d)


def upsert_health_snapshot(conn, record):
    d = record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO health_snapshot
           (calendar_date, activity_name, wellness_activity_type,
            start_timestamp_local, end_timestamp_local, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("activityName"),
            record.get("wellnessActivityType"),
            record.get("startTimestampLocal"),
            record.get("endTimestampLocal"),
            json.dumps(record),
        ),
    )

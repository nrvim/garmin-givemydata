"""
SQLite database layer for Garmin MCP server.

Provides connection management, schema initialization, upsert helpers for each
data type, a save_to_db() router, and a generic query helper.

35 dedicated tables — every Garmin endpoint maps to exactly one table.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional


def _default_db_path() -> str:
    """Find the database using the same logic as the CLI."""
    import os

    env_dir = os.environ.get("GARMIN_DATA_DIR")
    if env_dir:
        return str(Path(env_dir) / "garmin.db")

    cwd = Path.cwd()
    if (cwd / "garmin.db").exists() or (cwd / ".env").exists() or (cwd / "garmin_givemydata.py").exists():
        return str(cwd / "garmin.db")

    home_dir = Path.home() / ".garmin-givemydata"
    home_dir.mkdir(parents=True, exist_ok=True)
    return str(home_dir / "garmin.db")


DB_PATH = _default_db_path()

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a sqlite3 connection with WAL mode and Row factory enabled."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema — 35 tables
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- =========================================================================
-- Daily Health Tables (keyed by calendar_date)
-- =========================================================================

CREATE TABLE IF NOT EXISTS daily_summary (
    calendar_date                   TEXT PRIMARY KEY,
    total_steps                     INTEGER,
    daily_step_goal                 INTEGER,
    total_distance_meters           REAL,
    total_kilocalories              REAL,
    active_kilocalories             REAL,
    bmr_kilocalories                REAL,
    remaining_kilocalories          REAL,
    highly_active_seconds           INTEGER,
    active_seconds                  INTEGER,
    sedentary_seconds               INTEGER,
    sleeping_seconds                INTEGER,
    moderate_intensity_minutes      INTEGER,
    vigorous_intensity_minutes      INTEGER,
    intensity_minutes_goal          INTEGER,
    floors_ascended                 REAL,
    floors_descended                REAL,
    floors_ascended_goal            REAL,
    min_heart_rate                  INTEGER,
    max_heart_rate                  INTEGER,
    resting_heart_rate              INTEGER,
    avg_resting_heart_rate_7day     REAL,
    average_stress_level            INTEGER,
    max_stress_level                INTEGER,
    low_stress_seconds              INTEGER,
    medium_stress_seconds           INTEGER,
    high_stress_seconds             INTEGER,
    stress_qualifier                TEXT,
    body_battery_charged            INTEGER,
    body_battery_drained            INTEGER,
    body_battery_highest            INTEGER,
    body_battery_lowest             INTEGER,
    body_battery_most_recent        INTEGER,
    body_battery_at_wake            INTEGER,
    body_battery_during_sleep       INTEGER,
    average_spo2                    REAL,
    lowest_spo2                     REAL,
    latest_spo2                     REAL,
    avg_waking_respiration          REAL,
    highest_respiration             REAL,
    lowest_respiration              REAL,
    source                          TEXT,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS sleep (
    calendar_date               TEXT PRIMARY KEY,
    sleep_time_seconds          INTEGER,
    nap_time_seconds            INTEGER,
    deep_sleep_seconds          INTEGER,
    light_sleep_seconds         INTEGER,
    rem_sleep_seconds           INTEGER,
    awake_sleep_seconds         INTEGER,
    unmeasurable_sleep_seconds  INTEGER,
    awake_count                 INTEGER,
    average_spo2                REAL,
    lowest_spo2                 REAL,
    average_hr_sleep            REAL,
    average_respiration         REAL,
    lowest_respiration          REAL,
    highest_respiration         REAL,
    avg_sleep_stress            REAL,
    sleep_score_feedback        TEXT,
    sleep_score_insight         TEXT,
    raw_json                    TEXT
);

CREATE TABLE IF NOT EXISTS heart_rate (
    calendar_date   TEXT PRIMARY KEY,
    resting_hr      INTEGER,
    min_hr          INTEGER,
    max_hr          INTEGER,
    avg_hr          REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS stress (
    calendar_date       TEXT PRIMARY KEY,
    avg_stress          INTEGER,
    max_stress          INTEGER,
    stress_qualifier    TEXT,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS spo2 (
    calendar_date   TEXT PRIMARY KEY,
    avg_spo2        REAL,
    min_spo2        REAL,
    max_spo2        REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS respiration (
    calendar_date   TEXT PRIMARY KEY,
    avg_waking      REAL,
    min_value       REAL,
    max_value       REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS body_battery (
    calendar_date   TEXT PRIMARY KEY,
    charged         INTEGER,
    drained         INTEGER,
    highest         INTEGER,
    lowest          INTEGER,
    most_recent     INTEGER,
    at_wake         INTEGER,
    during_sleep    INTEGER,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    calendar_date       TEXT PRIMARY KEY,
    total_steps         INTEGER,
    goal                INTEGER,
    distance_meters     REAL,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS floors (
    calendar_date   TEXT PRIMARY KEY,
    ascended        REAL,
    descended       REAL,
    goal            REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS intensity_minutes (
    calendar_date   TEXT PRIMARY KEY,
    moderate        INTEGER,
    vigorous        INTEGER,
    goal            INTEGER,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS hydration (
    calendar_date   TEXT PRIMARY KEY,
    goal_ml         REAL,
    intake_ml       REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS fitness_age (
    calendar_date       TEXT PRIMARY KEY,
    chronological_age   INTEGER,
    fitness_age         REAL,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS daily_movement (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS wellness_activity (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS training_status (
    calendar_date   TEXT PRIMARY KEY,
    status          TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS health_status (
    calendar_date       TEXT PRIMARY KEY,
    overall_status      TEXT,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS daily_events (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS activity_trends (
    calendar_date   TEXT,
    activity_type   TEXT,
    raw_json        TEXT,
    PRIMARY KEY (calendar_date, activity_type)
);

-- =========================================================================
-- Activity Tables
-- =========================================================================

CREATE TABLE IF NOT EXISTS activity (
    activity_id                         INTEGER PRIMARY KEY,
    activity_name                       TEXT,
    activity_type                       TEXT,
    activity_type_id                    INTEGER,
    parent_type_id                      INTEGER,
    start_time_local                    TEXT,
    start_time_gmt                      TEXT,
    duration_seconds                    REAL,
    elapsed_duration_seconds            REAL,
    moving_duration_seconds             REAL,
    distance_meters                     REAL,
    calories                            REAL,
    bmr_calories                        REAL,
    average_hr                          REAL,
    max_hr                              REAL,
    average_speed                       REAL,
    max_speed                           REAL,
    elevation_gain                      REAL,
    elevation_loss                      REAL,
    min_elevation                       REAL,
    max_elevation                       REAL,
    avg_power                           REAL,
    max_power                           REAL,
    norm_power                          REAL,
    training_stress_score               REAL,
    intensity_factor                    REAL,
    aerobic_training_effect             REAL,
    anaerobic_training_effect           REAL,
    vo2max_value                        REAL,
    avg_cadence                         REAL,
    max_cadence                         REAL,
    avg_respiration                     REAL,
    training_load                       REAL,
    moderate_intensity_minutes          INTEGER,
    vigorous_intensity_minutes          INTEGER,
    start_latitude                      REAL,
    start_longitude                     REAL,
    end_latitude                        REAL,
    end_longitude                       REAL,
    location_name                       TEXT,
    lap_count                           INTEGER,
    water_estimated                     REAL,
    min_temperature                     REAL,
    max_temperature                     REAL,
    manufacturer                        TEXT,
    device_id                           INTEGER,
    raw_json                            TEXT
);

CREATE TABLE IF NOT EXISTS activity_types (
    type_id         INTEGER PRIMARY KEY,
    type_key        TEXT,
    parent_type_id  INTEGER,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS activity_trackpoints (
    activity_id     INTEGER,
    seq             INTEGER,
    timestamp_utc   TEXT,
    latitude        REAL,
    longitude       REAL,
    altitude_m      REAL,
    distance_m      REAL,
    speed_mps       REAL,
    heart_rate_bpm  INTEGER,
    cadence         INTEGER,
    power_w         INTEGER,
    temperature_c   REAL,
    PRIMARY KEY (activity_id, seq)
);

-- =========================================================================
-- Training Tables
-- =========================================================================

CREATE TABLE IF NOT EXISTS training_readiness (
    calendar_date                       TEXT PRIMARY KEY,
    score                               REAL,
    level                               TEXT,
    feedback_short                      TEXT,
    feedback_long                       TEXT,
    recovery_time                       REAL,
    recovery_time_factor_percent        REAL,
    recovery_time_factor_feedback       TEXT,
    hrv_factor_percent                  REAL,
    hrv_factor_feedback                 TEXT,
    hrv_weekly_average                  REAL,
    sleep_history_factor_percent        REAL,
    sleep_history_factor_feedback       TEXT,
    stress_history_factor_percent       REAL,
    stress_history_factor_feedback      TEXT,
    acwr_factor_percent                 REAL,
    acwr_factor_feedback                TEXT,
    raw_json                            TEXT
);

CREATE TABLE IF NOT EXISTS hrv (
    calendar_date       TEXT PRIMARY KEY,
    weekly_avg          REAL,
    last_night          REAL,
    last_night_avg      REAL,
    last_night_5min_high REAL,
    status              TEXT,
    baseline_low        REAL,
    baseline_upper      REAL,
    start_timestamp     TEXT,
    end_timestamp       TEXT,
    raw_json            TEXT
);

-- =========================================================================
-- Range/Aggregate Tables
-- =========================================================================

CREATE TABLE IF NOT EXISTS vo2max (
    calendar_date   TEXT,
    sport           TEXT,
    value           REAL,
    raw_json        TEXT,
    PRIMARY KEY (calendar_date, sport)
);

CREATE TABLE IF NOT EXISTS weight (
    calendar_date   TEXT PRIMARY KEY,
    weight          REAL,
    bmi             REAL,
    body_fat        REAL,
    body_water      REAL,
    bone_mass       REAL,
    muscle_mass     REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS blood_pressure (
    calendar_date   TEXT PRIMARY KEY,
    systolic        REAL,
    diastolic       REAL,
    pulse           REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS calories (
    calendar_date   TEXT PRIMARY KEY,
    total           REAL,
    active          REAL,
    bmr             REAL,
    consumed        REAL,
    remaining       REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS sleep_stats (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS health_snapshot (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS workout_schedule (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS workouts (
    workout_id      INTEGER PRIMARY KEY,
    workout_name    TEXT,
    sport_type      TEXT,
    created_date    TEXT,
    updated_date    TEXT,
    raw_json        TEXT
);

-- =========================================================================
-- Profile Tables (rarely change)
-- =========================================================================

CREATE TABLE IF NOT EXISTS personal_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name    TEXT,
    activity_type   TEXT,
    pr_type         TEXT,
    value           REAL,
    pr_date         TEXT,
    activity_id     INTEGER,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS device (
    device_id       INTEGER PRIMARY KEY,
    display_name    TEXT,
    device_type     TEXT,
    application_key TEXT,
    last_sync       TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS gear (
    gear_id         TEXT PRIMARY KEY,
    gear_type       TEXT,
    display_name    TEXT,
    brand           TEXT,
    model           TEXT,
    date_begin      TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    goal_id         INTEGER PRIMARY KEY,
    goal_type       TEXT,
    goal_value      REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS challenges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_type  TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS training_plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS hr_zones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS user_profile (
    key             TEXT PRIMARY KEY,
    raw_json        TEXT
);

-- =========================================================================
-- Performance Score Tables
-- =========================================================================

CREATE TABLE IF NOT EXISTS endurance_score (
    calendar_date                   TEXT PRIMARY KEY,
    overall_score                   INTEGER,
    classification                  TEXT,
    vo2_max                         REAL,
    vo2_max_precise                 REAL,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS hill_score (
    calendar_date                   TEXT PRIMARY KEY,
    overall_score                   INTEGER,
    endurance_score                 INTEGER,
    strength_score                  INTEGER,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS race_predictions (
    calendar_date                   TEXT PRIMARY KEY,
    time_5k                         REAL,
    time_10k                        REAL,
    time_half_marathon              REAL,
    time_marathon                   REAL,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS activity_splits (
    activity_id                     INTEGER,
    split_number                    INTEGER,
    distance_meters                 REAL,
    duration_seconds                REAL,
    average_speed                   REAL,
    average_hr                      REAL,
    max_hr                          REAL,
    elevation_gain                  REAL,
    elevation_loss                  REAL,
    avg_cadence                     REAL,
    raw_json                        TEXT,
    PRIMARY KEY (activity_id, split_number)
);

CREATE TABLE IF NOT EXISTS activity_hr_zones (
    activity_id                     INTEGER PRIMARY KEY,
    zone1_seconds                   REAL,
    zone2_seconds                   REAL,
    zone3_seconds                   REAL,
    zone4_seconds                   REAL,
    zone5_seconds                   REAL,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS activity_weather (
    activity_id                     INTEGER PRIMARY KEY,
    temperature                     REAL,
    apparent_temperature            REAL,
    humidity                        REAL,
    wind_speed                      REAL,
    wind_direction                  INTEGER,
    weather_type                    TEXT,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS activity_exercise_sets (
    activity_id                     INTEGER,
    set_number                      INTEGER,
    exercise_name                   TEXT,
    exercise_category               TEXT,
    reps                            INTEGER,
    weight                          REAL,
    duration_seconds                REAL,
    raw_json                        TEXT,
    PRIMARY KEY (activity_id, set_number)
);

CREATE TABLE IF NOT EXISTS earned_badges (
    badge_id                        INTEGER PRIMARY KEY,
    badge_key                       TEXT,
    badge_name                      TEXT,
    badge_category                  TEXT,
    earned_date                     TEXT,
    earned_number                   INTEGER,
    raw_json                        TEXT
);

-- =========================================================================
-- Sync Log
-- =========================================================================

CREATE TABLE IF NOT EXISTS sync_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_date           TEXT,
    sync_type           TEXT,
    records_upserted    INTEGER,
    status              TEXT,
    error               TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);

-- =========================================================================
-- Indexes
-- =========================================================================

CREATE INDEX IF NOT EXISTS idx_activity_type ON activity (activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity (start_time_local);
CREATE INDEX IF NOT EXISTS idx_daily_date    ON daily_summary (calendar_date);
CREATE INDEX IF NOT EXISTS idx_sleep_date    ON sleep (calendar_date);
CREATE INDEX IF NOT EXISTS idx_tr_date       ON training_readiness (calendar_date);
CREATE INDEX IF NOT EXISTS idx_weight_date   ON weight (calendar_date);
CREATE INDEX IF NOT EXISTS idx_hydration_date ON hydration (calendar_date);
CREATE INDEX IF NOT EXISTS idx_heart_rate_date ON heart_rate (calendar_date);
CREATE INDEX IF NOT EXISTS idx_stress_date   ON stress (calendar_date);
CREATE INDEX IF NOT EXISTS idx_steps_date    ON steps (calendar_date);
CREATE INDEX IF NOT EXISTS idx_body_battery_date ON body_battery (calendar_date);
CREATE INDEX IF NOT EXISTS idx_vo2max_date   ON vo2max (calendar_date);
CREATE INDEX IF NOT EXISTS idx_calories_date ON calories (calendar_date);
CREATE INDEX IF NOT EXISTS idx_endurance_date ON endurance_score (calendar_date);
CREATE INDEX IF NOT EXISTS idx_hill_date ON hill_score (calendar_date);
CREATE INDEX IF NOT EXISTS idx_race_pred_date ON race_predictions (calendar_date);
CREATE INDEX IF NOT EXISTS idx_act_splits ON activity_splits (activity_id);
CREATE INDEX IF NOT EXISTS idx_act_weather ON activity_weather (activity_id);
CREATE INDEX IF NOT EXISTS idx_trackpoints_activity ON activity_trackpoints (activity_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Upsert helpers — one per table
# ---------------------------------------------------------------------------


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


def upsert_sleep(conn: sqlite3.Connection, record: dict) -> None:
    dto: dict[str, Any] = record.get("dailySleepDTO") or record
    sleep_seconds = dto.get("sleepTimeSeconds")
    if sleep_seconds is None:
        return
    calendar_date = dto.get("calendarDate") or record.get("date")
    conn.execute(
        """
        INSERT OR REPLACE INTO sleep (
            calendar_date, sleep_time_seconds, nap_time_seconds,
            deep_sleep_seconds, light_sleep_seconds, rem_sleep_seconds,
            awake_sleep_seconds, unmeasurable_sleep_seconds, awake_count,
            average_spo2, lowest_spo2, average_hr_sleep, average_respiration,
            lowest_respiration, highest_respiration, avg_sleep_stress,
            sleep_score_feedback, sleep_score_insight, raw_json
        ) VALUES (
            :calendar_date, :sleep_time_seconds, :nap_time_seconds,
            :deep_sleep_seconds, :light_sleep_seconds, :rem_sleep_seconds,
            :awake_sleep_seconds, :unmeasurable_sleep_seconds, :awake_count,
            :average_spo2, :lowest_spo2, :average_hr_sleep, :average_respiration,
            :lowest_respiration, :highest_respiration, :avg_sleep_stress,
            :sleep_score_feedback, :sleep_score_insight, :raw_json
        )
        """,
        {
            "calendar_date": calendar_date,
            "sleep_time_seconds": sleep_seconds,
            "nap_time_seconds": dto.get("napTimeSeconds"),
            "deep_sleep_seconds": dto.get("deepSleepSeconds"),
            "light_sleep_seconds": dto.get("lightSleepSeconds"),
            "rem_sleep_seconds": dto.get("remSleepSeconds"),
            "awake_sleep_seconds": dto.get("awakeSleepSeconds"),
            "unmeasurable_sleep_seconds": dto.get("unmeasurableSleepSeconds"),
            "awake_count": dto.get("awakeSleepCount") or dto.get("awakeCount"),
            "average_spo2": dto.get("averageSpO2Value"),
            "lowest_spo2": dto.get("lowestSpO2Value"),
            "average_hr_sleep": dto.get("averageHrSleep") or dto.get("avgSleepHR"),
            "average_respiration": dto.get("averageRespirationValue"),
            "lowest_respiration": dto.get("lowestRespirationValue"),
            "highest_respiration": dto.get("highestRespirationValue"),
            "avg_sleep_stress": dto.get("avgSleepStress"),
            "sleep_score_feedback": dto.get("sleepScoreFeedback"),
            "sleep_score_insight": dto.get("sleepScoreInsight"),
            "raw_json": json.dumps(record),
        },
    )


def upsert_activity(conn: sqlite3.Connection, record: dict) -> None:
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
    conn.execute(
        """
        INSERT OR REPLACE INTO activity (
            activity_id, activity_name, activity_type, activity_type_id,
            parent_type_id, start_time_local, start_time_gmt,
            duration_seconds, elapsed_duration_seconds, moving_duration_seconds,
            distance_meters, calories, bmr_calories, average_hr, max_hr,
            average_speed, max_speed, elevation_gain, elevation_loss,
            min_elevation, max_elevation, avg_power, max_power, norm_power,
            training_stress_score, intensity_factor, aerobic_training_effect,
            anaerobic_training_effect, vo2max_value, avg_cadence, max_cadence,
            avg_respiration, training_load, moderate_intensity_minutes,
            vigorous_intensity_minutes, start_latitude, start_longitude,
            end_latitude, end_longitude, location_name, lap_count,
            water_estimated, min_temperature, max_temperature,
            manufacturer, device_id, raw_json
        ) VALUES (
            :activity_id, :activity_name, :activity_type, :activity_type_id,
            :parent_type_id, :start_time_local, :start_time_gmt,
            :duration_seconds, :elapsed_duration_seconds, :moving_duration_seconds,
            :distance_meters, :calories, :bmr_calories, :average_hr, :max_hr,
            :average_speed, :max_speed, :elevation_gain, :elevation_loss,
            :min_elevation, :max_elevation, :avg_power, :max_power, :norm_power,
            :training_stress_score, :intensity_factor, :aerobic_training_effect,
            :anaerobic_training_effect, :vo2max_value, :avg_cadence, :max_cadence,
            :avg_respiration, :training_load, :moderate_intensity_minutes,
            :vigorous_intensity_minutes, :start_latitude, :start_longitude,
            :end_latitude, :end_longitude, :location_name, :lap_count,
            :water_estimated, :min_temperature, :max_temperature,
            :manufacturer, :device_id, :raw_json
        )
        """,
        {
            "activity_id": record.get("activityId"),
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
            "raw_json": json.dumps(record),
        },
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
            last_night_5min_high, status, baseline_low, baseline_upper,
            start_timestamp, end_timestamp, raw_json
        ) VALUES (
            :calendar_date, :weekly_avg, :last_night, :last_night_avg,
            :last_night_5min_high, :status, :baseline_low, :baseline_upper,
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
    conn.execute(
        "INSERT OR REPLACE INTO heart_rate (calendar_date, resting_hr, min_hr, max_hr, avg_hr, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            d,
            record.get("restingHeartRate") or record.get("restingHR"),
            record.get("minHeartRate") or record.get("minHR"),
            record.get("maxHeartRate") or record.get("maxHR"),
            record.get("averageHeartRate") or record.get("avgHR"),
            json.dumps(record),
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
            record.get("averageStressLevel") or record.get("overallStressLevel"),
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
        "INSERT OR REPLACE INTO spo2 (calendar_date, avg_spo2, min_spo2, max_spo2, raw_json) VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("averageSpo2") or record.get("averageSpO2"),
            record.get("lowestSpo2") or record.get("lowestSpO2"),
            record.get("latestSpo2") or record.get("latestSpO2"),
            json.dumps(record),
        ),
    )


def upsert_respiration(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO respiration (calendar_date, avg_waking, min_value, max_value, raw_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            d,
            record.get("avgWakingRespirationValue"),
            record.get("lowestRespirationValue"),
            record.get("highestRespirationValue"),
            json.dumps(record),
        ),
    )


def upsert_body_battery(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO body_battery
           (calendar_date, charged, drained, highest, lowest, most_recent, at_wake, during_sleep, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    conn.execute(
        "INSERT OR REPLACE INTO hydration (calendar_date, goal_ml, intake_ml, raw_json) VALUES (?, ?, ?, ?)",
        (
            d,
            record.get("goalInML") or record.get("baseGoalInML"),
            record.get("intakeInML") or record.get("valueInML"),
            json.dumps(record),
        ),
    )


def upsert_fitness_age(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        "INSERT OR REPLACE INTO fitness_age (calendar_date, chronological_age, fitness_age, raw_json) "
        "VALUES (?, ?, ?, ?)",
        (
            d,
            record.get("chronologicalAge"),
            record.get("fitnessAge"),
            json.dumps(record),
        ),
    )


def upsert_weight(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    from datetime import datetime

    d = cal_date or record.get("calendarDate")

    # The "date" field from weight endpoints is a Unix timestamp in
    # milliseconds (e.g. 1743345400000), not a calendar date string.
    # Convert it properly instead of storing the raw integer.
    if not d:
        ts = record.get("date")
        if isinstance(ts, (int, float)):
            # Garmin uses milliseconds; values > 1e10 are ms timestamps
            if ts > 1e10:
                ts = ts / 1000
            d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        elif isinstance(ts, str) and ts[:4].isdigit() and "-" in ts:
            d = ts[:10]

    if not d:
        return
    d = str(d)[:10]
    conn.execute(
        """INSERT OR REPLACE INTO weight
           (calendar_date, weight, bmi, body_fat, body_water, bone_mass, muscle_mass, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("weight"),
            record.get("bmi"),
            record.get("bodyFat"),
            record.get("bodyWater"),
            record.get("boneMass"),
            record.get("muscleMass"),
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


def upsert_calories(conn: sqlite3.Connection, record: dict) -> None:
    d = record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO calories
           (calendar_date, total, active, bmr, consumed, remaining, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
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


def upsert_endurance_score(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO endurance_score
           (calendar_date, overall_score, classification, vo2_max, vo2_max_precise, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            d,
            record.get("overallScore"),
            record.get("classification"),
            record.get("vo2Max"),
            record.get("vo2MaxPreciseValue"),
            json.dumps(record),
        ),
    )


def upsert_hill_score(conn: sqlite3.Connection, record: dict, cal_date: str = None) -> None:
    d = cal_date or record.get("calendarDate") or record.get("date")
    if not d:
        return
    conn.execute(
        """INSERT OR REPLACE INTO hill_score
           (calendar_date, overall_score, endurance_score, strength_score, raw_json)
           VALUES (?, ?, ?, ?, ?)""",
        (
            d,
            record.get("overallScore"),
            record.get("enduranceScore"),
            record.get("strengthScore"),
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
                avg_cadence, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        conn.execute(
            """INSERT OR REPLACE INTO activity_exercise_sets
               (activity_id, set_number, exercise_name, exercise_category,
                reps, weight, duration_seconds, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                activity_id,
                i + 1,
                s.get("exerciseName"),
                s.get("exerciseCategory"),
                s.get("repetitionCount") or s.get("reps"),
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


def _upsert_raw_only(conn: sqlite3.Connection, table: str, key_col: str, record: dict, key_val: str) -> None:
    """Helper for tables that only have a key + raw_json."""
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({key_col}, raw_json) VALUES (?, ?)",
        (key_val, json.dumps(record)),
    )


def upsert_daily_movement(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "daily_movement", "calendar_date", record, d)


def upsert_wellness_activity(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "wellness_activity", "calendar_date", record, d)


def upsert_training_status(conn, record, cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        conn.execute(
            "INSERT OR REPLACE INTO training_status (calendar_date, status, raw_json) VALUES (?, ?, ?)",
            (d, record.get("trainingStatus") or record.get("status"), json.dumps(record)),
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
    if d:
        _upsert_raw_only(conn, "daily_events", "calendar_date", record, d)


def upsert_activity_trends(conn, record, activity_type="all", cal_date=None):
    d = cal_date or record.get("calendarDate") or record.get("date")
    if d:
        conn.execute(
            "INSERT OR REPLACE INTO activity_trends (calendar_date, activity_type, raw_json) VALUES (?, ?, ?)",
            (d, activity_type, json.dumps(record)),
        )


def upsert_sleep_stats(conn, record):
    d = record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "sleep_stats", "calendar_date", record, d)


def upsert_health_snapshot(conn, record):
    d = record.get("calendarDate") or record.get("date")
    if d:
        _upsert_raw_only(conn, "health_snapshot", "calendar_date", record, d)


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
           (device_id, display_name, device_type, application_key, last_sync, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            device_id,
            record.get("displayName"),
            record.get("deviceTypeSimpleName"),
            record.get("applicationKey"),
            record.get("lastSync"),
            json.dumps(record),
        ),
    )


def upsert_gear(conn, record):
    g_id = record.get("uuid") or record.get("gearPk")
    if not g_id:
        return
    conn.execute(
        """INSERT OR REPLACE INTO gear
           (gear_id, gear_type, display_name, brand, model, date_begin, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            str(g_id),
            record.get("gearTypeName"),
            record.get("displayName"),
            record.get("customMakeModel") or record.get("brandName"),
            record.get("modelName"),
            record.get("dateBegin"),
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


def upsert_activity_types(conn, record):
    t_id = record.get("typeId")
    if t_id is None:
        return
    conn.execute(
        "INSERT OR REPLACE INTO activity_types (type_id, type_key, parent_type_id, raw_json) VALUES (?, ?, ?, ?)",
        (t_id, record.get("typeKey"), record.get("parentTypeId"), json.dumps(record)),
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


# ---------------------------------------------------------------------------
# save_to_db — the main router
# ---------------------------------------------------------------------------


def _unwrap_gql_data(data):
    """Unwrap GraphQL response: {data: {scalarName: [...]}} -> [...]"""
    if isinstance(data, dict) and "data" in data and len(data) == 1:
        data = data["data"]
    if isinstance(data, dict) and len(data) == 1:
        inner = list(data.values())[0]
        return inner if isinstance(inner, list) else [inner] if isinstance(inner, dict) else data
    return data


def _ensure_list(data) -> list:
    """Coerce data to a list of records."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
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
            for rec in records:
                upsert_activity(conn, rec)
                count += 1

        elif name in ("weight_range", "weight_latest", "weight", "weight_range_rest", "weight_first", "goal_weight"):
            for rec in records:
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

        elif name in ("blood_pressure", "blood_pressure_rest"):
            for rec in records:
                upsert_blood_pressure(conn, rec)
                count += 1

        elif name == "calories":
            for rec in records:
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
            # than the list endpoint. Don't overwrite the activity table — it would
            # null out fields. Just update raw_json for activities that already exist.
            for rec in records:
                aid = rec.get("activityId")
                if aid:
                    import json as _json

                    conn.execute(
                        "UPDATE activity SET raw_json = ? WHERE activity_id = ?",
                        (_json.dumps(rec), aid),
                    )
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


# ---------------------------------------------------------------------------
# Generic query helper
# ---------------------------------------------------------------------------


def query(conn: sqlite3.Connection, sql: str, params: Any = None) -> list[dict]:
    """Execute *sql* with optional *params* and return results as a list of dicts."""
    cursor = conn.execute(sql, params or [])
    return [dict(row) for row in cursor.fetchall()]


def query_readonly(sql: str, params: Any = None, limit: int = 1000) -> list[dict]:
    """Execute a read-only query against the database.

    Opens the database in SQLite read-only mode (``?mode=ro`` URI),
    which enforces read-only at the engine level — no writes, no
    PRAGMA changes, regardless of the SQL content.  Additionally
    blocks ATTACH/DETACH to prevent filesystem side-effects.
    """
    # Block ATTACH/DETACH before opening any connection — these can
    # create zero-byte files on disk even in read-only mode.
    check = sql.strip().upper()
    if "ATTACH" in check or "DETACH" in check:
        raise PermissionError("ATTACH and DETACH are not permitted.")

    ro_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro_conn.row_factory = sqlite3.Row
    try:
        clamped = max(1, min(limit if isinstance(limit, int) else 1000, 10000))
        ro_conn.execute("PRAGMA busy_timeout = 5000")
        cursor = ro_conn.execute(sql, params or [])
        rows = [dict(row) for row in cursor.fetchmany(clamped)]
        return rows
    finally:
        ro_conn.close()

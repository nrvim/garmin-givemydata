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
    body_battery_change         INTEGER,
    resting_heart_rate          INTEGER,
    avg_skin_temp_deviation_c   REAL,
    avg_skin_temp_deviation_f   REAL,
    sleep_need_minutes          INTEGER,
    highest_spo2                REAL,
    sleep_score_overall         INTEGER,
    sleep_light_pct             INTEGER,
    sleep_score_rem             INTEGER,
    sleep_score_deep            INTEGER,
    raw_json                    TEXT
);

CREATE TABLE IF NOT EXISTS heart_rate (
    calendar_date           TEXT PRIMARY KEY,
    resting_hr              INTEGER,
    min_hr                  INTEGER,
    max_hr                  INTEGER,
    avg_hr                  REAL,
    last_7day_avg_resting   REAL,
    raw_json                TEXT
);

CREATE TABLE IF NOT EXISTS stress (
    calendar_date       TEXT PRIMARY KEY,
    avg_stress          INTEGER,
    max_stress          INTEGER,
    stress_qualifier    TEXT,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS spo2 (
    calendar_date                   TEXT PRIMARY KEY,
    avg_spo2                        REAL,
    min_spo2                        REAL,
    max_spo2                        REAL,
    events_below_threshold          INTEGER,
    duration_below_threshold_secs   REAL,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS respiration (
    calendar_date       TEXT PRIMARY KEY,
    avg_waking          REAL,
    avg_sleep           REAL,
    min_value           REAL,
    max_value           REAL,
    raw_json            TEXT
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
    calendar_date       TEXT PRIMARY KEY,
    goal_ml             REAL,
    intake_ml           REAL,
    sweat_loss_ml       REAL,
    activity_intake_ml  REAL,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS fitness_age (
    calendar_date           TEXT PRIMARY KEY,
    chronological_age       INTEGER,
    fitness_age             REAL,
    achievable_fitness_age  REAL,
    raw_json                TEXT
);

CREATE TABLE IF NOT EXISTS daily_movement (
    calendar_date   TEXT PRIMARY KEY,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS wellness_activity (
    calendar_date           TEXT PRIMARY KEY,
    activity_name           TEXT,
    wellness_activity_type  TEXT,
    start_timestamp_local   TEXT,
    end_timestamp_local     TEXT,
    raw_json                TEXT
);

CREATE TABLE IF NOT EXISTS training_status (
    calendar_date   TEXT PRIMARY KEY,
    status          TEXT,
    acute_load      REAL,
    chronic_load    REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS health_status (
    calendar_date       TEXT PRIMARY KEY,
    overall_status      TEXT,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS daily_events (
    calendar_date           TEXT PRIMARY KEY,
    activity_type           TEXT,
    activity_sub_type       TEXT,
    start_timestamp_local   TEXT,
    end_timestamp_local     TEXT,
    duration_seconds        REAL,
    device_id               TEXT,
    raw_json                TEXT
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
    body_battery_change                 INTEGER,
    total_work_kcal                     REAL,
    avg_grade_adjusted_speed            REAL,
    activity_steps                      INTEGER,
    activity_min_hr                     INTEGER,
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
    feedback_phrase     TEXT,
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

CREATE TABLE IF NOT EXISTS lactate_threshold (
    calendar_date       TEXT PRIMARY KEY,
    speed               REAL,
    heart_rate          INTEGER,
    heart_rate_cycling  INTEGER,
    rowing_speed        REAL,
    heart_rate_rowing   INTEGER,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS weight (
    timestamp       INTEGER PRIMARY KEY,
    calendar_date   TEXT,
    weight          REAL,
    bmi             REAL,
    body_fat        REAL,
    body_water      REAL,
    bone_mass       REAL,
    muscle_mass     REAL,
    metabolic_age   REAL,
    physique_rating INTEGER,
    visceral_fat    REAL,
    source          TEXT,
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
    calendar_date           TEXT PRIMARY KEY,
    activity_name           TEXT,
    wellness_activity_type  TEXT,
    start_timestamp_local   TEXT,
    end_timestamp_local     TEXT,
    raw_json                TEXT
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
    software_version TEXT,
    battery_status  TEXT,
    battery_voltage REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS gear (
    gear_id                     TEXT PRIMARY KEY,
    gear_type                   TEXT,
    display_name                TEXT,
    brand                       TEXT,
    model                       TEXT,
    date_begin                  TEXT,
    distance_used_meters        REAL,
    duration_used_seconds       INTEGER,
    days_used                   INTEGER,
    status                      TEXT,
    max_usage_distance_meters   REAL,
    raw_json                    TEXT
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
    feedback_phrase                 TEXT,
    contributors                    TEXT,
    raw_json                        TEXT
);

CREATE TABLE IF NOT EXISTS hill_score (
    calendar_date                   TEXT PRIMARY KEY,
    overall_score                   INTEGER,
    endurance_score                 INTEGER,
    strength_score                  INTEGER,
    vo2_max                         REAL,
    vo2_max_precise                 REAL,
    feedback_phrase_id              TEXT,
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
    avg_swim_cadence                REAL,
    avg_swolf                       REAL,
    total_strokes                   INTEGER,
    swim_stroke                     TEXT,
    num_active_lengths              INTEGER,
    normalized_power                REAL,
    avg_respiration_rate            REAL,
    max_respiration_rate            REAL,
    start_latitude                  REAL,
    start_longitude                 REAL,
    end_latitude                    REAL,
    end_longitude                   REAL,
    start_time_gmt                  TEXT,
    calories                        REAL,
    left_pedal_smoothness           REAL,
    right_pedal_smoothness          REAL,
    left_torque_effectiveness       REAL,
    right_torque_effectiveness      REAL,
    surface_unpaved_pct             REAL,
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
CREATE TABLE IF NOT EXISTS running_dynamics (
    activity_id     INTEGER PRIMARY KEY,
    avg_gct         REAL,
    avg_gct_balance REAL,
    avg_vert_osc    REAL,
    avg_vert_ratio  REAL,
    avg_stride_len  REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS load_focus (
    calendar_date   TEXT PRIMARY KEY,
    anaerobic       REAL,
    high_aerobic    REAL,
    low_aerobic     REAL,
    focus_status    TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS hrv_timeline (
    calendar_date   TEXT PRIMARY KEY,
    reading_count   INTEGER,
    raw_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_act_weather ON activity_weather (activity_id);
CREATE INDEX IF NOT EXISTS idx_trackpoints_activity ON activity_trackpoints (activity_id);
"""


def migrate_activity_splits_table(conn: sqlite3.Connection) -> None:
    """Add swim-specific columns to activity_splits and backfill from raw_json."""
    cursor = conn.execute("PRAGMA table_info(activity_splits)")
    cols = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("avg_swim_cadence", "REAL"),
        ("avg_swolf", "REAL"),
        ("total_strokes", "INTEGER"),
        ("swim_stroke", "TEXT"),
        ("num_active_lengths", "INTEGER"),
    ]
    added = []
    for name, col_type in new_cols:
        if name not in cols:
            try:
                conn.execute(f"ALTER TABLE activity_splits ADD COLUMN {name} {col_type}")
                added.append(name)
            except sqlite3.OperationalError as e:
                log.debug("Migration note (activity_splits.%s): %s", name, e)

    if not added:
        return

    log.info("Migrating activity_splits table, added columns: %s — backfilling from raw_json", ", ".join(added))
    rows = conn.execute(
        "SELECT activity_id, split_number, raw_json FROM activity_splits WHERE raw_json IS NOT NULL"
    ).fetchall()
    for activity_id, split_number, raw in rows:
        try:
            split = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        conn.execute(
            """UPDATE activity_splits
               SET avg_swim_cadence   = COALESCE(avg_swim_cadence,   ?),
                   avg_swolf          = COALESCE(avg_swolf,          ?),
                   total_strokes      = COALESCE(total_strokes,      ?),
                   swim_stroke        = COALESCE(swim_stroke,        ?),
                   num_active_lengths = COALESCE(num_active_lengths, ?)
               WHERE activity_id = ? AND split_number = ?""",
            (
                split.get("averageSwimCadence") or None,
                split.get("averageSWOLF") or None,
                split.get("totalNumberOfStrokes") or None,
                split.get("swimStroke"),
                split.get("numberOfActiveLengths") or None,
                activity_id,
                split_number,
            ),
        )
    log.info("Backfilled swim columns for %d splits", len(rows))


def _add_columns(conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]]) -> list[str]:
    """Add missing columns to *table*. Returns list of added column names."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    added = []
    for name, col_type in columns:
        if name not in existing:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
                added.append(name)
            except sqlite3.OperationalError as e:
                # The PRAGMA check above prevents "duplicate column" — anything
                # reaching here is a real problem (missing table, disk error,
                # etc.) and should be visible at default log level.
                log.warning("Could not add %s.%s: %s", table, name, e)
    if added:
        log.info("Migrated %s: added %s", table, ", ".join(added))
    return added


def _backfill_from_raw(
    conn: sqlite3.Connection, table: str, pk_cols: list[str], added: list[str], mapping: dict[str, str]
) -> None:
    """Backfill *added* columns from raw_json using *mapping* {col: json_key}."""
    if not added:
        return
    active = {c: mapping[c] for c in added if c in mapping}
    if not active:
        return
    pks = ", ".join(pk_cols)
    rows = conn.execute(f"SELECT {pks}, raw_json FROM {table} WHERE raw_json IS NOT NULL").fetchall()
    for row in rows:
        pk_vals = row[: len(pk_cols)]
        try:
            data = json.loads(row[len(pk_cols)])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            continue
        set_clause = ", ".join(f"{c} = COALESCE({c}, ?)" for c in active)
        # dict.get returns None for missing keys; do NOT coerce 0/False/'' to None.
        vals = [data.get(jk) for jk in active.values()]
        where = " AND ".join(f"{c} = ?" for c in pk_cols)
        conn.execute(f"UPDATE {table} SET {set_clause} WHERE {where}", vals + list(pk_vals))


def migrate_sleep_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "sleep",
        [
            ("body_battery_change", "INTEGER"),
            ("resting_heart_rate", "INTEGER"),
            ("avg_skin_temp_deviation_c", "REAL"),
            ("avg_skin_temp_deviation_f", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "sleep",
        ["calendar_date"],
        added,
        {
            "body_battery_change": "bodyBatteryChange",
            "resting_heart_rate": "restingHeartRate",
            "avg_skin_temp_deviation_c": "avgSkinTempDeviationC",
            "avg_skin_temp_deviation_f": "avgSkinTempDeviationF",
        },
    )


def migrate_hrv_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(conn, "hrv", [("feedback_phrase", "TEXT")])
    _backfill_from_raw(conn, "hrv", ["calendar_date"], added, {"feedback_phrase": "feedbackPhrase"})


def migrate_heart_rate_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(conn, "heart_rate", [("last_7day_avg_resting", "REAL")])
    _backfill_from_raw(
        conn, "heart_rate", ["calendar_date"], added, {"last_7day_avg_resting": "lastSevenDaysAvgRestingHeartRate"}
    )


def migrate_spo2_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "spo2",
        [
            ("events_below_threshold", "INTEGER"),
            ("duration_below_threshold_secs", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "spo2",
        ["calendar_date"],
        added,
        {
            "events_below_threshold": "numberOfEventsBelowThreshold",
            "duration_below_threshold_secs": "durationOfEventsBelowThreshold",
        },
    )


def migrate_respiration_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(conn, "respiration", [("avg_sleep", "REAL")])
    _backfill_from_raw(conn, "respiration", ["calendar_date"], added, {"avg_sleep": "avgSleepRespirationValue"})


def migrate_hydration_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "hydration",
        [
            ("sweat_loss_ml", "REAL"),
            ("activity_intake_ml", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "hydration",
        ["calendar_date"],
        added,
        {
            "sweat_loss_ml": "sweatLossInML",
            "activity_intake_ml": "activityIntakeInML",
        },
    )


def migrate_weight_table_v2(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "weight",
        [
            ("metabolic_age", "REAL"),
            ("physique_rating", "INTEGER"),
        ],
    )
    _backfill_from_raw(
        conn,
        "weight",
        ["timestamp"],
        added,
        {
            "metabolic_age": "metabolicAge",
            "physique_rating": "physiqueRating",
        },
    )


def migrate_endurance_score_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "endurance_score",
        [
            ("feedback_phrase", "TEXT"),
            ("contributors", "TEXT"),
        ],
    )
    if not added:
        return
    rows = conn.execute("SELECT calendar_date, raw_json FROM endurance_score WHERE raw_json IS NOT NULL").fetchall()
    for cal_date, raw in rows:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        contributors = data.get("contributors")
        conn.execute(
            """UPDATE endurance_score
               SET feedback_phrase = COALESCE(feedback_phrase, ?),
                   contributors    = COALESCE(contributors, ?)
               WHERE calendar_date = ?""",
            (
                data.get("feedbackPhrase"),
                json.dumps(contributors) if contributors is not None else None,
                cal_date,
            ),
        )


def migrate_hill_score_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "hill_score",
        [
            ("vo2_max", "REAL"),
            ("vo2_max_precise", "REAL"),
            ("feedback_phrase_id", "TEXT"),
        ],
    )
    _backfill_from_raw(
        conn,
        "hill_score",
        ["calendar_date"],
        added,
        {
            "vo2_max": "vo2Max",
            "vo2_max_precise": "vo2MaxPreciseValue",
            "feedback_phrase_id": "hillScoreFeedbackPhraseId",
        },
    )


def migrate_gear_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "gear",
        [
            ("distance_used_meters", "REAL"),
            ("duration_used_seconds", "INTEGER"),
            ("days_used", "INTEGER"),
        ],
    )
    _backfill_from_raw(
        conn,
        "gear",
        ["gear_id"],
        added,
        {
            "distance_used_meters": "distanceUsedMeters",
            "duration_used_seconds": "durationUsedSeconds",
            "days_used": "daysUsed",
        },
    )


def migrate_sleep_table_v2(conn: sqlite3.Connection) -> None:
    """Add sleep score and SpO2/sleep-need columns, backfill from nested raw_json paths.

    Requires SQLite >= 3.25 for ALTER TABLE ... RENAME COLUMN (Sept 2018).
    Python 3.10+ on any current OS satisfies this.

    The rename block handles an unreleased intermediate schema where columns
    were named with the wrong unit suffix. RENAME preserves existing values
    (it doesn't convert them) — if a fork stored seconds in sleep_need_seconds,
    those seconds-values are now mislabeled as minutes. In practice these
    columns never shipped, so no upstream user is affected.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sleep)").fetchall()}
    if "sleep_need_seconds" in cols and "sleep_need_minutes" not in cols:
        conn.execute("ALTER TABLE sleep RENAME COLUMN sleep_need_seconds TO sleep_need_minutes")
    if "sleep_score_composition" in cols and "sleep_light_pct" not in cols:
        conn.execute("ALTER TABLE sleep RENAME COLUMN sleep_score_composition TO sleep_light_pct")
    conn.commit()

    _add_columns(
        conn,
        "sleep",
        [
            ("sleep_need_minutes", "INTEGER"),
            ("highest_spo2", "REAL"),
            ("sleep_score_overall", "INTEGER"),
            ("sleep_light_pct", "INTEGER"),
            ("sleep_score_rem", "INTEGER"),
            ("sleep_score_deep", "INTEGER"),
        ],
    )
    # All fields are nested under dailySleepDTO — use direct SQL UPDATE with json_extract.
    # WHERE {col} IS NULL makes the backfill idempotent and safe to re-run even
    # if the schema is in a partially-migrated state.
    update_map = {
        "sleep_need_minutes": "$.dailySleepDTO.sleepNeed.actual",
        "highest_spo2": "$.dailySleepDTO.highestSpO2Value",
        "sleep_score_overall": "$.dailySleepDTO.sleepScores.overall.value",
        "sleep_light_pct": "$.dailySleepDTO.sleepScores.lightPercentage.value",
        "sleep_score_rem": "$.dailySleepDTO.sleepScores.remPercentage.value",
        "sleep_score_deep": "$.dailySleepDTO.sleepScores.deepPercentage.value",
    }
    for col, path in update_map.items():
        conn.execute(
            f"UPDATE sleep SET {col} = json_extract(raw_json, ?) WHERE raw_json IS NOT NULL AND {col} IS NULL",
            (path,),
        )
    conn.commit()


def migrate_fitness_age_table(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "fitness_age",
        [
            ("achievable_fitness_age", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "fitness_age",
        ["calendar_date"],
        added,
        {
            "achievable_fitness_age": "achievableFitnessAge",
        },
    )


def migrate_weight_table_v3(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "weight",
        [
            ("visceral_fat", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "weight",
        ["timestamp"],
        added,
        {
            "visceral_fat": "visceralFat",
        },
    )


def migrate_gear_table_v2(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "gear",
        [
            ("status", "TEXT"),
            ("max_usage_distance_meters", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "gear",
        ["gear_id"],
        added,
        {
            "status": "status",
            "max_usage_distance_meters": "maxUsageDistanceMeters",
        },
    )


def migrate_activity_table(conn: sqlite3.Connection) -> None:
    """Add new columns to activity table and backfill from summaryDTO in raw_json.

    Note: summaryDTO.totalWork is in kilocalories of mechanical work, not joules
    (verified against avg_power × duration: 224W × 4648s ≈ 1041 kJ ≈ 248 kcal,
    matching the stored value of 248.21).
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(activity)").fetchall()}
    if "total_work_kj" in cols and "total_work_kcal" not in cols:
        # Pre-release intermediate schema had wrong unit suffix; values were
        # always kcal — just rename the column.
        conn.execute("ALTER TABLE activity RENAME COLUMN total_work_kj TO total_work_kcal")
        conn.commit()

    _add_columns(
        conn,
        "activity",
        [
            ("body_battery_change", "INTEGER"),
            ("total_work_kcal", "REAL"),
            ("avg_grade_adjusted_speed", "REAL"),
            ("activity_steps", "INTEGER"),
            ("activity_min_hr", "INTEGER"),
        ],
    )
    update_map = {
        "body_battery_change": "$.summaryDTO.differenceBodyBattery",
        "total_work_kcal": "$.summaryDTO.totalWork",
        "avg_grade_adjusted_speed": "$.summaryDTO.avgGradeAdjustedSpeed",
        "activity_steps": "$.summaryDTO.steps",
        "activity_min_hr": "$.summaryDTO.minHR",
    }
    for col, path in update_map.items():
        conn.execute(
            f"UPDATE activity SET {col} = json_extract(raw_json, ?) WHERE raw_json IS NOT NULL AND {col} IS NULL",
            (path,),
        )
    conn.commit()


def migrate_activity_splits_v2(conn: sqlite3.Connection) -> None:
    added = _add_columns(
        conn,
        "activity_splits",
        [
            ("normalized_power", "REAL"),
            ("avg_respiration_rate", "REAL"),
            ("max_respiration_rate", "REAL"),
            ("start_latitude", "REAL"),
            ("start_longitude", "REAL"),
            ("end_latitude", "REAL"),
            ("end_longitude", "REAL"),
            ("start_time_gmt", "TEXT"),
            ("calories", "REAL"),
            ("left_pedal_smoothness", "REAL"),
            ("right_pedal_smoothness", "REAL"),
            ("left_torque_effectiveness", "REAL"),
            ("right_torque_effectiveness", "REAL"),
            ("surface_unpaved_pct", "REAL"),
        ],
    )
    _backfill_from_raw(
        conn,
        "activity_splits",
        ["activity_id", "split_number"],
        added,
        {
            "normalized_power": "normalizedPower",
            "avg_respiration_rate": "avgRespirationRate",
            "max_respiration_rate": "maxRespirationRate",
            "start_latitude": "startLatitude",
            "start_longitude": "startLongitude",
            "end_latitude": "endLatitude",
            "end_longitude": "endLongitude",
            "start_time_gmt": "startTimeGMT",
            "calories": "calories",
            "left_pedal_smoothness": "leftPedalSmoothness",
            "right_pedal_smoothness": "rightPedalSmoothness",
            "left_torque_effectiveness": "leftTorqueEffectiveness",
            "right_torque_effectiveness": "rightTorqueEffectiveness",
            "surface_unpaved_pct": "surfaceTypeUnpavedPercentage",
        },
    )


def migrate_hollow_tables(conn: sqlite3.Connection) -> None:
    """Add scalar columns to previously raw_json-only tables and backfill."""
    _add_columns(
        conn,
        "daily_events",
        [
            ("activity_type", "TEXT"),
            ("activity_sub_type", "TEXT"),
            ("start_timestamp_local", "TEXT"),
            ("end_timestamp_local", "TEXT"),
            ("duration_seconds", "REAL"),
            ("device_id", "TEXT"),
        ],
    )
    _add_columns(
        conn,
        "wellness_activity",
        [
            ("activity_name", "TEXT"),
            ("wellness_activity_type", "TEXT"),
            ("start_timestamp_local", "TEXT"),
            ("end_timestamp_local", "TEXT"),
        ],
    )
    _add_columns(
        conn,
        "health_snapshot",
        [
            ("activity_name", "TEXT"),
            ("wellness_activity_type", "TEXT"),
            ("start_timestamp_local", "TEXT"),
            ("end_timestamp_local", "TEXT"),
        ],
    )
    # Backfill daily_events via upsert (handles both dict and list raw_json)
    de_rows = conn.execute(
        "SELECT calendar_date, raw_json FROM daily_events WHERE activity_type IS NULL AND raw_json IS NOT NULL"
    ).fetchall()
    for cal_date, raw in de_rows:
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        upsert_daily_events(conn, record, cal_date=cal_date)

    # Backfill scalar columns for each hollow table from their raw_json
    for table, mapping in [
        (
            "wellness_activity",
            {
                "activity_name": "activityName",
                "wellness_activity_type": "wellnessActivityType",
                "start_timestamp_local": "startTimestampLocal",
                "end_timestamp_local": "endTimestampLocal",
            },
        ),
        (
            "health_snapshot",
            {
                "activity_name": "activityName",
                "wellness_activity_type": "wellnessActivityType",
                "start_timestamp_local": "startTimestampLocal",
                "end_timestamp_local": "endTimestampLocal",
            },
        ),
    ]:
        rows = conn.execute(f"SELECT calendar_date, raw_json FROM {table} WHERE raw_json IS NOT NULL").fetchall()
        for cal_date, raw in rows:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            set_parts = ", ".join(f"{col} = COALESCE({col}, ?)" for col in mapping)
            vals = [data.get(jk) for jk in mapping.values()]
            conn.execute(f"UPDATE {table} SET {set_parts} WHERE calendar_date = ?", vals + [cal_date])


def migrate_training_status_table(conn: sqlite3.Connection) -> None:
    """Migrate the training_status table to include acute and chronic load columns."""
    cursor = conn.execute("PRAGMA table_info(training_status)")
    cols = {row[1] for row in cursor.fetchall()}
    missing_cols = []
    if "acute_load" not in cols:
        missing_cols.append("acute_load")
    if "chronic_load" not in cols:
        missing_cols.append("chronic_load")

    if missing_cols:
        log.info(
            "Migrating training_status table, adding columns: %s",
            ", ".join(missing_cols),
        )
        for col in missing_cols:
            try:
                conn.execute(f"ALTER TABLE training_status ADD COLUMN {col} REAL")
            except sqlite3.OperationalError as e:
                log.debug("Migration note (training_status.%s): %s", col, e)


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn.executescript(_SCHEMA_SQL)
    migrate_weight_table(conn)
    migrate_device_table(conn)
    migrate_training_status_table(conn)
    migrate_activity_splits_table(conn)
    migrate_activity_splits_v2(conn)
    migrate_hrv_table(conn)
    migrate_sleep_table(conn)
    migrate_heart_rate_table(conn)
    migrate_spo2_table(conn)
    migrate_respiration_table(conn)
    migrate_hydration_table(conn)
    migrate_weight_table_v2(conn)
    migrate_endurance_score_table(conn)
    migrate_hill_score_table(conn)
    migrate_gear_table(conn)
    migrate_gear_table_v2(conn)
    migrate_hollow_tables(conn)
    migrate_sleep_table_v2(conn)
    migrate_fitness_age_table(conn)
    migrate_weight_table_v3(conn)
    migrate_activity_table(conn)

    # Only run cleanup/backfill when there are rows that actually need it.
    needs_cleanup = conn.execute(
        "SELECT 1 FROM hrv WHERE calendar_date IS NULL OR TRIM(calendar_date) = '' LIMIT 1"
    ).fetchone()
    if needs_cleanup:
        cleanup_invalid_rows(conn)

    needs_hrv_backfill = conn.execute(
        "SELECT 1 FROM hrv_timeline WHERE reading_count IS NULL OR reading_count = 0 LIMIT 1"
    ).fetchone()
    if needs_hrv_backfill:
        backfill_hrv_timeline_counts(conn)

    needs_cal_backfill = conn.execute(
        """SELECT 1 FROM daily_summary ds
           LEFT JOIN calories c ON c.calendar_date = ds.calendar_date
           WHERE c.calendar_date IS NULL
             AND (ds.total_kilocalories IS NOT NULL
                  OR ds.active_kilocalories IS NOT NULL
                  OR ds.bmr_kilocalories IS NOT NULL
                  OR ds.remaining_kilocalories IS NOT NULL)
           LIMIT 1"""
    ).fetchone()
    if needs_cal_backfill:
        backfill_calories_from_daily_summaries(conn)

    needs_bb_backfill = conn.execute(
        """SELECT 1 FROM daily_summary ds
           LEFT JOIN body_battery bb ON bb.calendar_date = ds.calendar_date
           WHERE (ds.body_battery_highest      IS NOT NULL
                  OR ds.body_battery_lowest        IS NOT NULL
                  OR ds.body_battery_charged       IS NOT NULL
                  OR ds.body_battery_drained       IS NOT NULL
                  OR ds.body_battery_most_recent   IS NOT NULL
                  OR ds.body_battery_at_wake       IS NOT NULL
                  OR ds.body_battery_during_sleep  IS NOT NULL)
             AND (bb.calendar_date IS NULL
                  OR (bb.highest      IS NULL AND ds.body_battery_highest      IS NOT NULL)
                  OR (bb.lowest       IS NULL AND ds.body_battery_lowest       IS NOT NULL)
                  OR (bb.charged      IS NULL AND ds.body_battery_charged      IS NOT NULL)
                  OR (bb.drained      IS NULL AND ds.body_battery_drained      IS NOT NULL)
                  OR (bb.most_recent  IS NULL AND ds.body_battery_most_recent  IS NOT NULL)
                  OR (bb.at_wake      IS NULL AND ds.body_battery_at_wake      IS NOT NULL)
                  OR (bb.during_sleep IS NULL AND ds.body_battery_during_sleep IS NOT NULL))
           LIMIT 1"""
    ).fetchone()
    if needs_bb_backfill:
        backfill_body_battery_from_daily_summaries(conn)

    conn.commit()


def migrate_device_table(conn: sqlite3.Connection) -> None:
    """Migrate the device table to include battery and software fields if missing."""
    cursor = conn.execute("PRAGMA table_info(device)")
    cols = {row[1] for row in cursor.fetchall()}
    missing_defs = [
        ("software_version", "TEXT"),
        ("battery_status", "TEXT"),
        ("battery_voltage", "REAL"),
    ]
    missing_cols = [name for name, _ in missing_defs if name not in cols]

    if missing_cols:
        log.info(
            "Migrating device table, adding columns: %s",
            ", ".join(missing_cols),
        )
        for name, col_type in missing_defs:
            if name in cols:
                continue
            try:
                conn.execute(f"ALTER TABLE device ADD COLUMN {name} {col_type}")
            except sqlite3.OperationalError as e:
                log.debug("Migration note (device.%s): %s", name, e)


def migrate_weight_table(conn: sqlite3.Connection) -> None:
    """Migrate the weight table to include the 'source' column and 'timestamp' PK if needed."""
    cursor = conn.execute("PRAGMA table_info(weight)")
    cols = {row[1] for row in cursor.fetchall()}

    # Check if we need to migrate (either missing 'source' or wrong PK)
    # The new schema has 'timestamp' as PK.
    is_legacy = "timestamp" not in cols

    if is_legacy:
        log.info("Migrating weight table to new schema...")
        conn.executescript(
            """
            ALTER TABLE weight RENAME TO weight_old;
            CREATE TABLE weight (
                timestamp       INTEGER PRIMARY KEY,
                calendar_date   TEXT,
                weight          REAL,
                bmi             REAL,
                body_fat        REAL,
                body_water      REAL,
                bone_mass       REAL,
                muscle_mass     REAL,
                source          TEXT,
                raw_json        TEXT
            );
            -- Use rowid as a millisecond offset to the date-based timestamp
            -- to ensure uniqueness for same-day legacy entries.
            INSERT INTO weight (timestamp, calendar_date, weight, bmi, body_fat, body_water, bone_mass, muscle_mass, source, raw_json)
            SELECT
                COALESCE(
                    json_extract(raw_json, '$.date'),
                    json_extract(raw_json, '$.timestampGMT'),
                    (CAST(strftime('%s', calendar_date) AS INTEGER) * 1000) + rowid
                ) as timestamp,
                calendar_date, weight, bmi, body_fat, body_water, bone_mass, muscle_mass,
                json_extract(raw_json, '$.sourceType'),
                raw_json
            FROM weight_old
            WHERE weight IS NOT NULL
            ON CONFLICT(timestamp) DO NOTHING;
            DROP TABLE weight_old;
            """
        )
        return

    if "source" not in cols:
        log.info("Migrating weight table, adding missing source column")
        try:
            conn.execute("ALTER TABLE weight ADD COLUMN source TEXT")
        except sqlite3.OperationalError as e:
            log.debug("Migration note (weight.source): %s", e)


# ---------------------------------------------------------------------------
# Upsert helpers — one per table
# ---------------------------------------------------------------------------


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


def backfill_calories_from_daily_summaries(conn: sqlite3.Connection) -> None:
    """Populate missing calories rows from already-synced daily summaries."""
    conn.execute(
        """
        INSERT INTO calories (calendar_date, total, active, bmr, consumed, remaining, raw_json)
        SELECT
            ds.calendar_date,
            ds.total_kilocalories,
            ds.active_kilocalories,
            ds.bmr_kilocalories,
            NULL,
            ds.remaining_kilocalories,
            ds.raw_json
        FROM daily_summary ds
        LEFT JOIN calories c ON c.calendar_date = ds.calendar_date
        WHERE c.calendar_date IS NULL
          AND (
              ds.total_kilocalories IS NOT NULL OR
              ds.active_kilocalories IS NOT NULL OR
              ds.bmr_kilocalories IS NOT NULL OR
              ds.remaining_kilocalories IS NOT NULL
          )
        """
    )


def backfill_body_battery_from_daily_summaries(conn: sqlite3.Connection) -> None:
    """Backfill body_battery aggregate columns from daily_summary.

    Historically body_battery rows were created from the body_battery_events
    endpoint which only contains time-series data — the aggregate columns
    (highest/lowest/charged/drained/etc.) were left NULL even though the
    same values lived in daily_summary the whole time. See issue #13.

    Inserts a body_battery row for any daily_summary date that doesn't have
    one, and fills NULL aggregate columns on existing rows. raw_json is left
    untouched so events-endpoint time-series data is preserved.
    """
    conn.execute(
        """
        INSERT INTO body_battery (calendar_date, charged, drained, highest, lowest, most_recent, at_wake, during_sleep)
        SELECT
            ds.calendar_date,
            ds.body_battery_charged,
            ds.body_battery_drained,
            ds.body_battery_highest,
            ds.body_battery_lowest,
            ds.body_battery_most_recent,
            ds.body_battery_at_wake,
            ds.body_battery_during_sleep
        FROM daily_summary ds
        WHERE ds.body_battery_highest      IS NOT NULL
           OR ds.body_battery_lowest       IS NOT NULL
           OR ds.body_battery_charged      IS NOT NULL
           OR ds.body_battery_drained      IS NOT NULL
           OR ds.body_battery_most_recent  IS NOT NULL
           OR ds.body_battery_at_wake      IS NOT NULL
           OR ds.body_battery_during_sleep IS NOT NULL
        ON CONFLICT(calendar_date) DO UPDATE SET
            charged      = COALESCE(body_battery.charged, excluded.charged),
            drained      = COALESCE(body_battery.drained, excluded.drained),
            highest      = COALESCE(body_battery.highest, excluded.highest),
            lowest       = COALESCE(body_battery.lowest, excluded.lowest),
            most_recent  = COALESCE(body_battery.most_recent, excluded.most_recent),
            at_wake      = COALESCE(body_battery.at_wake, excluded.at_wake),
            during_sleep = COALESCE(body_battery.during_sleep, excluded.during_sleep)
        """
    )


def cleanup_invalid_rows(conn: sqlite3.Connection) -> None:
    """Remove rows created by earlier permissive parsers."""
    conn.execute("DELETE FROM hrv WHERE calendar_date IS NULL OR TRIM(calendar_date) = ''")


def backfill_hrv_timeline_counts(conn: sqlite3.Connection) -> None:
    """Recompute reading_count from stored raw_json for existing HRV timeline rows."""
    conn.execute(
        """
        UPDATE hrv_timeline
        SET reading_count = COALESCE(
            json_array_length(json_extract(raw_json, '$.hrvReadings')),
            json_array_length(json_extract(raw_json, '$.hrvValues')),
            0
        )
        """
    )


def _mean_sample_values(samples: Any, value_key) -> Optional[float]:
    """Mean of positive numeric values in a Garmin time-series array.

    Garmin returns HR/SpO2 timelines as either ``[{startGMT, value}, ...]`` or
    ``[[ts, value], ...]``. Missing samples appear as ``None`` or ``0``;
    ignore both.
    """
    if not isinstance(samples, list):
        return None
    vals: list[float] = []
    for s in samples:
        v = None
        if isinstance(s, dict):
            v = s.get(value_key)
        elif isinstance(s, (list, tuple)) and len(s) > value_key:
            v = s[value_key]
        if isinstance(v, (int, float)) and v > 0:
            vals.append(float(v))
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


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

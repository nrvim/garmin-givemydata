"""Full CREATE TABLE/INDEX schema, applied by init_db()."""

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
    direct_workout_feel                 INTEGER,
    direct_workout_rpe                  INTEGER,
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

"""Idempotent schema migrations for databases created by older versions."""

import json
import logging
import sqlite3

from .upserts.daily import upsert_daily_events

# Keep the original logger name so existing logging config still applies.
log = logging.getLogger("garmin_mcp.db")


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
            ("direct_workout_feel", "INTEGER"),
            ("direct_workout_rpe", "INTEGER"),
        ],
    )
    update_map = {
        "body_battery_change": "$.summaryDTO.differenceBodyBattery",
        "total_work_kcal": "$.summaryDTO.totalWork",
        "avg_grade_adjusted_speed": "$.summaryDTO.avgGradeAdjustedSpeed",
        "activity_steps": "$.summaryDTO.steps",
        "activity_min_hr": "$.summaryDTO.minHR",
        "direct_workout_feel": "$.summaryDTO.directWorkoutFeel",
        "direct_workout_rpe": "$.summaryDTO.directWorkoutRpe",
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

"""init_db(): create schema, run migrations, then conditional backfills."""

import sqlite3

from .backfill import (
    backfill_body_battery_from_daily_summaries,
    backfill_calories_from_daily_summaries,
    backfill_hrv_timeline_counts,
    cleanup_invalid_rows,
)
from .migrations import (
    migrate_activity_splits_table,
    migrate_activity_splits_v2,
    migrate_activity_table,
    migrate_device_table,
    migrate_endurance_score_table,
    migrate_fitness_age_table,
    migrate_gear_table,
    migrate_gear_table_v2,
    migrate_heart_rate_table,
    migrate_hill_score_table,
    migrate_hollow_tables,
    migrate_hrv_table,
    migrate_hydration_table,
    migrate_respiration_table,
    migrate_sleep_table,
    migrate_sleep_table_v2,
    migrate_spo2_table,
    migrate_training_status_table,
    migrate_weight_table,
    migrate_weight_table_v2,
    migrate_weight_table_v3,
)
from .schema import _SCHEMA_SQL


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

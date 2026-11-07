"""init_db(): create schema, run pending migrations, then conditional backfills.

Schema versioning
-----------------
``PRAGMA user_version`` records how many entries of ``MIGRATIONS`` have been
applied to a database. ``init_db`` runs only the entries that are still pending,
so a database that is up to date skips all migration work on startup.

Databases created before versioning existed have ``user_version = 0`` and run
every migration once, exactly as ``init_db`` always did. All migrations are
idempotent, so resetting with ``PRAGMA user_version = 0`` is always safe.

Rules for changing ``MIGRATIONS``:
  * only ever append; never reorder, remove or replace an existing entry;
  * each new migration must be idempotent (safe on fresh and on old schemas);
  * a migration only has to repair rows written by *older* code: rows written
    afterwards come from the current upserts, which already fill new columns.
"""

import logging
import sqlite3
from typing import Callable

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

# Keep the original logger name so existing logging config still applies.
log = logging.getLogger("garmin_mcp.db")

# Ordered migrations; schema version N means MIGRATIONS[:N] have been applied.
# APPEND ONLY — see the module docstring.
MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (
    migrate_weight_table,  # 1
    migrate_device_table,  # 2
    migrate_training_status_table,  # 3
    migrate_activity_splits_table,  # 4
    migrate_activity_splits_v2,  # 5
    migrate_hrv_table,  # 6
    migrate_sleep_table,  # 7
    migrate_heart_rate_table,  # 8
    migrate_spo2_table,  # 9
    migrate_respiration_table,  # 10
    migrate_hydration_table,  # 11
    migrate_weight_table_v2,  # 12
    migrate_endurance_score_table,  # 13
    migrate_hill_score_table,  # 14
    migrate_gear_table,  # 15
    migrate_gear_table_v2,  # 16
    migrate_hollow_tables,  # 17
    migrate_sleep_table_v2,  # 18
    migrate_fitness_age_table,  # 19
    migrate_weight_table_v3,  # 20
    migrate_activity_table,  # 21
)

SCHEMA_VERSION = len(MIGRATIONS)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the number of MIGRATIONS applied to this database (PRAGMA user_version)."""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending MIGRATIONS in order and return how many were applied.

    The version is bumped and committed after each migration, so an interrupted
    run resumes at the first migration that did not complete. A database whose
    version is newer than this code (written by a later release) is left as is.
    """
    current = get_schema_version(conn)
    if current > SCHEMA_VERSION:
        log.warning(
            "Database schema version %d is newer than this code supports (%d); skipping migrations.",
            current,
            SCHEMA_VERSION,
        )
        return 0
    for version in range(current + 1, SCHEMA_VERSION + 1):
        MIGRATIONS[version - 1](conn)
        # PRAGMA cannot take bound parameters; version is an int from range().
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()
    applied = SCHEMA_VERSION - current
    if applied:
        log.info("Applied %d schema migration(s): version %d -> %d", applied, current, SCHEMA_VERSION)
    return applied


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if missing, apply pending migrations, run needed backfills."""
    conn.executescript(_SCHEMA_SQL)
    run_migrations(conn)

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

"""
Tests for activity table fields: direct_workout_feel, direct_workout_rpe,
and exercise_name/exercise_category extraction in activity_exercise_sets.
"""

import sqlite3

import pytest

from garmin_mcp.db import (
    init_db,
    migrate_activity_table,
    query,
    upsert_activity,
    upsert_activity_exercise_sets,
)


class TestActivityTableSchema:
    """Verify activity table contains the new workout feel/RPE columns."""

    def test_direct_workout_feel_column_exists(self, temp_db):
        cursor = temp_db.execute("PRAGMA table_info(activity)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert "direct_workout_feel" in cols
        assert cols["direct_workout_feel"] == "INTEGER"

    def test_direct_workout_rpe_column_exists(self, temp_db):
        cursor = temp_db.execute("PRAGMA table_info(activity)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert "direct_workout_rpe" in cols
        assert cols["direct_workout_rpe"] == "INTEGER"


class TestUpsertActivityWorkoutFields:
    """Verify direct_workout_feel and direct_workout_rpe are persisted."""

    def test_workout_feel_and_rpe_stored(self, temp_db):
        record = {
            "activityId": 99001,
            "activityName": "Strength",
            "activityType": {"typeKey": "strength_training", "typeId": 5, "parentTypeId": 4},
            "startTimeLocal": "2026-05-01T09:00:00",
            "startTimeGMT": "2026-05-01T13:00:00",
            "duration": 3600,
            "directWorkoutFeel": 4,
            "directWorkoutRpe": 7,
        }
        upsert_activity(temp_db, record)
        rows = query(temp_db, "SELECT direct_workout_feel, direct_workout_rpe FROM activity WHERE activity_id = ?", [99001])
        assert len(rows) == 1
        assert rows[0]["direct_workout_feel"] == 4
        assert rows[0]["direct_workout_rpe"] == 7

    def test_workout_feel_and_rpe_null_when_absent(self, temp_db):
        record = {
            "activityId": 99002,
            "activityName": "Run",
            "activityType": {"typeKey": "running", "typeId": 1, "parentTypeId": 1},
            "startTimeLocal": "2026-05-01T07:00:00",
            "startTimeGMT": "2026-05-01T11:00:00",
            "duration": 1800,
        }
        upsert_activity(temp_db, record)
        rows = query(temp_db, "SELECT direct_workout_feel, direct_workout_rpe FROM activity WHERE activity_id = ?", [99002])
        assert len(rows) == 1
        assert rows[0]["direct_workout_feel"] is None
        assert rows[0]["direct_workout_rpe"] is None


class TestUpsertActivityExerciseSets:
    """Verify exercise_name and exercise_category are extracted correctly."""

    def test_nested_exercises_structure(self, temp_db):
        """Garmin API returns exercise details nested under 'exercises' list."""
        data = {
            "exerciseSets": [
                {
                    "setType": "ACTIVE",
                    "exercises": [{"category": "CHEST", "name": "BENCH_PRESS"}],
                    "repetitionCount": 10,
                    "weight": 50000,
                    "duration": None,
                },
                {
                    "setType": "ACTIVE",
                    "exercises": [{"category": "BACK", "name": "PULL_UP"}],
                    "repetitionCount": 8,
                    "weight": None,
                    "duration": None,
                },
            ]
        }
        count = upsert_activity_exercise_sets(temp_db, 99001, data)
        assert count == 2
        rows = query(
            temp_db,
            "SELECT set_number, exercise_name, exercise_category FROM activity_exercise_sets WHERE activity_id = ? ORDER BY set_number",
            [99001],
        )
        assert rows[0]["exercise_name"] == "BENCH_PRESS"
        assert rows[0]["exercise_category"] == "CHEST"
        assert rows[1]["exercise_name"] == "PULL_UP"
        assert rows[1]["exercise_category"] == "BACK"

    def test_flat_exercises_structure_fallback(self, temp_db):
        """Backward compatibility: top-level exerciseName/exerciseCategory keys."""
        data = [
            {
                "exerciseName": "SQUAT",
                "exerciseCategory": "LEGS",
                "repetitionCount": 5,
                "weight": 80000,
            }
        ]
        count = upsert_activity_exercise_sets(temp_db, 99002, data)
        assert count == 1
        rows = query(
            temp_db,
            "SELECT exercise_name, exercise_category FROM activity_exercise_sets WHERE activity_id = ?",
            [99002],
        )
        assert rows[0]["exercise_name"] == "SQUAT"
        assert rows[0]["exercise_category"] == "LEGS"

    def test_empty_exercises_list_stores_null(self, temp_db):
        """Sets with no 'exercises' entries store NULL for name/category."""
        data = {
            "exerciseSets": [
                {
                    "setType": "REST",
                    "exercises": [],
                    "duration": 60,
                }
            ]
        }
        count = upsert_activity_exercise_sets(temp_db, 99003, data)
        assert count == 1
        rows = query(
            temp_db,
            "SELECT exercise_name, exercise_category FROM activity_exercise_sets WHERE activity_id = ?",
            [99003],
        )
        assert rows[0]["exercise_name"] is None
        assert rows[0]["exercise_category"] is None


class TestMigrateActivityTable:
    """Verify migrate_activity_table adds missing columns to existing databases."""

    def test_migration_adds_missing_columns(self):
        """Simulate a legacy database without the new columns."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Create activity table without the new columns (legacy schema)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS activity (
                activity_id INTEGER PRIMARY KEY,
                activity_name TEXT,
                raw_json TEXT
            )"""
        )
        conn.commit()

        migrate_activity_table(conn)

        cursor = conn.execute("PRAGMA table_info(activity)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "direct_workout_feel" in cols
        assert "direct_workout_rpe" in cols
        conn.close()

    def test_migration_idempotent(self, temp_db):
        """Running migration twice does not raise errors."""
        migrate_activity_table(temp_db)
        migrate_activity_table(temp_db)

        cursor = temp_db.execute("PRAGMA table_info(activity)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "direct_workout_feel" in cols
        assert "direct_workout_rpe" in cols

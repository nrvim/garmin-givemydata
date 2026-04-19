"""
Database tests for activity_trackpoints table and related operations.
"""

import sqlite3

import pytest

from garmin_mcp.db import init_db, query, save_to_db, upsert_activity, upsert_activity_trackpoints


class TestActivityTrackpointsTable:
    """Test activity_trackpoints table schema and basic operations."""

    def test_table_exists(self, temp_db):
        """Verify activity_trackpoints table is created."""
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_trackpoints'"
        )
        assert cursor.fetchone() is not None

    def test_table_schema(self, temp_db):
        """Verify table has correct columns."""
        cursor = temp_db.execute("PRAGMA table_info(activity_trackpoints)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        expected_columns = {
            "activity_id": "INTEGER",
            "seq": "INTEGER",
            "timestamp_utc": "TEXT",
            "latitude": "REAL",
            "longitude": "REAL",
            "altitude_m": "REAL",
            "distance_m": "REAL",
            "speed_mps": "REAL",
            "heart_rate_bpm": "INTEGER",
            "cadence": "INTEGER",
            "power_w": "INTEGER",
            "temperature_c": "REAL",
        }
        
        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Missing column: {col_name}"
            assert columns[col_name] == col_type, f"Column {col_name} has type {columns[col_name]}, expected {col_type}"

    def test_primary_key_constraint(self, temp_db):
        """Verify (activity_id, seq) is primary key."""
        cursor = temp_db.execute("PRAGMA table_info(activity_trackpoints)")
        pk_columns = [row[1] for row in cursor.fetchall() if row[5] > 0]
        
        assert "activity_id" in pk_columns
        assert "seq" in pk_columns


class TestUpsertActivityTrackpoints:
    """Test upsert_activity_trackpoints function."""

    def test_insert_trackpoints(self, temp_db, sample_trackpoints):
        """Test inserting trackpoints."""
        activity_id = 12345678
        count = upsert_activity_trackpoints(temp_db, activity_id, sample_trackpoints)
        
        assert count == len(sample_trackpoints)
        
        # Verify data was inserted
        rows = query(temp_db, "SELECT * FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert len(rows) == len(sample_trackpoints)

    def test_insert_empty_list(self, temp_db):
        """Test that empty list returns 0."""
        count = upsert_activity_trackpoints(temp_db, 12345678, [])
        assert count == 0

    def test_replace_existing_trackpoints(self, temp_db, sample_trackpoints):
        """Test that upsert replaces existing trackpoints."""
        activity_id = 12345678
        
        # Insert first time
        count1 = upsert_activity_trackpoints(temp_db, activity_id, sample_trackpoints)
        rows1 = query(temp_db, "SELECT COUNT(*) as cnt FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert rows1[0]["cnt"] == len(sample_trackpoints)
        
        # Insert again (should replace)
        new_trackpoints = sample_trackpoints[:3]  # Fewer points
        count2 = upsert_activity_trackpoints(temp_db, activity_id, new_trackpoints)
        
        # Should have only new points
        rows2 = query(temp_db, "SELECT COUNT(*) as cnt FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert rows2[0]["cnt"] == len(new_trackpoints)

    def test_trackpoint_data_integrity(self, temp_db, sample_trackpoints):
        """Test that trackpoint data is stored correctly."""
        activity_id = 12345678
        upsert_activity_trackpoints(temp_db, activity_id, sample_trackpoints)
        
        rows = query(temp_db, "SELECT * FROM activity_trackpoints WHERE activity_id = ? ORDER BY seq", [activity_id])
        
        # Verify first trackpoint
        first = rows[0]
        assert first["seq"] == 0
        assert first["timestamp_utc"] == "2026-04-19T08:00:00"
        assert abs(first["latitude"] - 40.712776) < 0.00001
        assert abs(first["longitude"] - (-74.005974)) < 0.00001
        assert first["altitude_m"] == 10.5
        assert first["heart_rate_bpm"] == 72
        
        # Verify second trackpoint
        second = rows[1]
        assert second["seq"] == 1
        assert second["heart_rate_bpm"] == 75
        assert second["cadence"] == 85
        assert second["power_w"] == 150


class TestSaveToDbTrackpoints:
    """Test save_to_db router for trackpoints."""

    def test_save_trackpoints_via_router(self, temp_db, sample_trackpoints):
        """Test saving trackpoints via save_to_db router."""
        activity_id = 12345678
        count = save_to_db(temp_db, "activity_trackpoints", sample_trackpoints, cal_date=str(activity_id))
        
        assert count == len(sample_trackpoints)
        
        rows = query(temp_db, "SELECT COUNT(*) as cnt FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert rows[0]["cnt"] == len(sample_trackpoints)

    def test_save_empty_trackpoints(self, temp_db):
        """Test saving empty trackpoints."""
        count = save_to_db(temp_db, "activity_trackpoints", [], cal_date="12345678")
        assert count == 0


class TestActivityTrackpointsIndex:
    """Test index on activity_trackpoints."""

    def test_index_exists(self, temp_db):
        """Verify index on activity_id exists."""
        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_trackpoints_activity'"
        )
        assert cursor.fetchone() is not None


class TestTrackpointsWithActivities:
    """Integration tests: trackpoints with activity records."""

    def test_activity_with_trackpoints(self, temp_db, sample_activity, sample_trackpoints):
        """Test storing activity and its trackpoints together."""
        # Insert activity
        upsert_activity(temp_db, sample_activity)
        
        # Insert trackpoints
        activity_id = sample_activity["activityId"]
        count = upsert_activity_trackpoints(temp_db, activity_id, sample_trackpoints)
        
        # Verify both exist
        activities = query(temp_db, "SELECT * FROM activity WHERE activity_id = ?", [activity_id])
        assert len(activities) == 1
        assert activities[0]["activity_name"] == "Test Run"
        
        trackpoints = query(temp_db, "SELECT * FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert len(trackpoints) == len(sample_trackpoints)

    def test_cascade_behavior(self, temp_db, sample_trackpoints):
        """Verify trackpoints can be managed independently of activities."""
        # Insert trackpoints without activity (should work if no FK constraint)
        activity_id = 99999999
        count = upsert_activity_trackpoints(temp_db, activity_id, sample_trackpoints)
        
        assert count == len(sample_trackpoints)
        
        rows = query(temp_db, "SELECT COUNT(*) as cnt FROM activity_trackpoints WHERE activity_id = ?", [activity_id])
        assert rows[0]["cnt"] == len(sample_trackpoints)

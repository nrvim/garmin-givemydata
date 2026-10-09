"""Tests for #85 finding 5: health_snapshot per-snapshot schema.

- summary (HR/respiration/stress/SpO2/HRV) surfaced as columns,
- snapshot_id primary key so two snapshots on the same day coexist,
- rebuild migration from the old calendar_date-keyed table.
"""

import json
import sqlite3

from garmin_mcp.db import (
    _SCHEMA_SQL,
    health_snapshot_id,
    init_db,
    migrate_health_snapshot_schema,
    upsert_health_snapshot,
)


def _snapshot(uuid, date, start, hr_avg=63):
    return {
        "activityUuid": {"uuid": uuid},
        "calendarDate": date,
        "activityName": "Health Snapshot",
        "wellnessActivityType": "HEALTH_MONITORING",
        "startTimestampLocal": start,
        "endTimestampLocal": start,
        "summaryTypeDataList": [
            {"summaryType": "HEART_RATE", "avgValue": hr_avg, "minValue": 59, "maxValue": 70},
            {"summaryType": "RESPIRATION", "avgValue": 18.17, "minValue": 15, "maxValue": 21},
            {"summaryType": "STRESS", "avgValue": 15, "minValue": 12, "maxValue": 19},
            {"summaryType": "SPO2", "avgValue": 99, "minValue": 93, "maxValue": 100},
            {"summaryType": "RMSSD_HRV", "avgValue": 42},
            {"summaryType": "SDRR_HRV", "avgValue": 57},
        ],
    }


class TestSnapshotId:
    def test_prefers_uuid(self):
        assert health_snapshot_id({"activityUuid": {"uuid": "abc"}, "startTimestampLocal": "t"}) == "abc"

    def test_falls_back_to_start(self):
        assert health_snapshot_id({"startTimestampLocal": "2026-01-01T10:00:00.0"}) == "2026-01-01T10:00:00.0"

    def test_none_when_no_id(self):
        assert health_snapshot_id({"calendarDate": "2026-01-01"}) is None


class TestUpsert:
    def test_summary_parsed_into_columns(self, temp_db):
        upsert_health_snapshot(temp_db, _snapshot("u1", "2026-01-01", "2026-01-01T10:00:00.0"))
        r = temp_db.execute("SELECT * FROM health_snapshot WHERE snapshot_id = 'u1'").fetchone()
        assert r["hr_avg"] == 63 and r["hr_min"] == 59 and r["hr_max"] == 70
        assert r["respiration_avg"] == 18.17 and r["respiration_max"] == 21
        assert r["stress_avg"] == 15 and r["spo2_avg"] == 99 and r["spo2_min"] == 93
        assert r["rmssd_hrv"] == 42 and r["sdrr_hrv"] == 57
        assert r["calendar_date"] == "2026-01-01"

    def test_two_snapshots_same_day_coexist(self, temp_db):
        upsert_health_snapshot(temp_db, _snapshot("morning", "2026-01-02", "2026-01-02T08:00:00.0", hr_avg=60))
        upsert_health_snapshot(temp_db, _snapshot("evening", "2026-01-02", "2026-01-02T20:00:00.0", hr_avg=70))
        rows = temp_db.execute(
            "SELECT snapshot_id, hr_avg FROM health_snapshot WHERE calendar_date = '2026-01-02' ORDER BY snapshot_id"
        ).fetchall()
        assert len(rows) == 2
        assert {r["snapshot_id"]: r["hr_avg"] for r in rows} == {"morning": 60, "evening": 70}

    def test_no_id_is_skipped(self, temp_db):
        upsert_health_snapshot(temp_db, {"calendarDate": "2026-01-03"})
        assert temp_db.execute("SELECT COUNT(*) FROM health_snapshot").fetchone()[0] == 0


class TestRebuildMigration:
    def _old_schema_conn(self):
        # Build a DB whose health_snapshot is the OLD calendar_date-keyed shape.
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)  # new schema
        conn.execute("DROP TABLE health_snapshot")
        conn.execute(
            """CREATE TABLE health_snapshot (
                 calendar_date TEXT PRIMARY KEY, activity_name TEXT,
                 wellness_activity_type TEXT, start_timestamp_local TEXT,
                 end_timestamp_local TEXT, raw_json TEXT)"""
        )
        return conn

    def test_rebuild_preserves_and_parses(self):
        conn = self._old_schema_conn()
        rec = _snapshot("u-old", "2025-04-30", "2025-04-30T19:08:17.0")
        conn.execute(
            "INSERT INTO health_snapshot (calendar_date, activity_name, start_timestamp_local, raw_json) VALUES (?,?,?,?)",
            ("2025-04-30", "Health Snapshot - Evening", "2025-04-30T19:08:17.0", json.dumps(rec)),
        )
        conn.commit()

        migrate_health_snapshot_schema(conn)

        cols = [c[1] for c in conn.execute("PRAGMA table_info(health_snapshot)")]
        assert "snapshot_id" in cols
        r = conn.execute("SELECT * FROM health_snapshot WHERE snapshot_id = 'u-old'").fetchone()
        assert r is not None
        assert r["hr_min"] == 59 and r["spo2_avg"] == 99 and r["respiration_avg"] == 18.17
        # the temp table is cleaned up
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = '_health_snapshot_old'").fetchone()[0] == 0

    def test_rebuild_is_idempotent_on_new_schema(self, temp_db):
        # temp_db already has the new schema; migration must be a no-op.
        upsert_health_snapshot(temp_db, _snapshot("u2", "2026-01-05", "2026-01-05T10:00:00.0"))
        migrate_health_snapshot_schema(temp_db)
        assert temp_db.execute("SELECT COUNT(*) FROM health_snapshot").fetchone()[0] == 1

    def test_rebuild_keeps_row_without_raw_json(self):
        conn = self._old_schema_conn()
        conn.execute(
            "INSERT INTO health_snapshot (calendar_date, activity_name, start_timestamp_local, raw_json) VALUES (?,?,?,NULL)",
            ("2024-01-01", "Snap", "2024-01-01T06:00:00.0"),
        )
        conn.commit()
        migrate_health_snapshot_schema(conn)
        r = conn.execute("SELECT snapshot_id, calendar_date FROM health_snapshot").fetchone()
        # falls back to the start timestamp as id, data preserved
        assert r["snapshot_id"] == "2024-01-01T06:00:00.0"
        assert r["calendar_date"] == "2024-01-01"

    def test_rebuild_never_drops_an_id_less_row(self):
        # Legacy row with NO uuid, NULL start, NULL raw_json: must still be
        # preserved (id falls back to calendar_date), never silently dropped.
        conn = self._old_schema_conn()
        conn.execute(
            "INSERT INTO health_snapshot (calendar_date, activity_name, start_timestamp_local, raw_json) VALUES (?,?,NULL,NULL)",
            ("2023-07-07", "Old Snap"),
        )
        conn.commit()
        migrate_health_snapshot_schema(conn)
        rows = conn.execute("SELECT snapshot_id, calendar_date FROM health_snapshot").fetchall()
        assert len(rows) == 1
        assert rows[0]["calendar_date"] == "2023-07-07"
        assert rows[0]["snapshot_id"] == "2023-07-07"  # calendar_date used as last-resort id

    def test_rebuild_handles_malformed_raw_json(self):
        conn = self._old_schema_conn()
        conn.execute(
            "INSERT INTO health_snapshot (calendar_date, start_timestamp_local, raw_json) VALUES (?,?,?)",
            ("2023-08-08", "2023-08-08T06:00:00.0", "<<not json>>"),
        )
        conn.commit()
        migrate_health_snapshot_schema(conn)  # must not raise
        r = conn.execute("SELECT snapshot_id FROM health_snapshot").fetchone()
        assert r is not None and r["snapshot_id"] == "2023-08-08T06:00:00.0"

    def test_rebuild_recovers_from_interrupted_run(self):
        # Simulate a crash mid-rebuild: new (empty) health_snapshot + leftover
        # _health_snapshot_old with the real data. The migration must restore and
        # re-migrate, losing nothing.
        conn = self._old_schema_conn()
        rec = _snapshot("u-recover", "2025-04-30", "2025-04-30T19:08:17.0")
        conn.execute(
            "INSERT INTO health_snapshot (calendar_date, start_timestamp_local, raw_json) VALUES (?,?,?)",
            ("2025-04-30", "2025-04-30T19:08:17.0", json.dumps(rec)),
        )
        # mimic the interrupted state
        conn.execute("ALTER TABLE health_snapshot RENAME TO _health_snapshot_old")
        conn.executescript(_SCHEMA_SQL)  # new empty health_snapshot
        conn.commit()
        migrate_health_snapshot_schema(conn)
        r = conn.execute("SELECT snapshot_id, hr_min FROM health_snapshot WHERE snapshot_id='u-recover'").fetchone()
        assert r is not None and r["hr_min"] == 59
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='_health_snapshot_old'").fetchone()[0] == 0


def test_schema_sql_defines_new_columns():
    assert "snapshot_id" in _SCHEMA_SQL and "respiration_avg" in _SCHEMA_SQL

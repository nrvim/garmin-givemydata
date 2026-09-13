"""Tests for issue #83 — the raw_json shape fix (#80) applied only to the
startup backfill. The live write paths still read nested-only, two tables
read key names Garmin never sends, and upsert_stress can store a duration
as a stress level."""

import json

from garmin_mcp.db import (
    migrate_activity_table,
    migrate_daily_summary_stress,
    migrate_running_dynamics_stride,
    migrate_stress_max_level,
    save_to_db,
    upsert_activity,
    upsert_daily_summary,
    upsert_running_dynamics,
    upsert_stress,
)


def _activity_row(conn, aid):
    row = conn.execute("SELECT * FROM activity WHERE activity_id = ?", (aid,)).fetchone()
    return dict(row) if row else None


def _rd_row(conn, aid):
    row = conn.execute("SELECT * FROM running_dynamics WHERE activity_id = ?", (aid,)).fetchone()
    return dict(row) if row else None


class TestUpsertActivityFlatShape:
    """Bug 1: upsert_activity read the 7 summaryDTO-derived fields nested-only,
    but it is fed list-endpoint records, which are flat."""

    def test_flat_record_populates_summary_columns(self, temp_db):
        upsert_activity(
            temp_db,
            {
                "activityId": 999,
                "differenceBodyBattery": -42,
                "steps": 1234,
                "minHR": 55,
                "directWorkoutFeel": 3,
                "directWorkoutRpe": 60,
            },
        )
        row = _activity_row(temp_db, 999)
        assert row["body_battery_change"] == -42
        assert row["activity_steps"] == 1234
        assert row["activity_min_hr"] == 55
        assert row["direct_workout_feel"] == 3
        assert row["direct_workout_rpe"] == 60

    def test_zero_values_survive(self, temp_db):
        """0 is a legitimate value — must not be dropped by truthiness checks."""
        upsert_activity(temp_db, {"activityId": 1000, "differenceBodyBattery": 0, "steps": 0})
        row = _activity_row(temp_db, 1000)
        assert row["body_battery_change"] == 0
        assert row["activity_steps"] == 0

    def test_nested_record_still_works(self, temp_db):
        upsert_activity(
            temp_db,
            {"activityId": 1001, "summaryDTO": {"differenceBodyBattery": -7, "steps": 500, "minHR": 61}},
        )
        row = _activity_row(temp_db, 1001)
        assert row["body_battery_change"] == -7
        assert row["activity_steps"] == 500
        assert row["activity_min_hr"] == 61

    def test_flat_value_wins_over_nested(self, temp_db):
        upsert_activity(
            temp_db,
            {"activityId": 1002, "steps": 100, "summaryDTO": {"steps": 999}},
        )
        assert _activity_row(temp_db, 1002)["activity_steps"] == 100

    def test_pack_weight_captured_on_live_path(self, temp_db):
        """#80 added the columns but only the migration filled them — the live
        write path must capture pack weight too."""
        upsert_activity(temp_db, {"activityId": 1003, "beginPackWeight": 9071.85, "endPackWeight": 4535.92})
        row = _activity_row(temp_db, 1003)
        assert row["begin_pack_weight"] == 9071.85
        assert row["end_pack_weight"] == 4535.92


class TestActivityDetailsFlatShape:
    """Bug 2: the activity_details branch of save_to_db read nested-only."""

    def test_flattened_detail_record_populates(self, temp_db):
        upsert_activity(temp_db, {"activityId": 2000})
        save_to_db(
            temp_db,
            "activity_details",
            [{"activityId": 2000, "differenceBodyBattery": -12, "steps": 4321, "minHR": 48}],
        )
        row = _activity_row(temp_db, 2000)
        assert row["body_battery_change"] == -12
        assert row["activity_steps"] == 4321
        assert row["activity_min_hr"] == 48

    def test_nested_detail_record_still_populates(self, temp_db):
        upsert_activity(temp_db, {"activityId": 2001})
        save_to_db(
            temp_db,
            "activity_details",
            [{"activityId": 2001, "summaryDTO": {"differenceBodyBattery": -9, "steps": 777}}],
        )
        row = _activity_row(temp_db, 2001)
        assert row["body_battery_change"] == -9
        assert row["activity_steps"] == 777


class TestRunningDynamicsStride:
    """Bug 3: Garmin sends avgStrideLength, only on list records; the details
    path read a strideLength key that never exists, so running_dynamics has
    never held a value."""

    def test_stride_captured_from_list_record(self, temp_db):
        upsert_activity(temp_db, {"activityId": 3000, "avgStrideLength": 111.5})
        rd = _rd_row(temp_db, 3000)
        assert rd is not None
        assert rd["avg_stride_len"] == 111.5

    def test_details_sync_does_not_wipe_stride(self, temp_db):
        """INSERT OR REPLACE used to rewrite the whole row; a details record
        (which never carries stride) must not null the stored value."""
        upsert_activity(temp_db, {"activityId": 3001, "avgStrideLength": 105.0})
        upsert_running_dynamics(temp_db, 3001, {"summaryDTO": {"groundContactTime": 250.0}})
        rd = _rd_row(temp_db, 3001)
        assert rd["avg_stride_len"] == 105.0
        assert rd["avg_gct"] == 250.0

    def test_no_row_created_when_no_dynamics_data(self, temp_db):
        """Rows used to be created for breathwork/strength activities that can
        never produce running dynamics, hiding the empty-table symptom."""
        upsert_running_dynamics(temp_db, 3002, {"summaryDTO": {"calories": 12}})
        assert _rd_row(temp_db, 3002) is None

    def test_details_dynamics_still_stored(self, temp_db):
        upsert_running_dynamics(
            temp_db,
            3003,
            {"summaryDTO": {"groundContactTime": 240.0, "verticalOscillation": 8.2}},
        )
        rd = _rd_row(temp_db, 3003)
        assert rd["avg_gct"] == 240.0
        assert rd["avg_vert_osc"] == 8.2

    def test_migration_backfills_stride_from_activity_raw_json(self, temp_db):
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (3004, json.dumps({"activityId": 3004, "avgStrideLength": 98.7})),
        )
        temp_db.commit()
        migrate_running_dynamics_stride(temp_db)
        rd = _rd_row(temp_db, 3004)
        assert rd is not None
        assert rd["avg_stride_len"] == 98.7

    def test_migration_is_idempotent(self, temp_db):
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (3005, json.dumps({"activityId": 3005, "avgStrideLength": 90.0})),
        )
        temp_db.commit()
        migrate_running_dynamics_stride(temp_db)
        migrate_running_dynamics_stride(temp_db)
        assert _rd_row(temp_db, 3005)["avg_stride_len"] == 90.0


class TestDailySummaryStressDurations:
    """Bug 4: Garmin sends lowStressDuration etc.; the code read a *Seconds
    spelling that matches nothing, so the columns were NULL on every row."""

    def _row(self, conn, day):
        return dict(conn.execute("SELECT * FROM daily_summary WHERE calendar_date = ?", (day,)).fetchone())

    def test_duration_spelling_captured(self, temp_db):
        upsert_daily_summary(
            temp_db,
            {
                "calendarDate": "2026-09-01",
                "lowStressDuration": 5000,
                "mediumStressDuration": 1200,
                "highStressDuration": 0,
            },
        )
        row = self._row(temp_db, "2026-09-01")
        assert row["low_stress_seconds"] == 5000
        assert row["medium_stress_seconds"] == 1200
        assert row["high_stress_seconds"] == 0

    def test_seconds_spelling_still_accepted(self, temp_db):
        upsert_daily_summary(
            temp_db,
            {
                "calendarDate": "2026-09-02",
                "lowStressSeconds": 100,
                "mediumStressSeconds": 200,
                "highStressSeconds": 300,
            },
        )
        row = self._row(temp_db, "2026-09-02")
        assert row["low_stress_seconds"] == 100
        assert row["medium_stress_seconds"] == 200
        assert row["high_stress_seconds"] == 300

    def test_migration_backfills_from_raw_json(self, temp_db):
        raw = {
            "calendarDate": "2026-09-03",
            "lowStressDuration": 2490,
            "mediumStressDuration": 0,
            "highStressDuration": 2335,
        }
        temp_db.execute(
            "INSERT INTO daily_summary (calendar_date, raw_json) VALUES (?, ?)",
            ("2026-09-03", json.dumps(raw)),
        )
        temp_db.commit()
        migrate_daily_summary_stress(temp_db)
        row = self._row(temp_db, "2026-09-03")
        assert row["low_stress_seconds"] == 2490
        assert row["medium_stress_seconds"] == 0
        assert row["high_stress_seconds"] == 2335


class TestUpsertStressMaxLevel:
    """max_stress is a 0-100 level; the old fallback stored highStressDuration
    (seconds) when maxStressLevel was missing or 0."""

    def _row(self, conn, day):
        return dict(conn.execute("SELECT * FROM stress WHERE calendar_date = ?", (day,)).fetchone())

    def test_duration_does_not_leak_into_max_stress(self, temp_db):
        upsert_stress(temp_db, {"calendarDate": "2026-09-04", "highStressDuration": 2335})
        assert self._row(temp_db, "2026-09-04")["max_stress"] is None

    def test_zero_max_stress_survives(self, temp_db):
        upsert_stress(temp_db, {"calendarDate": "2026-09-05", "maxStressLevel": 0, "highStressDuration": 2335})
        assert self._row(temp_db, "2026-09-05")["max_stress"] == 0

    def test_migration_repairs_duration_garbage(self, temp_db):
        raw = {"calendarDate": "2026-09-06", "maxStressLevel": 87, "highStressDuration": 2335}
        temp_db.execute(
            "INSERT OR REPLACE INTO stress (calendar_date, max_stress, raw_json) VALUES (?, ?, ?)",
            ("2026-09-06", 2335, json.dumps(raw)),
        )
        temp_db.commit()
        migrate_stress_max_level(temp_db)
        assert self._row(temp_db, "2026-09-06")["max_stress"] == 87


class TestEnvelopeRowCleanup:
    """Old versions stored API response envelopes as activity rows; nothing
    cleaned them up."""

    def test_envelope_rows_deleted_by_migration(self, temp_db):
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (22481682404, json.dumps({"activityList": [{"activityId": 6787057204}]})),
        )
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (
                22481682400,
                json.dumps({"data": {"activitiesScalar": None}, "errors": [{"extensions": {}}]}),
            ),
        )
        temp_db.execute(
            "INSERT INTO activity (activity_id, start_time_local, raw_json) VALUES (?, ?, ?)",
            (5000, "2026-09-01 08:00:00", json.dumps({"activityId": 5000})),
        )
        temp_db.commit()
        migrate_activity_table(temp_db)
        ids = {r[0] for r in temp_db.execute("SELECT activity_id FROM activity").fetchall()}
        assert 22481682404 not in ids
        assert 22481682400 not in ids
        assert 5000 in ids

    def test_rows_without_envelope_signature_survive(self, temp_db):
        """Deletion must positively match envelope shapes — a sparse but real
        row (no activityId key in raw_json) is not an envelope."""
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (5001, json.dumps({"summaryDTO": {"steps": 100}})),
        )
        temp_db.commit()
        migrate_activity_table(temp_db)
        assert _activity_row(temp_db, 5001) is not None

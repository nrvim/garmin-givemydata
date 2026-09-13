"""Tests for issue #83 — the raw_json shape fix (#80) applied only to the
startup backfill. The live write paths still read nested-only, two tables
read key names Garmin never sends, and upsert_stress can store a duration
as a stress level."""

import json

from garmin_mcp.db import (
    migrate_activity_table,
    migrate_calories_consumed,
    migrate_daily_summary_backfill,
    migrate_floors_totals,
    migrate_health_status,
    migrate_running_dynamics_backfill,
    migrate_stress_max_level,
    save_to_db,
    upsert_activity,
    upsert_daily_summary,
    upsert_floors,
    upsert_health_status,
    upsert_hrv,
    upsert_intensity_minutes,
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

    def test_pack_weight_from_nested_detail_record(self, temp_db):
        """Nested details records carry summaryDTO.beginPackWeight (#79 data);
        the details branch must capture it live, not only via migration."""
        upsert_activity(temp_db, {"activityId": 2002})
        save_to_db(
            temp_db,
            "activity_details",
            [{"activityId": 2002, "summaryDTO": {"beginPackWeight": 9071.85, "endPackWeight": 9000.0}}],
        )
        row = _activity_row(temp_db, 2002)
        assert row["begin_pack_weight"] == 9071.85
        assert row["end_pack_weight"] == 9000.0

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
        migrate_running_dynamics_backfill(temp_db)
        rd = _rd_row(temp_db, 3004)
        assert rd is not None
        assert rd["avg_stride_len"] == 98.7

    def test_migration_is_idempotent(self, temp_db):
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (3005, json.dumps({"activityId": 3005, "avgStrideLength": 90.0})),
        )
        temp_db.commit()
        migrate_running_dynamics_backfill(temp_db)
        migrate_running_dynamics_backfill(temp_db)
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
        migrate_daily_summary_backfill(temp_db)
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


class TestDailySummaryKeyNames:
    """Round 3 (#83 audit method on the live DB): two more daily_summary
    columns read keys Garmin never sends."""

    def _row(self, conn, day):
        return dict(conn.execute("SELECT * FROM daily_summary WHERE calendar_date = ?", (day,)).fetchone())

    def test_real_key_spellings_captured(self, temp_db):
        upsert_daily_summary(
            temp_db,
            {
                "calendarDate": "2026-09-10",
                "userFloorsAscendedGoal": 10,
                "lastSevenDaysAvgRestingHeartRate": 52,
            },
        )
        row = self._row(temp_db, "2026-09-10")
        assert row["floors_ascended_goal"] == 10
        assert row["avg_resting_heart_rate_7day"] == 52

    def test_old_spellings_still_accepted(self, temp_db):
        upsert_daily_summary(
            temp_db,
            {"calendarDate": "2026-09-11", "floorsAscendedGoal": 12, "averageRestingHeartRate": 55},
        )
        row = self._row(temp_db, "2026-09-11")
        assert row["floors_ascended_goal"] == 12
        assert row["avg_resting_heart_rate_7day"] == 55

    def test_migration_backfills_new_columns(self, temp_db):
        raw = {"calendarDate": "2026-09-12", "userFloorsAscendedGoal": 8, "lastSevenDaysAvgRestingHeartRate": 50}
        temp_db.execute(
            "INSERT INTO daily_summary (calendar_date, raw_json) VALUES (?, ?)",
            ("2026-09-12", json.dumps(raw)),
        )
        temp_db.commit()
        migrate_daily_summary_backfill(temp_db)
        row = self._row(temp_db, "2026-09-12")
        assert row["floors_ascended_goal"] == 8
        assert row["avg_resting_heart_rate_7day"] == 50


class TestFloorsTotals:
    """The floors endpoint returns only interval arrays — the totals the code
    read (floorsAscended etc.) never exist in that payload, so ascended and
    descended were NULL on every row."""

    _RECORD = {
        "startTimestampGMT": "2026-09-10T04:00:00.0",
        "floorsValueDescriptorDTOList": [
            {"index": 0, "key": "startTimeGMT"},
            {"index": 1, "key": "endTimeGMT"},
            {"index": 2, "key": "floorsAscended"},
            {"index": 3, "key": "floorsDescended"},
        ],
        "floorValuesArray": [
            ["2026-09-10T04:00:00.0", "2026-09-10T04:15:00.0", 3, 1],
            ["2026-09-10T04:15:00.0", "2026-09-10T04:30:00.0", 2, 0],
        ],
    }

    def _row(self, conn, day):
        return dict(conn.execute("SELECT * FROM floors WHERE calendar_date = ?", (day,)).fetchone())

    def test_totals_summed_from_value_array(self, temp_db):
        upsert_floors(temp_db, dict(self._RECORD), cal_date="2026-09-10")
        row = self._row(temp_db, "2026-09-10")
        assert row["ascended"] == 5
        assert row["descended"] == 1

    def test_explicit_totals_still_win(self, temp_db):
        rec = dict(self._RECORD, floorsAscended=7, floorsDescended=2)
        upsert_floors(temp_db, rec, cal_date="2026-09-11")
        row = self._row(temp_db, "2026-09-11")
        assert row["ascended"] == 7
        assert row["descended"] == 2

    def test_migration_backfills_from_raw_json(self, temp_db):
        temp_db.execute(
            "INSERT INTO floors (calendar_date, raw_json) VALUES (?, ?)",
            ("2026-09-12", json.dumps(self._RECORD)),
        )
        temp_db.commit()
        migrate_floors_totals(temp_db)
        row = self._row(temp_db, "2026-09-12")
        assert row["ascended"] == 5
        assert row["descended"] == 1


class TestHealthStatusKey:
    """health_status records carry a status key; the code read overallStatus,
    which never exists — 0 of 4,218 rows filled on a real DB. Old GraphQL
    error envelopes were also stored as rows."""

    def _row(self, conn, day):
        r = conn.execute("SELECT * FROM health_status WHERE calendar_date = ?", (day,)).fetchone()
        return dict(r) if r else None

    def test_status_key_captured(self, temp_db):
        upsert_health_status(
            temp_db, {"status": "IN_RANGE", "type": "SKIN_TEMP_F", "value": 0.5}, cal_date="2026-09-10"
        )
        assert self._row(temp_db, "2026-09-10")["overall_status"] == "IN_RANGE"

    def test_error_envelope_not_stored(self, temp_db):
        upsert_health_status(
            temp_db,
            {"message": "INTERNAL_ERROR", "extensions": {"classification": "INTERNAL_ERROR"}, "locations": []},
            cal_date="2026-09-11",
        )
        assert self._row(temp_db, "2026-09-11") is None

    def test_migration_backfills_and_cleans(self, temp_db):
        temp_db.execute(
            "INSERT INTO health_status (calendar_date, raw_json) VALUES (?, ?)",
            ("2026-09-12", json.dumps({"status": "OUT_OF_RANGE", "type": "HRV_STATUS"})),
        )
        temp_db.execute(
            "INSERT INTO health_status (calendar_date, raw_json) VALUES (?, ?)",
            ("2016-01-01", json.dumps({"message": "err", "extensions": {}, "locations": []})),
        )
        temp_db.commit()
        migrate_health_status(temp_db)
        assert self._row(temp_db, "2026-09-12")["overall_status"] == "OUT_OF_RANGE"
        assert self._row(temp_db, "2016-01-01") is None


class TestCaloriesConsumed:
    """The daily-summary path hardcoded consumed to NULL even when
    consumedKilocalories was present in the very record being stored."""

    def _row(self, conn, day):
        return dict(conn.execute("SELECT * FROM calories WHERE calendar_date = ?", (day,)).fetchone())

    def test_consumed_captured_from_daily_summary(self, temp_db):
        upsert_daily_summary(
            temp_db,
            {"calendarDate": "2026-09-10", "totalKilocalories": 2500, "consumedKilocalories": 1800},
        )
        assert self._row(temp_db, "2026-09-10")["consumed"] == 1800

    def test_nutrition_value_not_overwritten(self, temp_db):
        temp_db.execute(
            "INSERT INTO calories (calendar_date, consumed) VALUES (?, ?)",
            ("2026-09-11", 1500),
        )
        temp_db.commit()
        upsert_daily_summary(
            temp_db,
            {"calendarDate": "2026-09-11", "totalKilocalories": 2500, "consumedKilocalories": 1800},
        )
        assert self._row(temp_db, "2026-09-11")["consumed"] == 1500

    def test_migration_backfills_from_raw_json(self, temp_db):
        temp_db.execute(
            "INSERT INTO calories (calendar_date, total, raw_json) VALUES (?, ?, ?)",
            ("2026-09-12", 2400, json.dumps({"calendarDate": "2026-09-12", "consumedKilocalories": 2100})),
        )
        temp_db.commit()
        migrate_calories_consumed(temp_db)
        assert self._row(temp_db, "2026-09-12")["consumed"] == 2100


class TestRunningDynamicsListAliases:
    """List records carry ALL dynamics fields under avg* names
    (avgGroundContactTime, avgGroundContactBalance, ...), not just stride —
    a stride-only harvest leaves the other four NULL for users whose
    activities are never detail-fetched."""

    def test_all_dynamics_from_flat_list_record(self, temp_db):
        upsert_activity(
            temp_db,
            {
                "activityId": 4000,
                "avgGroundContactTime": 250.0,
                "avgGroundContactBalance": 49.8,
                "avgVerticalOscillation": 8.1,
                "avgVerticalRatio": 7.9,
                "avgStrideLength": 100.0,
            },
        )
        rd = _rd_row(temp_db, 4000)
        assert rd["avg_gct"] == 250.0
        assert rd["avg_gct_balance"] == 49.8
        assert rd["avg_vert_osc"] == 8.1
        assert rd["avg_vert_ratio"] == 7.9
        assert rd["avg_stride_len"] == 100.0

    def test_migration_backfills_all_five(self, temp_db):
        raw = {
            "activityId": 4001,
            "avgGroundContactTime": 240.0,
            "avgGroundContactBalance": 50.1,
            "avgVerticalOscillation": 8.5,
            "avgVerticalRatio": 8.0,
            "avgStrideLength": 95.0,
        }
        temp_db.execute(
            "INSERT INTO activity (activity_id, raw_json) VALUES (?, ?)",
            (4001, json.dumps(raw)),
        )
        temp_db.commit()
        migrate_running_dynamics_backfill(temp_db)
        rd = _rd_row(temp_db, 4001)
        assert rd["avg_gct"] == 240.0
        assert rd["avg_gct_balance"] == 50.1
        assert rd["avg_vert_osc"] == 8.5
        assert rd["avg_vert_ratio"] == 8.0
        assert rd["avg_stride_len"] == 95.0


class TestHrvAvgNotPollutedByHigh:
    """last_night_avg fell back to lastNight5MinHigh — a peak stored as an
    average, same unit-mismatch class as the max_stress bug."""

    def test_5min_high_not_stored_as_avg(self, temp_db):
        upsert_hrv(temp_db, {"calendarDate": "2026-09-10", "lastNight5MinHigh": 88})
        row = dict(temp_db.execute("SELECT * FROM hrv WHERE calendar_date = ?", ("2026-09-10",)).fetchone())
        assert row["last_night_avg"] is None
        assert row["last_night_5min_high"] == 88


class TestIntensityMinutesZeros:
    """0 moderate/vigorous minutes is a real value — the or-chains dropped it."""

    def test_zero_values_survive(self, temp_db):
        upsert_intensity_minutes(
            temp_db,
            {"moderateIntensityMinutes": 0, "vigorousIntensityMinutes": 0, "intensityMinutesGoal": 150},
            cal_date="2026-09-10",
        )
        row = dict(
            temp_db.execute("SELECT * FROM intensity_minutes WHERE calendar_date = ?", ("2026-09-10",)).fetchone()
        )
        assert row["moderate"] == 0
        assert row["vigorous"] == 0
        assert row["goal"] == 150

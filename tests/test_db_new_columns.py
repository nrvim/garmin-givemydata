"""
Tests for new columns added to garmin_mcp/db.py — both schema presence and
correct extraction from Garmin API JSON payloads.

Covers:
  - activity_splits: swim fields + performance fields (NP, respiration, GPS, power phase)
  - sleep:           body_battery_change, resting_heart_rate, skin temp deviation
  - heart_rate:      last_7day_avg_resting
  - spo2:            events_below_threshold, duration_below_threshold_secs
  - respiration:     avg_sleep
  - hydration:       sweat_loss_ml, activity_intake_ml
  - weight:          metabolic_age, physique_rating
  - endurance_score: feedback_phrase, contributors
  - hill_score:      vo2_max, vo2_max_precise, feedback_phrase_id
  - gear:            distance_used_meters, duration_used_seconds, days_used
  - daily_events:    activity_type, activity_sub_type, timestamps, duration, device_id
  - wellness_activity: activity_name, wellness_activity_type, timestamps
  - health_snapshot: activity_name, wellness_activity_type, timestamps
  - migrations:      _add_columns / _backfill_from_raw on pre-existing tables
"""

import json
import sqlite3

import pytest

from garmin_mcp.db import (
    _add_columns,
    _backfill_from_raw,
    init_db,
    migrate_activity_splits_v2,
    migrate_activity_table,
    migrate_endurance_score_table,
    migrate_fitness_age_table,
    migrate_gear_table,
    migrate_gear_table_v2,
    migrate_heart_rate_table,
    migrate_hill_score_table,
    migrate_hollow_tables,
    migrate_sleep_table,
    migrate_sleep_table_v2,
    migrate_spo2_table,
    migrate_weight_table_v3,
    upsert_activity,
    upsert_activity_splits,
    upsert_daily_events,
    upsert_endurance_score,
    upsert_gear,
    upsert_health_snapshot,
    upsert_heart_rate,
    upsert_hill_score,
    upsert_hydration,
    upsert_respiration,
    upsert_sleep,
    upsert_spo2,
    upsert_weight,
    upsert_wellness_activity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cols(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _row(conn, table: str, pk_col: str, pk_val) -> dict:
    row = conn.execute(f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk_val,)).fetchone()
    return dict(row) if row else {}


def _splits(conn, activity_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM activity_splits WHERE activity_id = ? ORDER BY split_number",
            (activity_id,),
        )
    ]


# ---------------------------------------------------------------------------
# Schema: new columns must exist after init_db
# ---------------------------------------------------------------------------


class TestSchemaNewColumns:
    def test_activity_splits_swim_columns(self, temp_db):
        cols = _cols(temp_db, "activity_splits")
        for col in ("avg_swim_cadence", "avg_swolf", "total_strokes", "swim_stroke", "num_active_lengths"):
            assert col in cols, f"Missing: {col}"

    def test_activity_splits_performance_columns(self, temp_db):
        cols = _cols(temp_db, "activity_splits")
        for col in (
            "normalized_power",
            "avg_respiration_rate",
            "max_respiration_rate",
            "start_latitude",
            "start_longitude",
            "end_latitude",
            "end_longitude",
            "start_time_gmt",
            "calories",
            "left_pedal_smoothness",
            "right_pedal_smoothness",
            "left_torque_effectiveness",
            "right_torque_effectiveness",
            "surface_unpaved_pct",
        ):
            assert col in cols, f"Missing: {col}"

    def test_sleep_new_columns(self, temp_db):
        cols = _cols(temp_db, "sleep")
        for col in (
            "body_battery_change",
            "resting_heart_rate",
            "avg_skin_temp_deviation_c",
            "avg_skin_temp_deviation_f",
        ):
            assert col in cols, f"Missing: {col}"

    def test_heart_rate_new_column(self, temp_db):
        assert "last_7day_avg_resting" in _cols(temp_db, "heart_rate")

    def test_spo2_new_columns(self, temp_db):
        cols = _cols(temp_db, "spo2")
        assert "events_below_threshold" in cols
        assert "duration_below_threshold_secs" in cols

    def test_respiration_new_column(self, temp_db):
        assert "avg_sleep" in _cols(temp_db, "respiration")

    def test_hydration_new_columns(self, temp_db):
        cols = _cols(temp_db, "hydration")
        assert "sweat_loss_ml" in cols
        assert "activity_intake_ml" in cols

    def test_weight_new_columns(self, temp_db):
        cols = _cols(temp_db, "weight")
        assert "metabolic_age" in cols
        assert "physique_rating" in cols

    def test_endurance_score_new_columns(self, temp_db):
        cols = _cols(temp_db, "endurance_score")
        assert "feedback_phrase" in cols
        assert "contributors" in cols

    def test_hill_score_new_columns(self, temp_db):
        cols = _cols(temp_db, "hill_score")
        assert "vo2_max" in cols
        assert "vo2_max_precise" in cols
        assert "feedback_phrase_id" in cols

    def test_gear_new_columns(self, temp_db):
        cols = _cols(temp_db, "gear")
        assert "distance_used_meters" in cols
        assert "duration_used_seconds" in cols
        assert "days_used" in cols

    def test_daily_events_columns(self, temp_db):
        cols = _cols(temp_db, "daily_events")
        for col in (
            "activity_type",
            "activity_sub_type",
            "start_timestamp_local",
            "end_timestamp_local",
            "duration_seconds",
            "device_id",
        ):
            assert col in cols, f"Missing: {col}"

    def test_wellness_activity_columns(self, temp_db):
        cols = _cols(temp_db, "wellness_activity")
        for col in ("activity_name", "wellness_activity_type", "start_timestamp_local", "end_timestamp_local"):
            assert col in cols, f"Missing: {col}"

    def test_health_snapshot_columns(self, temp_db):
        cols = _cols(temp_db, "health_snapshot")
        for col in ("activity_name", "wellness_activity_type", "start_timestamp_local", "end_timestamp_local"):
            assert col in cols, f"Missing: {col}"


# ---------------------------------------------------------------------------
# activity_splits — swim fields
# ---------------------------------------------------------------------------


class TestActivitySplitsSwim:
    _POOL_LAP = {
        "distance": 500,
        "duration": 841.929,
        "averageHR": 125,
        "maxHR": 148,
        "averageSwimCadence": 21,
        "averageSWOLF": 100,
        "totalNumberOfStrokes": 253,
        "swimStroke": "FREESTYLE",
        "numberOfActiveLengths": 10,
        "averageSpeed": 0.666,
    }

    def test_swim_fields_stored(self, temp_db):
        upsert_activity_splits(temp_db, 111, [self._POOL_LAP])
        row = _splits(temp_db, 111)[0]
        assert row["avg_swim_cadence"] == 21
        assert row["avg_swolf"] == 100
        assert row["total_strokes"] == 253
        assert row["swim_stroke"] == "FREESTYLE"
        assert row["num_active_lengths"] == 10

    def test_zero_swim_values_stored_as_null(self, temp_db):
        rest_lap = dict(
            self._POOL_LAP,
            averageSwimCadence=0,
            averageSWOLF=0,
            totalNumberOfStrokes=0,
            swimStroke=None,
            numberOfActiveLengths=0,
            distance=0,
        )
        upsert_activity_splits(temp_db, 222, [rest_lap])
        row = _splits(temp_db, 222)[0]
        assert row["avg_swim_cadence"] is None
        assert row["avg_swolf"] is None
        assert row["total_strokes"] is None
        assert row["num_active_lengths"] is None

    def test_non_swim_lap_leaves_swim_fields_null(self, temp_db):
        run_lap = {
            "distance": 1000,
            "duration": 300,
            "averageHR": 155,
            "averageRunCadence": 170,
            "elevationGain": 10,
        }
        upsert_activity_splits(temp_db, 333, [run_lap])
        row = _splits(temp_db, 333)[0]
        assert row["avg_swim_cadence"] is None
        assert row["swim_stroke"] is None
        assert row["avg_cadence"] == 170


# ---------------------------------------------------------------------------
# activity_splits — performance fields
# ---------------------------------------------------------------------------


class TestActivitySplitsPerformance:
    _CYCLING_LAP = {
        "distance": 5000,
        "duration": 600,
        "averageHR": 155,
        "maxHR": 170,
        "averageBikeCadence": 90,
        "normalizedPower": 240,
        "avgRespirationRate": 32.5,
        "maxRespirationRate": 40.1,
        "startLatitude": 49.468,
        "startLongitude": 11.077,
        "endLatitude": 49.510,
        "endLongitude": 11.120,
        "startTimeGMT": "2026-05-10T06:00:00.0",
        "calories": 120,
        "leftPedalSmoothness": 76.5,
        "rightPedalSmoothness": 74.2,
        "leftTorqueEffectiveness": 91.0,
        "rightTorqueEffectiveness": 89.5,
        "surfaceTypeUnpavedPercentage": 45.0,
    }

    def test_cycling_performance_fields_stored(self, temp_db):
        upsert_activity_splits(temp_db, 444, [self._CYCLING_LAP])
        row = _splits(temp_db, 444)[0]
        assert row["normalized_power"] == 240
        assert row["avg_respiration_rate"] == pytest.approx(32.5, abs=0.1)
        assert row["max_respiration_rate"] == pytest.approx(40.1, abs=0.1)
        assert row["start_latitude"] == pytest.approx(49.468, abs=0.001)
        assert row["start_longitude"] == pytest.approx(11.077, abs=0.001)
        assert row["end_latitude"] == pytest.approx(49.510, abs=0.001)
        assert row["end_longitude"] == pytest.approx(11.120, abs=0.001)
        assert row["start_time_gmt"] == "2026-05-10T06:00:00.0"
        assert row["calories"] == 120
        assert row["left_pedal_smoothness"] == pytest.approx(76.5, abs=0.1)
        assert row["right_pedal_smoothness"] == pytest.approx(74.2, abs=0.1)
        assert row["left_torque_effectiveness"] == pytest.approx(91.0, abs=0.1)
        assert row["right_torque_effectiveness"] == pytest.approx(89.5, abs=0.1)
        assert row["surface_unpaved_pct"] == pytest.approx(45.0, abs=0.1)

    def test_missing_performance_fields_are_null(self, temp_db):
        bare_lap = {"distance": 1000, "duration": 300, "averageHR": 140}
        upsert_activity_splits(temp_db, 555, [bare_lap])
        row = _splits(temp_db, 555)[0]
        assert row["normalized_power"] is None
        assert row["avg_respiration_rate"] is None
        assert row["start_latitude"] is None
        assert row["calories"] is None
        assert row["surface_unpaved_pct"] is None

    def test_multiple_laps_all_get_performance_data(self, temp_db):
        laps = [
            dict(self._CYCLING_LAP, normalizedPower=200, calories=80),
            dict(self._CYCLING_LAP, normalizedPower=220, calories=90),
            dict(self._CYCLING_LAP, normalizedPower=250, calories=110),
        ]
        upsert_activity_splits(temp_db, 666, laps)
        rows = _splits(temp_db, 666)
        assert len(rows) == 3
        assert [r["normalized_power"] for r in rows] == [200, 220, 250]
        assert [r["calories"] for r in rows] == [80, 90, 110]


# ---------------------------------------------------------------------------
# sleep
# ---------------------------------------------------------------------------


class TestSleepNewColumns:
    _RECORD = {
        "dailySleepDTO": {
            "calendarDate": "2026-05-10",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
        },
        "bodyBatteryChange": 42,
        "restingHeartRate": 52,
        "avgSkinTempDeviationC": -0.3,
        "avgSkinTempDeviationF": -0.54,
    }

    def test_new_sleep_fields_stored(self, temp_db):
        upsert_sleep(temp_db, self._RECORD)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["body_battery_change"] == 42
        assert row["resting_heart_rate"] == 52
        assert row["avg_skin_temp_deviation_c"] == pytest.approx(-0.3, abs=0.01)
        assert row["avg_skin_temp_deviation_f"] == pytest.approx(-0.54, abs=0.01)

    def test_missing_new_fields_stored_as_null(self, temp_db):
        record = {
            "dailySleepDTO": {
                "calendarDate": "2026-05-09",
                "sleepTimeSeconds": 25200,
            }
        }
        upsert_sleep(temp_db, record)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-09")
        assert row["body_battery_change"] is None
        assert row["resting_heart_rate"] is None
        assert row["avg_skin_temp_deviation_c"] is None

    def test_existing_sleep_fields_still_work(self, temp_db):
        upsert_sleep(temp_db, self._RECORD)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["sleep_time_seconds"] == 27000
        assert row["deep_sleep_seconds"] == 5400

    def test_rest_then_gql_preserves_bb_fields(self, temp_db):
        """REST record (has BB/HR) written first, then GQL overwrites — values must survive."""
        rest_record = {
            "dailySleepDTO": {"calendarDate": "2026-05-10", "sleepTimeSeconds": 27000},
            "bodyBatteryChange": 42,
            "restingHeartRate": 52,
            "avgSkinTempDeviationC": -0.3,
            "avgSkinTempDeviationF": -0.54,
        }
        gql_record = {
            "dailySleepDTO": {"calendarDate": "2026-05-10", "sleepTimeSeconds": 27000},
            # GQL endpoints do not carry these fields
        }
        upsert_sleep(temp_db, rest_record)
        upsert_sleep(temp_db, gql_record)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["body_battery_change"] == 42
        assert row["resting_heart_rate"] == 52
        assert row["avg_skin_temp_deviation_c"] == pytest.approx(-0.3, abs=0.01)

    def test_gql_then_rest_populates_bb_fields(self, temp_db):
        """GQL record (no BB/HR) written first, then REST record fills in values."""
        gql_record = {
            "dailySleepDTO": {"calendarDate": "2026-05-10", "sleepTimeSeconds": 27000},
        }
        rest_record = {
            "dailySleepDTO": {"calendarDate": "2026-05-10", "sleepTimeSeconds": 27000},
            "bodyBatteryChange": 38,
            "restingHeartRate": 55,
            "avgSkinTempDeviationC": 0.1,
            "avgSkinTempDeviationF": 0.18,
        }
        upsert_sleep(temp_db, gql_record)
        upsert_sleep(temp_db, rest_record)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["body_battery_change"] == 38
        assert row["resting_heart_rate"] == 55
        assert row["avg_skin_temp_deviation_c"] == pytest.approx(0.1, abs=0.01)

    def test_zero_skin_temp_stored_not_null(self, temp_db):
        """avgSkinTempDeviationC == 0 is a valid measurement, must not be coerced to NULL."""
        record = {
            "dailySleepDTO": {"calendarDate": "2026-05-10", "sleepTimeSeconds": 27000},
            "avgSkinTempDeviationC": 0,
            "avgSkinTempDeviationF": 0,
        }
        upsert_sleep(temp_db, record)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["avg_skin_temp_deviation_c"] == 0.0
        assert row["avg_skin_temp_deviation_f"] == 0.0


# ---------------------------------------------------------------------------
# heart_rate
# ---------------------------------------------------------------------------


class TestHeartRateNewColumn:
    def test_7day_avg_stored(self, temp_db):
        upsert_heart_rate(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "restingHeartRate": 54,
                "minHeartRate": 48,
                "maxHeartRate": 168,
                "lastSevenDaysAvgRestingHeartRate": 56.3,
            },
        )
        row = _row(temp_db, "heart_rate", "calendar_date", "2026-05-10")
        assert row["last_7day_avg_resting"] == pytest.approx(56.3, abs=0.1)

    def test_missing_7day_avg_is_null(self, temp_db):
        upsert_heart_rate(
            temp_db,
            {
                "calendarDate": "2026-05-09",
                "restingHeartRate": 55,
            },
        )
        row = _row(temp_db, "heart_rate", "calendar_date", "2026-05-09")
        assert row["last_7day_avg_resting"] is None
        assert row["resting_hr"] == 55

    def test_rest_then_gql_preserves_7day_avg(self, temp_db):
        """REST record sets 7-day avg; GQL detail overwrites (no such field) — value must survive."""
        upsert_heart_rate(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "restingHeartRate": 58,
                "lastSevenDaysAvgRestingHeartRate": 59,
            },
        )
        # GQL heart_rate_detail record has no lastSevenDaysAvgRestingHeartRate
        upsert_heart_rate(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "restingHeartRate": 58,
                "maxHeartRate": 160,
            },
        )
        row = _row(temp_db, "heart_rate", "calendar_date", "2026-05-10")
        assert row["last_7day_avg_resting"] == pytest.approx(59, abs=0.1)
        assert row["max_hr"] == 160

    def test_gql_then_rest_populates_7day_avg(self, temp_db):
        """GQL writes first (no 7-day field), then REST fills it in."""
        upsert_heart_rate(temp_db, {"calendarDate": "2026-05-10", "restingHeartRate": 58})
        upsert_heart_rate(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "restingHeartRate": 58,
                "lastSevenDaysAvgRestingHeartRate": 59,
            },
        )
        row = _row(temp_db, "heart_rate", "calendar_date", "2026-05-10")
        assert row["last_7day_avg_resting"] == pytest.approx(59, abs=0.1)


# ---------------------------------------------------------------------------
# spo2
# ---------------------------------------------------------------------------


class TestSpo2NewColumns:
    def test_spo2_events_stored(self, temp_db):
        upsert_spo2(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "averageSpO2": 96.0,
                "lowestSpO2": 88.0,
                "numberOfEventsBelowThreshold": 3,
                "durationOfEventsBelowThreshold": 420.0,
            },
        )
        row = _row(temp_db, "spo2", "calendar_date", "2026-05-10")
        assert row["events_below_threshold"] == 3
        assert row["duration_below_threshold_secs"] == pytest.approx(420.0)

    def test_spo2_no_events_stored_as_null(self, temp_db):
        upsert_spo2(temp_db, {"calendarDate": "2026-05-09", "averageSpO2": 98.0})
        row = _row(temp_db, "spo2", "calendar_date", "2026-05-09")
        assert row["events_below_threshold"] is None
        assert row["duration_below_threshold_secs"] is None


# ---------------------------------------------------------------------------
# respiration
# ---------------------------------------------------------------------------


class TestRespirationNewColumn:
    def test_avg_sleep_respiration_stored(self, temp_db):
        upsert_respiration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "avgWakingRespirationValue": 16.2,
                "avgSleepRespirationValue": 14.8,
                "lowestRespirationValue": 13.0,
                "highestRespirationValue": 22.0,
            },
        )
        row = _row(temp_db, "respiration", "calendar_date", "2026-05-10")
        assert row["avg_waking"] == pytest.approx(16.2, abs=0.1)
        assert row["avg_sleep"] == pytest.approx(14.8, abs=0.1)

    def test_missing_sleep_respiration_is_null(self, temp_db):
        upsert_respiration(
            temp_db,
            {
                "calendarDate": "2026-05-09",
                "avgWakingRespirationValue": 15.0,
            },
        )
        row = _row(temp_db, "respiration", "calendar_date", "2026-05-09")
        assert row["avg_sleep"] is None

    def test_sleep_respiration_preserved_on_overwrite(self, temp_db):
        """First write has sleep respiration; second write lacks it — value must survive."""
        upsert_respiration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "avgWakingRespirationValue": 16.0,
                "avgSleepRespirationValue": 14.5,
            },
        )
        upsert_respiration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "avgWakingRespirationValue": 16.0,
                # no avgSleepRespirationValue (e.g. same-day sync before sleep data is ready)
            },
        )
        row = _row(temp_db, "respiration", "calendar_date", "2026-05-10")
        assert row["avg_sleep"] == pytest.approx(14.5, abs=0.1)

    def test_sleep_respiration_filled_on_later_write(self, temp_db):
        """First write has no sleep value; later write fills it in."""
        upsert_respiration(temp_db, {"calendarDate": "2026-05-10", "avgWakingRespirationValue": 16.0})
        upsert_respiration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "avgWakingRespirationValue": 16.0,
                "avgSleepRespirationValue": 14.5,
            },
        )
        row = _row(temp_db, "respiration", "calendar_date", "2026-05-10")
        assert row["avg_sleep"] == pytest.approx(14.5, abs=0.1)


# ---------------------------------------------------------------------------
# hydration
# ---------------------------------------------------------------------------


class TestHydrationNewColumns:
    def test_sweat_loss_and_activity_intake_stored(self, temp_db):
        upsert_hydration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "goalInML": 2500,
                "valueInML": 2100,
                "sweatLossInML": 620,
                "activityIntakeInML": 400,
            },
        )
        row = _row(temp_db, "hydration", "calendar_date", "2026-05-10")
        assert row["sweat_loss_ml"] == pytest.approx(620)
        assert row["activity_intake_ml"] == pytest.approx(400)

    def test_missing_sweat_loss_is_null(self, temp_db):
        upsert_hydration(temp_db, {"calendarDate": "2026-05-09", "goalInML": 2000, "valueInML": 1800})
        row = _row(temp_db, "hydration", "calendar_date", "2026-05-09")
        assert row["sweat_loss_ml"] is None
        assert row["activity_intake_ml"] is None

    def test_sweat_loss_preserved_on_overwrite(self, temp_db):
        """First write has sweat/activity data; second write lacks them — values must survive."""
        upsert_hydration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "goalInML": 2500,
                "valueInML": 2100,
                "sweatLossInML": 1200,
                "activityIntakeInML": 350,
            },
        )
        upsert_hydration(temp_db, {"calendarDate": "2026-05-10", "goalInML": 2500, "valueInML": 2100})
        row = _row(temp_db, "hydration", "calendar_date", "2026-05-10")
        assert row["sweat_loss_ml"] == pytest.approx(1200)
        assert row["activity_intake_ml"] == pytest.approx(350)

    def test_zero_activity_intake_stored_not_null(self, temp_db):
        """activityIntakeInML == 0 is valid (no activity fluids), must not become NULL."""
        upsert_hydration(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "goalInML": 2500,
                "valueInML": 0,
                "sweatLossInML": 500,
                "activityIntakeInML": 0,
            },
        )
        row = _row(temp_db, "hydration", "calendar_date", "2026-05-10")
        assert row["activity_intake_ml"] == 0.0


# ---------------------------------------------------------------------------
# weight
# ---------------------------------------------------------------------------


class TestWeightNewColumns:
    def test_metabolic_age_and_physique_rating_stored(self, temp_db):
        upsert_weight(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "date": 1746835200000,
                "weight": 77000,
                "bmi": 25.7,
                "metabolicAge": 38.0,
                "physiqueRating": 4,
            },
        )
        row = _row(temp_db, "weight", "calendar_date", "2026-05-10")
        assert row["metabolic_age"] == pytest.approx(38.0)
        assert row["physique_rating"] == 4

    def test_missing_body_comp_fields_are_null(self, temp_db):
        upsert_weight(
            temp_db,
            {
                "calendarDate": "2026-05-09",
                "date": 1746748800000,
                "weight": 77500,
            },
        )
        row = _row(temp_db, "weight", "calendar_date", "2026-05-09")
        assert row["metabolic_age"] is None
        assert row["physique_rating"] is None
        assert row["weight"] == 77500


# ---------------------------------------------------------------------------
# endurance_score
# ---------------------------------------------------------------------------


class TestEnduranceScoreNewColumns:
    _CONTRIBUTORS = [
        {"activityTypeId": None, "contribution": 83.93, "group": 0},
        {"activityTypeId": None, "contribution": 16.07, "group": 6},
    ]

    def test_feedback_phrase_and_contributors_stored(self, temp_db):
        upsert_endurance_score(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "overallScore": 5200,
                "classification": "PRODUCTIVE",
                "vo2Max": 46.0,
                "feedbackPhrase": "ENDURANCE_SCORE_IMPROVING",
                "contributors": self._CONTRIBUTORS,
            },
        )
        row = _row(temp_db, "endurance_score", "calendar_date", "2026-05-10")
        assert row["feedback_phrase"] == "ENDURANCE_SCORE_IMPROVING"
        parsed = json.loads(row["contributors"])
        assert len(parsed) == 2
        assert parsed[0]["contribution"] == pytest.approx(83.93)

    def test_null_contributors_stored_as_null(self, temp_db):
        upsert_endurance_score(
            temp_db,
            {
                "calendarDate": "2026-05-09",
                "overallScore": 5100,
            },
        )
        row = _row(temp_db, "endurance_score", "calendar_date", "2026-05-09")
        assert row["feedback_phrase"] is None
        assert row["contributors"] is None


# ---------------------------------------------------------------------------
# hill_score
# ---------------------------------------------------------------------------


class TestHillScoreNewColumns:
    def test_vo2max_and_feedback_stored(self, temp_db):
        upsert_hill_score(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "overallScore": 58,
                "enduranceScore": 62,
                "strengthScore": 54,
                "vo2Max": 46.0,
                "vo2MaxPreciseValue": 46.3,
                "hillScoreFeedbackPhraseId": "HILL_SCORE_IMPROVING",
            },
        )
        row = _row(temp_db, "hill_score", "calendar_date", "2026-05-10")
        assert row["vo2_max"] == pytest.approx(46.0)
        assert row["vo2_max_precise"] == pytest.approx(46.3)
        assert row["feedback_phrase_id"] == "HILL_SCORE_IMPROVING"

    def test_existing_hill_fields_unaffected(self, temp_db):
        upsert_hill_score(
            temp_db,
            {
                "calendarDate": "2026-05-09",
                "overallScore": 55,
                "enduranceScore": 58,
                "strengthScore": 52,
                "vo2Max": 45.5,
            },
        )
        row = _row(temp_db, "hill_score", "calendar_date", "2026-05-09")
        assert row["overall_score"] == 55
        assert row["endurance_score"] == 58
        assert row["vo2_max"] == pytest.approx(45.5)
        assert row["feedback_phrase_id"] is None


# ---------------------------------------------------------------------------
# gear
# ---------------------------------------------------------------------------


class TestGearNewColumns:
    def test_usage_stats_stored(self, temp_db):
        upsert_gear(
            temp_db,
            {
                "uuid": "abc-123",
                "gearTypeName": "shoes",
                "displayName": "Canyon CFSLX",
                "distanceUsedMeters": 467282.78,
                "durationUsedSeconds": 85673,
                "daysUsed": 13,
                "dateBegin": "2024-01-01",
            },
        )
        row = _row(temp_db, "gear", "gear_id", "abc-123")
        assert row["distance_used_meters"] == pytest.approx(467282.78, rel=1e-4)
        assert row["duration_used_seconds"] == 85673
        assert row["days_used"] == 13

    def test_missing_usage_stats_are_null(self, temp_db):
        upsert_gear(temp_db, {"uuid": "xyz-999", "gearTypeName": "shoes"})
        row = _row(temp_db, "gear", "gear_id", "xyz-999")
        assert row["distance_used_meters"] is None
        assert row["duration_used_seconds"] is None
        assert row["days_used"] is None


# ---------------------------------------------------------------------------
# Hollow tables: daily_events, wellness_activity, health_snapshot
# ---------------------------------------------------------------------------


class TestDailyEvents:
    def test_scalar_fields_extracted(self, temp_db):
        upsert_daily_events(
            temp_db,
            {
                "activityType": "RUNNING",
                "activitySubType": "TRAIL_RUNNING",
                "startTimestampLocal": "2026-05-10T07:00:00",
                "endTimestampLocal": "2026-05-10T08:00:00",
                "duration": 3600.0,
                "deviceId": "device-42",
            },
            cal_date="2026-05-10",
        )
        row = _row(temp_db, "daily_events", "calendar_date", "2026-05-10")
        assert row["activity_type"] == "RUNNING"
        assert row["activity_sub_type"] == "TRAIL_RUNNING"
        assert row["start_timestamp_local"] == "2026-05-10T07:00:00"
        assert row["end_timestamp_local"] == "2026-05-10T08:00:00"
        assert row["duration_seconds"] == pytest.approx(3600.0)
        assert row["device_id"] == "device-42"

    def test_raw_json_still_stored(self, temp_db):
        record = {"activityType": "CYCLING", "duration": 7200.0}
        upsert_daily_events(temp_db, record, cal_date="2026-05-09")
        row = _row(temp_db, "daily_events", "calendar_date", "2026-05-09")
        assert row["raw_json"] is not None
        assert json.loads(row["raw_json"])["activityType"] == "CYCLING"

    def test_list_of_events_uses_first_typed_event(self, temp_db):
        events = [
            {"duration": 60.0},
            {"activityType": "SWIMMING", "startTimestampLocal": "2026-05-08T09:00:00", "duration": 2700.0},
        ]
        upsert_daily_events(temp_db, events, cal_date="2026-05-08")
        row = _row(temp_db, "daily_events", "calendar_date", "2026-05-08")
        assert row["activity_type"] == "SWIMMING"
        assert row["duration_seconds"] == pytest.approx(2700.0)


class TestWellnessActivity:
    def test_scalar_fields_extracted(self, temp_db):
        upsert_wellness_activity(
            temp_db,
            {
                "activityName": "Morning Walk",
                "wellnessActivityType": "WALKING",
                "startTimestampLocal": "2026-05-10T06:30:00",
                "endTimestampLocal": "2026-05-10T07:00:00",
            },
            cal_date="2026-05-10",
        )
        row = _row(temp_db, "wellness_activity", "calendar_date", "2026-05-10")
        assert row["activity_name"] == "Morning Walk"
        assert row["wellness_activity_type"] == "WALKING"
        assert row["start_timestamp_local"] == "2026-05-10T06:30:00"
        assert row["end_timestamp_local"] == "2026-05-10T07:00:00"

    def test_raw_json_preserved(self, temp_db):
        record = {"activityName": "Yoga", "wellnessActivityType": "YOGA"}
        upsert_wellness_activity(temp_db, record, cal_date="2026-05-09")
        row = _row(temp_db, "wellness_activity", "calendar_date", "2026-05-09")
        assert json.loads(row["raw_json"])["activityName"] == "Yoga"


class TestHealthSnapshot:
    def test_scalar_fields_extracted(self, temp_db):
        upsert_health_snapshot(
            temp_db,
            {
                "calendarDate": "2026-05-10",
                "activityName": "Health Snapshot",
                "wellnessActivityType": "HEALTH_SNAPSHOT",
                "startTimestampLocal": "2026-05-10T08:00:00",
                "endTimestampLocal": "2026-05-10T08:02:00",
            },
        )
        row = _row(temp_db, "health_snapshot", "calendar_date", "2026-05-10")
        assert row["activity_name"] == "Health Snapshot"
        assert row["wellness_activity_type"] == "HEALTH_SNAPSHOT"

    def test_missing_fields_are_null(self, temp_db):
        upsert_health_snapshot(temp_db, {"calendarDate": "2026-05-09"})
        row = _row(temp_db, "health_snapshot", "calendar_date", "2026-05-09")
        assert row["activity_name"] is None
        assert row["start_timestamp_local"] is None


# ---------------------------------------------------------------------------
# Migration: _add_columns / _backfill_from_raw
# ---------------------------------------------------------------------------


class TestAddColumns:
    def test_adds_missing_column(self, temp_db):
        _add_columns(temp_db, "sleep", [("test_col_xyzzy", "REAL")])
        assert "test_col_xyzzy" in _cols(temp_db, "sleep")

    def test_skips_existing_column(self, temp_db):
        # Running twice must not raise
        _add_columns(temp_db, "sleep", [("resting_heart_rate", "INTEGER")])
        assert "resting_heart_rate" in _cols(temp_db, "sleep")

    def test_returns_only_added_columns(self, temp_db):
        added = _add_columns(
            temp_db,
            "sleep",
            [
                ("resting_heart_rate", "INTEGER"),  # already exists
                ("test_brand_new_col", "TEXT"),  # new
            ],
        )
        assert added == ["test_brand_new_col"]


class TestBackfillFromRaw:
    def _make_db_with_old_schema(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE test_table (
                id TEXT PRIMARY KEY,
                raw_json TEXT
            )
        """)
        conn.execute(
            "INSERT INTO test_table VALUES (?, ?)",
            ("row1", json.dumps({"myField": 42.5, "otherField": "hello"})),
        )
        conn.execute(
            "INSERT INTO test_table VALUES (?, ?)",
            ("row2", json.dumps({"myField": 99.0})),
        )
        conn.commit()
        return conn

    def test_backfills_new_column_from_raw_json(self):
        conn = self._make_db_with_old_schema()
        conn.execute("ALTER TABLE test_table ADD COLUMN my_field REAL")
        _backfill_from_raw(conn, "test_table", ["id"], ["my_field"], {"my_field": "myField"})
        rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM test_table")}
        assert rows["row1"]["my_field"] == pytest.approx(42.5)
        assert rows["row2"]["my_field"] == pytest.approx(99.0)
        conn.close()

    def test_does_not_overwrite_existing_non_null_value(self):
        conn = self._make_db_with_old_schema()
        conn.execute("ALTER TABLE test_table ADD COLUMN my_field REAL")
        conn.execute("UPDATE test_table SET my_field = 1.0 WHERE id = 'row1'")
        _backfill_from_raw(conn, "test_table", ["id"], ["my_field"], {"my_field": "myField"})
        row = dict(conn.execute("SELECT my_field FROM test_table WHERE id = 'row1'").fetchone())
        assert row["my_field"] == pytest.approx(1.0)  # not overwritten with 42.5
        conn.close()

    def test_skips_unparseable_raw_json(self):
        conn = self._make_db_with_old_schema()
        conn.execute("INSERT INTO test_table VALUES (?, ?)", ("bad_row", "not-json"))
        conn.execute("ALTER TABLE test_table ADD COLUMN my_field REAL")
        _backfill_from_raw(conn, "test_table", ["id"], ["my_field"], {"my_field": "myField"})
        row = dict(conn.execute("SELECT my_field FROM test_table WHERE id = 'bad_row'").fetchone())
        assert row["my_field"] is None
        conn.close()

    def test_noop_when_added_list_empty(self):
        conn = self._make_db_with_old_schema()
        conn.execute("ALTER TABLE test_table ADD COLUMN my_field REAL")
        _backfill_from_raw(conn, "test_table", ["id"], [], {"my_field": "myField"})
        row = dict(conn.execute("SELECT my_field FROM test_table WHERE id = 'row1'").fetchone())
        assert row["my_field"] is None  # no backfill ran
        conn.close()


class TestMigrationFunctions:
    """Each migrate_* function must be idempotent and backfill correctly."""

    def _old_db(self, ddl: str) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(ddl)
        conn.commit()
        return conn

    def test_migrate_sleep_adds_and_backfills(self):
        conn = self._old_db("""
            CREATE TABLE sleep (
                calendar_date TEXT PRIMARY KEY,
                sleep_time_seconds INTEGER,
                raw_json TEXT
            );
            INSERT INTO sleep VALUES (
                '2026-05-10', 27000,
                '{"bodyBatteryChange": 40, "restingHeartRate": 53,
                  "avgSkinTempDeviationC": -0.2, "avgSkinTempDeviationF": -0.36}'
            );
        """)
        migrate_sleep_table(conn)
        row = dict(conn.execute("SELECT * FROM sleep WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["body_battery_change"] == 40
        assert row["resting_heart_rate"] == 53
        assert row["avg_skin_temp_deviation_c"] == pytest.approx(-0.2, abs=0.01)
        conn.close()

    def test_migrate_sleep_is_idempotent(self, temp_db):
        migrate_sleep_table(temp_db)  # second call — already has columns
        assert "resting_heart_rate" in _cols(temp_db, "sleep")

    def test_migrate_heart_rate_adds_and_backfills(self):
        conn = self._old_db("""
            CREATE TABLE heart_rate (
                calendar_date TEXT PRIMARY KEY,
                resting_hr INTEGER,
                raw_json TEXT
            );
            INSERT INTO heart_rate VALUES (
                '2026-05-10', 54,
                '{"lastSevenDaysAvgRestingHeartRate": 57.0}'
            );
        """)
        migrate_heart_rate_table(conn)
        row = dict(conn.execute("SELECT * FROM heart_rate WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["last_7day_avg_resting"] == pytest.approx(57.0)
        conn.close()

    def test_migrate_hill_score_adds_and_backfills(self):
        conn = self._old_db("""
            CREATE TABLE hill_score (
                calendar_date TEXT PRIMARY KEY,
                overall_score INTEGER,
                raw_json TEXT
            );
            INSERT INTO hill_score VALUES (
                '2026-05-10', 58,
                '{"vo2Max": 46.0, "vo2MaxPreciseValue": 46.3,
                  "hillScoreFeedbackPhraseId": "IMPROVING"}'
            );
        """)
        migrate_hill_score_table(conn)
        row = dict(conn.execute("SELECT * FROM hill_score WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["vo2_max"] == pytest.approx(46.0)
        assert row["vo2_max_precise"] == pytest.approx(46.3)
        assert row["feedback_phrase_id"] == "IMPROVING"
        conn.close()

    def test_migrate_gear_adds_and_backfills(self):
        conn = self._old_db("""
            CREATE TABLE gear (
                gear_id TEXT PRIMARY KEY,
                display_name TEXT,
                raw_json TEXT
            );
            INSERT INTO gear VALUES (
                'uuid-1', 'Canyon',
                '{"distanceUsedMeters": 12345.6, "durationUsedSeconds": 43200, "daysUsed": 5}'
            );
        """)
        migrate_gear_table(conn)
        row = dict(conn.execute("SELECT * FROM gear WHERE gear_id = 'uuid-1'").fetchone())
        assert row["distance_used_meters"] == pytest.approx(12345.6, rel=1e-4)
        assert row["duration_used_seconds"] == 43200
        assert row["days_used"] == 5
        conn.close()

    def test_migrate_activity_splits_v2_adds_and_backfills(self):
        conn = self._old_db("""
            CREATE TABLE activity_splits (
                activity_id INTEGER,
                split_number INTEGER,
                raw_json TEXT,
                PRIMARY KEY (activity_id, split_number)
            );
            INSERT INTO activity_splits VALUES (
                1001, 1,
                '{"normalizedPower": 230, "avgRespirationRate": 33.5,
                  "startLatitude": 49.46, "startLongitude": 11.07,
                  "calories": 115, "surfaceTypeUnpavedPercentage": 60.0}'
            );
        """)
        migrate_activity_splits_v2(conn)
        row = dict(conn.execute("SELECT * FROM activity_splits WHERE activity_id = 1001").fetchone())
        assert row["normalized_power"] == 230
        assert row["avg_respiration_rate"] == pytest.approx(33.5, abs=0.1)
        assert row["start_latitude"] == pytest.approx(49.46, abs=0.01)
        assert row["calories"] == 115
        assert row["surface_unpaved_pct"] == pytest.approx(60.0)
        conn.close()

    def test_migrate_hollow_tables_adds_columns(self):
        conn = self._old_db("""
            CREATE TABLE daily_events (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
            CREATE TABLE wellness_activity (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
            CREATE TABLE health_snapshot (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
            INSERT INTO daily_events VALUES (
                '2026-05-10',
                '{"activityType": "RUNNING", "startTimestampLocal": "2026-05-10T07:00:00",
                  "endTimestampLocal": "2026-05-10T08:00:00", "duration": 3600.0}'
            );
            INSERT INTO wellness_activity VALUES (
                '2026-05-10',
                '{"activityName": "Walk", "wellnessActivityType": "WALKING",
                  "startTimestampLocal": "2026-05-10T06:00:00"}'
            );
        """)
        migrate_hollow_tables(conn)
        de_cols = _cols(conn, "daily_events")
        assert "activity_type" in de_cols
        assert "start_timestamp_local" in de_cols
        wa = dict(conn.execute("SELECT * FROM wellness_activity WHERE calendar_date = '2026-05-10'").fetchone())
        assert wa["activity_name"] == "Walk"
        assert wa["wellness_activity_type"] == "WALKING"
        conn.close()

    def test_migrate_endurance_score_stores_contributors_as_json(self):
        contrib = [{"group": 0, "contribution": 80.0}, {"group": 6, "contribution": 20.0}]
        conn = self._old_db(f"""
            CREATE TABLE endurance_score (
                calendar_date TEXT PRIMARY KEY,
                overall_score INTEGER,
                raw_json TEXT
            );
            INSERT INTO endurance_score VALUES (
                '2026-05-10', 5200,
                '{json.dumps({"feedbackPhrase": "PRODUCTIVE", "contributors": contrib})}'
            );
        """)
        migrate_endurance_score_table(conn)
        row = dict(conn.execute("SELECT * FROM endurance_score WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["feedback_phrase"] == "PRODUCTIVE"
        parsed = json.loads(row["contributors"])
        assert len(parsed) == 2
        conn.close()


# ---------------------------------------------------------------------------
# New v2/v3 migrations: sleep_v2 (RENAME COLUMN + nested backfill), activity,
# fitness_age, weight_v3, gear_v2
# ---------------------------------------------------------------------------


class TestSleepMigrationV2:
    """RENAME COLUMN + nested json_extract backfill from dailySleepDTO."""

    def _old_db_with_rename_candidates(self) -> sqlite3.Connection:
        """Pre-v2 schema: has the old (wrongly-named) columns sleep_need_seconds
        and sleep_score_composition. These must be renamed in place."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE sleep (
                calendar_date TEXT PRIMARY KEY,
                sleep_time_seconds INTEGER,
                sleep_need_seconds INTEGER,
                sleep_score_composition INTEGER,
                raw_json TEXT
            );
        """)
        raw = {
            "dailySleepDTO": {
                "calendarDate": "2026-05-10",
                "sleepTimeSeconds": 28800,
                "sleepNeed": {"actual": 540},  # minutes
                "highestSpO2Value": 99,
                "sleepScores": {
                    "overall": {"value": 87},
                    "lightPercentage": {"value": 53},
                    "remPercentage": {"value": 21},
                    "deepPercentage": {"value": 26},
                },
            }
        }
        conn.execute(
            "INSERT INTO sleep (calendar_date, sleep_time_seconds, raw_json) VALUES (?, ?, ?)",
            ("2026-05-10", 28800, json.dumps(raw)),
        )
        conn.commit()
        return conn

    def test_renames_sleep_need_seconds_to_minutes(self):
        conn = self._old_db_with_rename_candidates()
        migrate_sleep_table_v2(conn)
        cols = _cols(conn, "sleep")
        assert "sleep_need_minutes" in cols
        assert "sleep_need_seconds" not in cols
        conn.close()

    def test_renames_composition_to_light_pct(self):
        conn = self._old_db_with_rename_candidates()
        migrate_sleep_table_v2(conn)
        cols = _cols(conn, "sleep")
        assert "sleep_light_pct" in cols
        assert "sleep_score_composition" not in cols
        conn.close()

    def test_backfill_from_nested_raw_json(self):
        conn = self._old_db_with_rename_candidates()
        migrate_sleep_table_v2(conn)
        row = dict(conn.execute("SELECT * FROM sleep WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["sleep_need_minutes"] == 540
        assert row["highest_spo2"] == pytest.approx(99.0)
        assert row["sleep_score_overall"] == 87
        assert row["sleep_light_pct"] == 53
        assert row["sleep_score_rem"] == 21
        assert row["sleep_score_deep"] == 26
        conn.close()

    def test_idempotent_on_fresh_schema(self, temp_db):
        # temp_db already ran init_db, which includes migrate_sleep_table_v2.
        # Second call must be a no-op without errors.
        migrate_sleep_table_v2(temp_db)
        cols = _cols(temp_db, "sleep")
        assert "sleep_need_minutes" in cols
        assert "sleep_light_pct" in cols
        assert "sleep_need_seconds" not in cols

    def test_idempotent_when_renames_already_done(self):
        """Second run must not error even though target columns already exist."""
        conn = self._old_db_with_rename_candidates()
        migrate_sleep_table_v2(conn)
        # Run again — RENAME COLUMN would fail if old name still present, but
        # the migration checks first.
        migrate_sleep_table_v2(conn)
        cols = _cols(conn, "sleep")
        assert "sleep_need_minutes" in cols
        conn.close()


class TestActivityMigration:
    """migrate_activity_table adds 5 columns and backfills from summaryDTO."""

    def _old_activity_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE activity (
                activity_id INTEGER PRIMARY KEY,
                activity_type TEXT,
                raw_json TEXT
            );
        """)
        raw = {
            "summaryDTO": {
                "differenceBodyBattery": -25,
                "totalWork": 850.5,
                "avgGradeAdjustedSpeed": 3.42,
                "steps": 11250,
                "minHR": 92,
            }
        }
        conn.execute(
            "INSERT INTO activity (activity_id, activity_type, raw_json) VALUES (?, ?, ?)",
            (9001, "running", json.dumps(raw)),
        )
        conn.commit()
        return conn

    def test_adds_all_new_activity_columns(self):
        conn = self._old_activity_db()
        migrate_activity_table(conn)
        cols = _cols(conn, "activity")
        for c in (
            "body_battery_change",
            "total_work_kcal",
            "avg_grade_adjusted_speed",
            "activity_steps",
            "activity_min_hr",
        ):
            assert c in cols, f"Missing: {c}"
        conn.close()

    def test_backfill_from_summary_dto(self):
        conn = self._old_activity_db()
        migrate_activity_table(conn)
        row = dict(conn.execute("SELECT * FROM activity WHERE activity_id = 9001").fetchone())
        assert row["body_battery_change"] == -25
        assert row["total_work_kcal"] == pytest.approx(850.5)
        assert row["avg_grade_adjusted_speed"] == pytest.approx(3.42, abs=0.01)
        assert row["activity_steps"] == 11250
        assert row["activity_min_hr"] == 92
        conn.close()

    def test_idempotent(self, temp_db):
        migrate_activity_table(temp_db)
        assert "body_battery_change" in _cols(temp_db, "activity")

    def test_missing_summary_dto_leaves_nulls(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE activity (
                activity_id INTEGER PRIMARY KEY,
                raw_json TEXT
            );
        """)
        conn.execute(
            "INSERT INTO activity VALUES (?, ?)",
            (1, json.dumps({"activityName": "X"})),
        )
        conn.commit()
        migrate_activity_table(conn)
        row = dict(conn.execute("SELECT * FROM activity WHERE activity_id = 1").fetchone())
        assert row["body_battery_change"] is None
        assert row["total_work_kcal"] is None
        conn.close()


class TestFitnessAgeMigration:
    def test_adds_achievable_fitness_age(self, temp_db):
        migrate_fitness_age_table(temp_db)
        assert "achievable_fitness_age" in _cols(temp_db, "fitness_age")

    def test_backfill_from_raw(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE fitness_age (
                calendar_date TEXT PRIMARY KEY,
                raw_json TEXT
            );
        """)
        conn.execute(
            "INSERT INTO fitness_age VALUES (?, ?)",
            ("2026-05-10", json.dumps({"achievableFitnessAge": 35.0})),
        )
        conn.commit()
        migrate_fitness_age_table(conn)
        row = dict(conn.execute("SELECT * FROM fitness_age WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["achievable_fitness_age"] == pytest.approx(35.0)
        conn.close()


class TestWeightMigrationV3:
    def test_adds_visceral_fat(self, temp_db):
        migrate_weight_table_v3(temp_db)
        assert "visceral_fat" in _cols(temp_db, "weight")

    def test_backfill_visceral_fat_from_raw(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE weight (
                timestamp INTEGER PRIMARY KEY,
                weight REAL,
                raw_json TEXT
            );
        """)
        conn.execute(
            "INSERT INTO weight VALUES (?, ?, ?)",
            (1746835200000, 77000, json.dumps({"visceralFat": 7.5})),
        )
        conn.commit()
        migrate_weight_table_v3(conn)
        row = dict(conn.execute("SELECT * FROM weight WHERE timestamp = 1746835200000").fetchone())
        assert row["visceral_fat"] == pytest.approx(7.5)
        conn.close()


class TestGearMigrationV2:
    def test_adds_status_and_max_distance(self, temp_db):
        migrate_gear_table_v2(temp_db)
        cols = _cols(temp_db, "gear")
        assert "status" in cols
        assert "max_usage_distance_meters" in cols

    def test_backfill_status_and_max_distance(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE gear (
                gear_id TEXT PRIMARY KEY,
                display_name TEXT,
                raw_json TEXT
            );
        """)
        conn.execute(
            "INSERT INTO gear VALUES (?, ?, ?)",
            ("uuid-7", "Canyon", json.dumps({"status": "active", "maxUsageDistanceMeters": 1500000.0})),
        )
        conn.commit()
        migrate_gear_table_v2(conn)
        row = dict(conn.execute("SELECT * FROM gear WHERE gear_id = 'uuid-7'").fetchone())
        assert row["status"] == "active"
        assert row["max_usage_distance_meters"] == pytest.approx(1500000.0)
        conn.close()


# ---------------------------------------------------------------------------
# End-to-end: full upgrade from old schema + idempotency of init_db itself
# ---------------------------------------------------------------------------


class TestFullUpgradePath:
    """Simulate a user upgrading from pre-PR DB by running init_db on it."""

    def test_init_db_is_idempotent(self, temp_db):
        """Running init_db twice on a fresh DB must not raise or change schema."""
        before_cols = _cols(temp_db, "sleep")
        init_db(temp_db)  # second call
        after_cols = _cols(temp_db, "sleep")
        assert before_cols == after_cols

    def test_init_db_recovers_old_sleep_schema(self):
        """Old DB has sleep_need_seconds & sleep_score_composition (wrong names).
        After init_db, the columns must be renamed and backfilled correctly."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # Build a deliberately incomplete pre-PR sleep table
        conn.executescript("""
            CREATE TABLE sleep (
                calendar_date TEXT PRIMARY KEY,
                sleep_time_seconds INTEGER,
                sleep_need_seconds INTEGER,
                sleep_score_composition INTEGER,
                raw_json TEXT
            );
        """)
        raw = json.dumps(
            {
                "dailySleepDTO": {
                    "calendarDate": "2026-05-10",
                    "sleepTimeSeconds": 28000,
                    "sleepNeed": {"actual": 540},
                    "sleepScores": {
                        "overall": {"value": 85},
                        "lightPercentage": {"value": 50},
                    },
                }
            }
        )
        conn.execute(
            "INSERT INTO sleep VALUES (?, ?, ?, ?, ?)",
            ("2026-05-10", 28000, None, None, raw),
        )
        conn.commit()

        init_db(conn)  # runs all migrations including sleep_v2

        cols = _cols(conn, "sleep")
        assert "sleep_need_minutes" in cols
        assert "sleep_light_pct" in cols
        assert "sleep_need_seconds" not in cols
        assert "sleep_score_composition" not in cols

        row = dict(conn.execute("SELECT * FROM sleep WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["sleep_need_minutes"] == 540
        assert row["sleep_light_pct"] == 50
        assert row["sleep_score_overall"] == 85
        conn.close()

    def test_init_db_twice_on_old_schema_is_safe(self):
        """Run init_db twice on a pre-PR DB — second pass must be a no-op."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE sleep (
                calendar_date TEXT PRIMARY KEY,
                sleep_time_seconds INTEGER,
                sleep_need_seconds INTEGER,
                raw_json TEXT
            );
        """)
        conn.execute(
            "INSERT INTO sleep VALUES (?, ?, ?, ?)",
            ("2026-05-10", 28000, None, json.dumps({"dailySleepDTO": {"sleepNeed": {"actual": 500}}})),
        )
        conn.commit()

        init_db(conn)
        init_db(conn)  # idempotency check

        row = dict(conn.execute("SELECT * FROM sleep WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["sleep_need_minutes"] == 500
        conn.close()


# ---------------------------------------------------------------------------
# Edge cases flagged in code review
# ---------------------------------------------------------------------------


class TestZeroValueBackfill:
    """Regression: data.get(jk) must not coerce 0/False/'' to None."""

    def test_zero_visceral_fat_preserved(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE weight (timestamp INTEGER PRIMARY KEY, weight REAL, raw_json TEXT);
        """)
        conn.execute(
            "INSERT INTO weight VALUES (?, ?, ?)",
            (1, 75000, json.dumps({"visceralFat": 0})),
        )
        conn.commit()
        migrate_weight_table_v3(conn)
        row = dict(conn.execute("SELECT * FROM weight WHERE timestamp = 1").fetchone())
        assert row["visceral_fat"] == 0.0  # not NULL
        conn.close()

    def test_zero_body_battery_change_preserved(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE activity (activity_id INTEGER PRIMARY KEY, raw_json TEXT);
        """)
        conn.execute(
            "INSERT INTO activity VALUES (?, ?)",
            (1, json.dumps({"summaryDTO": {"differenceBodyBattery": 0, "steps": 0, "totalWork": 0.0}})),
        )
        conn.commit()
        migrate_activity_table(conn)
        row = dict(conn.execute("SELECT * FROM activity WHERE activity_id = 1").fetchone())
        assert row["body_battery_change"] == 0
        assert row["activity_steps"] == 0
        assert row["total_work_kcal"] == 0.0
        conn.close()

    def test_zero_spo2_events_preserved(self):
        """Most users have events_below_threshold=0 — must not be NULL after backfill."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE spo2 (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
        """)
        conn.execute(
            "INSERT INTO spo2 VALUES (?, ?)",
            (
                "2026-05-10",
                json.dumps(
                    {
                        "numberOfEventsBelowThreshold": 0,
                        "durationOfEventsBelowThreshold": 0,
                    }
                ),
            ),
        )
        conn.commit()
        migrate_spo2_table(conn)
        row = dict(conn.execute("SELECT * FROM spo2 WHERE calendar_date = '2026-05-10'").fetchone())
        assert row["events_below_threshold"] == 0
        assert row["duration_below_threshold_secs"] == 0
        conn.close()


class TestSleepNullNestedScore:
    """Garmin sometimes returns sleepScores.overall = null for failed nights."""

    def test_null_overall_score_does_not_crash(self, temp_db):
        record = {
            "dailySleepDTO": {
                "calendarDate": "2026-05-10",
                "sleepTimeSeconds": 27000,
                "sleepScores": {
                    "overall": None,
                    "remPercentage": None,
                    "deepPercentage": None,
                    "lightPercentage": None,
                },
            }
        }
        upsert_sleep(temp_db, record)  # must not raise
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["sleep_score_overall"] is None
        assert row["sleep_score_rem"] is None
        assert row["sleep_score_deep"] is None
        assert row["sleep_light_pct"] is None

    def test_missing_sleep_scores_dict_entirely(self, temp_db):
        record = {"dailySleepDTO": {"calendarDate": "2026-05-09", "sleepTimeSeconds": 25000}}
        upsert_sleep(temp_db, record)  # must not raise
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-09")
        assert row["sleep_score_overall"] is None


class TestSleepLightPctUpsert:
    """Regression: upsert_sleep must write sleep_light_pct, not just the migration."""

    def test_sleep_light_pct_persisted_via_upsert(self, temp_db):
        record = {
            "dailySleepDTO": {
                "calendarDate": "2026-05-10",
                "sleepTimeSeconds": 27000,
                "sleepScores": {
                    "overall": {"value": 85},
                    "lightPercentage": {"value": 58},
                    "remPercentage": {"value": 25},
                    "deepPercentage": {"value": 17},
                },
            }
        }
        upsert_sleep(temp_db, record)
        row = _row(temp_db, "sleep", "calendar_date", "2026-05-10")
        assert row["sleep_light_pct"] == 58


class TestActivityUpsertPreservesSummaryData:
    """Regression: a flat list record (no summaryDTO) must not blank columns set
    by a prior detailed record."""

    def test_detail_then_flat_preserves_summary_columns(self, temp_db):
        detailed = {
            "activityId": 9999,
            "activityName": "Detail Run",
            "summaryDTO": {
                "differenceBodyBattery": -20,
                "totalWork": 180.5,
                "steps": 8500,
                "minHR": 95,
                "avgGradeAdjustedSpeed": 3.1,
            },
        }
        flat = {
            "activityId": 9999,
            "activityName": "List Run",
            # no summaryDTO
        }
        upsert_activity(temp_db, detailed)
        upsert_activity(temp_db, flat)
        row = _row(temp_db, "activity", "activity_id", 9999)
        # Basic fields take the latest write
        assert row["activity_name"] == "List Run"
        # Summary-only fields preserved from the detailed record
        assert row["body_battery_change"] == -20
        assert row["total_work_kcal"] == pytest.approx(180.5)
        assert row["activity_steps"] == 8500
        assert row["activity_min_hr"] == 95
        assert row["avg_grade_adjusted_speed"] == pytest.approx(3.1, abs=0.01)

    def test_flat_then_detail_populates_summary_columns(self, temp_db):
        upsert_activity(temp_db, {"activityId": 8888, "activityName": "First"})
        upsert_activity(
            temp_db,
            {
                "activityId": 8888,
                "activityName": "Second",
                "summaryDTO": {"differenceBodyBattery": -15, "steps": 7000},
            },
        )
        row = _row(temp_db, "activity", "activity_id", 8888)
        assert row["activity_name"] == "Second"
        assert row["body_battery_change"] == -15
        assert row["activity_steps"] == 7000


class TestRenameColumnGuard:
    """Regression: RENAME COLUMN must not crash when both source and target exist."""

    def test_sleep_v2_idempotent_when_target_pre_exists(self):
        """User manually ALTERed in the new column — migration must not duplicate-key crash."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE sleep (
                calendar_date TEXT PRIMARY KEY,
                sleep_need_seconds INTEGER,
                sleep_need_minutes INTEGER,
                raw_json TEXT
            );
        """)
        # Both columns exist — migration must skip the rename gracefully
        migrate_sleep_table_v2(conn)  # must not raise
        cols = _cols(conn, "sleep")
        # Both can exist (we don't drop the legacy one), but no crash
        assert "sleep_need_minutes" in cols
        conn.close()


class TestActivityKjToKcalRename:
    """Pre-release intermediate had total_work_kj; the column rename must work."""

    def test_renames_kj_to_kcal(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE activity (
                activity_id INTEGER PRIMARY KEY,
                total_work_kj REAL,
                raw_json TEXT
            );
            INSERT INTO activity VALUES (1, 248.21, NULL);
        """)
        migrate_activity_table(conn)
        cols = _cols(conn, "activity")
        assert "total_work_kcal" in cols
        assert "total_work_kj" not in cols
        # Existing value preserved (already in kcal — just relabeled)
        row = dict(conn.execute("SELECT * FROM activity WHERE activity_id = 1").fetchone())
        assert row["total_work_kcal"] == pytest.approx(248.21)
        conn.close()


class TestHollowTableArrayRawJson:
    """Edge: raw_json may be a JSON array (multi-event payloads)."""

    def test_daily_events_array_raw_json_does_not_crash(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE daily_events (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
            CREATE TABLE wellness_activity (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
            CREATE TABLE health_snapshot (calendar_date TEXT PRIMARY KEY, raw_json TEXT);
        """)
        # raw_json is a JSON array, not an object
        conn.execute(
            "INSERT INTO daily_events VALUES (?, ?)",
            ("2026-05-10", json.dumps([{"activityType": "RUN"}, {"activityType": "BIKE"}])),
        )
        conn.commit()
        # Must not crash; array rows just don't get scalar fields backfilled
        migrate_hollow_tables(conn)
        # Schema columns added regardless
        assert "activity_type" in _cols(conn, "daily_events")
        conn.close()

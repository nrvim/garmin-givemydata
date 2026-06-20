"""Tests for empty-day filtering in save_to_db.

Garmin returns a row for every queried day even when the device recorded
nothing — every measurement field comes back null while identifier, goal and
default fields stay populated. These placeholder rows (most visibly years of
empty days from before the account existed) must not be written. The payloads
below mirror real Garmin API responses for an empty (void) day versus a day
with data, including the traps that defeat a naive "any non-null field" check:

* daily_summary always returns ``netRemainingKilocalories: 0.0``
* intensity_minutes always returns ``weekGoal: 150``
* hydration always returns ``goalInML``/``baseGoalInML``

so ``0`` must count as real data while a goal/default must not.
"""

import pytest

from garmin_mcp.db import _daily_record_has_data, save_to_db

# ── Sample API payloads ───────────────────────────────────────────────────

EMPTY_DAILY_SUMMARY = {
    "calendarDate": "2020-06-15",
    "source": "GARMIN",
    "totalSteps": None,
    "totalKilocalories": None,
    "restingHeartRate": None,
    "netRemainingKilocalories": 0.0,  # trap: non-null even on void days
    "includesWellnessData": False,
    "includesActivityData": False,
    "includesCalorieConsumedData": False,
}

REAL_DAILY_SUMMARY = {
    "calendarDate": "2025-06-01",
    "source": "GARMIN",
    "totalSteps": 5738,
    "totalKilocalories": 1703.0,
    "restingHeartRate": 52,
    "includesWellnessData": True,
    "includesActivityData": False,
    "includesCalorieConsumedData": False,
}

# A real day on which the wearer happened to take zero steps. 0 is a genuine
# measurement and the day must be kept.
REAL_ZERO_STEP_DAILY_SUMMARY = {
    "calendarDate": "2025-11-24",
    "totalSteps": 0,
    "totalKilocalories": 1694.0,
    "includesWellnessData": True,
}

EMPTY_PAYLOADS = {
    "heart_rate": {
        "calendarDate": "2020-06-15",
        "maxHeartRate": None,
        "minHeartRate": None,
        "restingHeartRate": None,
        "heartRateValues": None,
    },
    "stress": {"calendarDate": "2020-06-15", "maxStressLevel": None, "avgStressLevel": None, "stressValuesArray": []},
    "spo2": {"calendarDate": "2020-06-15", "averageSpO2": None, "lowestSpO2": None, "spo2ValuesArray": []},
    "respiration": {
        "calendarDate": "2020-06-15",
        "avgWakingRespirationValue": None,
        "lowestRespirationValue": None,
        "highestRespirationValue": None,
        "respirationValuesArray": None,
    },
    "floors": {"floorValuesArray": [], "startTimestampGMT": None},
    "intensity_minutes": {
        "calendarDate": "2020-06-15",
        "moderateMinutes": None,
        "vigorousMinutes": None,
        "weeklyTotal": None,
        "weekGoal": 150,
    },  # weekGoal is a trap
    "hydration": {
        "calendarDate": "2020-06-15",
        "valueInML": None,
        "sweatLossInML": None,
        "activityIntakeInML": None,
        "goalInML": 2800.0,
        "baseGoalInML": 2800.0,
    },  # goals are traps
    "daily_movement": {"calendarDate": "2020-06-15", "movementValues": [], "movementValueDescriptors": []},
    "training_status": {"userId": None, "latestTrainingStatusData": None},
    "fitness_age": {"chronologicalAge": 25, "components": {"rhr": {"stale": True}, "bmi": {"stale": True}}},
    "body_battery_events": {
        "bodyBattery": {"labels": ["timestampGmt", "value"], "data": []},
        "stress": {"labels": ["timestampGmt", "value"], "data": []},
    },
}

REAL_PAYLOADS = {
    "heart_rate": {"calendarDate": "2025-06-01", "maxHeartRate": 142, "minHeartRate": 48, "restingHeartRate": 52},
    "stress": {"calendarDate": "2025-06-01", "maxStressLevel": 88, "avgStressLevel": 30},
    "spo2": {"calendarDate": "2025-06-01", "averageSpO2": 96, "lowestSpO2": 91},
    "respiration": {"calendarDate": "2025-06-01", "avgWakingRespirationValue": 14.0, "lowestRespirationValue": 11.0},
    "floors": {"floorValuesArray": [[0, 1700000000000, 3]], "startTimestampGMT": "2025-06-01T16:00:00.0"},
    "intensity_minutes": {
        "calendarDate": "2025-06-01",
        "moderateMinutes": 30,
        "vigorousMinutes": 0,
        "weeklyTotal": 120,
        "weekGoal": 150,
    },
    "hydration": {
        "calendarDate": "2025-05-04",
        "valueInML": 0.0,
        "sweatLossInML": 2147.0,
        "activityIntakeInML": 0.0,
        "goalInML": 4947.0,
    },
    "daily_movement": {"calendarDate": "2025-06-01", "movementValues": [[0, 12], [1, 30]]},
    "training_status": {"userId": 1, "latestTrainingStatusData": {"123": {"trainingStatus": 3}}},
    "fitness_age": {"chronologicalAge": 25, "components": {"rhr": {"stale": False, "value": 52}}},
    "body_battery_events": {
        "bodyBattery": {"labels": ["timestampGmt", "value"], "data": [[1700000000000, 55]]},
        "stress": {"labels": [], "data": []},
    },
}


# ── _daily_record_has_data ────────────────────────────────────────────────


@pytest.mark.unit
class TestDailyRecordHasData:
    def test_empty_daily_summary_has_no_data(self):
        assert _daily_record_has_data("daily_summary", EMPTY_DAILY_SUMMARY) is False

    def test_real_daily_summary_has_data(self):
        assert _daily_record_has_data("daily_summary", REAL_DAILY_SUMMARY) is True

    def test_zero_step_day_is_real_data(self):
        # 0 is a genuine measurement — the includes flag confirms a tracked day.
        assert _daily_record_has_data("daily_summary", REAL_ZERO_STEP_DAILY_SUMMARY) is True

    def test_net_remaining_calories_is_not_a_signal(self):
        # netRemainingKilocalories: 0.0 must not by itself keep a void day.
        rec = {
            "calendarDate": "2020-01-01",
            "netRemainingKilocalories": 0.0,
            "includesWellnessData": False,
            "includesActivityData": False,
            "includesCalorieConsumedData": False,
        }
        assert _daily_record_has_data("daily_summary", rec) is False

    @pytest.mark.parametrize("name", sorted(EMPTY_PAYLOADS))
    def test_empty_payloads_have_no_data(self, name):
        assert _daily_record_has_data(name, EMPTY_PAYLOADS[name]) is False

    @pytest.mark.parametrize("name", sorted(REAL_PAYLOADS))
    def test_real_payloads_have_data(self, name):
        assert _daily_record_has_data(name, REAL_PAYLOADS[name]) is True

    def test_goal_default_does_not_count_as_data(self):
        # intensity_minutes always carries weekGoal=150; hydration carries goals.
        assert _daily_record_has_data("intensity_minutes", EMPTY_PAYLOADS["intensity_minutes"]) is False
        assert _daily_record_has_data("hydration", EMPTY_PAYLOADS["hydration"]) is False

    def test_unmapped_endpoint_is_never_filtered(self):
        # Non-daily endpoints (sleep, activities, profile, …) pass through.
        assert _daily_record_has_data("sleep", {"anything": None}) is True
        assert _daily_record_has_data("activities", {}) is True

    def test_non_dict_record_passes_through(self):
        assert _daily_record_has_data("heart_rate", None) is True
        assert _daily_record_has_data("heart_rate", [1, 2, 3]) is True


# ── save_to_db end-to-end ─────────────────────────────────────────────────


@pytest.mark.unit
class TestSaveToDbFiltersEmptyDays:
    def _daily_summary_rows(self, conn):
        return conn.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0]

    def test_empty_daily_summary_writes_no_row(self, temp_db):
        assert save_to_db(temp_db, "daily_summary", [EMPTY_DAILY_SUMMARY]) == 0
        assert self._daily_summary_rows(temp_db) == 0

    def test_real_daily_summary_writes_one_row(self, temp_db):
        assert save_to_db(temp_db, "daily_summary", [REAL_DAILY_SUMMARY]) == 1
        assert self._daily_summary_rows(temp_db) == 1

    def test_mixed_batch_keeps_only_real_days(self, temp_db):
        batch = [EMPTY_DAILY_SUMMARY, REAL_DAILY_SUMMARY, REAL_ZERO_STEP_DAILY_SUMMARY]
        assert save_to_db(temp_db, "daily_summary", batch) == 2
        assert self._daily_summary_rows(temp_db) == 2

    @pytest.mark.parametrize(
        "name,table",
        [
            ("heart_rate", "heart_rate"),
            ("stress", "stress"),
            ("spo2", "spo2"),
            ("respiration", "respiration"),
            ("intensity_minutes", "intensity_minutes"),
        ],
    )
    def test_empty_day_writes_no_row(self, temp_db, name, table):
        assert save_to_db(temp_db, name, [EMPTY_PAYLOADS[name]], cal_date="2020-06-15") == 0
        assert temp_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

    @pytest.mark.parametrize(
        "name,table",
        [
            ("heart_rate", "heart_rate"),
            ("stress", "stress"),
            ("spo2", "spo2"),
            ("respiration", "respiration"),
            ("intensity_minutes", "intensity_minutes"),
        ],
    )
    def test_real_day_writes_one_row(self, temp_db, name, table):
        cal = REAL_PAYLOADS[name].get("calendarDate", "2025-06-01")
        assert save_to_db(temp_db, name, [REAL_PAYLOADS[name]], cal_date=cal) == 1
        assert temp_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1

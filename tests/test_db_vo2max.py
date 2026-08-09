"""
Tests for upsert_vo2max — Garmin nests the payload one level down under
"generic" (or "cycling"), so the upsert must read calendarDate/value from the
nested dict, not the top level (issue #73).
"""

import pytest

from garmin_mcp.db import save_to_db, upsert_vo2max


def _rows(conn):
    return conn.execute("SELECT calendar_date, sport, value FROM vo2max ORDER BY calendar_date, sport").fetchall()


NESTED_RUNNING_RECORD = {
    "cycling": None,
    "generic": {
        "calendarDate": "2026-07-07",
        "fitnessAge": None,
        "fitnessAgeDescription": None,
        "maxMetCategory": 0,
        "vo2MaxPreciseValue": 45.3,
        "vo2MaxValue": 45,
    },
    "heatAltitudeAcclimation": None,
    "userId": 125263072,
}


class TestUpsertVo2max:
    def test_nested_generic_record_inserted(self, temp_db):
        upsert_vo2max(temp_db, NESTED_RUNNING_RECORD, "RUNNING")
        rows = _rows(temp_db)
        assert len(rows) == 1
        assert rows[0]["calendar_date"] == "2026-07-07"
        assert rows[0]["sport"] == "RUNNING"
        assert rows[0]["value"] == pytest.approx(45.3)

    def test_nested_cycling_record_inserted(self, temp_db):
        record = {
            "cycling": {"calendarDate": "2026-07-08", "vo2MaxPreciseValue": 52.1, "vo2MaxValue": 52},
            "generic": None,
        }
        upsert_vo2max(temp_db, record, "CYCLING")
        rows = _rows(temp_db)
        assert len(rows) == 1
        assert rows[0]["sport"] == "CYCLING"
        assert rows[0]["calendar_date"] == "2026-07-08"
        assert rows[0]["value"] == pytest.approx(52.1)

    def test_flat_record_still_supported(self, temp_db):
        upsert_vo2max(temp_db, {"calendarDate": "2026-07-09", "vo2MaxPreciseValue": 44.8}, "RUNNING")
        rows = _rows(temp_db)
        assert len(rows) == 1
        assert rows[0]["calendar_date"] == "2026-07-09"
        assert rows[0]["value"] == pytest.approx(44.8)

    def test_falls_back_to_vo2max_value_when_precise_missing(self, temp_db):
        record = {"generic": {"calendarDate": "2026-07-10", "vo2MaxValue": 46}}
        upsert_vo2max(temp_db, record, "RUNNING")
        rows = _rows(temp_db)
        assert len(rows) == 1
        assert rows[0]["value"] == pytest.approx(46)

    def test_record_without_date_skipped(self, temp_db):
        upsert_vo2max(temp_db, {"generic": {"vo2MaxPreciseValue": 45.3}}, "RUNNING")
        assert _rows(temp_db) == []

    def test_record_without_value_skipped(self, temp_db):
        upsert_vo2max(temp_db, {"generic": {"calendarDate": "2026-07-11"}}, "RUNNING")
        assert _rows(temp_db) == []

    def test_value_is_never_a_dict(self, temp_db):
        # The old code fell back to record["generic"] (a dict) for the value
        # column; ensure only numeric values are ever written.
        upsert_vo2max(temp_db, NESTED_RUNNING_RECORD, "RUNNING")
        row = _rows(temp_db)[0]
        assert isinstance(row["value"], float)


class TestSaveToDbVo2max:
    def test_vo2max_trend_endpoint(self, temp_db):
        count = save_to_db(temp_db, "vo2max_trend", [NESTED_RUNNING_RECORD])
        assert count == 1
        rows = _rows(temp_db)
        assert rows[0]["calendar_date"] == "2026-07-07"
        assert rows[0]["value"] == pytest.approx(45.3)

    def test_gql_vo2max_running_endpoint(self, temp_db):
        payload = {"data": {"vo2MaxScalar": [NESTED_RUNNING_RECORD]}}
        count = save_to_db(temp_db, "gql_vo2max_running", payload)
        assert count == 1
        rows = _rows(temp_db)
        assert rows[0]["sport"] == "RUNNING"
        assert rows[0]["value"] == pytest.approx(45.3)

    def test_gql_vo2max_cycling_empty_for_running_only_account(self, temp_db):
        count = save_to_db(temp_db, "gql_vo2max_cycling", {"data": {"vo2MaxScalar": []}})
        assert count == 0
        assert _rows(temp_db) == []

"""Tests for #86: Pulse Ox spot checks + hourly averages from the
wellness/daily/spo2 endpoint, stored in spo2_spot_reading / spo2_hourly_average.
"""

from garmin_client.endpoints import daily_rest
from garmin_mcp.db import save_to_db, upsert_spo2_spot

SINGLE_DESCRIPTORS = [
    {"spo2ValueDescriptorIndex": 0, "spo2ValueDescriptorKey": "timestamp"},
    {"spo2ValueDescriptorIndex": 1, "spo2ValueDescriptorKey": "spo2Reading"},
    {"spo2ValueDescriptorIndex": 2, "spo2ValueDescriptorKey": "singleReadingPlottable"},
]


def _readings(conn, date):
    return conn.execute(
        "SELECT reading_timestamp, spo2, plottable FROM spo2_spot_reading WHERE calendar_date = ? ORDER BY reading_timestamp",
        (date,),
    ).fetchall()


def _hourly(conn, date):
    return conn.execute(
        "SELECT hour_timestamp, avg_spo2 FROM spo2_hourly_average WHERE calendar_date = ? ORDER BY hour_timestamp",
        (date,),
    ).fetchall()


class TestEndpointRegistered:
    def test_daily_spo2_spot_endpoint_present(self):
        eps = daily_rest("Xyz", "2026-01-01")
        assert eps["spo2_spot"] == "/gc-api/wellness-service/wellness/daily/spo2/2026-01-01"


class TestUpsertSpo2Spot:
    def test_stores_spot_checks_and_hourly(self, temp_db):
        rec = {
            "calendarDate": "2026-01-01",
            "spO2ValueDescriptorsDTOList": SINGLE_DESCRIPTORS,
            "spO2SingleValues": [[1767292200000, 97, True], [1767295800000, 94, False]],
            "spO2HourlyAverages": [[1767232800000, 95], [1767236400000, 96]],
        }
        n = upsert_spo2_spot(temp_db, rec)
        assert n == 4
        rows = _readings(temp_db, "2026-01-01")
        assert [(r["reading_timestamp"], r["spo2"], r["plottable"]) for r in rows] == [
            (1767292200000, 97, 1),
            (1767295800000, 94, 0),
        ]
        hrs = _hourly(temp_db, "2026-01-01")
        assert [(h["hour_timestamp"], h["avg_spo2"]) for h in hrs] == [(1767232800000, 95), (1767236400000, 96)]

    def test_all_day_mode_only_hourly(self, temp_db):
        # With All Day Pulse Ox, spO2SingleValues is null; only hourly averages.
        rec = {
            "calendarDate": "2026-01-02",
            "spO2SingleValues": None,
            "spO2HourlyAverages": [[1, 95], [2, 96]],
        }
        n = upsert_spo2_spot(temp_db, rec)
        assert n == 2
        assert len(_readings(temp_db, "2026-01-02")) == 0
        assert len(_hourly(temp_db, "2026-01-02")) == 2

    def test_descriptor_override_indices(self, temp_db):
        # Reordered columns: value at index 0, timestamp at index 1.
        descs = [
            {"spo2ValueDescriptorIndex": 1, "spo2ValueDescriptorKey": "timestamp"},
            {"spo2ValueDescriptorIndex": 0, "spo2ValueDescriptorKey": "spo2Reading"},
        ]
        rec = {
            "calendarDate": "2026-01-03",
            "spO2ValueDescriptorsDTOList": descs,
            "spO2SingleValues": [[98, 1767292200000]],
        }
        upsert_spo2_spot(temp_db, rec)
        rows = _readings(temp_db, "2026-01-03")
        assert len(rows) == 1
        assert rows[0]["reading_timestamp"] == 1767292200000
        assert rows[0]["spo2"] == 98

    def test_skips_malformed_rows(self, temp_db):
        rec = {
            "calendarDate": "2026-01-04",
            "spO2ValueDescriptorsDTOList": SINGLE_DESCRIPTORS,
            "spO2SingleValues": [[1, 97, True], "garbage", [2], [3, None, True], [4, 90, False]],
            "spO2HourlyAverages": [[10, 95], [20], "x"],
        }
        n = upsert_spo2_spot(temp_db, rec)
        # valid singles: (1,97) and (4,90); valid hourly: (10,95)
        assert n == 3
        assert len(_readings(temp_db, "2026-01-04")) == 2
        assert len(_hourly(temp_db, "2026-01-04")) == 1

    def test_no_date_returns_zero(self, temp_db):
        assert upsert_spo2_spot(temp_db, {"spO2SingleValues": [[1, 97, True]]}) == 0

    def test_skips_non_numeric_or_bool_timestamp(self, temp_db):
        # A non-numeric or bool timestamp must be skipped, not passed to int().
        rec = {
            "calendarDate": "2026-01-07",
            "spO2ValueDescriptorsDTOList": SINGLE_DESCRIPTORS,
            "spO2SingleValues": [["notanumber", 97, True], [True, 96, True], [12345, 95, True]],
            "spO2HourlyAverages": [["x", 95], [999, 94]],
        }
        n = upsert_spo2_spot(temp_db, rec)  # must not raise
        assert n == 2  # only (12345,95) single and (999,94) hourly survive
        rows = _readings(temp_db, "2026-01-07")
        assert [r["reading_timestamp"] for r in rows] == [12345]

    def test_plottable_is_null_when_absent(self, temp_db):
        # A 2-column single-value row has no plottable -> stored as NULL (tri-state).
        rec = {
            "calendarDate": "2026-01-08",
            "spO2ValueDescriptorsDTOList": [
                {"spo2ValueDescriptorIndex": 0, "spo2ValueDescriptorKey": "timestamp"},
                {"spo2ValueDescriptorIndex": 1, "spo2ValueDescriptorKey": "spo2Reading"},
            ],
            "spO2SingleValues": [[500, 97]],
        }
        upsert_spo2_spot(temp_db, rec)
        row = _readings(temp_db, "2026-01-08")[0]
        assert row["plottable"] is None

    def test_duplicate_timestamp_replaces(self, temp_db):
        # Two readings sharing a timestamp collapse to one (INSERT OR REPLACE on
        # the composite PK); documents the chosen behavior.
        rec = {
            "calendarDate": "2026-01-09",
            "spO2ValueDescriptorsDTOList": SINGLE_DESCRIPTORS,
            "spO2SingleValues": [[700, 97, True], [700, 90, False]],
        }
        upsert_spo2_spot(temp_db, rec)
        rows = _readings(temp_db, "2026-01-09")
        assert len(rows) == 1 and rows[0]["spo2"] == 90


class TestSaveToDbDispatch:
    def test_dispatch_stores_and_counts(self, temp_db):
        rec = {
            "calendarDate": "2026-01-05",
            "spO2ValueDescriptorsDTOList": SINGLE_DESCRIPTORS,
            "spO2SingleValues": [[1, 97, True]],
            "spO2HourlyAverages": [[2, 95]],
        }
        count = save_to_db(temp_db, "spo2_spot", rec, cal_date="2026-01-05")
        assert count == 2
        assert len(_readings(temp_db, "2026-01-05")) == 1
        assert len(_hourly(temp_db, "2026-01-05")) == 1

    def test_dispatch_drops_empty_day(self, temp_db):
        # A record with no spot-check signal fields is treated as a placeholder
        # day and dropped (0 rows written).
        count = save_to_db(temp_db, "spo2_spot", {"calendarDate": "2026-01-06"}, cal_date="2026-01-06")
        assert count == 0
        assert len(_readings(temp_db, "2026-01-06")) == 0

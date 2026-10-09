"""Tests for #85 finding 6 derivable columns:
- spo2.max_spo2 computed from the per-minute spo2ValuesArray,
- hrv.start_timestamp/end_timestamp filled from the matching hrv_timeline row.
"""

import json

from garmin_mcp.db import (
    _max_spo2_from_record,
    migrate_hrv_timestamps_from_timeline,
    migrate_spo2_max_backfill,
    upsert_spo2,
)

DESCRIPTORS = [
    {"spo2ValueDescriptorIndex": 0, "spo2ValueDescriptorKey": "timestamp"},
    {"spo2ValueDescriptorIndex": 1, "spo2ValueDescriptorKey": "spo2Reading"},
    {"spo2ValueDescriptorIndex": 2, "spo2ValueDescriptorKey": "readingConfidence"},
]


class TestMaxSpo2Helper:
    def test_picks_max_reading_by_descriptor_index(self):
        rec = {
            "spo2ValueDescriptorsDTOList": DESCRIPTORS,
            "spo2ValuesArray": [[1000, 95, 100], [2000, 98, 100], [3000, 92, 80]],
        }
        assert _max_spo2_from_record(rec) == 98

    def test_defaults_to_index_1_without_descriptors(self):
        rec = {"spo2ValuesArray": [[1000, 90], [2000, 97]]}
        assert _max_spo2_from_record(rec) == 97

    def test_empty_or_missing_array_is_none(self):
        assert _max_spo2_from_record({"spo2ValuesArray": []}) is None
        assert _max_spo2_from_record({}) is None

    def test_ignores_nonpositive_and_nonnumeric(self):
        rec = {"spo2ValuesArray": [[1, 0], [2, None], [3, 94], [4, -5]]}
        assert _max_spo2_from_record(rec) == 94

    def test_reordered_descriptors_still_pick_reading_column(self):
        # readingConfidence (index 2) listed BEFORE spo2Reading (index 1): the
        # exact-match must still select the reading column, not confidence.
        reordered = [
            {"spo2ValueDescriptorIndex": 0, "spo2ValueDescriptorKey": "timestamp"},
            {"spo2ValueDescriptorIndex": 2, "spo2ValueDescriptorKey": "readingConfidence"},
            {"spo2ValueDescriptorIndex": 1, "spo2ValueDescriptorKey": "spo2Reading"},
        ]
        rec = {
            "spo2ValueDescriptorsDTOList": reordered,
            "spo2ValuesArray": [[1000, 95, 100], [2000, 98, 100]],
        }
        assert _max_spo2_from_record(rec) == 98  # not 100 (the confidence column)

    def test_short_or_non_list_rows_are_skipped(self):
        rec = {"spo2ValuesArray": [[1000], "garbage", None, [2000, 96]]}
        assert _max_spo2_from_record(rec) == 96


class TestSpo2MaxUpsertAndBackfill:
    def test_upsert_computes_max(self, temp_db):
        upsert_spo2(
            temp_db,
            {
                "calendarDate": "2026-02-01",
                "averageSpO2": 95,
                "lowestSpO2": 90,
                "spo2ValueDescriptorsDTOList": DESCRIPTORS,
                "spo2ValuesArray": [[1, 95, 100], [2, 99, 100]],
            },
        )
        row = temp_db.execute("SELECT max_spo2 FROM spo2 WHERE calendar_date = ?", ("2026-02-01",)).fetchone()
        assert row["max_spo2"] == 99

    def test_backfill_fills_null_max(self, temp_db):
        conn = temp_db
        conn.execute(
            "INSERT INTO spo2 (calendar_date, avg_spo2, min_spo2, max_spo2, raw_json) VALUES (?, ?, ?, NULL, ?)",
            (
                "2026-02-02",
                95,
                90,
                json.dumps(
                    {
                        "spo2ValueDescriptorsDTOList": DESCRIPTORS,
                        "spo2ValuesArray": [[1, 93, 100], [2, 97, 100], [3, 96, 100]],
                    }
                ),
            ),
        )
        conn.commit()
        migrate_spo2_max_backfill(conn)
        row = conn.execute("SELECT max_spo2 FROM spo2 WHERE calendar_date = ?", ("2026-02-02",)).fetchone()
        assert row["max_spo2"] == 97

    def test_backfill_survives_malformed_raw_json(self, temp_db):
        conn = temp_db
        conn.execute(
            "INSERT INTO spo2 (calendar_date, max_spo2, raw_json) VALUES (?, NULL, ?)",
            ("2026-02-03", "not json"),
        )
        conn.commit()
        migrate_spo2_max_backfill(conn)  # must not raise
        row = conn.execute("SELECT max_spo2 FROM spo2 WHERE calendar_date = ?", ("2026-02-03",)).fetchone()
        assert row["max_spo2"] is None


class TestHrvTimestampBackfill:
    def _insert_hrv(self, conn, date):
        conn.execute(
            "INSERT INTO hrv (calendar_date, start_timestamp, end_timestamp, raw_json) VALUES (?, NULL, NULL, ?)",
            (date, json.dumps({"calendarDate": date})),
        )

    def _insert_timeline(self, conn, date, start_local, end_local):
        conn.execute(
            "INSERT INTO hrv_timeline (calendar_date, reading_count, raw_json) VALUES (?, ?, ?)",
            (
                date,
                100,
                json.dumps(
                    {
                        "startTimestampLocal": start_local,
                        "startTimestampGMT": start_local,
                        "endTimestampLocal": end_local,
                        "endTimestampGMT": end_local,
                    }
                ),
            ),
        )

    def test_fills_timestamps_from_timeline(self, temp_db):
        conn = temp_db
        self._insert_hrv(conn, "2026-02-10")
        self._insert_timeline(conn, "2026-02-10", "2026-02-09T23:00:00.0", "2026-02-10T07:00:00.0")
        conn.commit()
        migrate_hrv_timestamps_from_timeline(conn)
        row = conn.execute(
            "SELECT start_timestamp, end_timestamp FROM hrv WHERE calendar_date = ?", ("2026-02-10",)
        ).fetchone()
        assert row["start_timestamp"] == "2026-02-09T23:00:00.0"
        assert row["end_timestamp"] == "2026-02-10T07:00:00.0"

    def test_leaves_hrv_without_matching_timeline_null(self, temp_db):
        conn = temp_db
        self._insert_hrv(conn, "2026-02-11")  # no timeline row for this date
        conn.commit()
        migrate_hrv_timestamps_from_timeline(conn)
        row = conn.execute("SELECT start_timestamp FROM hrv WHERE calendar_date = ?", ("2026-02-11",)).fetchone()
        assert row["start_timestamp"] is None

    def test_does_not_overwrite_existing_timestamp(self, temp_db):
        conn = temp_db
        conn.execute(
            "INSERT INTO hrv (calendar_date, start_timestamp, raw_json) VALUES (?, ?, ?)",
            ("2026-02-12", "ORIGINAL", json.dumps({})),
        )
        self._insert_timeline(conn, "2026-02-12", "2026-02-11T23:00:00.0", "2026-02-12T07:00:00.0")
        conn.commit()
        migrate_hrv_timestamps_from_timeline(conn)
        row = conn.execute("SELECT start_timestamp FROM hrv WHERE calendar_date = ?", ("2026-02-12",)).fetchone()
        assert row["start_timestamp"] == "ORIGINAL"

    def test_uses_gmt_when_local_absent(self, temp_db):
        conn = temp_db
        self._insert_hrv(conn, "2026-02-13")
        conn.execute(
            "INSERT INTO hrv_timeline (calendar_date, reading_count, raw_json) VALUES (?, ?, ?)",
            (
                "2026-02-13",
                100,
                json.dumps({"startTimestampGMT": "2026-02-13T05:00:00.0", "endTimestampGMT": "2026-02-13T13:00:00.0"}),
            ),
        )
        conn.commit()
        migrate_hrv_timestamps_from_timeline(conn)
        row = conn.execute(
            "SELECT start_timestamp, end_timestamp FROM hrv WHERE calendar_date = ?", ("2026-02-13",)
        ).fetchone()
        assert row["start_timestamp"] == "2026-02-13T05:00:00.0"
        assert row["end_timestamp"] == "2026-02-13T13:00:00.0"

    def test_survives_malformed_timeline_json(self, temp_db):
        conn = temp_db
        self._insert_hrv(conn, "2026-02-14")
        conn.execute(
            "INSERT INTO hrv_timeline (calendar_date, reading_count, raw_json) VALUES (?, ?, ?)",
            ("2026-02-14", 0, "not json at all"),
        )
        conn.commit()
        migrate_hrv_timestamps_from_timeline(conn)  # must not raise
        row = conn.execute("SELECT start_timestamp FROM hrv WHERE calendar_date = ?", ("2026-02-14",)).fetchone()
        assert row["start_timestamp"] is None

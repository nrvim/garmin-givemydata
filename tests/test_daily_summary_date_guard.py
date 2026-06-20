"""Tests that daily_summary rows without a calendar date are not written.

A daily summary is keyed by its date. A payload without one produces a row
with ``calendar_date = NULL`` that can't be queried by date and only pollutes
the table, so ``upsert_daily_summary`` must drop it.
"""

import pytest

from garmin_mcp.db import save_to_db, upsert_daily_summary


def _row_count(conn):
    return conn.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0]


def _null_date_count(conn):
    return conn.execute("SELECT COUNT(*) FROM daily_summary WHERE calendar_date IS NULL").fetchone()[0]


@pytest.mark.unit
class TestDailySummaryDateGuard:
    def test_missing_calendar_date_is_skipped(self, temp_db):
        upsert_daily_summary(temp_db, {"totalSteps": 1000, "includesWellnessData": True})
        assert _row_count(temp_db) == 0

    def test_none_calendar_date_is_skipped(self, temp_db):
        upsert_daily_summary(temp_db, {"calendarDate": None, "totalSteps": 1000})
        assert _row_count(temp_db) == 0

    def test_blank_calendar_date_is_skipped(self, temp_db):
        upsert_daily_summary(temp_db, {"calendarDate": "   ", "totalSteps": 1000})
        assert _row_count(temp_db) == 0

    def test_valid_calendar_date_is_written(self, temp_db):
        upsert_daily_summary(temp_db, {"calendarDate": "2025-06-01", "totalSteps": 1000})
        assert _row_count(temp_db) == 1
        assert _null_date_count(temp_db) == 0

    def test_save_to_db_writes_no_null_date_row(self, temp_db):
        # Real measurements but no date: passes the empty-day filter, then the
        # date guard drops it — no NULL-date junk row lands in the table.
        rec = {"includesWellnessData": True, "totalSteps": 1234}
        save_to_db(temp_db, "daily_summary", [rec])
        assert _null_date_count(temp_db) == 0
        assert _row_count(temp_db) == 0

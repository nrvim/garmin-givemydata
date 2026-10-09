"""Tests for #85 finding 4: re-fetch recent activity details each sync so edits
made after the first sync (e.g. feel/RPE) are picked up.

Covered via the recent_activity_ids() helper that both sync paths use to pull
recently-started activities out of the "already has details, skip it" set.
"""

from garmin_mcp.db import (
    DEFAULT_REFETCH_RECENT_DAYS,
    recent_activity_ids,
    widen_start_for_refetch,
)


def _add_activity(conn, aid, start_local):
    conn.execute(
        "INSERT INTO activity (activity_id, start_time_local) VALUES (?, ?)",
        (aid, start_local),
    )


class TestRecentActivityIds:
    def test_default_is_seven(self):
        assert DEFAULT_REFETCH_RECENT_DAYS == 7

    def test_selects_only_recent(self, temp_db):
        _add_activity(temp_db, 1, "2026-10-09T08:00:00")  # today
        _add_activity(temp_db, 2, "2026-10-04T08:00:00")  # 5 days ago
        _add_activity(temp_db, 3, "2026-09-20T08:00:00")  # ~19 days ago
        temp_db.commit()
        got = recent_activity_ids(temp_db, "2026-10-09", 7)
        assert got == {1, 2}

    def test_boundary_day_is_included(self, temp_db):
        _add_activity(temp_db, 10, "2026-10-02T23:59:00")  # exactly 7 days before
        temp_db.commit()
        assert recent_activity_ids(temp_db, "2026-10-09", 7) == {10}

    def test_zero_disables(self, temp_db):
        _add_activity(temp_db, 1, "2026-10-09T08:00:00")
        temp_db.commit()
        assert recent_activity_ids(temp_db, "2026-10-09", 0) == set()
        assert recent_activity_ids(temp_db, "2026-10-09", -5) == set()

    def test_ignores_null_start(self, temp_db):
        _add_activity(temp_db, 1, None)
        temp_db.commit()
        assert recent_activity_ids(temp_db, "2026-10-09", 7) == set()

    def test_bad_today_returns_empty(self, temp_db):
        _add_activity(temp_db, 1, "2026-10-09T08:00:00")
        temp_db.commit()
        assert recent_activity_ids(temp_db, "not-a-date", 7) == set()

    def test_exclusion_set_difference(self, temp_db):
        # The sync paths do: known_activity_ids -= recent_activity_ids(...).
        _add_activity(temp_db, 1, "2026-10-09T08:00:00")  # recent
        _add_activity(temp_db, 2, "2026-01-01T08:00:00")  # old
        temp_db.commit()
        known = {1, 2}
        known -= recent_activity_ids(temp_db, "2026-10-09", 7)
        assert known == {2}  # recent activity 1 will be re-fetched; old 2 stays skipped


class TestWidenStartForRefetch:
    def test_widens_narrow_start_to_cover_window(self):
        # Default daily incremental start (yesterday) must widen back to today-7
        # so recent activities are actually in the fetched range.
        assert widen_start_for_refetch("2026-10-08", "2026-10-09", 7) == "2026-10-02"

    def test_keeps_earlier_start(self):
        # An already-wider start (e.g. a backfill) is not narrowed.
        assert widen_start_for_refetch("2026-01-01", "2026-10-09", 7) == "2026-01-01"

    def test_zero_or_negative_is_noop(self):
        assert widen_start_for_refetch("2026-10-08", "2026-10-09", 0) == "2026-10-08"
        assert widen_start_for_refetch("2026-10-08", "2026-10-09", -3) == "2026-10-08"

    def test_bad_date_returns_start_unchanged(self):
        assert widen_start_for_refetch("2026-10-08", "not-a-date", 7) == "2026-10-08"

    def test_empty_start_becomes_window(self):
        assert widen_start_for_refetch("", "2026-10-09", 7) == "2026-10-02"

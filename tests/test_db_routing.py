"""Tests for the save_to_db dispatch table in garmin_mcp.db.routing."""

import logging

import pytest

import garmin_mcp.db as db
from garmin_mcp.db import routing


@pytest.fixture
def conn(tmp_path):
    c = db.get_connection(str(tmp_path / "garmin.db"))
    db.init_db(c)
    yield c
    c.close()


def test_every_exact_route_resolves():
    for name, handler in routing._HANDLERS.items():
        assert routing._resolve_handler(name) is handler


def test_no_exact_route_is_shadowed_by_a_prefix():
    """Exact names are matched before prefixes; none may also match a prefix family."""
    for name in routing._HANDLERS:
        for prefix, _ in routing._PREFIX_HANDLERS:
            assert not name.startswith(prefix), f"{name!r} overlaps prefix {prefix!r}"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("activity_trends", routing._handle_activity_trends),
        ("activity_trends_running", routing._handle_activity_trends),
        ("activity_stats_cycling", routing._handle_activity_trends),
        ("challenges_badge", routing._handle_challenges),
        ("not_an_endpoint", None),
    ],
)
def test_prefix_and_unknown_resolution(name, expected):
    assert routing._resolve_handler(name) is expected


def test_unknown_endpoint_is_skipped_with_debug_log(conn, caplog):
    with caplog.at_level(logging.DEBUG, logger="garmin_mcp.db"):
        assert db.save_to_db(conn, "not_an_endpoint", [{"a": 1}, {"b": 2}]) == 0
    assert "no handler for endpoint 'not_an_endpoint', skipping 2 records" in caplog.text


@pytest.mark.parametrize("name", ["daily_summaries_avg", "stats_averages", "sync_timestamp"])
def test_metadata_endpoints_store_nothing(conn, name):
    assert db.save_to_db(conn, name, [{"calendarDate": "2026-01-01"}]) == 0


def test_empty_data_returns_zero(conn):
    assert db.save_to_db(conn, "daily_summary", None) == 0
    assert db.save_to_db(conn, "daily_summary", []) == 0


def test_gql_prefix_is_stripped_and_unwrapped(conn):
    payload = {"data": {"dailySummaries": [{"calendarDate": "2026-01-01", "totalSteps": 5}]}}
    assert db.save_to_db(conn, "gql_daily_summaries", payload) == 1
    assert db.query(conn, "SELECT calendar_date FROM daily_summary") == [{"calendar_date": "2026-01-01"}]


def test_vo2max_sport_follows_endpoint(conn):
    db.save_to_db(conn, "vo2max_running", [{"calendarDate": "2026-01-01", "value": 50}])
    db.save_to_db(conn, "vo2max_cycling", [{"calendarDate": "2026-01-01", "value": 45}])
    rows = db.query(conn, "SELECT sport, value FROM vo2max ORDER BY sport")
    assert rows == [{"sport": "CYCLING", "value": 45.0}, {"sport": "RUNNING", "value": 50.0}]


def test_snapshot_endpoint_replaces_table(conn):
    db.save_to_db(conn, "personal_records", [{"id": 1, "value": 10}, {"id": 2, "value": 20}])
    db.save_to_db(conn, "personal_records", [{"id": 3, "value": 30}])
    assert db.query(conn, "SELECT id FROM personal_record") == [{"id": 3}]


def test_partial_batch_is_counted_and_committed_on_error(conn, tmp_path, caplog):
    """An upsert failing mid-batch keeps the records stored before it (and commits them)."""
    payload = [{"calendarDate": "2026-01-01"}, "not-a-dict", {"calendarDate": "2026-01-03"}]
    with caplog.at_level(logging.WARNING, logger="garmin_mcp.db"):
        assert db.save_to_db(conn, "daily_summary", payload) == 1
    assert "save_to_db error for 'daily_summary'" in caplog.text
    other = db.get_connection(str(tmp_path / "garmin.db"))
    try:
        assert db.query(other, "SELECT calendar_date FROM daily_summary") == [{"calendar_date": "2026-01-01"}]
    finally:
        other.close()


def test_per_activity_endpoint_needs_activity_id(conn):
    assert db.save_to_db(conn, "activity_weather", {"temp": 10}, None) == 0
    assert db.save_to_db(conn, "activity_weather", {"temp": 10}, "123") == 1

"""Tests for the health_status GraphQL query fix.

``HealthStatusSummaryDTO`` no longer exposes ``calendarDate``/``overallStatus``/
``metricsMap``; the stale query returned a FieldUndefined validation error for
every day, and that error response was being stored as a row. The query now
requests the current ``metrics`` shape, and GraphQL error-only responses are
never stored.
"""

import pytest

from garmin_client.endpoints import daily_graphql
from garmin_mcp.db import _unwrap_gql_data, save_to_db


def _query():
    return daily_graphql("user", "2026-06-01")["health_status"]


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM health_status").fetchone()[0]


@pytest.mark.unit
class TestHealthStatusQuery:
    def test_query_drops_removed_fields(self):
        q = _query()
        assert "overallStatus" not in q
        assert "metricsMap" not in q

    def test_query_uses_current_metrics_shape(self):
        q = _query()
        assert "healthStatusSummary" in q
        assert "metrics" in q
        for field in ("type", "status", "value"):
            assert field in q


@pytest.mark.unit
class TestHealthStatusStorage:
    def test_null_node_writes_no_row(self, temp_db):
        resp = {"data": {"healthStatusSummary": None}}
        assert save_to_db(temp_db, "gql_health_status", resp, cal_date="2026-06-01") == 0
        assert _count(temp_db) == 0

    def test_populated_node_is_stored(self, temp_db):
        resp = {"data": {"healthStatusSummary": {"metrics": [{"type": "HRV", "status": "BALANCED", "value": 65}]}}}
        assert save_to_db(temp_db, "gql_health_status", resp, cal_date="2026-06-01") == 1
        row = temp_db.execute("SELECT calendar_date, raw_json FROM health_status").fetchone()
        assert row[0] == "2026-06-01"
        assert "HRV" in row[1]

    def test_validation_error_response_writes_no_row(self, temp_db):
        # The pre-fix failure mode: a FieldUndefined validation error (no data
        # key) must not be stored.
        resp = {
            "errors": [
                {
                    "message": "Validation error of type FieldUndefined: Field 'overallStatus' ...",
                    "extensions": {"classification": "ValidationError"},
                }
            ]
        }
        save_to_db(temp_db, "gql_health_status", resp, cal_date="2026-06-01")
        assert _count(temp_db) == 0


@pytest.mark.unit
class TestUnwrapGqlData:
    def test_error_only_response_unwraps_to_empty(self):
        assert _unwrap_gql_data({"errors": [{"message": "boom"}]}) == []

    def test_null_scalar_unwraps_to_empty(self):
        assert _unwrap_gql_data({"data": {"healthStatusSummary": None}}) == []

    def test_value_is_unwrapped(self):
        assert _unwrap_gql_data({"data": {"scalar": [1, 2, 3]}}) == [1, 2, 3]

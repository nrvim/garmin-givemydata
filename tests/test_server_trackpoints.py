"""Tests for the garmin_activity_trackpoints MCP tool."""

import json
import sqlite3
from unittest.mock import patch

from garmin_mcp.db import save_to_db
from garmin_mcp.server import garmin_activity_trackpoints


def _open_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _call(db_path: str, activity_id: int, limit: int = 500, offset: int = 0) -> dict:
    """Invoke the underlying function (FastMCP wraps it as a tool)."""
    fn = garmin_activity_trackpoints.fn if hasattr(garmin_activity_trackpoints, "fn") else garmin_activity_trackpoints
    with patch("garmin_mcp.tools.activities.get_connection", lambda: _open_conn(db_path)):
        return json.loads(fn(activity_id, limit=limit, offset=offset))


def test_returns_hint_when_activity_has_no_trackpoints(temp_db_file):
    result = _call(temp_db_file, activity_id=999_999_999)
    assert result["activity_id"] == 999_999_999
    assert result["total_count"] == 0
    assert "hint" in result


def test_returns_trackpoints_in_order(temp_db_file, sample_trackpoints):
    activity_id = 12345678
    conn = _open_conn(temp_db_file)
    save_to_db(conn, "activity_trackpoints", sample_trackpoints, cal_date=str(activity_id))
    conn.commit()
    conn.close()

    result = _call(temp_db_file, activity_id=activity_id)

    assert result["activity_id"] == activity_id
    assert result["total_count"] == len(sample_trackpoints)
    assert result["returned"] == len(sample_trackpoints)
    seqs = [p["seq"] for p in result["trackpoints"]]
    assert seqs == sorted(seqs)


def test_limit_and_offset_paginate_correctly(temp_db_file, sample_trackpoints):
    activity_id = 12345678
    conn = _open_conn(temp_db_file)
    save_to_db(conn, "activity_trackpoints", sample_trackpoints, cal_date=str(activity_id))
    conn.commit()
    conn.close()

    page1 = _call(temp_db_file, activity_id=activity_id, limit=2, offset=0)
    page2 = _call(temp_db_file, activity_id=activity_id, limit=2, offset=2)

    assert page1["returned"] == 2
    assert page2["returned"] == 2
    assert page1["total_count"] == len(sample_trackpoints)
    assert page1["trackpoints"][0]["seq"] == 0
    assert page2["trackpoints"][0]["seq"] == 2

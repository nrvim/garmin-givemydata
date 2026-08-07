"""Tests for the garmin_schema MCP tool."""

import json
import sqlite3
from unittest.mock import patch

from garmin_mcp import server
from garmin_mcp.server import garmin_schema


def _open_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _call(db_path: str, tables: str = "") -> dict:
    """Invoke the underlying function (FastMCP wraps it as a tool)."""
    fn = garmin_schema.fn if hasattr(garmin_schema, "fn") else garmin_schema
    with patch("garmin_mcp.server.get_connection", lambda: _open_conn(db_path)):
        return json.loads(fn(tables))


def _insert_sleep_row(db_path: str, cal_date: str = "2026-04-19"):
    conn = _open_conn(db_path)
    conn.execute("INSERT INTO sleep (calendar_date) VALUES (?)", (cal_date,))
    conn.commit()
    conn.close()


def test_index_lists_only_row_counts(temp_db_file):
    _insert_sleep_row(temp_db_file)

    result = _call(temp_db_file)

    assert result["tables"] == {"sleep": 1}
    assert "stress" in result["empty_tables"]
    # The whole point of the index: no column lists anywhere.
    assert "calendar_date" not in json.dumps(result)


def test_index_stays_small(temp_db_file):
    """Regression: the index used to dump every column of every table,
    costing ~3.8k tokens of context on each call."""
    fn = garmin_schema.fn if hasattr(garmin_schema, "fn") else garmin_schema
    with patch("garmin_mcp.server.get_connection", lambda: _open_conn(temp_db_file)):
        raw = fn("")

    assert len(raw) < 2000


def test_named_tables_return_their_columns(temp_db_file):
    _insert_sleep_row(temp_db_file)

    result = _call(temp_db_file, "sleep,stress")["tables"]

    assert set(result) == {"sleep", "stress"}
    assert result["sleep"]["row_count"] == 1
    assert result["stress"]["row_count"] == 0
    assert "deep_sleep_seconds" in result["sleep"]["columns"]
    assert "avg_stress" in result["stress"]["columns"]


def test_table_names_are_trimmed(temp_db_file):
    assert set(_call(temp_db_file, " sleep , stress ")["tables"]) == {"sleep", "stress"}


def test_epoch_ms_table_documents_its_raw_json(temp_db_file):
    """Regression: stressValuesArray is timestamped in epoch milliseconds while
    bodyBattery.data uses local ISO text, so reading one like the other groups
    every sample into its own bucket instead of failing."""
    result = _call(temp_db_file, "stress")

    assert result["tables"]["stress"]["raw_json"]["$.stressValuesArray"] == "[epoch_ms, stress]"
    assert "unixepoch" in result["timestamps"]
    assert "-2 off-wrist" in result["tables"]["stress"]["caveat"]


def test_iso_table_is_not_given_the_epoch_hint(temp_db_file):
    result = _call(temp_db_file, "body_battery")

    assert result["tables"]["body_battery"]["raw_json"]["$.bodyBattery.data"].startswith("[iso_local")
    assert "timestamps" not in result


def test_table_without_intraday_arrays_carries_no_notes(temp_db_file):
    result = _call(temp_db_file, "sleep")

    assert set(result["tables"]["sleep"]) == {"columns", "row_count"}
    assert "timestamps" not in result


def test_documented_tables_still_exist(temp_db_file):
    """A note pinned to a renamed or dropped table would silently never show up."""
    index = _call(temp_db_file)
    known = set(index["tables"]) | set(index["empty_tables"])

    assert set(server._RAW_JSON_SHAPES) <= known
    assert set(server._RAW_JSON_SENTINELS) <= known


def test_index_carries_no_raw_json_notes(temp_db_file):
    """The notes are for whoever is about to write SQL against one table —
    paying for all of them in the index would undo the slimming."""
    assert "epoch_ms" not in json.dumps(_call(temp_db_file))


def test_unknown_table_reports_available_ones(temp_db_file):
    result = _call(temp_db_file, "sleep,nope")

    assert result["unknown"] == ["nope"]
    assert "sleep" in result["available"]
    assert "columns" not in json.dumps(result)

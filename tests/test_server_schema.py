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


def _insert_raw_json(db_path: str, table: str, payload: dict, cal_date: str = "2026-04-19"):
    conn = _open_conn(db_path)
    conn.execute(
        f"INSERT INTO [{table}] (calendar_date, raw_json) VALUES (?, ?)",
        (cal_date, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


def _samples(*values):
    """An array long enough for the prober to treat it as an intraday feed."""
    return [list(v) for v in values] * 6


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
    _insert_raw_json(
        temp_db_file, "stress", {"stressValuesArray": _samples([1785874500000, 23])}
    )

    result = _call(temp_db_file, "stress")

    assert result["tables"]["stress"]["raw_json"]["$.stressValuesArray"] == "[epoch_ms, stress]"
    assert "unixepoch" in result["timestamps"]
    assert "-2 off-wrist" in result["tables"]["stress"]["caveat"]


def test_iso_table_is_not_given_the_epoch_hint(temp_db_file):
    _insert_raw_json(
        temp_db_file,
        "body_battery",
        {"bodyBattery": {"data": _samples(["2026-04-19T22:03:00.0", 45, 1, 3])}},
    )

    result = _call(temp_db_file, "body_battery")

    shape = result["tables"]["body_battery"]["raw_json"]["$.bodyBattery.data"]
    assert shape == "[iso_local, level, ?, status]"
    assert "timestamps" not in result


def test_shape_follows_the_data_not_a_declared_list(temp_db_file):
    """The point of reading the shape back: were Garmin to switch a feed from
    epoch milliseconds to ISO text, a hardcoded note would keep claiming the
    old format and send every query down the wrong path."""
    _insert_raw_json(
        temp_db_file, "stress", {"stressValuesArray": _samples(["2026-04-19T10:00:00.0", 23])}
    )

    result = _call(temp_db_file, "stress")

    assert result["tables"]["stress"]["raw_json"]["$.stressValuesArray"] == "[iso_local, stress]"
    assert "timestamps" not in result


def test_position_null_in_the_first_sample_is_still_labelled(temp_db_file):
    """Garmin leaves the leading samples of a feed null; classifying off the
    first one alone would describe a real reading as an absence."""
    _insert_raw_json(
        temp_db_file,
        "stress",
        {"bodyBatteryValuesArray": _samples([1785874500000, None, None, 3], [1785874800000, 45, 1, 3])},
    )

    shape = _call(temp_db_file, "stress")["tables"]["stress"]["raw_json"]["$.bodyBatteryValuesArray"]

    assert shape == "[epoch_ms, level, ?, status]"


def test_table_without_intraday_arrays_carries_no_notes(temp_db_file):
    _insert_sleep_row(temp_db_file)

    result = _call(temp_db_file, "sleep")

    assert set(result["tables"]["sleep"]) == {"columns", "row_count"}
    assert "timestamps" not in result


def test_empty_table_cannot_be_described(temp_db_file):
    """No stored row, nothing to read the shape from — and nothing to query
    either, so an absent note costs the caller nothing."""
    result = _call(temp_db_file, "stress")

    assert "raw_json" not in result["tables"]["stress"]


def test_documented_tables_still_exist(temp_db_file):
    """A caveat pinned to a renamed or dropped table would silently never show up."""
    index = _call(temp_db_file)
    known = set(index["tables"]) | set(index["empty_tables"])

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

"""Guard the garmin_mcp.db package split: the façade keeps the old API intact."""

import importlib
import subprocess
import sys

import pytest

import garmin_mcp.db as db

SUBMODULES = [
    "garmin_mcp.db.connection",
    "garmin_mcp.db.schema",
    "garmin_mcp.db.migrations",
    "garmin_mcp.db.backfill",
    "garmin_mcp.db.bootstrap",
    "garmin_mcp.db.routing",
    "garmin_mcp.db.upserts._common",
    "garmin_mcp.db.upserts.daily",
    "garmin_mcp.db.upserts.activities",
    "garmin_mcp.db.upserts.fitness",
    "garmin_mcp.db.upserts.profile",
]

# Names imported from garmin_mcp.db anywhere in the code base or tests.
USED_API = [
    "DB_PATH",
    "get_connection",
    "init_db",
    "save_to_db",
    "query",
    "query_readonly",
    "upsert_activity",
    "upsert_activity_trackpoints",
    "upsert_activity_exercise_sets",
    "upsert_daily_summary",
    "upsert_body_battery",
    "upsert_body_battery_from_daily_summary",
    "backfill_body_battery_from_daily_summaries",
    "migrate_activity_table",
    "migrate_hollow_tables",
    "_add_columns",
    "_backfill_from_raw",
]


@pytest.mark.parametrize("name", USED_API)
def test_facade_exports_former_api(name):
    assert hasattr(db, name), f"garmin_mcp.db no longer exports {name}"


@pytest.mark.parametrize("module", SUBMODULES)
def test_submodule_imports_standalone(module):
    """Each submodule imports on its own in a fresh interpreter (no import cycles)."""
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_db_path_is_single_source():
    connection = importlib.import_module("garmin_mcp.db.connection")
    assert db.DB_PATH == connection.DB_PATH


def test_query_readonly_reads_connection_db_path(tmp_path, monkeypatch):
    connection = importlib.import_module("garmin_mcp.db.connection")
    db_file = tmp_path / "garmin.db"
    conn = db.get_connection(str(db_file))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(connection, "DB_PATH", str(db_file))
    assert db.query_readonly("SELECT x FROM t") == [{"x": 42}]


def test_init_db_and_save_to_db_roundtrip(tmp_path):
    conn = db.get_connection(str(tmp_path / "garmin.db"))
    db.init_db(conn)
    n = db.save_to_db(conn, "daily_summary", {"calendarDate": "2026-01-01", "totalSteps": 1234})
    assert n == 1
    rows = db.query(conn, "SELECT calendar_date FROM daily_summary")
    assert rows == [{"calendar_date": "2026-01-01"}]


def test_logger_name_preserved():
    routing = importlib.import_module("garmin_mcp.db.routing")
    assert routing.log.name == "garmin_mcp.db"

"""Regression test for #85 finding 7: the test suite must not open the user's
real garmin.db.

garmin_mcp.db resolves DB_PATH at import time and garmin_mcp.server opens it +
runs init_db() at import. conftest.py forces GARMIN_DATA_DIR to a throwaway temp
dir before importing garmin_mcp, so DB_PATH must resolve under that temp dir and
never to a garmin.db in the current working directory.
"""

import os
from pathlib import Path

import garmin_mcp.db as db


def test_db_path_resolves_under_temp_data_dir():
    data_dir = os.environ.get("GARMIN_DATA_DIR")
    assert data_dir, "conftest must set GARMIN_DATA_DIR before importing garmin_mcp"
    assert Path(db.DB_PATH).resolve() == (Path(data_dir) / "garmin.db").resolve()


def test_db_path_is_not_the_cwd_database():
    # Even when a real garmin.db sits in the CWD (a cloned install dir), the
    # forced GARMIN_DATA_DIR must win, so tests never touch it.
    assert Path(db.DB_PATH).resolve() != (Path.cwd() / "garmin.db").resolve()

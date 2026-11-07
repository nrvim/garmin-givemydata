"""Every MCP tool must close the database connection it opens, also when a query fails."""

import importlib

import pytest

import garmin_mcp.db as db
from garmin_mcp import server

TOOL_MODULES = ["core", "background_sync", "summary", "daily", "activities", "fitness", "profile"]

ARGS = {
    "garmin_query": {"sql": "SELECT 1"},
    "garmin_trends": {"metric": "resting_hr"},
    "garmin_activity_trackpoints": {"activity_id": 1},
    "garmin_compare": {
        "period1_start": "2026-01-01",
        "period1_end": "2026-01-31",
        "period2_start": "2026-02-01",
        "period2_end": "2026-02-28",
    },
    "garmin_sync": {"refresh": False},
}

# Tools that do not open a connection through get_connection().
NO_CONNECTION = {"garmin_query"}  # uses query_readonly, which manages its own read-only connection


class TrackedConnection:
    """Proxy around a real sqlite3 connection that records close() and can fail on execute()."""

    def __init__(self, real, fail):
        self._real = real
        self._fail = fail
        self.closed = False

    def execute(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError("simulated query failure")
        return self._real.execute(*args, **kwargs)

    def close(self):
        self.closed = True
        self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def tracked(tmp_path, monkeypatch):
    path = str(tmp_path / "garmin.db")
    setup = db.get_connection(path)
    db.init_db(setup)
    setup.close()
    opened = []
    state = {"fail": False}

    def factory(*_args, **_kwargs):
        conn = TrackedConnection(db.get_connection(path), state["fail"])
        opened.append(conn)
        return conn

    for name in TOOL_MODULES:
        monkeypatch.setattr(importlib.import_module(f"garmin_mcp.tools.{name}"), "get_connection", factory)
    return opened, state


@pytest.mark.parametrize("fail", [False, True], ids=["ok", "query-fails"])
@pytest.mark.parametrize("tool", server.TOOLS, ids=lambda f: f.__name__)
def test_tool_closes_its_connection(tracked, tool, fail):
    opened, state = tracked
    state["fail"] = fail
    try:
        tool(**ARGS.get(tool.__name__, {}))
    except RuntimeError:
        pass  # tools without their own error handling let the failure propagate; closing still matters
    if tool.__name__ not in NO_CONNECTION:
        assert opened, f"{tool.__name__} did not open a connection"
    assert all(c.closed for c in opened), f"{tool.__name__} left a connection open"

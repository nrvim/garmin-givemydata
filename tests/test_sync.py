"""Regression tests for garmin_mcp.sync."""

import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_DIR = Path(__file__).resolve().parent.parent


class TestIncrementalSyncChdir(unittest.TestCase):
    """Issue #35 bug 1: incremental_sync must chdir to PROJECT_DIR before
    SeleniumBase launches. The host CWD when run as an MCP server can be
    a system path with no write access (e.g. C:\\Windows\\System32 on
    Windows), and SeleniumBase tries to create downloaded_files/ relative
    to CWD, which crashes with PermissionError.
    """

    def setUp(self):
        self._original_cwd = os.getcwd()

    def tearDown(self):
        try:
            os.chdir(self._original_cwd)
        except OSError:
            pass

    def test_incremental_sync_chdirs_to_project_dir(self):
        # Simulate an MCP launch from a different CWD. Use a temp dir so
        # the test runs on every platform (Windows has no /tmp).
        with tempfile.TemporaryDirectory() as starting_cwd:
            os.chdir(starting_cwd)
            self.assertNotEqual(Path(os.getcwd()).resolve(), PROJECT_DIR)

            mock_client_cls = MagicMock()
            mock_client_cls.return_value.login.return_value = False  # short-circuit
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []

            with (
                patch("garmin_client.GarminClient", mock_client_cls),
                patch("garmin_mcp.sync.get_connection", return_value=mock_conn),
                patch("garmin_mcp.sync.init_db"),
                patch.dict(os.environ, {"GARMIN_EMAIL": "x", "GARMIN_PASSWORD": "y"}),
            ):
                from garmin_mcp.sync import incremental_sync

                incremental_sync()

            self.assertEqual(Path(os.getcwd()).resolve(), PROJECT_DIR)


class TestCatchUpStart(unittest.TestCase):
    """The default sync window used to be yesterday..today, so activities
    recorded between the previous sync and yesterday were never fetched by
    garmin_sync. The window must start the day before the last ok sync."""

    TODAY = "2026-10-09"

    def setUp(self):
        from garmin_mcp.db import init_db

        self.conn = sqlite3.connect(":memory:")
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _log(self, sync_date, status="ok"):
        self.conn.execute(
            "INSERT INTO sync_log (sync_date, sync_type, records_upserted, status) VALUES (?, ?, ?, ?)",
            (sync_date, "incremental_sync", 1, status),
        )

    def _start(self):
        from garmin_mcp.sync import _catch_up_start

        return _catch_up_start(self.conn, self.TODAY)

    def test_no_previous_sync_defaults_to_yesterday(self):
        self.assertEqual(self._start(), "2026-10-08")

    def test_gap_since_last_sync_is_covered(self):
        self._log("2026-10-02T16:46:46.673462+00:00")
        self.assertEqual(self._start(), "2026-10-01")

    def test_failed_syncs_are_ignored(self):
        self._log("2026-10-02T16:46:46+00:00")
        self._log("2026-10-08T10:00:00+00:00", status="error")
        self.assertEqual(self._start(), "2026-10-01")

    def test_recent_sync_still_includes_yesterday(self):
        self._log("2026-10-09T07:00:00+00:00")
        self.assertEqual(self._start(), "2026-10-08")

    def test_long_gap_is_capped(self):
        from garmin_mcp.sync import MAX_CATCH_UP_DAYS

        self._log("2026-01-01T00:00:00+00:00")
        self.assertEqual(self._start(), (date(2026, 10, 9) - timedelta(days=MAX_CATCH_UP_DAYS)).isoformat())


if __name__ == "__main__":
    unittest.main()

"""Regression tests for garmin_mcp.sync."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import garmin_givemydata


class TestIncrementalSyncChdir(unittest.TestCase):
    """Issue #35 bug 1: incremental_sync must chdir to DATA_DIR before
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

    def test_incremental_sync_chdirs_to_data_dir(self):
        # Simulate an MCP launch from a different CWD. Use a temp dir so
        # the test runs on every platform (Windows has no /tmp).
        with tempfile.TemporaryDirectory() as starting_cwd:
            os.chdir(starting_cwd)
            self.assertNotEqual(Path(os.getcwd()).resolve(), garmin_givemydata.DATA_DIR.resolve())

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

            self.assertEqual(Path(os.getcwd()).resolve(), garmin_givemydata.DATA_DIR.resolve())


class TestIncrementalSyncCredentialResolution(unittest.TestCase):
    """``garmin_sync`` resolved ``.env``, the browser profile and the session
    file relative to the installed package (``Path(__file__).parent.parent``)
    instead of the data directory. On pip/pipx/brew installs that is
    site-packages, where no ``.env`` exists, so every MCP sync returned
    "Credentials not found" while the CLI worked. Same bug as #53, sync path."""

    def setUp(self):
        self._original_cwd = os.getcwd()

    def tearDown(self):
        try:
            os.chdir(self._original_cwd)
        except OSError:
            pass

    def test_credentials_and_paths_come_from_data_dir(self):
        captured = {}

        class FakeClient:
            def __init__(self, email=None, password=None, profile_dir=None, session_file=None, **kwargs):
                captured.update(email=email, profile_dir=profile_dir, session_file=session_file)

            def login(self):
                return False  # stop before any network/browser

            def close(self):
                pass

        def fake_load_env():
            # Simulates load_env() reading DATA_DIR/.env into the environment.
            os.environ["GARMIN_EMAIL"] = "datadir@example.com"
            os.environ["GARMIN_PASSWORD"] = "from-data-dir"

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with (
            patch("garmin_client.GarminClient", FakeClient),
            patch.object(garmin_givemydata, "load_env", fake_load_env),
            patch("garmin_mcp.sync.get_connection", return_value=mock_conn),
            patch("garmin_mcp.sync.init_db"),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("GARMIN_EMAIL", None)
            os.environ.pop("GARMIN_PASSWORD", None)
            from garmin_mcp.sync import incremental_sync

            result = incremental_sync()

        self.assertEqual(result, {"status": "error", "message": "Login failed"})
        self.assertEqual(captured.get("email"), "datadir@example.com")
        self.assertEqual(captured.get("profile_dir"), garmin_givemydata.PROFILE_DIR)
        self.assertEqual(captured.get("session_file"), garmin_givemydata.SESSION_FILE)


if __name__ == "__main__":
    unittest.main()

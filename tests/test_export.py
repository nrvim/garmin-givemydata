"""Regression tests for garmin_mcp.export."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import garmin_givemydata
from garmin_mcp import export


class TestExportJsonTables(unittest.TestCase):
    def _make_db(self, tmpdir: Path, table: str, columns_sql: str, rows: list[tuple]) -> Path:
        db_path = tmpdir / "test.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(f"CREATE TABLE {table} ({columns_sql})")
        placeholders = ", ".join("?" * len(rows[0]))
        conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        conn.commit()
        conn.close()
        return db_path

    def _run_export(self, db_path: Path, output_dir: Path):
        def _connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(export, "get_connection", _connect):
            export.export_json_tables(output_dir)

    def test_array_rooted_raw_json_does_not_crash(self):
        # Regression for issue #34: activity_hr_zones stores a JSON array
        # at the root of raw_json. The merge loop used to crash with
        # "TypeError: list indices must be integers or slices, not str".
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            zones = [
                {"secsInZone": 60, "zoneNumber": 1},
                {"secsInZone": 120, "zoneNumber": 2},
            ]
            db_path = self._make_db(
                tmpdir,
                "activity_hr_zones",
                "activity_id INTEGER, raw_json TEXT",
                [(12345, json.dumps(zones))],
            )
            output_dir = tmpdir / "out"
            self._run_export(db_path, output_dir)

            payload = json.loads((output_dir / "activity_hr_zones.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["items"], zones)
            self.assertEqual(payload[0]["__activity_id"], 12345)

    def test_object_rooted_raw_json_unchanged(self):
        # Object roots keep their existing shape: raw fields at top level
        # plus structured columns prefixed with "__".
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            raw = {"avgHr": 135, "maxHr": 170}
            db_path = self._make_db(
                tmpdir,
                "activity",
                "activity_id INTEGER, avg_hr INTEGER, raw_json TEXT",
                [(12345, 135, json.dumps(raw))],
            )
            output_dir = tmpdir / "out"
            self._run_export(db_path, output_dir)

            payload = json.loads((output_dir / "activity.json").read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["avgHr"], 135)
            self.assertEqual(payload[0]["maxHr"], 170)
            self.assertEqual(payload[0]["__activity_id"], 12345)
            self.assertEqual(payload[0]["__avg_hr"], 135)
            self.assertNotIn("items", payload[0])


class TestExportCredentialResolution(unittest.TestCase):
    """Regression for issue #53: ``--export-gpx`` resolved ``.env`` relative to
    the installed package (``Path(__file__).parent.parent``) instead of the data
    directory, so pip/pipx/brew installs printed "Credentials not found" because
    no ``.env`` sits next to the package. The download path must load credentials
    via the main module's ``load_env()`` (which reads ``DATA_DIR/.env``)."""

    def test_credentials_loaded_via_data_dir_load_env(self):
        captured = {}

        class FakeClient:
            def __init__(self, email=None, password=None, profile_dir=None, **kwargs):
                captured["email"] = email
                captured["profile_dir"] = profile_dir

            def login(self):
                return False  # stop before any network/browser

            def close(self):
                pass

        def fake_load_env():
            # Simulates load_env() reading DATA_DIR/.env into the environment.
            os.environ["GARMIN_EMAIL"] = "datadir@example.com"
            os.environ["GARMIN_PASSWORD"] = "from-data-dir"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gpx"
            with (
                patch("garmin_client.GarminClient", FakeClient),
                patch.object(garmin_givemydata, "load_env", fake_load_env),
            ):
                os.environ.pop("GARMIN_EMAIL", None)
                os.environ.pop("GARMIN_PASSWORD", None)
                # activity_ids given explicitly so no DB lookup is needed.
                export.download_activity_files(out, file_format="gpx", activity_ids=[123])

        # Credentials must have come from the data-dir loader, proving the path
        # resolution bug is fixed (otherwise email would be "" -> early return).
        self.assertEqual(captured.get("email"), "datadir@example.com")
        self.assertEqual(captured.get("profile_dir"), garmin_givemydata.PROFILE_DIR)


if __name__ == "__main__":
    unittest.main()

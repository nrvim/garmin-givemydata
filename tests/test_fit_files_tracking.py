"""Tests for FIT parse tracking and trackpoint backfill reconciliation.

Trackpoints used to be parsed only for freshly downloaded FIT files, so FIT
archives kept on disk across a DB wipe (or restored from elsewhere) were never
parsed. The ``fit_files`` table records every parse — including GPS-less
activities marked 'skipped' — so a sync reconciles on-disk files against it
without re-parsing every run.
"""

import pytest

import garmin_givemydata as ggm
from garmin_mcp.db import record_fit_parse


@pytest.mark.unit
class TestFitFilesTable:
    def test_table_exists(self, temp_db):
        cols = {r[1] for r in temp_db.execute("PRAGMA table_info(fit_files)")}
        assert {"filename", "activity_id", "status", "point_count", "parsed_at"} <= cols

    def test_record_fit_parse_inserts(self, temp_db):
        record_fit_parse(temp_db, "2025-01-01_111_Run.zip", 111, "ingested", 1234)
        row = temp_db.execute("SELECT filename, activity_id, status, point_count FROM fit_files").fetchone()
        assert tuple(row) == ("2025-01-01_111_Run.zip", 111, "ingested", 1234)

    def test_record_fit_parse_upserts_by_filename(self, temp_db):
        record_fit_parse(temp_db, "f.zip", 1, "failed", 0)
        record_fit_parse(temp_db, "f.zip", 1, "ingested", 42)
        rows = temp_db.execute("SELECT status, point_count FROM fit_files WHERE filename='f.zip'").fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == ("ingested", 42)


@pytest.mark.unit
class TestBackfillUnparsedFit:
    def _make_fit(self, d, name):
        (d / name).write_bytes(b"PK\x03\x04")

    def _fake_save(self):
        # Mirror _save_trackpoints_from_fit: record the parse, return (status, count).
        def fake(conn, path):
            if "333" in path.name:  # pretend this activity has no GPS
                record_fit_parse(conn, path.name, 333, "skipped", 0)
                return "skipped", 0
            aid = int(path.stem.split("_")[1])
            record_fit_parse(conn, path.name, aid, "ingested", 5)
            return "ingested", 5

        return fake

    def test_parses_all_then_is_idempotent(self, temp_db, tmp_path, monkeypatch):
        for n in ("2025-01-01_111_Run.zip", "2025-01-02_222_Ride.zip", "2025-01-03_333_Strength.zip"):
            self._make_fit(tmp_path, n)
        monkeypatch.setattr(ggm, "_save_trackpoints_from_fit", self._fake_save())

        first = ggm._backfill_unparsed_fit(temp_db, tmp_path)
        assert first["targeted"] == 3
        assert first["ingested"] == 2
        assert first["skipped"] == 1
        assert temp_db.execute("SELECT COUNT(*) FROM fit_files").fetchone()[0] == 3

        # Second run: every file (incl. the GPS-less 'skipped' one) is recorded,
        # so nothing is re-parsed.
        second = ggm._backfill_unparsed_fit(temp_db, tmp_path)
        assert second["targeted"] == 0

    def test_only_new_file_is_parsed_on_next_run(self, temp_db, tmp_path, monkeypatch):
        self._make_fit(tmp_path, "2025-01-01_111_Run.zip")
        monkeypatch.setattr(ggm, "_save_trackpoints_from_fit", self._fake_save())

        assert ggm._backfill_unparsed_fit(temp_db, tmp_path)["targeted"] == 1

        # A new activity's FIT lands later.
        self._make_fit(tmp_path, "2025-02-02_222_Ride.zip")
        result = ggm._backfill_unparsed_fit(temp_db, tmp_path)
        assert result["targeted"] == 1
        assert result["ingested"] == 1

    def test_missing_dir_is_safe(self, temp_db, tmp_path):
        result = ggm._backfill_unparsed_fit(temp_db, tmp_path / "does-not-exist")
        assert result["targeted"] == 0

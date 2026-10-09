"""Tests for the post-#84 audit hygiene migrations (#85):
- training_status backfill from raw_json (older rows left status/load NULL),
- cleanup of NULL-calendar_date daily_summary wrapper rows,
- cleanup of body_battery GraphQL error-envelope rows.
"""

import json

from garmin_mcp.db import (
    cleanup_body_battery_error_rows,
    cleanup_daily_summary_wrappers,
    migrate_training_status_backfill,
)


class TestTrainingStatusBackfill:
    def _insert_null_row(self, conn, date, record):
        conn.execute(
            """INSERT OR REPLACE INTO training_status
               (calendar_date, status, acute_load, chronic_load, raw_json)
               VALUES (?, NULL, NULL, NULL, ?)""",
            (date, json.dumps(record)),
        )
        conn.commit()

    def test_backfills_status_and_loads_from_raw_json(self, temp_db):
        record = {
            "latestTrainingStatusData": {
                "3447746126": {
                    "trainingStatusFeedbackPhrase": "PRODUCTIVE_1",
                    "calendarDate": "2026-03-01",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 350,
                        "dailyTrainingLoadChronic": 420,
                    },
                }
            }
        }
        self._insert_null_row(temp_db, "2026-03-01", record)

        migrate_training_status_backfill(temp_db)

        row = temp_db.execute(
            "SELECT status, acute_load, chronic_load FROM training_status WHERE calendar_date = ?",
            ("2026-03-01",),
        ).fetchone()
        assert row["status"] == "PRODUCTIVE_1"
        assert row["acute_load"] == 350
        assert row["chronic_load"] == 420

    def test_is_idempotent(self, temp_db):
        record = {
            "latestTrainingStatusData": {
                "1": {
                    "trainingStatusFeedbackPhrase": "MAINTAINING_1",
                    "calendarDate": "2026-03-02",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 100,
                        "dailyTrainingLoadChronic": 110,
                    },
                }
            }
        }
        self._insert_null_row(temp_db, "2026-03-02", record)
        migrate_training_status_backfill(temp_db)
        # second pass must be a no-op (row no longer matches status IS NULL)
        migrate_training_status_backfill(temp_db)
        rows = temp_db.execute("SELECT status FROM training_status WHERE calendar_date = ?", ("2026-03-02",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "MAINTAINING_1"

    def test_leaves_rows_without_nested_data_untouched(self, temp_db):
        # A NULL-status row whose raw_json has no latestTrainingStatusData object
        # must not be touched (nothing to derive).
        conn = temp_db
        conn.execute(
            """INSERT OR REPLACE INTO training_status
               (calendar_date, status, acute_load, chronic_load, raw_json)
               VALUES (?, NULL, NULL, NULL, ?)""",
            ("2026-03-03", json.dumps({"somethingElse": 1})),
        )
        conn.commit()
        migrate_training_status_backfill(conn)
        row = conn.execute("SELECT status FROM training_status WHERE calendar_date = ?", ("2026-03-03",)).fetchone()
        assert row["status"] is None

    def test_pins_write_to_selected_pk_not_embedded_date(self, temp_db):
        # Regression for the review finding: a row stored under one PK whose
        # raw_json embeds a DIFFERENT calendarDate (as the weekly path can do).
        # The backfill must fix the selected row and must NOT create a row at,
        # or clobber, the embedded date.
        conn = temp_db
        record = {
            "latestTrainingStatusData": {
                "9": {
                    "trainingStatusFeedbackPhrase": "PEAKING_1",
                    "calendarDate": "2026-04-10",  # different from the stored PK
                    "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 7, "dailyTrainingLoadChronic": 9},
                }
            }
        }
        self._insert_null_row(conn, "2026-04-01", record)  # stored under 2026-04-01
        # a real, populated row already exists at the embedded date
        conn.execute(
            """INSERT OR REPLACE INTO training_status
               (calendar_date, status, acute_load, chronic_load, raw_json)
               VALUES (?, 'REAL', 100, 110, ?)""",
            ("2026-04-10", json.dumps({"preexisting": True})),
        )
        conn.commit()

        migrate_training_status_backfill(conn)

        # selected row (PK 2026-04-01) is fixed
        fixed = conn.execute("SELECT status FROM training_status WHERE calendar_date = ?", ("2026-04-01",)).fetchone()
        assert fixed["status"] == "PEAKING_1"
        # the embedded-date row was NOT clobbered
        other = conn.execute(
            "SELECT status, acute_load FROM training_status WHERE calendar_date = ?", ("2026-04-10",)
        ).fetchone()
        assert other["status"] == "REAL" and other["acute_load"] == 100

    def test_survives_malformed_raw_json(self, temp_db):
        # A legacy row with non-JSON raw_json must not abort the migration.
        conn = temp_db
        conn.execute(
            """INSERT OR REPLACE INTO training_status
               (calendar_date, status, acute_load, chronic_load, raw_json)
               VALUES (?, NULL, NULL, NULL, ?)""",
            ("2026-04-02", "not json at all"),
        )
        conn.commit()
        migrate_training_status_backfill(conn)  # must not raise
        row = conn.execute("SELECT status FROM training_status WHERE calendar_date = ?", ("2026-04-02",)).fetchone()
        assert row["status"] is None


class TestDailySummaryWrapperCleanup:
    def test_removes_null_date_wrapper_rows_only(self, temp_db):
        conn = temp_db
        # a wrapper row: NULL calendar_date, raw_json is a {"data": [...]} range payload
        conn.execute(
            "INSERT INTO daily_summary (calendar_date, raw_json) VALUES (NULL, ?)",
            (json.dumps({"data": [{"calendarDate": "2026-01-01"}, {"calendarDate": "2026-01-02"}]}),),
        )
        # a real per-day row that must survive
        conn.execute(
            "INSERT INTO daily_summary (calendar_date, total_steps, raw_json) VALUES (?, ?, ?)",
            ("2026-01-01", 5000, json.dumps({"calendarDate": "2026-01-01", "totalSteps": 5000})),
        )
        conn.commit()

        cleanup_daily_summary_wrappers(conn)

        assert conn.execute("SELECT COUNT(*) FROM daily_summary WHERE calendar_date IS NULL").fetchone()[0] == 0
        kept = conn.execute("SELECT total_steps FROM daily_summary WHERE calendar_date = ?", ("2026-01-01",)).fetchone()
        assert kept["total_steps"] == 5000

    def test_keeps_null_date_row_that_is_not_a_wrapper(self, temp_db):
        # A NULL-date row whose raw_json has no $.data array is not our signature.
        conn = temp_db
        conn.execute(
            "INSERT INTO daily_summary (calendar_date, raw_json) VALUES (NULL, ?)",
            (json.dumps({"calendarDate": None, "totalSteps": 1}),),
        )
        conn.commit()
        cleanup_daily_summary_wrappers(conn)
        assert conn.execute("SELECT COUNT(*) FROM daily_summary WHERE calendar_date IS NULL").fetchone()[0] == 1


class TestBodyBatteryErrorCleanup:
    def test_removes_error_envelope_rows_only(self, temp_db):
        conn = temp_db
        conn.execute(
            "INSERT INTO body_battery (calendar_date, raw_json) VALUES (?, ?)",
            ("2025-05-05", json.dumps({"data": {"epochChartScalar": None}, "errors": [{"message": "Bulkhead"}]})),
        )
        conn.execute(
            "INSERT INTO body_battery (calendar_date, highest, lowest, raw_json) VALUES (?, ?, ?, ?)",
            ("2025-05-06", 90, 20, json.dumps({"highest": 90, "lowest": 20})),
        )
        conn.commit()

        cleanup_body_battery_error_rows(conn)

        assert (
            conn.execute("SELECT COUNT(*) FROM body_battery WHERE calendar_date = ?", ("2025-05-05",)).fetchone()[0]
            == 0
        )
        kept = conn.execute("SELECT highest FROM body_battery WHERE calendar_date = ?", ("2025-05-06",)).fetchone()
        assert kept["highest"] == 90

    def test_keeps_errors_row_that_still_has_real_data(self, temp_db):
        # Regression for the review finding: a partial-success response that
        # carries an errors array AND real body-battery values must be kept.
        conn = temp_db
        conn.execute(
            "INSERT INTO body_battery (calendar_date, highest, lowest, raw_json) VALUES (?, ?, ?, ?)",
            ("2025-06-01", 88, 25, json.dumps({"highest": 88, "lowest": 25, "errors": [{"message": "warn"}]})),
        )
        conn.commit()
        cleanup_body_battery_error_rows(conn)
        row = conn.execute("SELECT highest FROM body_battery WHERE calendar_date = ?", ("2025-06-01",)).fetchone()
        assert row is not None and row["highest"] == 88

    def test_survives_malformed_raw_json(self, temp_db):
        # A legacy non-JSON row must not abort the cleanup (json_valid guard).
        conn = temp_db
        conn.execute(
            "INSERT INTO body_battery (calendar_date, raw_json) VALUES (?, ?)",
            ("2025-06-02", "<<not json>>"),
        )
        conn.commit()
        cleanup_body_battery_error_rows(conn)  # must not raise
        assert (
            conn.execute("SELECT COUNT(*) FROM body_battery WHERE calendar_date = ?", ("2025-06-02",)).fetchone()[0]
            == 1
        )

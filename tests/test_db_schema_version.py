"""Tests for versioned migrations (PRAGMA user_version) in garmin_mcp.db.bootstrap."""

import logging
import sqlite3

import pytest

import garmin_mcp.db as db
from garmin_mcp.db import bootstrap

# The order init_db used before versioning. MIGRATIONS must start with exactly
# this sequence; new migrations may only be appended after it.
LEGACY_ORDER = [
    "migrate_weight_table",
    "migrate_device_table",
    "migrate_training_status_table",
    "migrate_activity_splits_table",
    "migrate_activity_splits_v2",
    "migrate_hrv_table",
    "migrate_sleep_table",
    "migrate_heart_rate_table",
    "migrate_spo2_table",
    "migrate_respiration_table",
    "migrate_hydration_table",
    "migrate_weight_table_v2",
    "migrate_endurance_score_table",
    "migrate_hill_score_table",
    "migrate_gear_table",
    "migrate_gear_table_v2",
    "migrate_hollow_tables",
    "migrate_sleep_table_v2",
    "migrate_fitness_age_table",
    "migrate_weight_table_v3",
    "migrate_activity_table",
]


def _conn(path):
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture
def spies(monkeypatch):
    """Replace MIGRATIONS with recording wrappers around the real migrations."""
    calls = []

    def wrap(fn):
        def spy(conn):
            calls.append(fn.__name__)
            fn(conn)

        spy.__name__ = fn.__name__
        return spy

    monkeypatch.setattr(bootstrap, "MIGRATIONS", tuple(wrap(m) for m in bootstrap.MIGRATIONS))
    return calls


def test_migrations_keep_legacy_order_append_only():
    names = [m.__name__ for m in bootstrap.MIGRATIONS]
    assert names[: len(LEGACY_ORDER)] == LEGACY_ORDER
    assert len(set(names)) == len(names)
    assert bootstrap.SCHEMA_VERSION == len(bootstrap.MIGRATIONS)


def test_fresh_database_ends_at_latest_version(tmp_path):
    conn = _conn(tmp_path / "g.db")
    db.init_db(conn)
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION


def test_up_to_date_database_skips_all_migrations(tmp_path, spies):
    conn = _conn(tmp_path / "g.db")
    db.init_db(conn)
    assert spies == LEGACY_ORDER  # first start: everything, in the legacy order
    spies.clear()
    db.init_db(conn)
    assert spies == []


def test_unversioned_database_runs_every_migration_once(tmp_path, spies):
    conn = _conn(tmp_path / "g.db")
    db.init_db(conn)
    conn.execute("PRAGMA user_version = 0")  # a database created before versioning
    conn.commit()
    spies.clear()
    db.init_db(conn)
    assert spies == LEGACY_ORDER
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION


def test_only_pending_migrations_run(tmp_path, spies):
    conn = _conn(tmp_path / "g.db")
    db.init_db(conn)
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION - 2}")
    conn.commit()
    spies.clear()
    assert db.run_migrations(conn) == 2
    assert spies == LEGACY_ORDER[-2:]


def test_newer_database_is_left_alone(tmp_path, spies, caplog):
    conn = _conn(tmp_path / "g.db")
    db.init_db(conn)
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 5}")
    conn.commit()
    spies.clear()
    with caplog.at_level(logging.WARNING, logger="garmin_mcp.db"):
        db.init_db(conn)
    assert spies == []
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION + 5
    assert "newer than this code supports" in caplog.text


def test_failed_migration_resumes_from_that_migration(tmp_path, monkeypatch):
    conn = _conn(tmp_path / "g.db")
    conn.executescript(bootstrap._SCHEMA_SQL)
    real = bootstrap.MIGRATIONS
    fail_at = 5  # the 5th migration raises

    def boom(c):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(bootstrap, "MIGRATIONS", real[: fail_at - 1] + (boom,) + real[fail_at:])
    with pytest.raises(RuntimeError):
        db.init_db(conn)
    assert db.get_schema_version(conn) == fail_at - 1  # versions 1..4 are committed

    monkeypatch.setattr(bootstrap, "MIGRATIONS", real)
    db.init_db(conn)
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION


def test_legacy_weight_table_is_upgraded_and_versioned(tmp_path):
    """A real pre-versioning shape: weight without the timestamp primary key."""
    path = tmp_path / "g.db"
    conn = _conn(path)
    conn.execute(
        "CREATE TABLE weight (calendar_date TEXT PRIMARY KEY, weight REAL, bmi REAL, body_fat REAL,"
        " body_water REAL, bone_mass REAL, muscle_mass REAL, raw_json TEXT)"
    )
    conn.execute(
        "INSERT INTO weight (calendar_date, weight, raw_json) VALUES ('2026-01-01', 80000, '{\"date\": 1767225600000}')"
    )
    conn.commit()
    assert db.get_schema_version(conn) == 0
    db.init_db(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(weight)")}
    assert {"timestamp", "source", "metabolic_age", "visceral_fat"} <= cols
    assert db.query(conn, "SELECT timestamp, weight FROM weight") == [{"timestamp": 1767225600000, "weight": 80000.0}]
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION

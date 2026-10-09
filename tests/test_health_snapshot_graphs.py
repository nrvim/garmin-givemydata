"""Tests for #86 part 2: per-second Health Snapshot graphs.

The FIT parser is exercised with a fake FitFile (no real binary needed); the
readings table + upsert and the self-check aggregator are tested directly.
"""

import json
from datetime import datetime

import garmin_mcp.parse_activity_files as paf
from garmin_mcp.db import upsert_health_snapshot_readings
from garmin_mcp.parse_activity_files import (
    parse_health_snapshot_fit,
    snapshot_reading_summary,
)


class _FakeField:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _FakeMsg:
    def __init__(self, d):
        self._d = d

    def __iter__(self):
        return iter(_FakeField(k, v) for k, v in self._d.items())


class _FakeFit:
    """Reads a JSON list of record dicts from the 'blob'; converts the
    timestamp string to a datetime so the parser sees a real datetime."""

    def __init__(self, bio):
        self._records = json.loads(bio.read().decode())

    def get_messages(self, name):
        assert name == "record"
        for d in self._records:
            d = dict(d)
            if d.get("timestamp"):
                d["timestamp"] = datetime.fromisoformat(d["timestamp"])
            yield _FakeMsg(d)


def _blob(records):
    return json.dumps(records).encode()


def _records(n=3, base_hr=60):
    # 108=respiration x100, 116=stress x100, 133=SpO2
    out = []
    for i in range(n):
        out.append(
            {
                "timestamp": f"2025-04-30T17:08:{17 + i:02d}",
                "heart_rate": base_hr + i,
                "unknown_108": 1800 + i * 10,  # 18.0, 18.1, 18.2
                "unknown_116": 1500,  # 15
                "unknown_133": 99 - i,
                "unknown_136": base_hr + i,  # HR duplicate, ignored
            }
        )
    return out


class TestParseHealthSnapshotFit:
    def test_maps_inferred_fields(self, monkeypatch):
        monkeypatch.setattr(paf, "FitFile", _FakeFit)
        out = parse_health_snapshot_fit(_blob(_records(3, base_hr=60)))
        assert out["start_time"] == "2025-04-30T17:08:17"
        assert out["readings"] == [
            (0, 60, 18.0, 15, 99),
            (1, 61, 18.1, 15, 98),
            (2, 62, 18.2, 15, 97),
        ]

    def test_missing_fields_become_none(self, monkeypatch):
        monkeypatch.setattr(paf, "FitFile", _FakeFit)
        out = parse_health_snapshot_fit(_blob([{"timestamp": "2025-04-30T17:08:17", "heart_rate": 60}]))
        assert out["readings"] == [(0, 60, None, None, None)]

    def test_records_without_timestamp_skipped(self, monkeypatch):
        monkeypatch.setattr(paf, "FitFile", _FakeFit)
        recs = [{"heart_rate": 99}, {"timestamp": "2025-04-30T17:08:17", "heart_rate": 60}]
        out = parse_health_snapshot_fit(_blob(recs))
        assert len(out["readings"]) == 1 and out["readings"][0][1] == 60


class TestSummaryAggregator:
    def test_agg_matches_expected(self):
        readings = [(0, 59, 18.0, 12, 100), (1, 70, 21.0, 19, 93), (2, 63, 18.17, 15, 99)]
        s = snapshot_reading_summary(readings)
        assert s["heart_rate"] == {"avg": round((59 + 70 + 63) / 3, 2), "min": 59, "max": 70}
        assert s["spo2"]["min"] == 93 and s["spo2"]["max"] == 100
        assert s["stress"]["min"] == 12 and s["stress"]["max"] == 19

    def test_all_none_metric_is_none(self):
        readings = [(0, 60, None, None, None)]
        s = snapshot_reading_summary(readings)
        assert s["respiration"] is None and s["heart_rate"] == {"avg": 60, "min": 60, "max": 60}


class TestReadingsUpsert:
    def test_stores_and_counts(self, temp_db):
        readings = [(0, 60, 18.0, 15, 99), (1, 61, 18.1, 15, 98)]
        n = upsert_health_snapshot_readings(temp_db, "snap-1", readings)
        assert n == 2
        rows = temp_db.execute(
            "SELECT reading_index, heart_rate, respiration, stress, spo2 FROM health_snapshot_reading "
            "WHERE snapshot_id = 'snap-1' ORDER BY reading_index"
        ).fetchall()
        assert [tuple(r) for r in rows] == [(0, 60, 18.0, 15, 99), (1, 61, 18.1, 15, 98)]

    def test_reingest_replaces_not_duplicates(self, temp_db):
        upsert_health_snapshot_readings(temp_db, "snap-2", [(0, 60, 18.0, 15, 99)])
        upsert_health_snapshot_readings(temp_db, "snap-2", [(0, 65, 19.0, 16, 97)])
        rows = temp_db.execute("SELECT heart_rate FROM health_snapshot_reading WHERE snapshot_id = 'snap-2'").fetchall()
        assert len(rows) == 1 and rows[0]["heart_rate"] == 65

    def test_empty_or_no_id_returns_zero(self, temp_db):
        assert upsert_health_snapshot_readings(temp_db, "snap-3", []) == 0
        assert upsert_health_snapshot_readings(temp_db, "", [(0, 60, 18.0, 15, 99)]) == 0


def test_parse_iso():
    from garmin_givemydata import _parse_iso

    assert _parse_iso("2025-04-30T17:08:17.0") == datetime(2025, 4, 30, 17, 8, 17)
    assert _parse_iso(None) is None


class TestAssignSnapshots:
    def _fn(self):
        from garmin_givemydata import _assign_snapshots

        return _assign_snapshots

    def test_single_member_single_candidate_time_agnostic(self):
        # The clean common case pairs directly even without a GMT time.
        assign = self._fn()
        assert assign([("m1.fit", None)], [("snap-A", None)]) == {"m1.fit": "snap-A"}

    def test_two_candidates_match_nearest_gmt_one_to_one(self):
        assign = self._fn()
        members = [
            ("morning.fit", datetime(2026, 1, 1, 8, 0, 0)),
            ("evening.fit", datetime(2026, 1, 1, 20, 0, 0)),
        ]
        cands = [
            ("snap-morning", datetime(2026, 1, 1, 8, 0, 10)),
            ("snap-evening", datetime(2026, 1, 1, 20, 0, 5)),
        ]
        assert self._fn()(members, cands) == {"morning.fit": "snap-morning", "evening.fit": "snap-evening"}

    def test_two_members_one_candidate_does_not_clobber(self):
        # Regression: a stray extra FIT must NOT be force-matched onto the only
        # snapshot (which would overwrite the real one's readings).
        assign = self._fn()
        members = [
            ("real.fit", datetime(2026, 1, 1, 8, 0, 0)),
            ("stray.fit", datetime(2026, 1, 1, 8, 0, 30)),
        ]
        cands = [("snap-A", datetime(2026, 1, 1, 8, 0, 5))]
        result = assign(members, cands)
        assert list(result.values()) == ["snap-A"]  # exactly one member assigned
        assert len(result) == 1

    def test_out_of_range_is_unassigned(self):
        assign = self._fn()
        members = [("m.fit", datetime(2026, 1, 1, 1, 0, 0))]
        cands = [("x", datetime(2026, 1, 1, 12, 0, 0)), ("y", datetime(2026, 1, 1, 13, 0, 0))]
        assert assign(members, cands) == {}


def test_parser_sorts_readings_by_timestamp(monkeypatch):
    # Records arriving out of chronological order are sorted; reading_index is
    # chronological and start_time is the earliest sample.
    monkeypatch.setattr(paf, "FitFile", _FakeFit)
    recs = [
        {"timestamp": "2025-04-30T17:08:19", "heart_rate": 62},
        {"timestamp": "2025-04-30T17:08:17", "heart_rate": 60},
        {"timestamp": "2025-04-30T17:08:18", "heart_rate": 61},
    ]
    out = parse_health_snapshot_fit(_blob(recs))
    assert out["start_time"] == "2025-04-30T17:08:17"
    assert [r[1] for r in out["readings"]] == [60, 61, 62]

"""
Trackpoints parsing module for Garmin FIT files.

Adapted from Training_Planner project for garmin-givemydata workflow.
"""

import io
import re
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from fitparse import FitFile

_ACTIVITY_ID_RE = re.compile(r"(\d+)_activity\.fit$", re.IGNORECASE)
_ZIP_ACTIVITY_ID_RE = re.compile(r"(?:^|_)(\d{7,})(?:_|$)")


def _semicircles_to_degrees(value: object) -> float | None:
    """Convert Garmin semicircles to decimal degrees."""
    if value is None:
        return None
    try:
        return float(value) * (180.0 / (2**31))
    except Exception:
        return None


def _extract_activity_id_from_member(name: str) -> int | None:
    """Extract activity ID from FIT filename inside ZIP.

    Activity IDs must be at least 7 digits (typically Unix timestamps).
    """
    m = _ACTIVITY_ID_RE.search(name)
    if m:
        try:
            id_str = m.group(1)
            # Filter out IDs with fewer than 7 digits (likely test/invalid data)
            if len(id_str) >= 7:
                return int(id_str)
        except Exception:
            pass
    return None


def _activity_id_from_zip_filename(zip_path: Path) -> int | None:
    """Extract activity ID from garmin-givemydata ZIP filename.

    Expected format: YYYY-MM-DD_<activity_id>_<name>.zip
    Tries all numeric groups >= 7 digits (activity IDs are large ints).
    """
    stem = zip_path.stem
    for m in _ZIP_ACTIVITY_ID_RE.finditer(stem):
        try:
            candidate = int(m.group(1))
            if candidate > 1_000_000:
                return candidate
        except Exception:
            continue
    return None


def _track_rows_from_fit_bytes(fit_blob: bytes) -> List[Tuple]:
    """Parse trackpoints from FIT file bytes."""
    fit = FitFile(io.BytesIO(fit_blob))
    rows: List[Tuple] = []
    seq = 0

    for msg in fit.get_messages("record"):
        values = {f.name: f.value for f in msg}
        ts = values.get("timestamp")
        if ts is None:
            continue

        rows.append(
            (
                seq,
                ts.isoformat(),
                _semicircles_to_degrees(values.get("position_lat")),
                _semicircles_to_degrees(values.get("position_long")),
                values.get("enhanced_altitude", values.get("altitude")),
                values.get("distance"),
                values.get("enhanced_speed", values.get("speed")),
                values.get("heart_rate"),
                values.get("cadence"),
                values.get("power"),
                values.get("temperature"),
            )
        )
        seq += 1

    return rows


# ── Health Snapshot per-second graphs (#86) ──────────────────────────────────
# The 2-minute Health Snapshot's per-second HR/respiration/stress/SpO2 curves
# live only inside the _ACTIVITY.fit of the daily wellness download, as
# undecoded record fields. These numbers are inferred (no published FIT
# profile) and were confirmed against the stored summaryTypeDataList: on a real
# snapshot, unknown_108/100, unknown_116/100 and unknown_133 reproduced the
# summary's respiration/stress/SpO2 (min/max exact, respiration avg to 2 dp).
_SNAPSHOT_RESPIRATION_FIELD = "unknown_108"  # respiration x100
_SNAPSHOT_STRESS_FIELD = "unknown_116"  # stress x100
_SNAPSHOT_SPO2_FIELD = "unknown_133"  # SpO2


def parse_health_snapshot_fit(fit_blob: bytes) -> dict:
    """Parse one Health Snapshot ``_ACTIVITY.fit`` into per-second readings.

    Returns ``{"start_time": <iso str|None>, "readings": [(reading_index,
    heart_rate, respiration, stress, spo2), ...]}``. respiration/stress are the
    x100 fields divided down; all values are None when absent. See the module
    note above for the field-mapping provenance.
    """

    def _num(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

    fit = FitFile(io.BytesIO(fit_blob))
    samples = []  # (timestamp, hr, respiration, stress, spo2)
    for msg in fit.get_messages("record"):
        v = {f.name: f.value for f in msg}
        ts = v.get("timestamp")
        if ts is None:
            continue
        resp = _num(v.get(_SNAPSHOT_RESPIRATION_FIELD))
        stress = _num(v.get(_SNAPSHOT_STRESS_FIELD))
        samples.append(
            (
                ts,
                _num(v.get("heart_rate")),
                round(resp / 100, 2) if resp is not None else None,
                round(stress / 100) if stress is not None else None,
                _num(v.get(_SNAPSHOT_SPO2_FIELD)),
            )
        )
    # FIT does not guarantee record ordering; sort by timestamp so reading_index
    # is chronological and start_time is the earliest sample.
    samples.sort(key=lambda s: s[0])
    readings = [(i, hr, resp, stress, spo2) for i, (_ts, hr, resp, stress, spo2) in enumerate(samples)]
    start = samples[0][0] if samples else None
    return {"start_time": start.isoformat() if start is not None else None, "readings": readings}


def snapshot_reading_summary(readings: List[Tuple]) -> dict:
    """Aggregate per-second readings into avg/min/max per metric, for a self-check
    against the snapshot's stored summary. Column order: (index, hr, resp, stress, spo2)."""

    def agg(vals):
        vals = [x for x in vals if x is not None]
        if not vals:
            return None
        return {"avg": round(sum(vals) / len(vals), 2), "min": min(vals), "max": max(vals)}

    return {
        "heart_rate": agg([r[1] for r in readings]),
        "respiration": agg([r[2] for r in readings]),
        "stress": agg([r[3] for r in readings]),
        "spo2": agg([r[4] for r in readings]),
    }


def parse_trackpoints_from_fit_archive(
    fit_archive_path: Path,
) -> Tuple[Optional[int], List[Tuple]]:
    """Parse trackpoints from a garmin-givemydata FIT ZIP archive.

    Returns:
        Tuple of (activity_id, trackpoint_rows) or (None, []) if parsing failed
    """
    if not fit_archive_path.exists():
        return None, []

    # Try to extract activity ID from filename first
    activity_id = _activity_id_from_zip_filename(fit_archive_path)

    try:
        with zipfile.ZipFile(fit_archive_path, "r") as zf:
            fit_members = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if not fit_members:
                return None, []

            # If we didn't get activity ID from filename, try from FIT filename
            if activity_id is None:
                activity_id = _extract_activity_id_from_member(fit_members[0])

            if activity_id is None:
                return None, []

            fit_bytes = zf.read(fit_members[0])
            rows = _track_rows_from_fit_bytes(fit_bytes)
            return activity_id, rows

    except Exception:
        return None, []


def parse_trackpoints_from_directory(
    fit_dir: Path,
    activity_ids: Optional[List[int]] = None,
) -> List[Tuple[int, List[Tuple]]]:
    """Parse trackpoints from all FIT archives in a directory.

    Args:
        fit_dir: Directory containing FIT ZIP files
        activity_ids: Optional list of activity IDs to process (filters the results)

    Returns:
        List of (activity_id, trackpoint_rows) tuples
    """
    results = []

    if not fit_dir.exists():
        return results

    wanted = set(activity_ids) if activity_ids is not None else None
    zip_files = list(fit_dir.glob("*.zip"))

    for zip_path in zip_files:
        # Cheap pre-filter: when caller supplied activity_ids, try to
        # read the activity ID from the zip filename before doing the
        # expensive unzip + FIT parse. If the filename gives us a clear
        # ID and it's not in the wanted set, skip the zip entirely.
        if wanted is not None:
            cheap_id = _activity_id_from_zip_filename(zip_path)
            if cheap_id is not None and cheap_id not in wanted:
                continue

        activity_id, rows = parse_trackpoints_from_fit_archive(zip_path)

        if activity_id is None or not rows:
            continue

        # Filter by activity_ids if provided
        if wanted is not None and activity_id not in wanted:
            continue

        results.append((activity_id, rows))

    return results

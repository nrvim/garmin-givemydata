"""
Trackpoints parsing module for Garmin FIT files.

Adapted from Training_Planner project for garmin-givemydata workflow.
"""

import io
import re
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional

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

    # Find all ZIP files
    zip_files = list(fit_dir.glob("*.zip"))
    
    for zip_path in zip_files:
        activity_id, rows = parse_trackpoints_from_fit_archive(zip_path)
        
        if activity_id is None or not rows:
            continue
            
        # Filter by activity_ids if provided
        if activity_ids is not None and activity_id not in activity_ids:
            continue
            
        results.append((activity_id, rows))
    
    return results
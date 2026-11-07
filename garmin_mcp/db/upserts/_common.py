"""Shared helpers for upsert modules."""

import json
import sqlite3
from typing import Any, Optional


def _mean_sample_values(samples: Any, value_key) -> Optional[float]:
    """Mean of positive numeric values in a Garmin time-series array.

    Garmin returns HR/SpO2 timelines as either ``[{startGMT, value}, ...]`` or
    ``[[ts, value], ...]``. Missing samples appear as ``None`` or ``0``;
    ignore both.
    """
    if not isinstance(samples, list):
        return None
    vals: list[float] = []
    for s in samples:
        v = None
        if isinstance(s, dict):
            v = s.get(value_key)
        elif isinstance(s, (list, tuple)) and len(s) > value_key:
            v = s[value_key]
        if isinstance(v, (int, float)) and v > 0:
            vals.append(float(v))
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _upsert_raw_only(conn: sqlite3.Connection, table: str, key_col: str, record: dict, key_val: str) -> None:
    """Helper for tables that only have a key + raw_json."""
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({key_col}, raw_json) VALUES (?, ?)",
        (key_val, json.dumps(record)),
    )

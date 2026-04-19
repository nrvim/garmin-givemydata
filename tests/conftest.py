"""
Pytest configuration and shared fixtures for garmin-givemydata tests.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from garmin_mcp.db import init_db


@pytest.fixture
def temp_db():
    """Create an in-memory SQLite database with schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def temp_db_file():
    """Create a temporary SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    init_db(conn)
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_trackpoints():
    """Sample trackpoint data for testing.
    
    Returns list of tuples: (seq, timestamp, lat, lon, alt, dist, speed, hr, cad, pwr, temp)
    """
    return [
        (0, "2026-04-19T08:00:00", 40.712776, -74.005974, 10.5, 0.0, 0.0, 72, 0, 0, 25.0),
        (1, "2026-04-19T08:00:05", 40.712900, -74.005850, 11.2, 25.5, 5.1, 75, 85, 150, 25.1),
        (2, "2026-04-19T08:00:10", 40.713022, -74.005720, 12.1, 51.0, 5.1, 78, 87, 160, 25.2),
        (3, "2026-04-19T08:00:15", 40.713145, -74.005590, 13.0, 76.5, 5.1, 80, 89, 165, 25.3),
        (4, "2026-04-19T08:00:20", 40.713268, -74.005460, 14.2, 102.0, 5.0, 82, 91, 168, 25.4),
    ]


@pytest.fixture
def sample_activity():
    """Sample activity data for testing."""
    return {
        "activityId": 12345678,
        "activityName": "Test Run",
        "activityType": {"typeKey": "running", "typeId": 1, "parentTypeId": 1},
        "startTimeLocal": "2026-04-19T08:00:00",
        "startTimeGMT": "2026-04-19T12:00:00",
        "distance": 5000.0,
        "duration": 1800,
        "averageHR": 150,
        "maxHR": 175,
        "calories": 500,
        "startLatitude": 40.712776,
        "startLongitude": -74.005974,
        "endLatitude": 40.720000,
        "endLongitude": -74.010000,
    }

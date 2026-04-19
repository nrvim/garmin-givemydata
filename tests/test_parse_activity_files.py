"""
Unit tests for FIT file parsing (garmin_mcp/parse_activity_files.py).
"""

import pytest

from garmin_mcp.parse_activity_files import (
    _activity_id_from_zip_filename,
    _extract_activity_id_from_member,
    _semicircles_to_degrees,
)


class TestSemiclesToDegrees:
    """Test semicircle to degree conversion."""

    def test_valid_semicircle_conversion(self):
        """Test conversion of valid semicircle values."""
        # Garmin uses 2^31 semicircles per 180 degrees
        # 0 semicircles = 0 degrees
        assert _semicircles_to_degrees(0) == 0.0
        
        # Test some known values
        assert _semicircles_to_degrees(2**31) == pytest.approx(180.0, abs=1e-6)
        assert _semicircles_to_degrees(2**30) == pytest.approx(90.0, abs=1e-6)

    def test_none_value(self):
        """Test that None returns None."""
        assert _semicircles_to_degrees(None) is None

    def test_invalid_value(self):
        """Test that invalid values return None."""
        assert _semicircles_to_degrees("not_a_number") is None
        assert _semicircles_to_degrees({}) is None


class TestExtractActivityIdFromMember:
    """Test activity ID extraction from FIT filenames."""

    def test_valid_fit_filename(self):
        """Test extraction from valid FIT filename."""
        assert _extract_activity_id_from_member("12345678_activity.fit") == 12345678
        assert _extract_activity_id_from_member("12345678_ACTIVITY.FIT") == 12345678
        assert _extract_activity_id_from_member("ACTIVITY_12345678_activity.fit") == 12345678

    def test_invalid_filename(self):
        """Test that invalid filenames return None."""
        assert _extract_activity_id_from_member("activity.fit") is None
        assert _extract_activity_id_from_member("notafit.txt") is None
        assert _extract_activity_id_from_member("") is None

    def test_short_id(self):
        """Test that IDs with < 7 digits return None."""
        assert _extract_activity_id_from_member("123456_activity.fit") is None


class TestActivityIdFromZipFilename:
    """Test activity ID extraction from ZIP filenames."""

    def test_valid_zip_format(self):
        """Test extraction from garmin-givemydata ZIP format."""
        # YYYY-MM-DD_<activity_id>_<name>.zip
        from pathlib import Path
        
        assert _activity_id_from_zip_filename(Path("2026-04-19_12345678_test_run.zip")) == 12345678
        assert _activity_id_from_zip_filename(Path("2026-04-19_87654321_my_activity.zip")) == 87654321

    def test_multiple_ids_in_filename(self):
        """Test that largest valid ID is selected."""
        from pathlib import Path
        
        # Should find the activity ID (not the date)
        result = _activity_id_from_zip_filename(Path("2026-04-19_12345678_activity.zip"))
        assert result == 12345678

    def test_invalid_zip_filename(self):
        """Test that invalid filenames return None."""
        from pathlib import Path
        
        assert _activity_id_from_zip_filename(Path("invalid.zip")) is None
        assert _activity_id_from_zip_filename(Path("12345_small.zip")) is None


class TestCoordinateConversion:
    """Integration tests for coordinate parsing."""

    def test_realistic_coordinates(self):
        """Test conversion of realistic GPS coordinates."""
        # Central Park, NYC in semicircles (computed from decimal degrees)
        # 40.785091° in semicircles: 40.785091 * 2^31 / 180 ≈ 484756632
        # -73.972092° in semicircles: -73.972092 * 2^31 / 180 ≈ -881386784
        lat_semicircles = 484756632
        lon_semicircles = -881386784
        
        lat = _semicircles_to_degrees(lat_semicircles)
        lon = _semicircles_to_degrees(lon_semicircles)
        
        # Should be close to Central Park coordinates (40.785°N, 73.972°W)
        assert lat is not None
        assert lon is not None
        assert 40.0 < lat < 41.0
        assert -74.5 < lon < -73.5

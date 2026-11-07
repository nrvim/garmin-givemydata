"""Guard the MCP tool registry after splitting server.py into garmin_mcp.tools.*."""

import asyncio
import importlib
import inspect
import subprocess
import sys

import pytest

from garmin_mcp import server

# The tool list clients have always seen, in order. Adding a tool means appending
# it here and to server.TOOLS; removing or renaming one is a breaking change.
EXPECTED_TOOLS = [
    "garmin_schema", "garmin_query", "garmin_health_summary", "garmin_activities", "garmin_trends",
    "garmin_sync", "garmin_today", "garmin_activity_detail", "garmin_activity_trackpoints", "garmin_sleep",
    "garmin_training_load", "garmin_compare", "garmin_records", "garmin_fitness_age", "garmin_hrv",
    "garmin_body_battery", "garmin_stress", "garmin_heart_rate", "garmin_spo2", "garmin_body_composition",
    "garmin_devices", "garmin_week_summary", "garmin_recovery", "garmin_training_status", "garmin_workouts",
    "garmin_badges", "garmin_hydration", "garmin_respiration", "garmin_intensity_minutes", "garmin_floors",
    "garmin_steps", "garmin_calories", "garmin_blood_pressure", "garmin_goals", "garmin_challenges",
    "garmin_user_profile", "garmin_race_predictions", "garmin_endurance_score", "garmin_hill_score",
    "garmin_vo2max", "garmin_health_snapshot", "garmin_gear", "garmin_daily_events", "garmin_activity_types",
    "garmin_hr_zones", "garmin_load_focus", "garmin_lactate_threshold", "garmin_wellness_activity",
]  # fmt: skip

TOOL_MODULES = ["core", "background_sync", "summary", "daily", "activities", "fitness", "profile"]


def _listed_tools():
    return asyncio.run(server.mcp.list_tools())


def test_registered_tools_match_expected_order():
    assert [t.name for t in _listed_tools()] == EXPECTED_TOOLS


def test_every_tool_function_is_registered():
    """A garmin_* function in a tools module that is missing from TOOLS would be silently unavailable."""
    registered = {fn.__name__ for fn in server.TOOLS}
    for mod_name in TOOL_MODULES:
        mod = importlib.import_module(f"garmin_mcp.tools.{mod_name}")
        for name, obj in vars(mod).items():
            if name.startswith("garmin_") and inspect.isfunction(obj) and obj.__module__ == mod.__name__:
                assert name in registered, f"{mod.__name__}.{name} is not in server.TOOLS"


def test_every_tool_has_a_description():
    for tool in _listed_tools():
        assert tool.description and tool.description.strip(), tool.name


@pytest.mark.parametrize("module", [f"garmin_mcp.tools.{m}" for m in TOOL_MODULES])
def test_tool_module_imports_standalone(module):
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "name",
    ["mcp", "main", "garmin_activity_trackpoints", "_sync_state", "_sync_lock", "_start_background_sync"],
)
def test_server_keeps_names_used_elsewhere(name):
    assert hasattr(server, name)


def test_sync_state_is_shared_with_tool_module():
    from garmin_mcp.tools import background_sync

    assert server._sync_state is background_sync._sync_state
    assert server._sync_lock is background_sync._sync_lock

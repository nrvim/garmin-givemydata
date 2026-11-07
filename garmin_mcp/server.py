"""
Garmin MCP server — exposes health and activity data as MCP tools.

The tool implementations live in ``garmin_mcp.tools``; this module creates the
MCPServer instance (mcp 2.x), prepares the database and registers every tool in ``TOOLS``.
Tool names, descriptions and parameters come from the functions themselves.
"""

import logging

from mcp.server.mcpserver import MCPServer

from .db import get_connection, init_db
from .tools import activities, background_sync, core, daily, fitness, profile, summary
from .tools.activities import (  # noqa: F401  (re-exported for existing imports)
    garmin_activities,
    garmin_activity_detail,
    garmin_activity_trackpoints,
    garmin_activity_types,
    garmin_records,
)
from .tools.background_sync import (  # noqa: F401  (re-exported for existing imports)
    SYNC_TIMEOUT_SEC,
    _get_data_freshness,
    _start_background_sync,
    _sync_lock,
    _sync_state,
    garmin_sync,
)
from .tools.core import (  # noqa: F401  (re-exported for existing imports)
    garmin_query,
    garmin_schema,
)
from .tools.daily import (  # noqa: F401  (re-exported for existing imports)
    garmin_body_battery,
    garmin_calories,
    garmin_daily_events,
    garmin_floors,
    garmin_health_snapshot,
    garmin_heart_rate,
    garmin_hrv,
    garmin_hydration,
    garmin_intensity_minutes,
    garmin_respiration,
    garmin_sleep,
    garmin_spo2,
    garmin_steps,
    garmin_stress,
    garmin_wellness_activity,
)
from .tools.fitness import (  # noqa: F401  (re-exported for existing imports)
    garmin_blood_pressure,
    garmin_body_composition,
    garmin_endurance_score,
    garmin_fitness_age,
    garmin_hill_score,
    garmin_lactate_threshold,
    garmin_load_focus,
    garmin_race_predictions,
    garmin_recovery,
    garmin_training_load,
    garmin_training_status,
    garmin_vo2max,
)
from .tools.profile import (  # noqa: F401  (re-exported for existing imports)
    garmin_badges,
    garmin_challenges,
    garmin_devices,
    garmin_gear,
    garmin_goals,
    garmin_hr_zones,
    garmin_user_profile,
    garmin_workouts,
)
from .tools.summary import (  # noqa: F401  (re-exported for existing imports)
    _TREND_METRICS,
    garmin_compare,
    garmin_health_summary,
    garmin_today,
    garmin_trends,
    garmin_week_summary,
)

log = logging.getLogger(__name__)

mcp = MCPServer("garmin")

# Ensure all tables exist on startup
_conn = get_connection()
init_db(_conn)
_conn.close()

# Registration order is the order clients see in the tool list. Keep it stable.
TOOLS = (
    core.garmin_schema,
    core.garmin_query,
    summary.garmin_health_summary,
    activities.garmin_activities,
    summary.garmin_trends,
    background_sync.garmin_sync,
    summary.garmin_today,
    activities.garmin_activity_detail,
    activities.garmin_activity_trackpoints,
    daily.garmin_sleep,
    fitness.garmin_training_load,
    summary.garmin_compare,
    activities.garmin_records,
    fitness.garmin_fitness_age,
    daily.garmin_hrv,
    daily.garmin_body_battery,
    daily.garmin_stress,
    daily.garmin_heart_rate,
    daily.garmin_spo2,
    fitness.garmin_body_composition,
    profile.garmin_devices,
    summary.garmin_week_summary,
    fitness.garmin_recovery,
    fitness.garmin_training_status,
    profile.garmin_workouts,
    profile.garmin_badges,
    daily.garmin_hydration,
    daily.garmin_respiration,
    daily.garmin_intensity_minutes,
    daily.garmin_floors,
    daily.garmin_steps,
    daily.garmin_calories,
    fitness.garmin_blood_pressure,
    profile.garmin_goals,
    profile.garmin_challenges,
    profile.garmin_user_profile,
    fitness.garmin_race_predictions,
    fitness.garmin_endurance_score,
    fitness.garmin_hill_score,
    fitness.garmin_vo2max,
    daily.garmin_health_snapshot,
    profile.garmin_gear,
    daily.garmin_daily_events,
    activities.garmin_activity_types,
    profile.garmin_hr_zones,
    fitness.garmin_load_focus,
    fitness.garmin_lactate_threshold,
    daily.garmin_wellness_activity,
)

for _tool in TOOLS:
    mcp.tool()(_tool)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")

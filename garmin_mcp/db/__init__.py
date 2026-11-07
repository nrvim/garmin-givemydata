"""SQLite database layer for Garmin MCP server.

Split into focused modules; this package re-exports the full former
``garmin_mcp.db`` API so existing imports keep working unchanged.

Note: ``DB_PATH`` is re-exported by value. Code that must change the
database location at runtime should set ``garmin_mcp.db.connection.DB_PATH``.
"""

from .backfill import (  # noqa: F401
    backfill_body_battery_from_daily_summaries,
    backfill_calories_from_daily_summaries,
    backfill_hrv_timeline_counts,
    cleanup_invalid_rows,
)
from .bootstrap import (  # noqa: F401
    MIGRATIONS,
    SCHEMA_VERSION,
    get_schema_version,
    init_db,
    run_migrations,
)
from .connection import (  # noqa: F401
    DB_PATH,
    _default_db_path,
    get_connection,
    query,
    query_readonly,
)
from .migrations import (  # noqa: F401
    _add_columns,
    _backfill_from_raw,
    migrate_activity_splits_table,
    migrate_activity_splits_v2,
    migrate_activity_table,
    migrate_device_table,
    migrate_endurance_score_table,
    migrate_fitness_age_table,
    migrate_gear_table,
    migrate_gear_table_v2,
    migrate_heart_rate_table,
    migrate_hill_score_table,
    migrate_hollow_tables,
    migrate_hrv_table,
    migrate_hydration_table,
    migrate_respiration_table,
    migrate_sleep_table,
    migrate_sleep_table_v2,
    migrate_spo2_table,
    migrate_training_status_table,
    migrate_weight_table,
    migrate_weight_table_v2,
    migrate_weight_table_v3,
)
from .routing import (  # noqa: F401
    _ensure_list,
    _extract_activity_records,
    _extract_calories_records,
    _extract_weight_records,
    _unwrap_gql_data,
    save_to_db,
)
from .schema import (  # noqa: F401
    _SCHEMA_SQL,
)
from .upserts._common import (  # noqa: F401
    _mean_sample_values,
    _upsert_raw_only,
)
from .upserts.activities import (  # noqa: F401
    upsert_activity,
    upsert_activity_exercise_sets,
    upsert_activity_hr_zones,
    upsert_activity_splits,
    upsert_activity_trackpoints,
    upsert_activity_trends,
    upsert_activity_types,
    upsert_activity_weather,
    upsert_running_dynamics,
)
from .upserts.daily import (  # noqa: F401
    upsert_body_battery,
    upsert_body_battery_from_daily_summary,
    upsert_calories,
    upsert_calories_from_daily_summary,
    upsert_daily_events,
    upsert_daily_movement,
    upsert_daily_summary,
    upsert_floors,
    upsert_health_snapshot,
    upsert_health_status,
    upsert_heart_rate,
    upsert_hrv,
    upsert_hrv_timeline,
    upsert_hydration,
    upsert_intensity_minutes,
    upsert_respiration,
    upsert_sleep,
    upsert_sleep_stats,
    upsert_spo2,
    upsert_steps,
    upsert_stress,
    upsert_wellness_activity,
)
from .upserts.fitness import (  # noqa: F401
    upsert_blood_pressure,
    upsert_endurance_score,
    upsert_fitness_age,
    upsert_hill_score,
    upsert_lactate_threshold,
    upsert_race_predictions,
    upsert_training_readiness,
    upsert_training_status,
    upsert_vo2max,
    upsert_weight,
)
from .upserts.profile import (  # noqa: F401
    upsert_challenges,
    upsert_device,
    upsert_earned_badges,
    upsert_gear,
    upsert_goals,
    upsert_hr_zones,
    upsert_personal_record,
    upsert_training_plans,
    upsert_user_profile,
    upsert_workout,
    upsert_workout_schedule,
)

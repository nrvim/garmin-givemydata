"""
Export Garmin data from SQLite to CSV, JSON, and download activity files (FIT/GPX/TCX).
"""

import csv
import json
import os
import time
from pathlib import Path
from typing import Optional

from .db import get_connection
from .db import query as db_query

_CSV_COLUMN_MAP = {
    "daily_summary": {
        "calendar_date": "Date",
        "total_steps": "Steps",
        "daily_step_goal": "Step Goal",
        "total_distance_meters": "Distance (m)",
        "total_kilocalories": "Total Calories",
        "active_kilocalories": "Active Calories",
        "bmr_kilocalories": "BMR Calories",
        "remaining_kilocalories": "Remaining Calories",
        "highly_active_seconds": "Highly Active (s)",
        "active_seconds": "Active (s)",
        "sedentary_seconds": "Sedentary (s)",
        "sleeping_seconds": "Sleeping (s)",
        "moderate_intensity_minutes": "Moderate Intensity (min)",
        "vigorous_intensity_minutes": "Vigorous Intensity (min)",
        "intensity_minutes_goal": "Intensity Goal (min)",
        "floors_ascended": "Floors Ascended",
        "floors_descended": "Floors Descended",
        "floors_ascended_goal": "Floors Goal",
        "min_heart_rate": "Min HR (bpm)",
        "max_heart_rate": "Max HR (bpm)",
        "resting_heart_rate": "Resting HR (bpm)",
        "avg_resting_heart_rate_7day": "7-Day Avg Resting HR (bpm)",
        "average_stress_level": "Avg Stress",
        "max_stress_level": "Max Stress",
        "low_stress_seconds": "Low Stress (s)",
        "medium_stress_seconds": "Medium Stress (s)",
        "high_stress_seconds": "High Stress (s)",
        "stress_qualifier": "Stress Qualifier",
        "body_battery_charged": "Body Battery Charged",
        "body_battery_drained": "Body Battery Drained",
        "body_battery_highest": "Body Battery High",
        "body_battery_lowest": "Body Battery Low",
        "body_battery_most_recent": "Body Battery Latest",
        "body_battery_at_wake": "Body Battery at Wake",
        "body_battery_during_sleep": "Body Battery During Sleep",
        "average_spo2": "Avg SpO2 (%)",
        "lowest_spo2": "Lowest SpO2 (%)",
        "latest_spo2": "Latest SpO2 (%)",
        "avg_waking_respiration": "Avg Respiration (brpm)",
        "highest_respiration": "Max Respiration (brpm)",
        "lowest_respiration": "Min Respiration (brpm)",
        "source": "Source",
    },
    "sleep": {
        "calendar_date": "Date",
        "sleep_time_seconds": "Sleep Time (s)",
        "nap_time_seconds": "Nap Time (s)",
        "deep_sleep_seconds": "Deep Sleep (s)",
        "light_sleep_seconds": "Light Sleep (s)",
        "rem_sleep_seconds": "REM Sleep (s)",
        "awake_sleep_seconds": "Awake (s)",
        "unmeasurable_sleep_seconds": "Unmeasurable (s)",
        "awake_count": "Awake Count",
        "average_spo2": "Avg SpO2 (%)",
        "lowest_spo2": "Lowest SpO2 (%)",
        "average_hr_sleep": "Avg Sleeping HR (bpm)",
        "average_respiration": "Avg Respiration (brpm)",
        "lowest_respiration": "Min Respiration (brpm)",
        "highest_respiration": "Max Respiration (brpm)",
        "avg_sleep_stress": "Avg Sleep Stress",
        "sleep_score_feedback": "Sleep Score Feedback",
        "sleep_score_insight": "Sleep Score Insight",
    },
    "activity": {
        "activity_id": "Activity ID",
        "activity_name": "Activity Name",
        "activity_type": "Activity Type",
        "activity_type_id": "Activity Type ID",
        "parent_type_id": "Parent Type ID",
        "start_time_local": "Start Time",
        "start_time_gmt": "Start Time (GMT)",
        "duration_seconds": "Duration (s)",
        "elapsed_duration_seconds": "Elapsed Duration (s)",
        "moving_duration_seconds": "Moving Duration (s)",
        "distance_meters": "Distance (m)",
        "calories": "Calories",
        "bmr_calories": "BMR Calories",
        "average_hr": "Avg HR (bpm)",
        "max_hr": "Max HR (bpm)",
        "average_speed": "Avg Speed (m/s)",
        "max_speed": "Max Speed (m/s)",
        "elevation_gain": "Elevation Gain (m)",
        "elevation_loss": "Elevation Loss (m)",
        "min_elevation": "Min Elevation (m)",
        "max_elevation": "Max Elevation (m)",
        "avg_power": "Avg Power (W)",
        "max_power": "Max Power (W)",
        "norm_power": "Normalized Power (W)",
        "training_stress_score": "TSS",
        "intensity_factor": "Intensity Factor",
        "aerobic_training_effect": "Aerobic TE",
        "anaerobic_training_effect": "Anaerobic TE",
        "vo2max_value": "VO2max",
        "avg_cadence": "Avg Cadence",
        "max_cadence": "Max Cadence",
        "avg_respiration": "Avg Respiration (brpm)",
        "training_load": "Training Load",
        "moderate_intensity_minutes": "Moderate Intensity (min)",
        "vigorous_intensity_minutes": "Vigorous Intensity (min)",
        "start_latitude": "Start Latitude (°)",
        "start_longitude": "Start Longitude (°)",
        "end_latitude": "End Latitude (°)",
        "end_longitude": "End Longitude (°)",
        "location_name": "Location",
        "lap_count": "Laps",
        "water_estimated": "Water Estimated (ml)",
        "min_temperature": "Min Temp (°C)",
        "max_temperature": "Max Temp (°C)",
        "manufacturer": "Manufacturer",
        "device_id": "Device ID",
    },
    "activity_trackpoints": {
        "activity_id": "Activity ID",
        "seq": "Sequence",
        "timestamp_utc": "Timestamp (UTC)",
        "latitude": "Latitude (°)",
        "longitude": "Longitude (°)",
        "altitude_m": "Altitude (m)",
        "distance_m": "Distance (m)",
        "speed_mps": "Speed (m/s)",
        "heart_rate_bpm": "Heart Rate (bpm)",
        "cadence": "Cadence",
        "power_w": "Power (W)",
        "temperature_c": "Temperature (°C)",
    },
    "hrv": {
        "calendar_date": "Date",
        "weekly_avg": "Weekly Avg (ms)",
        "last_night": "Last Night (ms)",
        "last_night_avg": "Last Night Avg (ms)",
        "last_night_5min_high": "Last Night 5-min High (ms)",
        "status": "Status",
        "baseline_low": "Baseline Low (ms)",
        "baseline_upper": "Baseline Upper (ms)",
        "start_timestamp": "Start Time",
        "end_timestamp": "End Time",
    },
    "training_readiness": {
        "calendar_date": "Date",
        "score": "Score",
        "level": "Level",
        "feedback_short": "Feedback",
        "feedback_long": "Feedback Detail",
        "recovery_time": "Recovery Time (h)",
        "recovery_time_factor_percent": "Recovery Factor (%)",
        "recovery_time_factor_feedback": "Recovery Feedback",
        "hrv_factor_percent": "HRV Factor (%)",
        "hrv_factor_feedback": "HRV Feedback",
        "hrv_weekly_average": "HRV Weekly Avg (ms)",
        "sleep_history_factor_percent": "Sleep Factor (%)",
        "sleep_history_factor_feedback": "Sleep Feedback",
        "stress_history_factor_percent": "Stress Factor (%)",
        "stress_history_factor_feedback": "Stress Feedback",
        "acwr_factor_percent": "ACWR Factor (%)",
        "acwr_factor_feedback": "ACWR Feedback",
    },
    "heart_rate": {
        "calendar_date": "Date",
        "resting_hr": "Resting HR (bpm)",
        "min_hr": "Min HR (bpm)",
        "max_hr": "Max HR (bpm)",
        "avg_hr": "Avg HR (bpm)",
    },
    "stress": {
        "calendar_date": "Date",
        "avg_stress": "Avg Stress",
        "max_stress": "Max Stress",
        "stress_qualifier": "Stress Qualifier",
    },
    "spo2": {
        "calendar_date": "Date",
        "avg_spo2": "Avg SpO2 (%)",
        "min_spo2": "Min SpO2 (%)",
        "max_spo2": "Max SpO2 (%)",
    },
    "respiration": {
        "calendar_date": "Date",
        "avg_waking": "Avg Waking (brpm)",
        "min_value": "Min (brpm)",
        "max_value": "Max (brpm)",
    },
    "body_battery": {
        "calendar_date": "Date",
        "charged": "Charged",
        "drained": "Drained",
        "highest": "Highest",
        "lowest": "Lowest",
        "most_recent": "Most Recent",
        "at_wake": "At Wake",
        "during_sleep": "During Sleep",
    },
    "steps": {
        "calendar_date": "Date",
        "total_steps": "Steps",
        "goal": "Goal",
        "distance_meters": "Distance (m)",
    },
    "floors": {
        "calendar_date": "Date",
        "ascended": "Ascended",
        "descended": "Descended",
        "goal": "Goal",
    },
    "intensity_minutes": {
        "calendar_date": "Date",
        "moderate": "Moderate (min)",
        "vigorous": "Vigorous (min)",
        "goal": "Goal (min)",
    },
    "weight": {
        "calendar_date": "Date",
        "weight": "Weight (kg)",
        "bmi": "BMI",
        "body_fat": "Body Fat (%)",
        "body_water": "Body Water (%)",
        "bone_mass": "Bone Mass (kg)",
        "muscle_mass": "Muscle Mass (kg)",
    },
    "vo2max": {
        "calendar_date": "Date",
        "sport": "Sport",
        "value": "VO2max",
    },
    "blood_pressure": {
        "calendar_date": "Date",
        "systolic": "Systolic (mmHg)",
        "diastolic": "Diastolic (mmHg)",
        "pulse": "Pulse (bpm)",
    },
    "calories": {
        "calendar_date": "Date",
        "total": "Total (kcal)",
        "active": "Active (kcal)",
        "bmr": "BMR (kcal)",
        "consumed": "Consumed (kcal)",
        "remaining": "Remaining (kcal)",
    },
    "hydration": {
        "calendar_date": "Date",
        "goal_ml": "Goal (ml)",
        "intake_ml": "Intake (ml)",
    },
    "fitness_age": {
        "calendar_date": "Date",
        "chronological_age": "Chronological Age",
        "fitness_age": "Fitness Age",
    },
}


def export_csv(output_dir: Path):
    """Export all tables to CSV with human-readable column headers.

    Column names include units matching community standards
    (e.g. 'Distance (m)', 'Avg HR (bpm)', 'Elevation Gain (m)').
    raw_json is excluded — use JSON export for full data.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()

    tables = db_query(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'",
    )

    for t in tables:
        name = t["name"]
        rows = db_query(conn, f"SELECT * FROM {name}")
        if not rows:
            continue

        db_columns = [k for k in rows[0].keys() if k != "raw_json"]
        col_map = _CSV_COLUMN_MAP.get(name, {})
        csv_columns = [col_map.get(c, c) for c in db_columns]

        csv_path = output_dir / f"{name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(csv_columns)
            for row in rows:
                writer.writerow([row[c] for c in db_columns])

        print(f"  {name}.csv ({len(rows)} rows)")

    conn.close()


def export_json_tables(output_dir: Path):
    """Export each table as a separate JSON file.

    JSON uses the full original Garmin data from raw_json, merged with
    the structured columns. This gives users the complete data that
    Garmin returned — including fields not captured in the schema.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()

    tables = db_query(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'",
    )

    for t in tables:
        name = t["name"]
        rows = db_query(conn, f"SELECT * FROM {name}")
        if not rows:
            continue

        export_rows = []
        for row in rows:
            raw = row.get("raw_json")
            if raw:
                # Start with the full original Garmin data
                try:
                    full = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    full = {}
                # Add our structured columns on top (they're cleaner/normalized)
                for k, v in row.items():
                    if k != "raw_json" and v is not None:
                        full[f"__{k}"] = v
                export_rows.append(full)
            else:
                # No raw_json — just export structured columns
                export_rows.append({k: v for k, v in row.items() if k != "raw_json"})

        json_path = output_dir / f"{name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(export_rows, f, indent=2, default=str)

        size_kb = json_path.stat().st_size / 1024
        print(f"  {name}.json ({len(rows)} rows, {size_kb:.0f} KB)")

    conn.close()


def download_activity_files(
    output_dir: Path,
    file_format: str = "fit",
    activity_ids: Optional[list] = None,
):
    """Download original activity files (FIT, GPX, or TCX) from Garmin Connect.

    Requires an active browser session (Playwright).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get activity IDs from database if not provided
    if not activity_ids:
        conn = get_connection()
        rows = db_query(
            conn,
            "SELECT activity_id, activity_name, start_time_local FROM activity ORDER BY start_time_local DESC",
        )
        conn.close()
        activity_ids = [(r["activity_id"], r["activity_name"], r["start_time_local"]) for r in rows]
    else:
        activity_ids = [(aid, None, None) for aid in activity_ids]

    if not activity_ids:
        print("  No activities found in database.")
        return

    # Build download URLs based on format
    # FIT uses /modern/proxy/ prefix, GPX/TCX use /modern/proxy/ with export path
    if file_format == "fit":
        url_pattern = "/gc-api/download-service/files/activity/{id}"
        ext = ".zip"  # FIT downloads come as ZIP
    elif file_format == "gpx":
        url_pattern = "/gc-api/download-service/export/gpx/activity/{id}"
        ext = ".gpx"
    elif file_format == "tcx":
        url_pattern = "/gc-api/download-service/export/tcx/activity/{id}"
        ext = ".tcx"
    else:
        print(f"  Unknown format: {file_format}. Use fit, gpx, or tcx.")
        return

    print(f"  Downloading {len(activity_ids)} activities as {file_format.upper()}...")

    from garmin_client import GarminClient

    project_dir = Path(__file__).parent.parent
    profile_dir = project_dir / "browser_profile"

    env_file = project_dir / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    email = os.environ.get("GARMIN_EMAIL", "")
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        print("  Credentials not found. Run ./setup.sh first.")
        return

    client = GarminClient(email=email, password=password, profile_dir=profile_dir)

    try:
        if not client.login():
            print("  Login failed!")
            return

        downloaded = 0
        skipped = 0
        failed = 0

        for i, activity_info in enumerate(activity_ids):
            if isinstance(activity_info, tuple):
                aid, name, date_str = activity_info
            else:
                aid, name, date_str = activity_info, None, None

            safe_name = ""
            if name:
                safe_name = "_" + "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(
                    " ", "_"
                )
            if date_str:
                safe_date = date_str[:10]
                filename = f"{safe_date}_{aid}{safe_name}{ext}"
            else:
                filename = f"{aid}{safe_name}{ext}"

            filepath = output_dir / filename
            if filepath.exists():
                skipped += 1
                continue

            api_path = url_pattern.format(id=aid)
            file_data = client.download_file(api_path)

            if file_data:
                with open(filepath, "wb") as f:
                    f.write(file_data)
                downloaded += 1
            else:
                failed += 1

            if downloaded > 0 and (downloaded % 10) == 0:
                print(f"    {downloaded}/{len(activity_ids)} downloaded...")

            if i % 20 == 19:
                time.sleep(1)

        print(f"  Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}, Total: {len(activity_ids)}")

    finally:
        client.close()


def export_all(output_dir: Path, include_fit: bool = False, fit_format: str = "fit"):
    """Export everything: CSV + JSON + optionally activity files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nExporting to {output_dir}/")

    # CSV
    csv_dir = output_dir / "csv"
    print("\nCSV files:")
    export_csv(csv_dir)

    # JSON
    json_dir = output_dir / "json"
    print("\nJSON files:")
    export_json_tables(json_dir)

    # Activity files
    if include_fit:
        files_dir = output_dir / fit_format
        print(f"\n{fit_format.upper()} activity files:")
        download_activity_files(files_dir, file_format=fit_format)

    print(f"\nAll exports saved to: {output_dir}/")

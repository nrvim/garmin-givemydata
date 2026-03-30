"""
Garmin Connect API endpoint definitions.
"""


def profile_endpoints() -> dict:
    """Endpoints that don't need a date."""
    return {
        "personal_info": "/gc-api/userprofile-service/userprofile/personal-information",
        "user_settings": "/gc-api/userprofile-service/userprofile/user-settings/",
        "social_profile": "/gc-api/userprofile-service/socialProfile",
        "user_profile_base": "/gc-api/userprofile-service/userprofile/userProfileBase",
        "devices": "/gc-api/device-service/deviceregistration/devices",
        "devices_historical": "/gc-api/device-service/deviceregistration/devices/historical",
        "last_used_device": "/gc-api/device-service/deviceservice/mylastused",
        "sensors": "/gc-api/device-service/sensors",
        "hr_zones": "/gc-api/biometric-service/heartRateZones/",
        "training_plans": "/gc-api/trainingplan-service/trainingplan/plans?limit=50",
        "sync_timestamp": "/gc-api/wellness-service/wellness/syncTimestamp",
        "activity_types": "/gc-api/activity-service/activity/activityTypes",
        "gear_list": "/gc-api/gear-service/gear/v2/list",
        "gear_types": "/gc-api/gear-service/gear/v2/user-gear-types",
        "goals": "/gc-api/goal-service/goal/goals",
        "weight_first": "/gc-api/weight-service/weight/first",
        "daily_summaries_count": "/gc-api/usersummary-service/usersummary/dailySummariesCount",
        "earned_badges": "/gc-api/badge-service/badge/earned",
    }


def profile_graphql(display_name: str) -> dict:
    """One-shot GraphQL queries."""
    dn = display_name
    return {
        "personal_records": f'query{{personalRecordScalar(displayName:"{dn}")}}',
        "user_goals": "query { userGoalsScalar }",
        "challenges_adhoc": "query { adhocChallengesScalar }",
        "challenges_badge": "query { badgeChallengesScalar }",
        "challenges_expeditions": "query { expeditionsChallengesScalar }",
    }


def full_range_rest(display_name: str, start_date: str, end_date: str) -> dict:
    """REST endpoints that support full date ranges."""
    dn = display_name
    return {
        "activities": "/gc-api/activitylist-service/activities/search/activities?limit=1000&start=0",
        "weight_range": f"/gc-api/weight-service/weight/dateRange?startDate={start_date}&endDate={end_date}",
        "weight_latest": f"/gc-api/weight-service/weight/latest?date={end_date}",
        "vo2max_trend": f"/gc-api/metrics-service/metrics/maxmet/daily/{start_date}/{end_date}",
        "personal_records": f"/gc-api/personalrecord-service/personalrecord/prs/{dn}",
        "personal_record_types": f"/gc-api/personalrecord-service/personalrecordtype/prtypes/{dn}",
    }


def full_range_graphql(display_name: str, start_date: str, end_date: str) -> dict:
    """GraphQL queries that support full date ranges (tested with 365 days)."""
    dn = display_name
    return {
        "daily_summaries": f'query{{userDailySummaryV2Scalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "daily_summaries_avg": f'query{{userDailySummaryV2AverageScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "hrv": f'query{{heartRateVariabilityScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "training_readiness": f'query{{trainingReadinessRangeScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "training_status_weekly": f'query{{trainingStatusWeeklyScalar(startDate:"{start_date}", endDate:"{end_date}", displayName:"{dn}")}}',
        "vo2max_running": f'query{{vo2MaxScalar(startDate:"{start_date}", endDate:"{end_date}", sport:"RUNNING")}}',
        "vo2max_cycling": f'query{{vo2MaxScalar(startDate:"{start_date}", endDate:"{end_date}", sport:"CYCLING")}}',
        "weight": f'query{{weightScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "blood_pressure": f'query{{bloodPressureScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "activities_range": f'query{{activitiesScalar(displayName:"{dn}", startTimestampLocal:"{start_date}T00:00:00.00", endTimestampLocal:"{end_date}T23:59:59.99")}}',
        "activity_stats_all": f'query{{activityStatsScalar(aggregation:"daily", startDate:"{start_date}", endDate:"{end_date}", activityType:"all")}}',
        "activity_stats_running": f'query{{activityStatsScalar(aggregation:"daily", startDate:"{start_date}", endDate:"{end_date}", activityType:"running")}}',
        "activity_stats_cycling": f'query{{activityStatsScalar(aggregation:"daily", startDate:"{start_date}", endDate:"{end_date}", activityType:"cycling")}}',
    }


def monthly_rest(display_name: str, start_date: str, end_date: str) -> dict:
    """REST endpoints limited to ~31 days."""
    return {
        "sleep_stats": f"/gc-api/sleep-service/stats/sleep/daily/{start_date}/{end_date}",
        "hrv_daily": f"/gc-api/hrv-service/hrv/daily/{start_date}/{end_date}",
        "stats_daily": f"/gc-api/usersummary-service/stats/daily/{start_date}/{end_date}",
        "stats_averages": f"/gc-api/usersummary-service/stats/averages/{start_date}/{end_date}",
        "blood_pressure_rest": f"/gc-api/bloodpressure-service/bloodpressure/daily/last/{start_date}/{end_date}",
        "weight_range_rest": f"/gc-api/weight-service/weight/range/{start_date}/{end_date}",
        "goal_weight": f"/gc-api/goal-service/goal/user/effective/weightgoal/{start_date}/{end_date}",
        "intensity_minutes_weekly": f"/gc-api/usersummary-service/stats/im/weekly/{start_date}/{end_date}",
    }


def monthly_graphql(display_name: str, start_date: str, end_date: str) -> dict:
    """GraphQL queries limited to ~31 days. Need chunking for longer ranges."""
    return {
        "sleep_summaries": f'query{{sleepSummariesScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "calories": f'''query {{
            calorieSummaryDailyStats(startDate: "{start_date}", endDate: "{end_date}") {{
                calendarDate totalKilocalories activeKilocalories bmrKilocalories
                consumedKilocalories remainingKilocalories
            }}
        }}''',
        "health_snapshot": f'query{{healthSnapshotScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
        "workout_schedule": f'query{{workoutScheduleSummariesScalar(startDate:"{start_date}", endDate:"{end_date}")}}',
    }


def daily_rest(display_name: str, date: str) -> dict:
    """REST endpoints for a single date."""
    dn = display_name
    return {
        "daily_summary": f"/gc-api/usersummary-service/usersummary/daily/{dn}?calendarDate={date}",
        "heart_rate": f"/gc-api/wellness-service/wellness/dailyHeartRate/{dn}?date={date}",
        "sleep": f"/gc-api/wellness-service/wellness/dailySleepData/{dn}?date={date}",
        "stress": f"/gc-api/wellness-service/wellness/dailyStress/{date}",
        "spo2": f"/gc-api/wellness-service/wellness/dailySpo2/{date}",
        "steps": f"/gc-api/usersummary-service/stats/steps/daily/{date}/{date}",
        "respiration": f"/gc-api/wellness-service/wellness/daily/respiration/{date}",
        "floors": f"/gc-api/wellness-service/wellness/floorsChartData/daily/{date}",
        "intensity_minutes": f"/gc-api/wellness-service/wellness/daily/im/{date}",
        "hydration": f"/gc-api/usersummary-service/usersummary/hydration/allData/{date}",
        "body_battery_events": f"/gc-api/wellness-service/wellness/bodyBattery/events/{date}",
        "fitness_age": f"/gc-api/fitnessage-service/fitnessage/{date}",
        "wellness_activity": f"/gc-api/wellnessactivity-service/activity/summary/{date}",
        "daily_movement": f"/gc-api/wellness-service/wellness/dailyMovement?calendarDate={date}",
        "endurance_score": f"/gc-api/metrics-service/metrics/endurancescore?calendarDate={date}",
        "hill_score": f"/gc-api/metrics-service/metrics/hillscore?calendarDate={date}",
        "race_predictions": f"/gc-api/metrics-service/metrics/racepredictions/daily/{dn}?fromCalendarDate={date}&toCalendarDate={date}",
    }


def daily_graphql(display_name: str, date: str) -> dict:
    """GraphQL queries for a single date."""
    return {
        "body_battery_stress": f'query{{epochChartScalar(date:"{date}", include:["bodyBattery","stress"])}}',
        "heart_rate_detail": f'query{{heartRateScalar(date:"{date}")}}',
        "sleep_detail": f'query{{sleepScalar(date:"{date}", sleepOnly: false)}}',
        "training_status_daily": f'query{{trainingStatusDailyScalar(calendarDate:"{date}")}}',
        "daily_events": f'query{{dailyEventsScalar(date:"{date}")}}',
        "health_status": f'''query {{
            healthStatusSummary(calendarDate:"{date}") {{
                calendarDate overallStatus metricsMap
            }}
        }}''',
        "activity_trends_all": f'query{{activityTrendsScalar(activityType:"all",date:"{date}")}}',
        "activity_trends_running": f'query{{activityTrendsScalar(activityType:"running",date:"{date}")}}',
        "activity_trends_cycling": f'query{{activityTrendsScalar(activityType:"cycling",date:"{date}")}}',
    }


def activity_detail_endpoints(activity_id: int) -> dict:
    """REST endpoints for detailed per-activity data."""
    aid = activity_id
    return {
        "activity_splits": f"/gc-api/activity-service/activity/{aid}/splits",
        "activity_hr_zones": f"/gc-api/activity-service/activity/{aid}/hrTimeInZones",
        "activity_weather": f"/gc-api/activity-service/activity/{aid}/weather",
        "activity_details": f"/gc-api/activity-service/activity/{aid}",
        "activity_exercise_sets": f"/gc-api/activity-service/activity/{aid}/exerciseSets",
    }

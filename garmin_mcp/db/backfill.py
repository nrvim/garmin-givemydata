"""One-off data repairs and backfills run conditionally by init_db()."""

import sqlite3


def backfill_calories_from_daily_summaries(conn: sqlite3.Connection) -> None:
    """Populate missing calories rows from already-synced daily summaries."""
    conn.execute(
        """
        INSERT INTO calories (calendar_date, total, active, bmr, consumed, remaining, raw_json)
        SELECT
            ds.calendar_date,
            ds.total_kilocalories,
            ds.active_kilocalories,
            ds.bmr_kilocalories,
            NULL,
            ds.remaining_kilocalories,
            ds.raw_json
        FROM daily_summary ds
        LEFT JOIN calories c ON c.calendar_date = ds.calendar_date
        WHERE c.calendar_date IS NULL
          AND (
              ds.total_kilocalories IS NOT NULL OR
              ds.active_kilocalories IS NOT NULL OR
              ds.bmr_kilocalories IS NOT NULL OR
              ds.remaining_kilocalories IS NOT NULL
          )
        """
    )


def backfill_body_battery_from_daily_summaries(conn: sqlite3.Connection) -> None:
    """Backfill body_battery aggregate columns from daily_summary.

    Historically body_battery rows were created from the body_battery_events
    endpoint which only contains time-series data — the aggregate columns
    (highest/lowest/charged/drained/etc.) were left NULL even though the
    same values lived in daily_summary the whole time. See issue #13.

    Inserts a body_battery row for any daily_summary date that doesn't have
    one, and fills NULL aggregate columns on existing rows. raw_json is left
    untouched so events-endpoint time-series data is preserved.
    """
    conn.execute(
        """
        INSERT INTO body_battery (calendar_date, charged, drained, highest, lowest, most_recent, at_wake, during_sleep)
        SELECT
            ds.calendar_date,
            ds.body_battery_charged,
            ds.body_battery_drained,
            ds.body_battery_highest,
            ds.body_battery_lowest,
            ds.body_battery_most_recent,
            ds.body_battery_at_wake,
            ds.body_battery_during_sleep
        FROM daily_summary ds
        WHERE ds.body_battery_highest      IS NOT NULL
           OR ds.body_battery_lowest       IS NOT NULL
           OR ds.body_battery_charged      IS NOT NULL
           OR ds.body_battery_drained      IS NOT NULL
           OR ds.body_battery_most_recent  IS NOT NULL
           OR ds.body_battery_at_wake      IS NOT NULL
           OR ds.body_battery_during_sleep IS NOT NULL
        ON CONFLICT(calendar_date) DO UPDATE SET
            charged      = COALESCE(body_battery.charged, excluded.charged),
            drained      = COALESCE(body_battery.drained, excluded.drained),
            highest      = COALESCE(body_battery.highest, excluded.highest),
            lowest       = COALESCE(body_battery.lowest, excluded.lowest),
            most_recent  = COALESCE(body_battery.most_recent, excluded.most_recent),
            at_wake      = COALESCE(body_battery.at_wake, excluded.at_wake),
            during_sleep = COALESCE(body_battery.during_sleep, excluded.during_sleep)
        """
    )


def cleanup_invalid_rows(conn: sqlite3.Connection) -> None:
    """Remove rows created by earlier permissive parsers."""
    conn.execute("DELETE FROM hrv WHERE calendar_date IS NULL OR TRIM(calendar_date) = ''")


def backfill_hrv_timeline_counts(conn: sqlite3.Connection) -> None:
    """Recompute reading_count from stored raw_json for existing HRV timeline rows."""
    conn.execute(
        """
        UPDATE hrv_timeline
        SET reading_count = COALESCE(
            json_array_length(json_extract(raw_json, '$.hrvReadings')),
            json_array_length(json_extract(raw_json, '$.hrvValues')),
            0
        )
        """
    )

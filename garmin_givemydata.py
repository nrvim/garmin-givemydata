#!/usr/bin/env python3
"""
garmin-givemydata: Get your Garmin Connect data back.

Smart sync: if the database is empty, fetches all historical data year by year.
If the database already has data, fetches only what's new since the last sync.

Data goes straight to SQLite — each batch is committed immediately so a crash
never loses previously fetched data.

Usage:
    python garmin_givemydata.py                    # Smart sync (all data)
    python garmin_givemydata.py --profile health   # Only health metrics
    python garmin_givemydata.py --profile activities  # Only activities
    python garmin_givemydata.py --export ./output  # Export from DB to CSV+JSON
    python garmin_givemydata.py --export-all ./out  # Export CSV+JSON+FIT
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from garmin_client import GarminClient
from garmin_mcp.db import get_connection, init_db, save_to_db
from garmin_mcp.db import query as db_query


def _get_data_dir() -> Path:
    """Determine where to store data (DB, FIT files, .env, browser profile).

    Priority:
    1. GARMIN_DATA_DIR env var (explicit override)
    2. Current working directory — if it contains garmin.db or .env (cloned repo)
    3. ~/.garmin-givemydata/ (pip install default)
    """
    env_dir = os.environ.get("GARMIN_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    cwd = Path.cwd()
    if (cwd / "garmin.db").exists() or (cwd / ".env").exists() or (cwd / "garmin_givemydata.py").exists():
        return cwd

    home_dir = Path.home() / ".garmin-givemydata"
    home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


DATA_DIR = _get_data_dir()
PROFILE_DIR = DATA_DIR / "browser_profile"

# ─── Fetch profiles ──────────────────────────────────────────
FETCH_PROFILES = {
    "all": {
        "description": "Everything — health, activities, training, devices",
        "categories": [
            "profile",
            "full_range",
            "monthly",
            "daily_health",
            "daily_activity",
        ],
    },
    "health": {
        "description": "Health metrics only — HR, sleep, stress, body battery, SpO2, HRV",
        "categories": ["profile", "full_range_health", "monthly", "daily_health"],
    },
    "activities": {
        "description": "Activities only — workouts, GPS tracks, training load",
        "categories": ["profile", "full_range_activities", "daily_activity"],
    },
    "sleep": {
        "description": "Sleep data only — stages, scores, SpO2 during sleep",
        "categories": ["profile", "monthly_sleep", "daily_sleep"],
    },
}


def load_env():
    """Load .env file if present."""
    env_file = DATA_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def get_db_status() -> dict:
    """Check the database: does it exist, how much data, last sync date."""
    db_path = DATA_DIR / "garmin.db"
    if not db_path.exists():
        return {"exists": False, "rows": 0, "last_date": None, "first_date": None}

    conn = get_connection()
    init_db(conn)
    try:
        rows = db_query(conn, "SELECT COUNT(*) as c FROM daily_summary")[0]["c"]
        last = db_query(conn, "SELECT MAX(calendar_date) as d FROM daily_summary")[0]["d"]
        first = db_query(
            conn,
            "SELECT MIN(calendar_date) as d FROM daily_summary WHERE total_steps IS NOT NULL",
        )[0]["d"]
        return {"exists": True, "rows": rows, "last_date": last, "first_date": first}
    finally:
        conn.close()


def fetch_direct_to_db(
    client: GarminClient,
    conn,
    start_date: str,
    end_date: str,
) -> None:
    """Fetch data and save each batch directly to SQLite."""
    counts = {}

    # Get activity IDs that already have detail data (splits/weather/HR zones)
    # This is a mutable set — updated as new details are fetched so subsequent
    # chunks skip activities that were already processed in earlier chunks.
    existing = db_query(
        conn,
        "SELECT DISTINCT activity_id FROM activity_splits",
    )
    known_activity_ids = {r["activity_id"] for r in existing}

    def on_batch(endpoint_name, data, cal_date=None):
        n = save_to_db(conn, endpoint_name, data, cal_date=cal_date)
        if n > 0:
            counts[endpoint_name] = counts.get(endpoint_name, 0) + n
        # Track newly fetched activity details so later chunks skip them
        if endpoint_name == "activity_splits" and cal_date:
            try:
                known_activity_ids.add(int(cal_date))
            except (ValueError, TypeError):
                pass

    s = date.fromisoformat(start_date)
    e = date.fromisoformat(end_date)
    total_days = (e - s).days

    if total_days <= 365:
        print(f"\n  Fetching {start_date} to {end_date} ({total_days} days)...")
        client.fetch_all(
            target_date=end_date,
            start_date=start_date,
            end_date=end_date,
            on_batch=on_batch,
            known_activity_ids=known_activity_ids,
        )
    else:
        # Calculate total chunks for progress reporting
        total_chunks = 0
        c = e
        while c > s:
            total_chunks += 1
            c = max(s, c - timedelta(days=365)) - timedelta(days=1)

        # Chunk into yearly segments (most recent first)
        year_num = 0
        cursor = e
        while cursor > s:
            chunk_start = max(s, cursor - timedelta(days=365))
            chunk_end = cursor

            year_num += 1
            pct = int(year_num / total_chunks * 100)
            print(f"\n[{pct:3d}%] Year {year_num}/{total_chunks}: {chunk_start.isoformat()} to {chunk_end.isoformat()}")

            prev_total = sum(counts.values())
            client.fetch_all(
                target_date=chunk_end.isoformat(),
                start_date=chunk_start.isoformat(),
                end_date=chunk_end.isoformat(),
                on_batch=on_batch,
                known_activity_ids=known_activity_ids,
            )

            new_total = sum(counts.values())
            if new_total == prev_total:
                print("  No data in this chunk, stopping.")
                break

            cursor = chunk_start - timedelta(days=1)

        print("\n[100%] Done.")


def _log_sync(conn, sync_type, count):
    from datetime import datetime, timezone

    conn.execute(
        "INSERT INTO sync_log (sync_date, sync_type, records_upserted, status) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), sync_type, count, "ok"),
    )
    conn.commit()


def main():
    # Send debug logs to file only (not console)
    log_file = DATA_DIR / "debug.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, mode="a")],
        force=True,
    )

    parser = argparse.ArgumentParser(
        description="garmin-givemydata: Get your Garmin Connect data back.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
fetch profiles:
  all          Everything — health, activities, training, devices (default)
  health       Health metrics only — HR, sleep, stress, body battery, SpO2, HRV
  activities   Activities only — workouts, GPS tracks, training load
  sleep        Sleep data only — stages, scores, SpO2 during sleep

examples:
  python garmin_givemydata.py                          # all data → SQLite + FIT files
  python garmin_givemydata.py --profile health          # health metrics only (no FIT)
  python garmin_givemydata.py --no-files                # API data only, skip FIT downloads
  python garmin_givemydata.py --export ./my_data        # export DB to CSV + JSON
  python garmin_givemydata.py --export-gpx ./gpx        # export activities as GPX
  python garmin_givemydata.py --export-tcx ./tcx        # export activities as TCX
""",
    )

    # Fetch options
    fetch_group = parser.add_argument_group("fetch options")
    fetch_group.add_argument(
        "--profile",
        type=str,
        default="all",
        choices=list(FETCH_PROFILES.keys()),
        help="What data to fetch (default: all)",
    )
    fetch_group.add_argument("--full", action="store_true", help="Force full historical fetch")
    fetch_group.add_argument("--days", type=int, help="Fetch last N days")
    fetch_group.add_argument("--since", type=str, help="Fetch from date (YYYY-MM-DD)")
    fetch_group.add_argument(
        "--no-files",
        action="store_true",
        help="Skip FIT file downloads (only fetch API data to SQLite)",
    )

    # Export options
    export_group = parser.add_argument_group("export options (from local database, no Garmin login needed)")
    export_group.add_argument("--export", type=str, metavar="DIR", help="Export to CSV + JSON")
    export_group.add_argument("--export-gpx", type=str, metavar="DIR", help="Export activities as GPX files")
    export_group.add_argument("--export-tcx", type=str, metavar="DIR", help="Export activities as TCX files")

    # FIT-only download
    fit_group = parser.add_argument_group("FIT file download (skip health data sync)")
    fit_group.add_argument(
        "--fit-only",
        action="store_true",
        help="Download FIT files only, skip health data sync",
    )
    fit_group.add_argument(
        "--latest", action="store_true", help="Download only the latest FIT file (use with --fit-only)"
    )
    fit_group.add_argument(
        "--date", type=str, help="Download FIT file for a specific date YYYY-MM-DD (use with --fit-only)"
    )

    # Utility
    parser.add_argument("--json-import", type=str, help="Import existing JSON file to DB")
    parser.add_argument("--status", action="store_true", help="Show database status and exit")
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Show the browser window (default: headless). Useful for debugging login issues.",
    )

    args = parser.parse_args()

    # ── Status ────────────────────────────────────────────
    if args.status:
        status = get_db_status()
        if not status["exists"] or status["rows"] == 0:
            print("No data in database. Run: python garmin_givemydata.py")
        else:
            print(f"Database: {DATA_DIR / 'garmin.db'}")
            print(f"  Daily summaries: {status['rows']} days")
            print(f"  Date range: {status.get('first_date', '?')} to {status.get('last_date', '?')}")

            conn = get_connection()
            for table in [
                "sleep",
                "activity",
                "hrv",
                "training_readiness",
                "heart_rate",
                "stress",
                "body_battery",
                "steps",
                "weight",
                "personal_record",
                "device",
            ]:
                try:
                    count = db_query(conn, f"SELECT COUNT(*) as c FROM {table}")[0]["c"]
                    if count > 0:
                        print(f"  {table}: {count}")
                except Exception:
                    pass
            conn.close()
        return

    # ── JSON import ───────────────────────────────────────
    if args.json_import:
        from garmin_mcp.import_json import main as import_main

        import_main(args.json_import)
        return

    # ── Export (from existing DB, no Garmin login needed) ───
    if args.export or args.export_gpx or args.export_tcx:
        from garmin_mcp.export import (
            download_activity_files,
            export_csv,
            export_json_tables,
        )

        if args.export:
            out = Path(args.export)
            print(f"\nExporting to {out}/")
            print("\nCSV files:")
            export_csv(out / "csv")
            print("\nJSON files:")
            export_json_tables(out / "json")

        if args.export_gpx:
            print(f"\nDownloading GPX files to {args.export_gpx}/")
            download_activity_files(Path(args.export_gpx), file_format="gpx")

        if args.export_tcx:
            print(f"\nDownloading TCX files to {args.export_tcx}/")
            download_activity_files(Path(args.export_tcx), file_format="tcx")
        return

    # ── Fetch from Garmin ─────────────────────────────────
    load_env()
    email = os.environ.get("GARMIN_EMAIL", "")
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        # Interactive prompt — ask for credentials and save them
        print("Garmin Connect credentials required.\n")
        import getpass

        try:
            email = input("  Garmin email: ").strip()
            password = getpass.getpass("  Garmin password: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)

        if not email or not password:
            print("\nEmail and password are required.")
            sys.exit(1)

        # Offer to save to .env so they don't have to enter again
        env_file = DATA_DIR / ".env"
        try:
            save = input("\n  Save credentials to .env for next time? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            save = "n"

        if save != "n":
            env_file.write_text(f"GARMIN_EMAIL={email}\nGARMIN_PASSWORD={password}\n")
            env_file.chmod(0o600)  # restrict to owner-only
            print(f"  Saved to {env_file}")
        else:
            print("  Not saved. Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables next time.")

    today = date.today()
    profile = args.profile

    # FIT-only mode skips DB status check entirely
    if not args.fit_only:
        status = get_db_status()
    else:
        status = {"exists": False, "rows": 0, "last_date": None, "first_date": None}

    if args.full:
        mode = "full"
        start = (today - timedelta(days=365 * 10)).isoformat()
        end = today.isoformat()
    elif args.days:
        mode = "range"
        start = (today - timedelta(days=args.days)).isoformat()
        end = today.isoformat()
    elif args.since:
        mode = "range"
        start = args.since
        end = today.isoformat()
    elif not status["exists"] or status["rows"] == 0:
        mode = "full"
        start = (today - timedelta(days=365 * 10)).isoformat()
        end = today.isoformat()
        if not args.fit_only:
            print("No existing data found. Running full historical fetch...")
    else:
        mode = "incremental"
        last = date.fromisoformat(status["last_date"])
        start = (last - timedelta(days=1)).isoformat()
        end = today.isoformat()
        gap_days = (today - last).days
        print(f"Database has data through {status['last_date']} ({status['rows']} daily records)")
        print(f"Fetching {gap_days + 1} days: {start} to {end}")

    # ── FIT-only mode ─────────────────────────────────────
    if args.fit_only:
        client = GarminClient(
            email=email,
            password=password,
            profile_dir=PROFILE_DIR,
            headless=not args.visible,
        )
        try:
            if not client.login():
                print("Login failed!")
                sys.exit(1)

            # Get activity list from API
            print("Fetching activity list...")
            client._page.goto("https://connect.garmin.com/modern/", wait_until="domcontentloaded")
            time.sleep(2)

            act_result = client._page.evaluate("""
                async () => {
                    const csrf = document.querySelector('meta[name="csrf-token"], meta[name="_csrf"]')?.content;
                    const resp = await fetch('/gc-api/activitylist-service/activities/search/activities?limit=1000&start=0', {
                        credentials: 'include',
                        headers: {'connect-csrf-token': csrf || '', 'Accept': 'application/json'}
                    });
                    if (resp.status !== 200) return [];
                    return await resp.json();
                }
            """)

            if not act_result:
                print("No activities found.")
                sys.exit(1)

            # Filter by date or latest
            if args.latest:
                activities = act_result[:1]
            elif args.date:
                activities = [a for a in act_result if a.get("startTimeLocal", "").startswith(args.date)]
                if not activities:
                    print(f"No activity found for date {args.date}")
                    sys.exit(1)
            elif args.days:
                cutoff = (today - timedelta(days=args.days)).isoformat()
                activities = [a for a in act_result if (a.get("startTimeLocal") or "") >= cutoff]
            else:
                activities = act_result

            fit_dir = DATA_DIR / "fit"
            fit_dir.mkdir(exist_ok=True)

            print(f"Downloading {len(activities)} FIT file(s)...")
            downloaded = 0
            for a in activities:
                aid = a.get("activityId")
                name = a.get("activityName", "")
                date_str = a.get("startTimeLocal", "")
                safe_name = ""
                if name:
                    safe_name = "_" + "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(
                        " ", "_"
                    )
                safe_date = date_str[:10] if date_str else str(aid)
                filename = f"{safe_date}_{aid}{safe_name}.zip"
                filepath = fit_dir / filename

                if filepath.exists():
                    print(f"  {filename} (already exists)")
                    continue

                url = f"/gc-api/download-service/files/activity/{aid}"
                result = client._page.evaluate(
                    f"""
                    async () => {{
                        try {{
                            const csrf = document.querySelector(
                                'meta[name="csrf-token"], meta[name="_csrf"]'
                            )?.content;
                            const resp = await fetch('{url}', {{
                                credentials: 'include',
                                headers: {{'connect-csrf-token': csrf || ''}}
                            }});
                            if (resp.status !== 200) return {{status: resp.status}};
                            const buffer = await resp.arrayBuffer();
                            return {{status: 200, data: Array.from(new Uint8Array(buffer))}};
                        }} catch(e) {{
                            return {{status: 'error'}};
                        }}
                    }}
                """
                )

                if result.get("status") == 200 and result.get("data"):
                    with open(filepath, "wb") as f:
                        f.write(bytes(result["data"]))
                    downloaded += 1
                    print(f"  {filename}")

            print(f"\n{downloaded} FIT file(s) downloaded to {fit_dir}/")
        finally:
            client.close()
        return

    profile_desc = FETCH_PROFILES[profile]["description"]
    print(f"\nMode: {mode}")
    print(f"Profile: {profile} — {profile_desc}")
    print(f"Range: {start} to {end}")

    # Open DB connection — stays open for the entire fetch
    conn = get_connection()
    init_db(conn)

    # Connect and fetch — data goes directly to SQLite
    client = GarminClient(
        email=email,
        password=password,
        profile_dir=PROFILE_DIR,
        headless=not args.visible,
    )

    try:
        if not client.login():
            print("Login failed!")
            sys.exit(1)

        fetch_direct_to_db(client, conn, start, end)

        # Report actual row counts from the database (not upsert operations)
        tables = db_query(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name",
        )
        print("\nDatabase contents:")
        total = 0
        for t in tables:
            name = t["name"]
            row_count = db_query(conn, f"SELECT COUNT(*) as cnt FROM [{name}]")[0]["cnt"]
            if row_count > 0:
                print(f"  {name}: {row_count} rows")
                total += row_count
        print(f"  Total: {total} rows")

        _log_sync(conn, "garmin_givemydata", total)

        # Download FIT files for activities (unless --no-files)
        if not args.no_files and profile in ("all", "activities"):
            fit_dir = DATA_DIR / "fit"
            fit_dir.mkdir(exist_ok=True)

            activities = db_query(
                conn,
                "SELECT activity_id, activity_name, start_time_local FROM activity WHERE start_time_local IS NOT NULL ORDER BY start_time_local DESC",
            )

            # Only download FIT files we don't already have
            existing_fits = {f.stem.split("_")[1] for f in fit_dir.glob("*.zip")} if fit_dir.exists() else set()
            new_activities = [
                (a["activity_id"], a["activity_name"], a["start_time_local"])
                for a in activities
                if str(a["activity_id"]) not in existing_fits
            ]

            if new_activities:
                print(
                    f"\nDownloading FIT files ({len(new_activities)} new, {len(existing_fits)} already downloaded)..."
                )

                client._page.goto(
                    "https://connect.garmin.com/modern/",
                    wait_until="domcontentloaded",
                )
                time.sleep(2)

                downloaded = 0
                for i, (aid, name, date_str) in enumerate(new_activities):
                    safe_name = ""
                    if name:
                        safe_name = "_" + "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(
                            " ", "_"
                        )
                    safe_date = date_str[:10] if date_str else str(aid)
                    filename = f"{safe_date}_{aid}{safe_name}.zip"
                    filepath = fit_dir / filename

                    url = f"/gc-api/download-service/files/activity/{aid}"
                    result = client._page.evaluate(
                        f"""
                        async () => {{
                            try {{
                                const csrf = document.querySelector(
                                    'meta[name="csrf-token"], meta[name="_csrf"]'
                                )?.content;
                                const resp = await fetch('{url}', {{
                                    credentials: 'include',
                                    headers: {{'connect-csrf-token': csrf || ''}}
                                }});
                                if (resp.status !== 200) return {{status: resp.status}};
                                const buffer = await resp.arrayBuffer();
                                return {{status: 200, data: Array.from(new Uint8Array(buffer))}};
                            }} catch(e) {{
                                return {{status: 'error'}};
                            }}
                        }}
                    """
                    )

                    if result.get("status") == 200 and result.get("data"):
                        with open(filepath, "wb") as f:
                            f.write(bytes(result["data"]))
                        downloaded += 1

                    if downloaded > 0 and downloaded % 10 == 0:
                        print(f"  {downloaded}/{len(new_activities)} downloaded...")

                    if i % 20 == 19:
                        time.sleep(1)

                print(f"  FIT files: {downloaded} downloaded to {fit_dir}/")
            else:
                print(f"\nFIT files: all {len(existing_fits)} already downloaded")

    finally:
        client.close()
        conn.close()

    # Final status
    final = get_db_status()
    fit_dir = DATA_DIR / "fit"
    fit_count = len(list(fit_dir.glob("*.zip"))) if fit_dir.exists() else 0

    print("\nDatabase status:")
    print(f"  Daily summaries: {final['rows']} days")
    print(f"  Date range: {final.get('first_date', '?')} to {final.get('last_date', '?')}")
    print(f"  FIT files: {fit_count}")
    print(f"  Location: {DATA_DIR / 'garmin.db'}")


if __name__ == "__main__":
    main()

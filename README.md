# garmin-givemydata

[![CI](https://github.com/nrvim/garmin-givemydata/actions/workflows/ci.yml/badge.svg)](https://github.com/nrvim/garmin-givemydata/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/garmin-givemydata.svg)](https://pypi.org/project/garmin-givemydata/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/nrvim/garmin-givemydata?style=social)](https://github.com/nrvim/garmin-givemydata)

**It's YOUR data. Take it back.**

Garmin makes it nearly impossible for individuals to access their own health data programmatically. There is no public API. The official "developer program" is restricted to approved businesses only. And in March 2026, Garmin deployed aggressive Cloudflare protections that broke **every single community library** — [garth](https://github.com/matin/garth) (deprecated), [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (broken auth), and all downstream tools like Home Assistant integrations.

You paid for the hardware. You generated the data with your body. You should be able to access it.

This project gets your data out of Garmin Connect and into a local SQLite database where **you** own it and **AI can analyze it** through an MCP server for Claude Code.

**47 tables, 10+ years of history, 44 MCP tools for AI analysis. Your data stays on your machine.**

## The Problem

- **No public API**: Garmin's [Connect Developer Program](https://developer.garmin.com/gc-developer-program/) requires a business application. Individual developers are denied.
- **garth is dead**: The most popular auth library was [deprecated on March 28, 2026](https://github.com/matin/garth/releases/tag/v0.8.0) after Garmin changed their SSO flow.
- **Bot detection**: Garmin deployed aggressive bot detection that blocks all known Python HTTP libraries. Every existing workaround stopped working.
- **python-garminconnect is broken**: Depends on garth for auth. [Issue #332](https://github.com/cyberjunky/python-garminconnect/issues/332) has 40+ comments from affected users.
- **Connect+ paywall**: Garmin launched a [$7/month subscription](https://the5krunner.com/2026/03/24/garmin-connect-plus-strength-apps/) and is restricting third-party access to features that compete with it.

**Nobody should buy Garmin products until they open their API to the people who paid for the hardware.**

## Quick Start

### Install

```bash
# macOS
brew install nrvim/tap/garmin-givemydata

# pip (Linux / Windows / macOS)
pip install garmin-givemydata

# or clone
git clone https://github.com/nrvim/garmin-givemydata.git
cd garmin-givemydata
bash setup.sh          # macOS / Linux
setup.bat              # Windows
```

### Fetch your data

```bash
garmin-givemydata                    # fetches all historical data + FIT files
```

First run prompts for credentials, launches a headless browser, and fetches your full history (~30 min for 10 years). After that, daily syncs take seconds.

### Connect AI

Add the MCP server to Claude Code, Claude Desktop, or any MCP client. The config depends on how you installed:

**Homebrew or pip install** — `garmin-mcp` is already in your PATH:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "garmin-mcp"
    }
  }
}
```

**Git clone** — use absolute paths to the venv:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/absolute/path/to/garmin-givemydata/venv/bin/python",
      "args": ["/absolute/path/to/garmin-givemydata/run_mcp.py"],
      "cwd": "/absolute/path/to/garmin-givemydata"
    }
  }
}
```

Save this as:
- **Claude Code:** `.mcp.json` in your project root, or `~/.claude/settings.json` under `mcpServers` for global access
- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

Restart your client and run `/mcp` to approve the server. Then ask:

```
"How was my sleep this week?"
"Am I overtraining? Check my HRV and recovery"
"Compare my fitness this month vs last month"
"Give me a full sports medicine health check"
```

<details>
<summary>Windows, OpenClaw, and other MCP clients</summary>

#### Windows (git clone)

```json
{
  "mcpServers": {
    "garmin": {
      "command": "C:\\Users\\jane\\code\\garmin-givemydata\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\jane\\code\\garmin-givemydata\\run_mcp.py"],
      "cwd": "C:\\Users\\jane\\code\\garmin-givemydata"
    }
  }
}
```

#### Other MCP clients (OpenClaw, Cline, Cursor)

Any client supporting [MCP stdio transport](https://spec.modelcontextprotocol.io/specification/basic/transports/#stdio) can connect. For pip/brew: `garmin-mcp`. For git clone:

```bash
/path/to/garmin-givemydata/venv/bin/python /path/to/garmin-givemydata/run_mcp.py
```

**Important:** Paths must be **absolute** — relative paths will not work.

</details>

## What You Get

- **ALL your data** in one command — 47 tables, activities with splits/weather/HR zones, original FIT files
- **10+ years** of history fetched automatically, smart incremental sync after that
- **44 MCP tools** for AI analysis — not just raw data, but tools with clinical context, anomaly detection, and professional training metrics
- **Export to anything** — CSV, JSON, GPX, TCX from your local database
- **Your data stays local** — nothing is sent anywhere

## MCP Tools (44)

The MCP server gives AI assistants deep access to your health data. Every tool returns **data + context** — not just numbers, but trend direction, anomaly flags, clinical thresholds, and goal attainment.

<details>
<summary><strong>Data & Sync (3 tools)</strong></summary>

| Tool | What It Does |
|------|-------------|
| `garmin_sync` | Check data freshness and pull latest data from Garmin — always shows when the last sync happened. Use `refresh=False` to just check status |
| `garmin_schema` | Show all 47 tables, columns, and row counts |
| `garmin_query` | Run any read-only SELECT query (read-only enforced at the SQLite engine level) |

</details>

<details>
<summary><strong>Daily Overview (3 tools)</strong></summary>

| Tool | What It Does |
|------|-------------|
| `garmin_today` | Complete snapshot: daily summary, last night's sleep, training readiness, HRV, fitness age, last activity |
| `garmin_week_summary` | Current week's totals vs goals: steps, intensity minutes, floors, calories |
| `garmin_health_summary` | Health overview for any date range with all metrics aggregated |

</details>

<details>
<summary><strong>Health Metrics (13 tools)</strong> — enriched with trends, anomaly flags, clinical thresholds</summary>

| Tool | What It Does |
|------|-------------|
| `garmin_heart_rate` | Resting HR with 7-day rolling average and anomaly detection (flags >5 bpm spikes) |
| `garmin_hrv` | HRV with baseline position, BALANCED/UNBALANCED streak, trend direction |
| `garmin_sleep` | Per-night breakdown with stages, deep/REM %, SpO2, stress, Garmin feedback |
| `garmin_stress` | Time-in-zone breakdown (hours in low/medium/high per day) |
| `garmin_body_battery` | Charge/drain patterns with wake values and sleep quality correlation |
| `garmin_spo2` | Clinical threshold flags (<95% warning, <80% sleep apnea recommendation) |
| `garmin_respiration` | Waking respiration with elevated-day flags (>20 breaths/min) |
| `garmin_steps` | Steps with goal attainment % and longest goal-met streak |
| `garmin_floors` | Floors climbed vs goal with ascent/descent breakdown |
| `garmin_calories` | Calorie breakdown: total, active, BMR, consumed |
| `garmin_intensity_minutes` | Weekly intensity vs WHO 150 min/week target, moderate vs vigorous |
| `garmin_hydration` | Fluid intake vs Garmin-calculated goal |
| `garmin_blood_pressure` | Readings with AHA guideline flags (>140/90 mmHg) |

</details>

<details open>
<summary><strong>Training & Performance (13 tools)</strong> — includes tools unique to this project</summary>

| Tool | What It Does |
|------|-------------|
| `garmin_training_load` | **CTL/ATL/TSB** — professional periodization metrics with weekly volume and load by sport |
| `garmin_recovery` | **Post-workout recovery signatures** — RHR/HRV/body battery tracking after hard sessions, by sport |
| `garmin_compare` | **Side-by-side period comparison** — any two date ranges, all metrics, deltas + % changes |
| `garmin_activities` | List/filter activities by type and date — power, HR, training load, location |
| `garmin_activity_detail` | Deep-dive: splits, HR zones, weather, exercise sets in one call |
| `garmin_race_predictions` | 5K/10K/half/marathon times with human-readable formatting and trend |
| `garmin_endurance_score` | Endurance score with classification tier and trend |
| `garmin_hill_score` | Hill score with endurance and strength sub-scores |
| `garmin_vo2max` | VO2max estimates from activities and dedicated tracking |
| `garmin_training_status` | Status history (Productive/Recovery/Detraining) with transition detection |
| `garmin_fitness_age` | Fitness age vs chronological age trajectory with gap analysis |
| `garmin_records` | All PRs with human-readable names (Fastest 5K, Longest Ride, etc.) |
| `garmin_trends` | Weekly/monthly trends for 17 metrics |

</details>

<details>
<summary><strong>Profile & Devices (12 tools)</strong></summary>

| Tool | What It Does |
|------|-------------|
| `garmin_user_profile` | Profile and settings from Garmin Connect |
| `garmin_devices` | Connected devices with type and last sync |
| `garmin_gear` | Equipment tracking (shoes, bikes, etc.) |
| `garmin_badges` | Earned achievements with dates |
| `garmin_body_composition` | Weight, BMI, body fat, muscle mass history |
| `garmin_workouts` | Workout library, training plans, scheduled workouts |
| `garmin_goals` | Active fitness goals |
| `garmin_challenges` | Garmin Connect challenges |
| `garmin_health_snapshot` | On-demand 2-minute health readings (HR, HRV, SpO2, stress) |
| `garmin_daily_events` | Daily events (stress spikes, body battery events) |
| `garmin_activity_types` | All activity type definitions |
| `garmin_hr_zones` | Heart rate zone definitions per sport |

</details>

## Usage

### Fetch (from Garmin Connect)

```bash
garmin-givemydata                              # smart sync (all data + FIT files)
garmin-givemydata --full                       # force full historical re-fetch
garmin-givemydata --days 90                    # fetch last 90 days
garmin-givemydata --since 2025-01-01           # fetch from specific date
garmin-givemydata --profile health             # health metrics only
garmin-givemydata --profile activities         # activities + FIT files only
garmin-givemydata --profile sleep              # sleep data only
garmin-givemydata --no-files                   # skip FIT file downloads
garmin-givemydata --status                     # check database contents
```

### FIT file download only

```bash
garmin-givemydata --fit-only --latest          # latest FIT file
garmin-givemydata --fit-only --date 2026-03-30 # specific date
garmin-givemydata --fit-only --days 7          # last 7 days
garmin-givemydata --fit-only                   # all FIT files
```

### Export (from local database)

```bash
garmin-givemydata --export ./output            # CSV + JSON
garmin-givemydata --export-gpx ./gpx           # GPX (for Strava, Komoot)
garmin-givemydata --export-tcx ./tcx           # TCX (for TrainingPeaks)
```

<details>
<summary>Supported export formats</summary>

| Format | Content | How |
|--------|---------|-----|
| **SQLite** | Health + activities | Default — always created |
| **FIT** (ZIP) | Activities (lossless) | Default — downloaded automatically |
| **CSV** | Health + activities | `--export ./dir` |
| **JSON** | Health + activities | `--export ./dir` |
| **GPX** | Activities (GPS tracks) | `--export-gpx ./dir` |
| **TCX** | Activities (XML) | `--export-tcx ./dir` |

</details>

### Browser engines

| Engine | Flag | Headless | Cloudflare bypass |
|--------|------|----------|-------------------|
| **Camoufox** (default) | none | Yes | Yes |
| **Chrome** | `--chrome --visible` | Needs `--visible` for first login | Only with visible window |

<details>
<summary>Where data is stored</summary>

| Install method | Data location |
|---------------|---------------|
| **Homebrew / pip** | `~/.garmin-givemydata/` |
| **Git clone** | Current directory |
| **Custom** | Set `GARMIN_DATA_DIR` env var |

```
garmin.db              # SQLite database (all health + activity data)
browser_profile/       # Browser session (persists ~1 year)
.env                   # Garmin credentials
fit/                   # Original FIT files (lossless)
```

</details>

<details>
<summary>Comprehensive data — 47 tables</summary>

| Category | Data |
|----------|------|
| **Daily Health** | Steps, calories, distance, floors, intensity minutes, active/sedentary time |
| **Heart Rate** | Resting HR, min/max HR, 7-day average |
| **Stress** | Average/max stress, stress duration by level, stress qualifier |
| **Body Battery** | Charged/drained values, highest/lowest, wake value, sleep value |
| **Sleep** | Duration by stage (deep/light/REM/awake), SpO2 during sleep, sleeping HR, respiration, sleep score |
| **SpO2** | Average, lowest, latest readings |
| **Respiration** | Waking average, highest, lowest |
| **HRV** | Weekly average, last night, baseline ranges, status |
| **Training Readiness** | Score, level, factor breakdowns (HRV, sleep, stress, recovery, load ratio) |
| **Endurance Score** | Overall score, classification tier, VO2max precise value |
| **Hill Score** | Overall score, endurance sub-score, strength sub-score |
| **Race Predictions** | Predicted times for 5K, 10K, half marathon, marathon |
| **Activities** | 45+ fields per activity: duration, distance, HR, power, cadence, elevation, TSS, training effect, VO2max, GPS, temperature, laps |
| **Activity Splits** | Per-km/mile splits with pace, HR, elevation, cadence |
| **Activity HR Zones** | Time spent in each HR zone per activity |
| **Activity Weather** | Temperature, humidity, wind speed/direction during activity |
| **Activity Exercise Sets** | Strength training: exercise name, reps, weight, duration per set |
| **Weight** | Weight, BMI, body fat, body water, bone mass, muscle mass |
| **VO2max** | Running and cycling VO2max trend over time |
| **Blood Pressure** | Systolic, diastolic, pulse |
| **Calories** | Total, active, BMR, consumed, remaining |
| **Fitness Age** | Chronological age vs fitness age |
| **Personal Records** | All PRs across all activity types |
| **Earned Badges** | All badges earned with date and category |
| **Devices** | All registered Garmin devices and sensors |
| **Gear** | Shoes, bikes, etc. with brand, model, usage tracking |
| **Training Status** | Daily and weekly training status (productive, recovery, etc.) |
| **Health Status** | Overall daily health status assessment |
| **Hydration** | Daily goal and intake in ml |

</details>

## Architecture

<details>
<summary>Project structure and data flow</summary>

```
garmin-givemydata/
├── garmin_givemydata.py       # Main entry: smart sync (full or incremental)
├── garmin_client/              # Playwright-based Garmin Connect client
│   ├── client.py               #   GarminClient (login, fetch, export)
│   └── endpoints.py            #   API endpoint definitions
├── garmin_mcp/                 # MCP server + database layer
│   ├── db.py                   #   SQLite schema (47 tables), upsert helpers
│   ├── server.py               #   FastMCP server with 44 tools
│   ├── export.py               #   CSV, JSON, GPX, TCX export
│   ├── import_json.py          #   JSON → SQLite bulk import
│   └── sync.py                 #   Incremental sync engine
├── run_mcp.py                  # MCP server entry point
├── garmin.db                   # Your health data (SQLite, gitignored)
├── fit/                        # Your activity files (FIT/ZIP, gitignored)
├── browser_profile/            # Browser session (gitignored)
└── pyproject.toml
```

**Data flow:**
```
Garmin Connect ──→ SQLite (health + activity metrics)
                └─→ fit/ (original FIT files, lossless)

SQLite ──→ MCP server (AI queries via 44 tools)
       ├─→ CSV/JSON (--export)
       └─→ GPX/TCX (--export-gpx, --export-tcx)
```

</details>

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | Tested | Primary development platform |
| **Linux (Ubuntu/Debian/Fedora)** | Supported | May need `playwright install-deps` for system libraries |
| **Windows 10/11** | Supported | Use PowerShell or Command Prompt |
| **WSL2** | Supported | Works headless with Camoufox |

<details>
<summary>Manual setup (if setup script doesn't work)</summary>

<details>
<summary>macOS</summary>

```bash
brew install python@3.12
cd garmin-givemydata
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # only for --chrome fallback
cp .env.example .env
```
</details>

<details>
<summary>Ubuntu / Debian</summary>

```bash
sudo apt update && sudo apt install python3.12 python3.12-venv
cd garmin-givemydata
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
sudo python -m playwright install-deps chromium
cp .env.example .env
```
</details>

<details>
<summary>Fedora / RHEL</summary>

```bash
sudo dnf install python3.12
cd garmin-givemydata
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
sudo python -m playwright install-deps chromium
cp .env.example .env
```
</details>

<details>
<summary>Windows</summary>

Install Python 3.10+ from [python.org](https://www.python.org/downloads/) — check **"Add to PATH"**.

```powershell
cd garmin-givemydata
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
```

If PowerShell blocks the activate script: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
</details>

</details>

## Troubleshooting

<details>
<summary>Common issues and fixes</summary>

**"Login failed"**: Delete the browser profile and run again. For pip/brew: `rm -rf ~/.garmin-givemydata/browser_profile`. For git clone: `rm -rf browser_profile/`.

**Script crashed / "Execution context was destroyed"**: If using `--chrome --visible`, don't close the Chrome window. Run again.

**"Python not found"**: Make sure Python 3.10+ is on your PATH. macOS: `brew install python@3.12`. Ubuntu: `sudo apt install python3.12 python3.12-venv`.

**403 or session errors**: Session expired. Delete the browser profile and re-login.

**Chrome doesn't open (Linux)**: Use the default Camoufox engine (no display needed), or install Xvfb: `sudo apt install xvfb && xvfb-run python garmin_givemydata.py`.

**Playwright install fails (Linux)**: `sudo python -m playwright install-deps`

**MCP server "failed to connect"**: Paths in `.mcp.json` must be **absolute**. Test: `<path>/venv/bin/python <path>/run_mcp.py`

**Empty data for some metrics**: Training readiness, HRV, body battery, endurance score, hill score, and race predictions require compatible devices (Fenix 7+, Forerunner 265+, Venu 3+, etc.).

**Windows: "execution of scripts is disabled"**: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

</details>

<details>
<summary><strong>How Garmin compares to competitors</strong></summary>

| Company | Open API for Individuals? | Real-time Access? | Data Portability Grade |
|---------|--------------------------|-------------------|----------------------|
| **[Oura](https://cloud.ouraring.com/v2/docs)** | Yes — free, any ring owner | Yes, REST API | **A+** |
| **[WHOOP](https://developer.whoop.com/)** | Yes — free, any member | Yes, API + webhooks | **A+** |
| **[Fitbit](https://dev.fitbit.com/)** | Yes — personal app type | Yes, REST API | **A** |
| **[Apple Health](https://developer.apple.com/documentation/healthkit)** | Yes — HealthKit on-device | Yes, on-device | **A-** |
| **[Polar](https://www.polar.com/accesslink-api/)** | Yes — any developer | Partial | **B+** |
| **Garmin** | **No — business-only** | **No** | **D** |
| **COROS** | No — partner-only | No | **D+** |
| **Samsung** | No — deprecated SDK | On-device only | **D** |
| **Amazfit/Zepp** | No | No | **F** |

</details>

## Contributing

<details>
<summary>How to help</summary>

- **New endpoints**: Garmin has hundreds of internal APIs. Discover new ones via browser dev tools and add them to `endpoints.py`.
- **More MCP tools**: The server has 44 tools including CTL/ATL/TSB, recovery signatures, and period comparison. Ideas: injury risk prediction, sleep optimization, race readiness scoring, overtraining detection.
- **MCP client integrations**: Test with OpenClaw, Cline, Continue, Cursor, or other clients.
- **Other platforms**: ARM (Raspberry Pi), Docker, etc.
- **Data visualization**: Dashboards, charts, reports from SQLite.
- **Export formats**: Parquet, or other formats for pandas, R.
- **Other wearables**: The architecture (browser auth + SQLite + MCP) could work for COROS, Samsung, Amazfit/Zepp.
- **Testing**: Tests, CI, more platform support.

Open an issue or submit a PR.

</details>

## Support This Project

- **Star this repository** — helps others discover the project
- **Report issues** — improve stability and compatibility
- **Spread the word** — share with other Garmin users
- **Contribute code** — new endpoints, MCP tools, export formats, bug fixes
- **[File a GDPR/CCPA request with Garmin](https://www.garmin.com/en-US/account/datamanagement/)** — the more users who formally request data portability, the harder it is to ignore

## Acknowledgments

<details>
<summary>Standing on the shoulders of the community</summary>

- **[garth](https://github.com/matin/garth)** by [@matin](https://github.com/matin) — 350k+ monthly PyPI downloads before deprecation. The auth library that powered the Garmin Python ecosystem.
- **[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)** by [@cyberjunky](https://github.com/cyberjunky) — 2,000+ stars, 127+ API methods. The endpoint catalog was informed by their work.
- **[GarminDB](https://github.com/tcgoetz/GarminDB)** by [@tcgoetz](https://github.com/tcgoetz) — 3,000+ stars. Pioneered SQLite-first Garmin data storage.
- **[garmin-connect-export](https://github.com/pe-st/garmin-connect-export)** — Reliable activity export (GPX, TCX, FIT, JSON).
- **[garmin-data-export](https://github.com/sirredbeard/garmin-data-export)** — Garmin data into LLM-readable text files.
- **[garmy](https://github.com/bes-dev/garmy)** — AI-first Garmin data access with MCP support.

</details>

<details>
<summary>Your legal right to your data (GDPR, CCPA, EU Data Act)</summary>

### EU/EEA — GDPR

**Article 20 — Right to Data Portability** grants the right to receive personal data in a "structured, commonly used and machine-readable format." This covers raw sensor data (heart rate, sleep, steps, SpO2). Derived metrics (training readiness, fitness age) are covered under **Article 15 — Right of Access**.

### United States — CCPA

**Section 1798.100(d)** requires businesses to provide personal information in a "readily useable format that allows the consumer to transmit this information from one entity to another entity without hindrance."

### EU Data Act (Since September 2025)

**Article 3** explicitly requires IoT manufacturers to make data available "without undue delay, free of charge, and, where applicable, continuously and in real-time." A Garmin watch is an IoT device. The data it generates belongs to the user.

**If Garmin provided an open API, this tool would not need to exist.**

</details>

## Disclaimer

This tool is **unofficial** and **not affiliated with Garmin**. It accesses Garmin Connect using your own credentials to retrieve your own data. **Use may violate Garmin's Terms of Service.** You assume all risk and responsibility. See the [full disclaimer](https://github.com/nrvim/garmin-givemydata/wiki/Disclaimer) for details.

## License

[AGPL-3.0](LICENSE) — Free to use, modify, and distribute. If you build a service using this code, you must keep it open source.

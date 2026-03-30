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

## The Problem

- **No public API**: Garmin's [Connect Developer Program](https://developer.garmin.com/gc-developer-program/) requires a business application. Individual developers are denied.
- **garth is dead**: The most popular auth library was [deprecated on March 28, 2026](https://github.com/matin/garth/releases/tag/v0.8.0) after Garmin changed their SSO flow.
- **Bot detection**: Garmin deployed aggressive bot detection that blocks all known Python HTTP libraries. Every existing workaround stopped working.
- **python-garminconnect is broken**: Depends on garth for auth. [Issue #332](https://github.com/cyberjunky/python-garminconnect/issues/332) has 40+ comments from affected users.
- **Connect+ paywall**: Garmin launched a [$7/month subscription](https://the5krunner.com/2026/03/24/garmin-connect-plus-strength-apps/) and is restricting third-party access to features that compete with it.

**Nobody should buy Garmin products until they open their API to the people who paid for the hardware.**

### How Garmin Compares to Competitors

Other wearable companies prove that open data access and a successful business are not mutually exclusive:

| Company | Open API for Individuals? | Real-time Access? | Export Formats | Data Portability Grade |
|---------|--------------------------|-------------------|----------------|----------------------|
| **[Oura](https://cloud.ouraring.com/v2/docs)** | Yes — free, any ring owner | Yes, REST API | JSON, CSV | **A+** |
| **[WHOOP](https://developer.whoop.com/)** | Yes — free, any member | Yes, API + webhooks | JSON, CSV | **A+** |
| **[Fitbit](https://dev.fitbit.com/)** | Yes — personal app type | Yes, REST API | JSON, CSV, TCX | **A** |
| **[Apple Health](https://developer.apple.com/documentation/healthkit)** | Yes — HealthKit on-device | Yes, on-device | XML | **A-** |
| **[Polar](https://www.polar.com/accesslink-api/)** | Yes — any developer | Partial (new data only) | TCX, GPX, FIT, JSON | **B+** |
| **[Wahoo](https://developers.wahooligan.com/)** | Yes, with approval | Yes, REST API | FIT, JSON | **B** |
| **[Suunto](https://apizone.suunto.com/)** | Partner program | Yes, if approved | FIT, GPX, JSON | **B-** |
| **Garmin** | **No — business-only** | **No** | **Incomplete ZIP after 30 days** | **D** |
| **COROS** | No — partner-only | No | One-at-a-time only | **D+** |
| **Samsung** | No — deprecated SDK | On-device only | Limited CSV | **D** |
| **Amazfit/Zepp** | No | No | Barely (1-by-1 GPX) | **F** |

Oura and WHOOP give every user free, documented API access with real-time data. Garmin — a company with $6B+ annual revenue — refuses to offer the same. **This tool exists to fill that gap.**

## The Solution

This project uses browser automation to log into Garmin Connect the same way you would — through a real browser. It handles authentication, extracts your data through the web interface, and stores it locally.

### What You Get

- **ALL your data** in one command — 47 tables covering health metrics, performance scores, activities with splits/weather/HR zones, AND original FIT files
- **10+ years** of historical data fetched automatically
- **Smart sync**: first run fetches everything, subsequent runs only fetch what's new
- **47-table SQLite database** — structured and optimized for analysis, with every field Garmin tracks
- **Per-activity details** — splits, HR zone time, weather conditions, exercise sets for strength training
- **Performance scores** — endurance score, hill score, race predictions (5K/10K/half/marathon)
- **Original FIT files** — lossless device data for every activity, ready to import to Strava, TrainingPeaks, or any platform
- **MCP server** — let AI analyze your health data through Claude Code, Claude Desktop, OpenClaw, or any MCP-compatible client
- **Export to anything** — CSV, JSON, GPX, TCX from your local data
- **Your data stays local** — everything is stored on your machine, nothing is sent anywhere

## Features

### AI-Powered Health Analysis (MCP Server)

The built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server lets any compatible AI assistant query your health database in natural language. No code needed — just ask questions:

```
"How has my resting heart rate changed over 6 months?"
"Show me my cycling activities this year with power data"
"Compare my sleep quality this month vs last month"
"What's my training readiness trend?"
"Am I overtraining? Look at my HRV and stress patterns"
"What day of the week do I sleep best?"
"How is my endurance score trending? Am I getting fitter?"
"What are my predicted race times for a 10K?"
"Show me the weather and HR zones for my last run"
"Break down my last activity by splits — where did I slow down?"
"Give me a full sports medicine health check using all my data"
```

Works with:
- **[Claude Code](https://claude.ai/code)** (CLI, desktop app, VS Code, JetBrains)
- **[Claude Desktop](https://claude.ai/download)** (macOS, Windows)
- **[OpenClaw](https://github.com/nicobailey/OpenClaw)** and other open-source MCP clients
- **Any MCP-compatible tool** — the server follows the standard [MCP protocol](https://spec.modelcontextprotocol.io/)

6 tools are available to the AI:

| Tool | What It Does |
|------|-------------|
| `garmin_schema` | Show all 47 tables, columns, and row counts |
| `garmin_query` | Run any SELECT query against the 47-table database |
| `garmin_health_summary` | Health overview for any date range: daily metrics, sleep, training readiness, endurance score, hill score, race predictions |
| `garmin_activities` | List/filter activities by type, date, distance — includes power, HR, training load, location |
| `garmin_trends` | Weekly/monthly trends for 17 metrics: `resting_hr`, `hrv`, `stress`, `steps`, `sleep_hours`, `body_battery`, `spo2`, `training_readiness`, `floors`, `calories`, `active_minutes`, `respiration`, `weight`, `endurance_score`, `hill_score`, `race_5k`, `race_10k` |
| `garmin_sync` | Pull latest data from Garmin without leaving the chat |

The AI can combine these tools to answer complex questions — correlating sleep with training load, spotting trends you wouldn't notice, comparing HR zones across activities, predicting race times, or building custom reports across years of data. It can also query per-activity details like splits, weather, and exercise sets via `garmin_query`.

### Smart Sync

One command gets everything — health data to SQLite, FIT files to disk:

```bash
# First run: empty DB → fetches all historical data + downloads all FIT files
python garmin_givemydata.py

# Next day: DB has data → fetches only new data + downloads only new FIT files
python garmin_givemydata.py

# Override: fetch last 90 days regardless
python garmin_givemydata.py --days 90
```

### Fetch Profiles

Not everyone needs everything. Pick what you want:

```bash
python garmin_givemydata.py                       # all data + FIT files (default)
python garmin_givemydata.py --profile health       # health metrics only (HR, sleep, stress, HRV)
python garmin_givemydata.py --profile activities    # activities + FIT files only
python garmin_givemydata.py --profile sleep         # sleep data only
python garmin_givemydata.py --no-files              # any profile, but skip FIT downloads
```

### Comprehensive Data — 47 Tables

Every metric Garmin tracks, extracted and stored locally in 47 dedicated SQLite tables:

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

## Getting Started

You need **Google Chrome** installed. That's it.

### Option A: Homebrew (macOS — recommended)

```bash
brew install nrvim/tap/garmin-givemydata
playwright install chromium
garmin-givemydata
```

### Option B: pip install (Linux / Windows / macOS)

```bash
pip install garmin-givemydata
playwright install chromium
garmin-givemydata
```

### Option C: Clone the repo

```bash
git clone https://github.com/nrvim/garmin-givemydata.git
cd garmin-givemydata
./setup.sh                  # macOS/Linux (setup.bat for Windows)
python garmin_givemydata.py
```

### First run

1. A Chrome window opens for Garmin login (first time only — needed for Cloudflare verification)
2. If you have MFA, enter the code in the **terminal**
3. The tool prompts for your credentials and saves them to `.env`
4. Full history is fetched year by year — takes about **30 minutes** for 10 years of data
5. All subsequent runs are **headless** and take **seconds** (incremental sync)

### Where data is stored

| Install method | Data location |
|---------------|---------------|
| **Homebrew / pip** | `~/.garmin-givemydata/` |
| **Git clone** | Current directory (same as the repo) |
| **Custom** | Set `GARMIN_DATA_DIR` env var |

Inside the data directory:
```
garmin.db              # SQLite database (all health + activity data)
browser_profile/       # Chrome session (persists ~1 year)
.env                   # Garmin credentials (email + password)
fit/                   # Original FIT files (lossless activity data)
```

### Reset / clean start

To start fresh, delete the data directory:

```bash
# Homebrew / pip install
rm -rf ~/.garmin-givemydata

# Git clone
rm -f garmin.db && rm -rf browser_profile_stealth
```

### Manual setup (if setup script doesn't work)

<details>
<summary>macOS</summary>

```bash
brew install python@3.12       # skip if you have Python 3.10+
cd garmin-givemydata
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env           # edit .env with your credentials
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
sudo python -m playwright install-deps chromium   # system libraries
cp .env.example .env           # edit .env with your credentials
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
cp .env.example .env           # edit .env with your credentials
```
</details>

<details>
<summary>Windows</summary>

Install Python 3.10+ from [python.org](https://www.python.org/downloads/) — check **"Add to PATH"** during install.

```powershell
cd garmin-givemydata
python -m venv venv
venv\Scripts\Activate.ps1      # or venv\Scripts\activate.bat for CMD
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env         # edit .env with your credentials
```

If PowerShell blocks the activate script:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
</details>

### 3. Connect AI (Optional)

The MCP server lets any AI assistant query your Garmin database. It exposes 6 tools over the [Model Context Protocol](https://modelcontextprotocol.io/):

| Tool | What It Does |
|------|-------------|
| `garmin_schema` | Show all 47 tables, columns, and row counts |
| `garmin_query` | Run any SELECT query against the database |
| `garmin_health_summary` | Health overview: daily metrics, sleep, training readiness, endurance, hill score, race predictions |
| `garmin_activities` | List/filter activities by type, date, distance — includes power, HR, training load |
| `garmin_trends` | Weekly/monthly trends for 17 metrics: `resting_hr`, `hrv`, `stress`, `steps`, `sleep_hours`, `body_battery`, `spo2`, `training_readiness`, `floors`, `calories`, `active_minutes`, `respiration`, `weight`, `endurance_score`, `hill_score`, `race_5k`, `race_10k` |
| `garmin_sync` | Pull latest data from Garmin without leaving the chat |

#### Claude Code (CLI, Desktop App, VS Code, JetBrains)

Create a `.mcp.json` file. You have two options:

**Option A — Global (available in all projects):**

Create `~/.claude/.mcp.json`:

```bash
# macOS / Linux
cat > ~/.claude/.mcp.json << 'EOF'
{
  "mcpServers": {
    "garmin": {
      "command": "/absolute/path/to/garmin-givemydata/venv/bin/python",
      "args": ["/absolute/path/to/garmin-givemydata/run_mcp.py"]
    }
  }
}
EOF
```

**Option B — Per-project (available only in that directory):**

Create `.mcp.json` in your project folder:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/absolute/path/to/garmin-givemydata/venv/bin/python",
      "args": ["/absolute/path/to/garmin-givemydata/run_mcp.py"]
    }
  }
}
```

**Important:** Replace `/absolute/path/to/garmin-givemydata` with the actual path where you cloned the repo. Paths must be **absolute** — relative paths will not work.

Example with a real path:
```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/jane/code/garmin-givemydata/venv/bin/python",
      "args": ["/Users/jane/code/garmin-givemydata/run_mcp.py"]
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "garmin": {
      "command": "C:\\Users\\jane\\code\\garmin-givemydata\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\jane\\code\\garmin-givemydata\\run_mcp.py"]
    }
  }
}
```

After creating the file, restart Claude Code and run `/mcp` to approve the Garmin server.

#### Claude Desktop

Edit the config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the Garmin server to the `mcpServers` object (same format as above). Restart Claude Desktop.

#### OpenClaw / Other MCP Clients

Any client that supports the [MCP stdio transport](https://spec.modelcontextprotocol.io/specification/basic/transports/#stdio) can connect. The server command is:

```bash
/path/to/garmin-givemydata/venv/bin/python /path/to/garmin-givemydata/run_mcp.py
```

#### Verify It Works

Once connected, ask your AI:

```
"Show me the garmin schema"
"Give me a health summary for the last 7 days"
"How has my resting heart rate changed over 6 months?"
"Show me my cycling activities this year"
"What's my endurance score trend?"
"Show me the splits and weather for my last run"
"Give me a full sports medicine health check"
```

## Usage

### Fetch (from Garmin Connect)

```bash
# Smart sync — all data + FIT files (full if empty, incremental if data exists)
python garmin_givemydata.py

# Force full historical re-fetch
python garmin_givemydata.py --full

# Fetch specific range
python garmin_givemydata.py --days 90
python garmin_givemydata.py --since 2025-01-01

# Fetch profiles — get only what you need
python garmin_givemydata.py --profile health       # health metrics only
python garmin_givemydata.py --profile activities    # activities + FIT files
python garmin_givemydata.py --profile sleep         # sleep data only

# Skip FIT file downloads (faster, API data only)
python garmin_givemydata.py --no-files

# Check what's in your database
python garmin_givemydata.py --status
```

### FIT file download only (skip health data sync)

```bash
# Download the latest FIT file
garmin-givemydata --fit-only --latest

# Download FIT file for a specific date
garmin-givemydata --fit-only --date 2026-03-30

# Download FIT files for the last 7 days
garmin-givemydata --fit-only --days 7

# Download all FIT files
garmin-givemydata --fit-only
```

### Export (from local database — no Garmin login needed)

```bash
# Export to CSV + JSON (for Excel, pandas, R, web apps)
python garmin_givemydata.py --export ./my_garmin_data

# Export activities as GPX (for Strava, Komoot, AllTrails)
python garmin_givemydata.py --export-gpx ./gpx_files

# Export activities as TCX (for TrainingPeaks)
python garmin_givemydata.py --export-tcx ./tcx_files
```

### What gets stored where

```
garmin-givemydata/
├── garmin.db              # SQLite — all health + activity data (queryable)
└── fit/                   # Original FIT files (lossless device data)
    ├── 2026-03-03_12345678901_Morning_Road_Cycling.zip
    ├── 2026-02-28_12345678902_Evening_Running.zip
    └── ...
```

FIT files are the **master copy** of your activity data — lossless, straight from the device. You can re-import them to Strava, TrainingPeaks, Intervals.icu, or any platform. GPX and TCX are lossy conversions available as export options for tools that need them.

**All supported formats:**

| Format | Content | How |
|--------|---------|-----|
| **SQLite** | Health + activities | Default — always created |
| **FIT** (ZIP) | Activities (lossless) | Default — downloaded automatically |
| **CSV** | Health + activities | `--export ./dir` |
| **JSON** | Health + activities | `--export ./dir` |
| **GPX** | Activities (GPS tracks) | `--export-gpx ./dir` |
| **TCX** | Activities (XML) | `--export-tcx ./dir` |

## Architecture

```
garmin-givemydata/
├── garmin_givemydata.py       # Main entry: smart sync (full or incremental)
├── garmin_client/              # Playwright-based Garmin Connect client
│   ├── client.py               #   GarminClient (login, fetch, export)
│   └── endpoints.py            #   API endpoint definitions
├── garmin_mcp/                 # MCP server + database layer
│   ├── db.py                   #   SQLite schema (47 tables), upsert helpers
│   ├── server.py               #   FastMCP server with 6 tools
│   ├── export.py               #   CSV, JSON, GPX, TCX export
│   ├── import_json.py          #   JSON → SQLite bulk import
│   └── sync.py                 #   Incremental sync engine
├── run_mcp.py                  # MCP server entry point
├── garmin.db                   # Your health data (SQLite, gitignored, stored in data dir)
├── fit/                        # Your activity files (FIT/ZIP, gitignored)
├── browser_profile/            # Chrome session (gitignored, stored in data dir)
└── pyproject.toml
```

**Data flow:**
```
Garmin Connect ──→ SQLite (health + activity metrics)
                └─→ fit/ (original FIT files, lossless)

SQLite ──→ MCP server (AI queries)
       ├─→ CSV/JSON (--export)
       └─→ GPX/TCX (--export-gpx, --export-tcx)
```

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | Tested | Primary development platform |
| **Linux (Ubuntu/Debian/Fedora)** | Supported | May need `playwright install-deps` for system libraries |
| **Windows 10/11** | Supported | Use PowerShell or Command Prompt |
| **WSL2** | Supported | Needs Chrome installed in WSL or `DISPLAY` set for X11 forwarding |

## Known Limitations

- **MFA on first login**: You can enter the MFA code in the **terminal** or in the **browser window** — either works. After that, the session persists ~1 year.
- **Google Chrome required**: Must be installed on your system. Other Chromium-based browsers are not supported.
- **Don't close the Chrome window**: The script uses the browser to fetch data. Closing it will crash the script. It closes automatically when done.
- **Garmin can change things**: If Garmin updates their bot detection or API endpoints, this tool may need updates. Open an issue if it breaks.
- **First fetch is slow**: 10 years of daily data takes ~30 minutes. After that, daily syncs take seconds.
- **Linux display**: On headless Linux servers, you need a virtual display (Xvfb) or X11 forwarding for the browser window.
- **Garmin ToS**: This accesses Garmin's web interface the same way you do. We believe data portability is a right.

## Troubleshooting

**"Login failed"**: Delete the browser profile and run again for a fresh session. For pip/brew: `rm -rf ~/.garmin-givemydata/browser_profile`. For git clone: `rm -rf browser_profile_stealth/`.

**Script crashed / "Execution context was destroyed"**: You probably closed the Chrome window. Don't close it — the script needs the browser open to fetch data. Run again.

**"Python not found" or wrong version**: Make sure Python 3.10+ is installed and on your PATH. On macOS use `brew install python@3.12`, on Ubuntu `sudo apt install python3.12 python3.12-venv`.

**403 or session errors**: Session may have expired. Delete the browser profile (see "Reset / clean start" above) and re-login.

**Browser doesn't open (Linux)**: You need a display. Either use a desktop environment, or install Xvfb: `sudo apt install xvfb && xvfb-run python garmin_givemydata.py`

**Playwright install fails (Linux)**: Run `sudo python -m playwright install-deps chromium` to install system dependencies (libnss3, libatk, etc.).

**MCP server "failed to connect"**:
- Paths in `.mcp.json` must be **absolute** (not relative)
- On Windows use `\\` or `/` in paths, and point to `venv\Scripts\python.exe`
- Test manually: `<path-to-venv>/python <path-to>/run_mcp.py`
- Check Python version: needs 3.10+

**Empty data for some metrics**: Training readiness, HRV, body battery, endurance score, hill score, and race predictions require a compatible Garmin device (Fenix 7+, Forerunner 265+, Venu 3+, etc.). Older devices may not support all metrics. Activity weather requires GPS-enabled activities.

**"No existing data found" on every run**: Make sure `garmin.db` is in the project root directory (same folder as `garmin_givemydata.py`).

**Windows: "execution of scripts is disabled"**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell to allow activating the venv.

## Contributing

This project exists because Garmin refuses to give users access to their own data. If you believe in data portability, help make this better:

- **New endpoints**: Garmin has hundreds of internal APIs. If you discover new ones via browser dev tools, add them to `endpoints.py`.
- **More MCP tools**: Build specialized analysis tools — training load analysis, injury risk prediction, sleep optimization, race readiness scoring, overtraining detection.
- **MCP client integrations**: Test and document setup with more MCP clients — OpenClaw, Cline, Continue, Cursor, or your own tools.
- **Headless mode**: Figure out how to run fully headless after the initial session is established.
- **Other browsers**: Test with Firefox/Edge using Playwright's other browser channels.
- **Data visualization**: Build dashboards, charts, or reports from the SQLite data.
- **Export formats**: Add CSV, Parquet, or other export formats for use with pandas, R, or other analysis tools.
- **Other wearables**: The architecture (browser auth + SQLite + MCP) could work for COROS, Samsung, Amazfit/Zepp, and others that restrict API access. Fork this and adapt it. (Note: Oura, WHOOP, Polar, Fitbit, Wahoo, and Apple HealthKit already offer open APIs — use those directly instead of scraping.)
- **Testing**: Add tests, CI, and help us support more platforms.

Open an issue or submit a PR. Let's build the data portability tools these companies should have given us.

## Support This Project

If you find this tool useful, please consider supporting its continued development:

- **Star this repository** — helps others discover the project
- **Report issues** — help improve stability and compatibility
- **Spread the word** — share with other Garmin users who want access to their own data
- **Contribute code** — new endpoints, MCP tools, export formats, bug fixes
- **File a GDPR/CCPA data portability request with Garmin** through their [Data Management portal](https://www.garmin.com/en-US/account/datamanagement/) — the more users who formally request proper data portability, the harder it is for Garmin to ignore. The day Garmin opens a real API for individual users, this project can be decommissioned. That's the goal.

## Why This Matters

You bought a $500+ watch. You wear it 24/7. It tracks your heart rate, sleep, stress, blood oxygen, respiration, training load, and recovery — the most intimate data about your body.

And Garmin says you can't have it unless you're a business.

The [garth library](https://github.com/matin/garth) served the community for years, reaching 350k+ monthly PyPI downloads. When Garmin broke it in March 2026, the maintainer couldn't keep up with the arms race and deprecated it. [python-garminconnect](https://github.com/cyberjunky/python-garminconnect), with 2,000 stars, is stuck waiting for a fix that may never come.

This is not about piracy or scraping. This is about **data portability**. The EU's GDPR gives you the right to your data. California's CCPA does too. But rights without tools are meaningless.

**garmin-givemydata** is the tool.

## Acknowledgments

This project stands on the shoulders of the community that has been fighting for Garmin data access for years:

- **[garth](https://github.com/matin/garth)** by [@matin](https://github.com/matin) — The authentication library that powered the entire Garmin Python ecosystem. Reached 350k+ monthly PyPI downloads before Garmin's changes forced its deprecation in March 2026. Garth's clean design and the maintainer's tireless work through multiple Garmin SSO changes kept the community alive for years.
- **[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)** by [@cyberjunky](https://github.com/cyberjunky) — 2,000+ stars, 127+ API methods mapped, the most comprehensive Garmin API wrapper. The endpoint catalog in this project was informed by their work.
- **[GarminDB](https://github.com/tcgoetz/GarminDB)** by [@tcgoetz](https://github.com/tcgoetz) — 3,000+ stars, pioneered the approach of storing Garmin data in a local database with analysis notebooks. The SQLite-first design of garmin-givemydata follows their lead.
- **[garmin-connect-export](https://github.com/pe-st/garmin-connect-export)** — Reliable activity export tool supporting GPX, TCX, FIT, and JSON formats.
- **[garmin-data-export](https://github.com/sirredbeard/garmin-data-export)** — Exports Garmin data into LLM-readable text files.
- **[garmy](https://github.com/bes-dev/garmy)** — Brought AI-first thinking to Garmin data access with MCP server support.

These projects served the community faithfully. When Garmin broke them, we built on what they taught us.

### Before garmin-givemydata

The community has been working around Garmin's restrictions for years using various formats and tools:

| Approach | Format | Limitation |
|----------|--------|------------|
| Garmin Connect web export | CSV (bulk), GPX/TCX/FIT (per activity) | Manual, one activity at a time for GPS data |
| Garmin GDPR data request | JSON (zip file) | Can take **up to 30 days** to process |
| garmin-connect-export | GPX, TCX, FIT, JSON | Activities only, no health metrics |
| GarminDB | SQLite (from FIT files) | Requires USB download from device |
| python-garminconnect | JSON (API responses) | Broken since March 2026 |
| garth | JSON (auth only) | Deprecated March 2026 |

garmin-givemydata gives you **all your data** — health metrics AND original FIT files — in a **queryable database** (not raw files), with **AI analysis built in** (not just export), and **daily incremental sync** (not a one-time dump).

## Your Legal Right to Your Data

Data portability laws in multiple jurisdictions grant individuals the right to access and receive their personal data. Your applicable rights depend on your jurisdiction and which Garmin entity controls your data (Garmin Ltd. is incorporated in Switzerland; Garmin International is in Kansas, USA).

### EU/EEA — General Data Protection Regulation (GDPR)

**Article 20 — Right to Data Portability:**

> *"The data subject shall have the right to receive the personal data concerning him or her, which he or she has provided to a controller, in a structured, commonly used and machine-readable format and have the right to transmit those data to another controller without hindrance from the controller to which the personal data have been provided."*

Article 20 covers data you directly provided and data observed/collected by sensors (heart rate readings, sleep stages, steps, SpO2, respiration — i.e., raw sensor data from your Garmin device). Note that Article 20 may **not** cover derived or inferred data — metrics like training readiness scores, endurance scores, hill scores, race predictions, and fitness age are algorithmic outputs that Garmin computes from raw data. These derived metrics may fall outside Article 20's portability requirement (per EDPB guidance), though they are covered under **Article 15 — Right of Access**, which grants the right to access **all** personal data a controller processes, including derived data.

If Garmin's official export is inadequate, the proper legal remedy under GDPR is to file a complaint with your national Data Protection Authority. This tool helps you exercise your right of access in practice.

**Applies to:** EU/EEA residents only.

### United States — California Consumer Privacy Act (CCPA)

**Section 1798.100(a) — Right to Know:**

> *"A consumer shall have the right to request that a business that collects a consumer's personal information disclose to that consumer the categories and specific pieces of personal information the business has collected."*

**Section 1798.100(d) — Right to Portability:** Businesses must provide personal information in a "readily useable format that allows the consumer to transmit this information from one entity to another entity without hindrance."

The CCPA allows up to **two right-to-know requests per 12-month period**, with a 45-day response window (extendable by 45 more days). California residents (and residents of states with similar laws — Colorado, Connecticut, Virginia, Utah, Oregon, Texas, Montana, and others) have statutory rights to their personal data.

**Applies to:** California residents (and residents of other states with similar privacy laws).

### US Federal — Computer Fraud and Abuse Act (CFAA)

In **Van Buren v. United States (2021)**, the US Supreme Court narrowed the CFAA's "exceeds authorized access" provision, holding it means accessing areas of a computer one is not entitled to access at all — not using authorized access for purposes that violate a terms-of-service agreement. However, Van Buren addressed the "exceeds authorized access" prong, not the separate "without authorization" prong. Whether a platform can revoke authorization through technical measures (like bot detection) and thereby make continued automated access "without authorization" is **not settled law**.

In practice, accessing your own account with your own legitimate credentials to retrieve your own personal data carries low CFAA risk, but the interaction between ToS violations and the CFAA remains an open legal question.

### Brazil — Lei Geral de Proteção de Dados (LGPD)

**Article 18(V) — Right to Data Portability:**

> *"The data subject has the right to obtain from the controller, at any time and upon request: [...] V - portability of the data to another service or product provider, through an express request, subject to observance of commercial and industrial secrets."*

Brazilian residents have similar (though not identical) data portability rights to EU citizens. The LGPD portability right is still largely unregulated by Brazil's ANPD and includes additional restrictions around commercial and industrial secrets.

**Applies to:** Brazilian residents only.

### Why This Tool Exists

**This tool would not need to exist if Garmin provided adequate data portability.**

Garmin offers a data export through their Data Management portal. In practice, the export has significant gaps:

| Issue | Garmin's Export | What we believe the law requires |
|-------|----------------|----------------------------------|
| **Completeness** | Missing raw sensor data: continuous heart rate readings, detailed HRV nightly data, per-activity running dynamics (ground contact time, vertical oscillation, stride length, ground contact balance). Garmin collects and displays these in their app but does not include them in the export | GDPR Art. 15 requires access to **all** personal data; Art. 20 requires portability of raw sensor data in a machine-readable format |
| **Format** | Raw JSON blobs in a ZIP file — not tabular, not queryable, not structured for transfer to another service | GDPR Art. 20 requires "structured, commonly used and machine-readable" format that enables transfer "without hindrance" |
| **Timeliness** | One-time snapshot that can take up to 30 days (within the legally permitted window, but not designed for ongoing access) | While 30 days is technically compliant with GDPR Art. 12, the lack of any real-time or incremental export mechanism means users cannot practically exercise ongoing control over their data |

Garmin collects your heart rate every second, your sleep stages every night, your stress levels continuously, your running dynamics on every step — and displays all of it in their app. But their official export omits much of this raw sensor data and delivers it in a format not suited for analysis or transfer to another service.

Even if Garmin's one-time export were complete and well-formatted, it would still be insufficient. Your body generates new health data **every day** — every heartbeat, every night's sleep, every workout. A one-time ZIP dump is stale the moment it's delivered. What data portability actually requires is **ongoing, programmatic access** — an API or daily export that lets you keep your local copy current, analyze trends in real-time, and feed your data to the tools of your choice. Garmin has the infrastructure (their app syncs in seconds), but they choose not to expose it to users. They reserve programmatic access exclusively for approved business partners through the [Garmin Connect Developer Program](https://developer.garmin.com/gc-developer-program/), which individual developers are denied entry to.

**If Garmin provided an open API or even a daily automated export, this tool would not need to exist.** We built it because the official channels fail to deliver what the law intends and what users need.

### EU Data Act (Applicable Since September 2025)

The [EU Data Act](https://eur-lex.europa.eu/eli/reg/2023/2854/oj) (Regulation 2023/2854) goes further than GDPR. It **explicitly requires manufacturers of connected devices (IoT) to provide users access to data generated by their devices** — which includes fitness trackers and wearables like Garmin watches.

**Article 3 — Obligation to make data accessible:**

> *"Where data cannot be directly accessed by the user from the product, the data holder shall make available to the user the data [...] without undue delay, free of charge, and, where applicable, continuously and in real-time."*

**Article 4 — Right of users to access and use data:**

Users have the right to access data generated by their connected devices, and manufacturers must make this data available in a "comprehensive, structured, commonly used and machine-readable format."

Under the EU Data Act, Garmin is legally required to provide EU users with real-time, machine-readable access to the data generated by their watches — including heart rate, sleep, steps, GPS, and all other sensor data. The Act applies to data generated by the device, not just data "provided by" the user (which was the narrower scope of GDPR Article 20).

**This is now EU law. A Garmin watch is an IoT device. The data it generates belongs to the user.**

## Disclaimer

**This project is for personal, educational, and research purposes only. Nothing in this document constitutes legal advice. Consult a qualified attorney in your jurisdiction for legal guidance specific to your situation.**

- This tool is **unofficial** and is **not affiliated with, endorsed by, or supported by Garmin Ltd. or its subsidiaries**.
- This tool accesses Garmin Connect using your own credentials to retrieve your own personal data. It does not access, collect, or store any other user's data.
- **Use of this tool may violate Garmin's Terms of Service.** While we believe the legal right to data portability is clear, the interaction between data protection law and terms of service is unsettled in many jurisdictions. **You assume all risk and responsibility** for your use of this tool, including the risk of account suspension or termination by Garmin.
- The authors and contributors of this project are **not responsible** for any consequences arising from the use of this tool, including but not limited to: account termination, data loss, legal action, breach of contract claims, or any other damages.
- This tool is provided **"as is"**, without warranty of any kind, express or implied.
- This tool does **not** bypass any authentication, encryption, or security measures. It logs in through the standard web interface using your own credentials, the same way you would in a browser.
- **Do not** use this tool to access accounts that do not belong to you.
- **Do not** use this tool for commercial purposes, competitive intelligence, or any activity that harms Garmin or its users.
- Users are solely responsible for complying with all applicable laws and terms of service in their jurisdiction.
- Raw personal health data (sensor readings) is not copyrightable. However, Garmin's specific data structures, API designs, and derived algorithmic outputs may have intellectual property protections.

If you believe in the right to personal data portability, consider filing a formal GDPR/CCPA data portability request with Garmin through their [Data Management portal](https://www.garmin.com/en-US/account/datamanagement/) to establish a record of what their official export provides and what it omits.

## License

[AGPL-3.0](LICENSE) — Free to use, modify, and distribute. If you build a service using this code, you must keep it open source. This ensures data portability tools remain available to everyone.

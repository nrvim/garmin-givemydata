#!/usr/bin/env bash
# garmin-givemydata setup — one script to get everything running
set -e

echo
echo "  ╔══════════════════════════════════════╗"
echo "  ║       garmin-givemydata setup        ║"
echo "  ║    It's YOUR data. Take it back.     ║"
echo "  ╚══════════════════════════════════════╝"
echo

# ── Step 1: Check Python ──────────────────────────────────────
echo "[1/5] Checking Python..."

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            echo "       Found Python $version ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo
    echo "  ERROR: Python 3.10+ is required but not found."
    echo
    echo "  Install it first:"
    echo "    macOS:   brew install python@3.12"
    echo "    Ubuntu:  sudo apt install python3.12 python3.12-venv"
    echo "    Fedora:  sudo dnf install python3.12"
    echo
    exit 1
fi

# ── Step 2: Check Chrome ──────────────────────────────────────
echo "[2/5] Checking Google Chrome..."

CHROME_FOUND=false
if [ "$(uname)" = "Darwin" ]; then
    [ -d "/Applications/Google Chrome.app" ] && CHROME_FOUND=true
elif command -v google-chrome &>/dev/null || command -v google-chrome-stable &>/dev/null; then
    CHROME_FOUND=true
fi

if [ "$CHROME_FOUND" = false ]; then
    echo
    echo "  WARNING: Google Chrome was not detected."
    echo "  Chrome is required for authentication."
    echo "  Install it from: https://www.google.com/chrome/"
    echo
    read -p "  Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "       Chrome found"
fi

# ── Step 3: Create venv + install deps ────────────────────────
echo "[3/5] Setting up Python environment..."

if [ ! -d "venv" ]; then
    "$PYTHON" -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip -q 2>&1 | tail -1
pip install -r requirements.txt -q 2>&1 | tail -1
echo "       Dependencies installed"

# ── Step 4: Install browser driver ────────────────────────────
echo "[4/5] Installing browser driver..."
python -m playwright install chromium 2>&1 | grep -E "downloaded|Downloading" || echo "       Browser driver ready"

# Linux may need system deps
if [ "$(uname)" = "Linux" ]; then
    echo "       (Linux detected — if browser fails, run: sudo python -m playwright install-deps chromium)"
fi

# ── Step 5: Garmin credentials ────────────────────────────────
echo "[5/5] Garmin Connect credentials"
echo

if [ -f ".env" ]; then
    echo "       .env file already exists."
    read -p "       Overwrite with new credentials? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "       Keeping existing credentials."
    else
        SETUP_CREDS=true
    fi
else
    SETUP_CREDS=true
fi

if [ "${SETUP_CREDS:-false}" = true ]; then
    echo "       Enter your Garmin Connect login credentials."
    echo "       (These are saved locally in .env and never sent anywhere)"
    echo
    read -p "       Email: " GARMIN_EMAIL
    read -s -p "       Password: " GARMIN_PASSWORD
    echo
    echo

    cat > .env << ENVEOF
GARMIN_EMAIL=${GARMIN_EMAIL}
GARMIN_PASSWORD=${GARMIN_PASSWORD}
ENVEOF
    chmod 600 .env
    echo "       Credentials saved to .env (permissions: owner-only)"
fi

# ── Done ──────────────────────────────────────────────────────
echo
echo "  ╔══════════════════════════════════════╗"
echo "  ║          Setup complete!             ║"
echo "  ╚══════════════════════════════════════╝"
echo
echo "  Fetch your data:"
echo
echo "    source venv/bin/activate"
echo "    python garmin_givemydata.py"
echo
echo "  A Chrome window will open. If you have MFA enabled,"
echo "  enter the code in the browser when prompted."
echo
echo "  First run fetches all history (~30 min)."
echo "  After that, daily syncs take seconds."
echo

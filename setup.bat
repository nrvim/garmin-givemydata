@echo off
REM garmin-givemydata setup — one script to get everything running
echo.
echo   ==========================================
echo        garmin-givemydata setup
echo     It's YOUR data. Take it back.
echo   ==========================================
echo.

REM ── Step 1: Check Python ──
echo [1/4] Checking Python...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Python not found.
    echo   Install Python 3.10+ from https://www.python.org/downloads/
    echo   IMPORTANT: Check "Add Python to PATH" during installation.
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Python 3.10+ is required.
    python --version
    echo   Download from https://www.python.org/downloads/
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version') do echo        %%v found

REM ── Step 2: Create venv + install deps ──
echo [2/4] Setting up Python environment...

if not exist "venv" (
    python -m venv venv
)

call venv\Scripts\activate.bat

pip install --upgrade pip -q 2>nul
pip install -r requirements.txt -q 2>nul
echo        Dependencies installed

REM ── Step 3: Install browser driver ──
echo [3/4] Installing browser driver...
python -m playwright install chromium
echo        Browser driver ready

REM ── Step 4: Garmin credentials ──
echo [4/4] Garmin Connect credentials
echo.

if exist ".env" (
    echo        .env file already exists.
    set /p OVERWRITE="       Overwrite with new credentials? (y/N) "
    if /i not "%OVERWRITE%"=="y" (
        echo        Keeping existing credentials.
        goto :done
    )
)

echo        Enter your Garmin Connect login credentials.
echo        (These are saved locally in .env and never sent anywhere)
echo.
set /p GARMIN_EMAIL="       Email: "
set /p GARMIN_PASSWORD="       Password: "

echo GARMIN_EMAIL=%GARMIN_EMAIL%> .env
echo GARMIN_PASSWORD=%GARMIN_PASSWORD%>> .env
echo.
echo        Credentials saved to .env

:done

REM ── Done ──
echo.
echo   ==========================================
echo          Setup complete!
echo   ==========================================
echo.
echo   Fetch your data:
echo.
echo     venv\Scripts\activate.bat
echo     python garmin_givemydata.py
echo.
echo   A Chrome window will open. If you have MFA enabled,
echo   enter the code in the browser when prompted.
echo.
echo   First run fetches all history (~30 min).
echo   After that, daily syncs take seconds.
echo.

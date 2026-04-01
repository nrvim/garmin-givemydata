"""
Garmin Connect Client using SeleniumBase (UC mode) for authentication and data fetching.

Uses undetected-chromedriver via SeleniumBase to bypass Cloudflare bot detection
on Garmin Connect.  All API calls go through the browser context via
``execute_async_script`` so the TLS fingerprint, cookies, and CSRF tokens are
always consistent — the only pattern confirmed working as of April 2026
(see matin/garth#225).
"""

import atexit
import json
import logging
import os as _os
import shutil
import signal
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver

from .endpoints import (
    activity_detail_endpoints,
    daily_graphql,
    daily_rest,
    full_range_graphql,
    full_range_rest,
    monthly_graphql,
    monthly_rest,
    profile_endpoints,
    profile_graphql,
)

log = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path.home() / ".garmin-client" / "browser_profile"

SSO_LOGIN_URL = (
    "https://sso.garmin.com/portal/sso/en-US/sign-in"
    "?clientId=GarminConnect"
    "&service=https%3A%2F%2Fconnect.garmin.com%2Fapp"
)

CSRF_TTL = 1800  # 30 minutes — re-read meta tag after this
_XVFB_SCREEN = "1920x1080x24"
_SENTINEL = ".garmin_clean_exit"


# ─── Process lifecycle ───────────────────────────────────────────


class _ProcessLifecycle:
    """Ensures clean browser shutdown on SIGHUP, SIGTERM, SIGINT, and atexit.

    SSH disconnects send SIGHUP to the child process.  Without this handler
    Chrome dies mid-IndexedDB-write and the profile state is torn — exactly
    the failure mode that causes issue #11's session rot.
    """

    def __init__(self, cleanup_fn):
        self._cleanup = cleanup_fn
        self._cleaned = False

    def install(self):
        atexit.register(self._on_exit)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_signal)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._on_signal)

    def _on_signal(self, signum, frame):
        self._on_exit()
        sys.exit(128 + signum)

    def _on_exit(self):
        if self._cleaned:
            return
        self._cleaned = True
        try:
            self._cleanup()
        except Exception:
            pass


# ─── Garmin Client ───────────────────────────────────────────────


class GarminClient:
    def __init__(
        self,
        email: str,
        password: str,
        profile_dir: Optional[Path] = None,
        headless: bool = False,
        session_file: Optional[Path] = None,
        **_kwargs,  # absorb legacy engine= kwarg
    ):
        self.email = email
        self.password = password
        self.profile_dir = profile_dir or DEFAULT_PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.session_file = session_file
        self._driver = None
        self._csrf: Optional[str] = None
        self._csrf_time: float = 0
        self._display_name: Optional[str] = None
        self._lifecycle: Optional[_ProcessLifecycle] = None
        self._xvfb_proc = None
        self._xvfb_display = None
        self._xvfb_prev_display = None
        self._save_raw_enabled = False

    # ── Display management ───────────────────────────────────────

    def _spawn_xvfb(self) -> Optional[str]:
        """Spawn Xvfb at a realistic size and return its ``:N`` display string."""
        import subprocess

        xvfb = shutil.which("Xvfb")
        if not xvfb:
            return None

        chosen = None
        for n in range(99, 200):
            if not Path(f"/tmp/.X{n}-lock").exists():
                chosen = n
                break
        if chosen is None:
            log.debug("No free Xvfb display slots in :99-:199")
            return None

        display = f":{chosen}"
        try:
            self._xvfb_proc = subprocess.Popen(
                [
                    xvfb,
                    display,
                    "-screen",
                    "0",
                    _XVFB_SCREEN,
                    "-ac",
                    "-nolisten",
                    "tcp",
                    "+extension",
                    "RANDR",
                    "+extension",
                    "GLX",
                    "+extension",
                    "RENDER",
                    "+extension",
                    "COMPOSITE",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        except Exception as e:
            log.debug("Failed to spawn Xvfb: %s", e)
            return None

        for _ in range(20):
            if self._xvfb_proc.poll() is not None:
                log.debug("Xvfb exited immediately, rc=%s", self._xvfb_proc.returncode)
                self._xvfb_proc = None
                return None
            if Path(f"/tmp/.X{chosen}-lock").exists():
                break
            time.sleep(0.1)

        self._xvfb_display = display
        log.info("Spawned Xvfb on %s (%s)", display, _XVFB_SCREEN)
        return display

    def _stop_xvfb(self) -> None:
        """Restore $DISPLAY and stop any Xvfb we spawned."""
        if self._xvfb_prev_display is None:
            _os.environ.pop("DISPLAY", None)
        else:
            _os.environ["DISPLAY"] = self._xvfb_prev_display
        self._xvfb_prev_display = None
        self._xvfb_display = None
        if self._xvfb_proc is not None:
            try:
                self._xvfb_proc.terminate()
                try:
                    self._xvfb_proc.wait(timeout=3)
                except Exception:
                    self._xvfb_proc.kill()
            except Exception as e:
                log.debug("Error stopping Xvfb: %s", e)
            self._xvfb_proc = None

    # ── Profile management ───────────────────────────────────────

    def _cleanup_stale_locks(self) -> None:
        """Remove Chrome profile lock files left behind by unclean exits."""
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            p = self.profile_dir / name
            try:
                if p.exists() or p.is_symlink():
                    p.unlink()
                    log.debug("Removed stale Chrome lock: %s", p)
            except Exception as e:
                log.debug("Could not remove lock %s: %s", p, e)

    def _write_sentinel(self) -> None:
        """Write a clean-exit sentinel after successful browser shutdown."""
        try:
            (self.profile_dir / _SENTINEL).write_text(str(time.time()))
        except Exception:
            pass

    def _check_sentinel(self) -> bool:
        """Check if last exit was clean. Returns True if clean, False if dirty."""
        sentinel = self.profile_dir / _SENTINEL
        if sentinel.exists():
            try:
                sentinel.unlink()
            except Exception:
                pass
            return True
        return False

    def _load_legacy_session(self) -> None:
        """Import cookies from legacy session.json if profile is fresh."""
        if not self.session_file or not self.session_file.exists():
            return
        default_dir = self.profile_dir / "Default"
        if default_dir.exists() and any(default_dir.iterdir()):
            return
        try:
            session = json.loads(self.session_file.read_text())
            age_days = (time.time() - session.get("saved_at", 0)) / 86400
            if age_days >= 364 or not session.get("cookies"):
                return
            self._driver.get("https://connect.garmin.com")
            time.sleep(1)
            count = 0
            for cookie in session["cookies"]:
                if "expires" in cookie:
                    cookie["expiry"] = int(cookie.pop("expires"))
                cookie.pop("size", None)
                try:
                    self._driver.add_cookie(cookie)
                    count += 1
                except Exception:
                    pass
            log.info("Migrated %d legacy cookies from session.json", count)
        except Exception as e:
            log.debug("Legacy session migration failed: %s", e)

    def _save_session(self) -> None:
        """Export Garmin cookies to JSON as a portable backup."""
        if not self.session_file:
            return
        try:
            cookies = self._driver.get_cookies()
        except Exception:
            return
        garmin_cookies = [c for c in cookies if "garmin" in c.get("domain", "")]
        if not garmin_cookies:
            return
        session = {"cookies": garmin_cookies, "saved_at": time.time()}
        fd = _os.open(str(self.session_file), _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o600)
        with _os.fdopen(fd, "w") as f:
            json.dump(session, f, indent=2)
        log.info("Session saved: %d cookies to %s", len(garmin_cookies), self.session_file)

    # ── Browser launch ───────────────────────────────────────────

    def _launch_browser(self) -> None:
        """Launch SeleniumBase UC Chrome with appropriate display settings."""
        self._cleanup_stale_locks()

        use_headless2 = False

        if self.headless:
            if sys.platform.startswith("linux") and not _os.environ.get("DISPLAY"):
                # No display (SSH/server) — spawn Xvfb and run headed against it
                # for better stealth than Chrome's headless mode.
                display = self._spawn_xvfb()
                if display:
                    self._xvfb_prev_display = _os.environ.get("DISPLAY")
                    _os.environ["DISPLAY"] = display
                else:
                    log.warning(
                        "No display and Xvfb not found (apt install xvfb). "
                        "Falling back to headless mode (more detectable)."
                    )
                    use_headless2 = True
            else:
                # Desktop or macOS/Windows — use Chrome's new headless mode
                use_headless2 = True

        driver_kwargs = dict(
            uc=True,
            user_data_dir=str(self.profile_dir),
            locale_code="en-US",
        )
        if use_headless2:
            driver_kwargs["headless2"] = True

        try:
            self._driver = Driver(**driver_kwargs)
        except Exception:
            self._stop_xvfb()
            raise

        self._driver.set_script_timeout(120)

        last_exit_clean = self._check_sentinel()
        if not last_exit_clean:
            log.info("Previous exit was unclean — profile may need warm-up")

        self._load_legacy_session()

        self._lifecycle = _ProcessLifecycle(self.close)
        self._lifecycle.install()

        log.info("Browser engine: SeleniumBase UC (Chrome)")

    # ── Browser helpers ──────────────────────────────────────────

    def _uc_navigate(self, url: str, reconnect_time: int = 10) -> None:
        """Navigate to a URL with Cloudflare bypass (disconnects CDP briefly)."""
        self._driver.uc_open_with_reconnect(url, reconnect_time)
        try:
            WebDriverWait(self._driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    def _type_slowly(self, text: str, delay_s: float = 0.03) -> None:
        """Type text with delays between keystrokes for stealth."""
        actions = ActionChains(self._driver)
        for char in text:
            actions.send_keys(char)
            actions.pause(delay_s)
        actions.perform()

    # ── Login flow ───────────────────────────────────────────────

    def login(self, timeout_ms: int = 600000) -> bool:
        self._launch_browser()

        log.debug("Navigating to connect.garmin.com/modern/")
        try:
            self._uc_navigate("https://connect.garmin.com/modern/", 12)
        except Exception as e:
            log.debug("Initial navigation error (expected for fresh profile): %s", e)
        time.sleep(3)

        log.debug("URL after initial navigation: %s", self._driver.current_url)

        if not self._is_on_login_page():
            setup_ok = self._post_login_setup()
            if setup_ok:
                print("Already logged in (session restored)")
                self._save_session()
                return True
            # If we are on a connect page but CSRF failed, don't clear cookies yet.
            # Just try one navigation to /modern/ to see if it wakes up.
            log.debug("On app page but no CSRF — attempting to refresh context")
            try:
                self._uc_navigate("https://connect.garmin.com/modern/", 12)
                time.sleep(3)
                if self._post_login_setup():
                    print("Already logged in (session restored after refresh)")
                    self._save_session()
                    return True
            except Exception:
                pass

        print("Logging in...")

        # Only clear cookies if we are on the SSO login page (fresh login needed)
        if self._is_on_login_page():
            try:
                self._driver.delete_all_cookies()
                log.debug("Cleared stale cookies for fresh login")
            except Exception as e:
                log.debug("Cookie clear error: %s", e)

        for attempt in range(3):
            try:
                self._uc_navigate(SSO_LOGIN_URL, 12)
                break
            except Exception as e:
                log.debug("SSO navigation attempt %d error: %s", attempt + 1, e)
                time.sleep(3)

        time.sleep(2)
        log.debug("SSO page URL: %s", self._driver.current_url)

        # Wait for login form
        try:
            email_input = WebDriverWait(self._driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]'))
            )
        except Exception:
            log.error("Login form not found on page: %s", self._driver.current_url)
            try:
                body = self._driver.execute_script("return document.body?.innerText?.substring(0, 500)")
                print(f"Login form not found. Current URL: {self._driver.current_url}")
                print(f"Page content: {body}")
            except Exception:
                print(f"Login form not found. Current URL: {self._driver.current_url}")
            print("Try running with --visible or deleting browser_profile/")
            return False

        email_input.click()
        self._type_slowly(self.email, delay_s=0.03)

        try:
            pwd_input = WebDriverWait(self._driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
            )
        except Exception:
            log.error("Password field not found")
            return False

        pwd_input.click()
        self._type_slowly(self.password, delay_s=0.03)

        # Auto-check "Remember Me"
        try:
            self._driver.execute_script("""
                var cb = document.querySelector('input[name="remember"], input[id="remember"]');
                if (cb && !cb.checked) cb.click();
            """)
        except Exception:
            pass

        try:
            submit = self._driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            submit.click()
        except Exception:
            ActionChains(self._driver).send_keys(Keys.ENTER).perform()

        print("Credentials submitted, waiting for Garmin...")

        # Poll until we leave SSO
        max_polls = timeout_ms // 1000
        mfa_prompted = False
        mfa_code_thread = None
        mfa_code_result = [None]

        for poll in range(max_polls):
            time.sleep(1)
            try:
                url = self._driver.current_url
            except Exception:
                continue

            if poll % 5 == 0:
                log.debug("Poll %d: URL = %s", poll, url)

            # Success: we left SSO
            if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                log.info("Login redirect detected: %s", url)
                break

            # Check other tabs (Garmin sometimes opens app in a new tab after MFA)
            handles = self._driver.window_handles
            if len(handles) > 1:
                original = self._driver.current_window_handle
                for handle in handles:
                    self._driver.switch_to.window(handle)
                    p_url = self._driver.current_url
                    if "connect.garmin.com" in p_url and "sso.garmin.com" not in p_url:
                        log.info("Found app in another tab: %s", p_url)
                        url = p_url
                        break
                else:
                    self._driver.switch_to.window(original)
            if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                break

            # MFA detection
            is_mfa_page = "/mfa" in url.lower() or "verifymfa" in url.lower()
            if not is_mfa_page and not mfa_prompted and "sso.garmin.com" in url:
                try:
                    has_mfa_input = self._driver.execute_script("""
                        var inputs = document.querySelectorAll(
                            'input[name="verificationCode"], input[name="securityCode"], input[type="tel"], '
                            + 'input[placeholder*="code"], input[placeholder*="Code"], '
                            + 'input[name="mfaCode"], input[autocomplete="one-time-code"]'
                        );
                        return inputs.length > 0;
                    """)
                    if has_mfa_input:
                        is_mfa_page = True
                        log.info("MFA input found on page (same URL)")
                except Exception:
                    pass

            if not mfa_prompted and is_mfa_page:
                mfa_prompted = True
                log.info("MFA page detected: %s", url)

                try:
                    self._driver.execute_script("""
                        var cb = document.querySelector(
                            'input[name="remember"], input[id="remember"], input[type="checkbox"]'
                        );
                        if (cb && !cb.checked) cb.click();
                    """)
                except Exception:
                    pass

                if sys.stdin.isatty():
                    import threading

                    def _read_mfa():
                        try:
                            mfa_code_result[0] = input("  Enter MFA code: ").strip()
                        except (EOFError, OSError):
                            pass

                    print()
                    print("  MFA required!")
                    print("  Enter code here OR in the browser window:")
                    mfa_code_thread = threading.Thread(target=_read_mfa, daemon=True)
                    mfa_code_thread.start()
                else:
                    print()
                    print("  MFA required — enter code in the browser window...")

            if mfa_prompted and poll % 15 == 0 and poll > 0:
                print("  Still waiting for MFA code...")

            if mfa_prompted and poll > 0 and poll % 30 == 0:
                log.debug("Stuck on SSO after MFA — trying to navigate to app...")
                try:
                    self._driver.get("https://connect.garmin.com/modern/")
                    time.sleep(2)
                    url = self._driver.current_url
                    if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                        log.info("Navigated to app after MFA: %s", url)
                        break
                except Exception as e:
                    log.debug("Nav attempt error: %s", e)

            if mfa_code_result[0] is not None:
                code = mfa_code_result[0]
                mfa_code_result[0] = None
                log.info("MFA code from console (%d chars), submitting...", len(code))
                self._submit_mfa_code(code)

        # Wait for app to load
        time.sleep(3)
        log.debug("Final URL: %s", self._driver.current_url)

        if self._is_on_login_page():
            print(f"Login failed — still on login page: {self._driver.current_url}")
            return False

        print("Login successful!")
        print("Setting up session...")
        log.info("Login successful, URL: %s", self._driver.current_url)
        self._save_session()
        return self._post_login_setup()

    def _submit_mfa_code(self, code: str) -> None:
        """Type an MFA code into the browser and submit."""
        mfa_selectors = [
            'input[name="securityCode"]',
            'input[name="verificationCode"]',
            'input[type="tel"]',
            'input[placeholder*="code"]',
            'input[placeholder*="Code"]',
            'input[name="mfaCode"]',
            'input[autocomplete="one-time-code"]',
        ]

        time.sleep(1)
        for sel in mfa_selectors:
            try:
                mfa_input = WebDriverWait(self._driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                mfa_input.click()
                mfa_input.clear()
                mfa_input.send_keys(code)
                log.info("MFA code filled via selector: %s", sel)

                try:
                    submit_btn = self._driver.find_element(
                        By.CSS_SELECTOR,
                        'button[type="submit"]',
                    )
                    submit_btn.click()
                except Exception:
                    mfa_input.send_keys(Keys.ENTER)

                log.info("MFA code submitted via browser")
                return
            except Exception:
                continue

        log.warning("Could not find MFA input field to fill")

    def _is_on_login_page(self) -> bool:
        try:
            url = self._driver.current_url.lower()
        except Exception:
            return True
        if "connect.garmin.com" in url and "sso.garmin.com" not in url:
            return False
        return "sso.garmin.com" in url or "signin" in url or "sign-in" in url

    # ── Post-login setup ─────────────────────────────────────────

    def _post_login_setup(self) -> bool:
        current = self._driver.current_url
        if "/modern/" not in current:
            log.debug("Navigating to /modern/ for CSRF (was on %s)", current)
            try:
                self._driver.get("https://connect.garmin.com/modern/")
            except Exception:
                pass
            time.sleep(3)

        setup = self._driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            (async function() {
                try {
                    var csrf = document.querySelector(
                        'meta[name="csrf-token"], meta[name="_csrf"]'
                    )?.content;
                    var h = {'connect-csrf-token': csrf};
                    var resp = await fetch(
                        '/gc-api/userprofile-service/socialProfile',
                        {credentials: 'include', headers: h}
                    );
                    var profile = resp.status === 200 ? await resp.json() : null;
                    return {csrf: csrf, displayName: profile ? profile.displayName : null};
                } catch(e) {
                    return {error: String(e)};
                }
            })().then(callback).catch(function(e) { callback({error: String(e)}); });
        """)

        self._csrf = setup.get("csrf") if setup else None
        self._csrf_time = time.time() if self._csrf else 0
        self._display_name = setup.get("displayName") if setup else None
        if not self._csrf:
            log.debug("Could not extract CSRF token")
            return False
        log.info("Display name: %s", self._display_name)
        return True

    def _ensure_csrf(self) -> Optional[str]:
        """Re-read CSRF from page meta tag if stale."""
        if self._csrf and time.time() - self._csrf_time < CSRF_TTL:
            return self._csrf
        self._ensure_on_garmin()
        csrf = self._driver.execute_script(
            'return document.querySelector(\'meta[name="csrf-token"], meta[name="_csrf"]\')?.content'
        )
        if csrf:
            self._csrf = csrf
            self._csrf_time = time.time()
        return self._csrf

    def _ensure_on_garmin(self) -> None:
        """Make sure the browser is on connect.garmin.com for fetch context."""
        try:
            current = self._driver.current_url
        except Exception:
            return
        if "connect.garmin.com" not in current or "sso.garmin.com" in current:
            self._driver.get("https://connect.garmin.com/modern/")
            time.sleep(2)

    # ── Public API ───────────────────────────────────────────────

    def navigate(self, url: str) -> None:
        """Navigate the browser to a URL (same-origin, no CF challenge expected)."""
        self._driver.get(url)
        time.sleep(2)

    def api_fetch(self, api_path: str):
        """Fetch JSON from a /gc-api endpoint via the browser context.

        Returns the parsed JSON or None on failure.
        """
        self._ensure_on_garmin()
        csrf = self._ensure_csrf()
        return self._driver.execute_async_script(
            """
            var callback = arguments[arguments.length - 1];
            var url = arguments[0];
            var csrf = arguments[1];
            (async function() {
                try {
                    var resp = await fetch(url, {
                        credentials: 'include',
                        headers: {'connect-csrf-token': csrf || '', 'Accept': 'application/json'}
                    });
                    if (resp.status !== 200) return null;
                    return await resp.json();
                } catch(e) { return null; }
            })().then(callback).catch(function() { callback(null); });
        """,
            api_path,
            csrf,
        )

    def download_file(self, api_path: str) -> Optional[bytes]:
        """Download a binary file from a /gc-api endpoint. Returns bytes or None."""
        self._ensure_on_garmin()
        csrf = self._ensure_csrf()
        result = self._driver.execute_async_script(
            """
            var callback = arguments[arguments.length - 1];
            var url = arguments[0];
            var csrf = arguments[1];
            (async function() {
                try {
                    var resp = await fetch(url, {
                        credentials: 'include',
                        headers: {'connect-csrf-token': csrf || ''}
                    });
                    if (resp.status !== 200) return {status: resp.status};
                    var buffer = await resp.arrayBuffer();
                    return {status: 200, data: Array.from(new Uint8Array(buffer))};
                } catch(e) { return {status: 'error'}; }
            })().then(callback).catch(function() { callback({status: 'error'}); });
        """,
            api_path,
            csrf,
        )
        if result and result.get("status") == 200 and result.get("data"):
            return bytes(result["data"])
        return None

    # ── Save raw debug data ─────────────────────────────────────

    def _save_raw(self, name: str, data):
        """Save raw JSON response under the ``debug/raw`` directory (next to browser_profile)."""
        if not self.profile_dir:
            return
        raw_dir = self.profile_dir.parent / "debug" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_name = name.replace("/", "_").replace("?", "_").replace("=", "_").replace(":", "_")
        try:
            payload = json.dumps(data, indent=2, sort_keys=True)
            file_path = raw_dir / f"{safe_name}.json"

            if file_path.exists():
                try:
                    if file_path.read_text() == payload:
                        return
                except Exception:
                    pass

                suffix = 2
                while True:
                    candidate = raw_dir / f"{safe_name}__{suffix}.json"
                    if not candidate.exists():
                        file_path = candidate
                        break
                    try:
                        if candidate.read_text() == payload:
                            return
                    except Exception:
                        pass
                    suffix += 1

            file_path.write_text(payload)
        except Exception as e:
            log.debug("Could not save raw data: %s", e)

    # ── Batch fetching ───────────────────────────────────────────

    def _fetch_batch(self, rest: dict, gql: dict) -> dict:
        """Fetch a batch of REST + GraphQL endpoints in parallel via browser."""
        self._ensure_on_garmin()
        csrf = self._ensure_csrf()

        rest_entries = list(rest.items())
        gql_entries = list(gql.items())

        result = self._driver.execute_async_script(
            """
            var callback = arguments[arguments.length - 1];
            var csrf = arguments[0];
            var restEntries = arguments[1];
            var gqlEntries = arguments[2];

            (async function() {
                var h = {'connect-csrf-token': csrf, 'Accept': 'application/json'};

                async function get(url) {
                    try {
                        var resp = await fetch(url, {credentials:'include', headers: h});
                        if (resp.status === 200) {
                            var text = await resp.text();
                            try { return {status: 200, data: JSON.parse(text)}; }
                            catch(e) { return {status: 200, data: text}; }
                        }
                        return {status: resp.status, data: null};
                    } catch(e) { return {status: 'error', data: e.message}; }
                }

                async function gql(query) {
                    try {
                        var resp = await fetch('/gc-api/graphql-gateway/graphql', {
                            method: 'POST',
                            credentials: 'include',
                            headers: Object.assign({}, h, {'Content-Type': 'application/json'}),
                            body: JSON.stringify({query: query})
                        });
                        if (resp.status === 200) return {status: 200, data: await resp.json()};
                        return {status: resp.status, data: null};
                    } catch(e) { return {status: 'error', data: e.message}; }
                }

                var promises = restEntries.map(function(entry) {
                    return get(entry[1]).then(function(r) { return [entry[0], r]; });
                }).concat(gqlEntries.map(function(entry) {
                    return gql(entry[1]).then(function(r) { return ['gql_' + entry[0], r]; });
                }));

                var results = await Promise.all(promises);
                var output = {};
                for (var i = 0; i < results.length; i++) {
                    output[results[i][0]] = results[i][1];
                }
                return output;
            })().then(callback).catch(function(e) { callback({error: String(e)}); });
        """,
            csrf,
            rest_entries,
            gql_entries,
        )

        if result and "error" in result:
            log.warning("_fetch_batch JS error: %s", result["error"])
            return {}

        # Save raw payloads and failures for later replay/debugging.
        if self._save_raw_enabled and result:
            for name, res in result.items():
                if res.get("status") == 200 and res.get("data") is not None:
                    self._save_raw(name, res["data"])
                else:
                    self._save_raw(name, res)

        return result or {}

    def _date_chunks(self, start: str, end: str, max_days: int = 28) -> list:
        """Split a date range into chunks of max_days."""
        chunks = []
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        while s < e:
            chunk_end = min(s + timedelta(days=max_days), e)
            chunks.append((s.isoformat(), chunk_end.isoformat()))
            s = chunk_end + timedelta(days=1)
        return chunks

    def fetch_all(
        self,
        target_date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        on_batch=None,
        known_activity_ids: Optional[set] = None,
        save_raw: bool = False,
    ) -> dict:
        """Fetch all data from Garmin Connect.

        Parameters
        ----------
        on_batch : callable, optional
            ``on_batch(endpoint_name, data, cal_date=None)`` called after each
            successful fetch.
        known_activity_ids : set, optional
            Activity IDs that already have detail data (splits, HR zones, weather).
            These will be skipped during per-activity detail fetching.
        save_raw : bool, default False
            Whether to save raw JSON responses under the ``debug/raw`` directory
            (next to ``browser_profile``).
        """
        self._save_raw_enabled = save_raw
        today = target_date or date.today().isoformat()
        e_date = end_date or today
        s_date = start_date or (date.fromisoformat(today) - timedelta(days=30)).isoformat()

        all_results = {}

        def _process_batch(batch_result, cal_date=None):
            for name, result in batch_result.items():
                if result.get("status") != 200 or not result.get("data"):
                    continue
                if on_batch:
                    on_batch(name, result["data"], cal_date=cal_date)
                else:
                    if name not in all_results:
                        all_results[name] = result
                    else:
                        existing = all_results[name].get("data")
                        new = result["data"]
                        all_results[name]["data"] = _merge_data(existing, new)

        # 1. Profile endpoints (no date)
        print("  Fetching profile data...")
        profile = self._fetch_batch(
            profile_endpoints(),
            profile_graphql(self._display_name),
        )
        _process_batch(profile)

        # 2. Full-range queries
        print("  Fetching full-range data (activities, HRV, training, VO2max, weight)...")
        full_rest = full_range_rest(self._display_name, s_date, e_date)
        full_gql = full_range_graphql(self._display_name, s_date, e_date)
        full = self._fetch_batch(full_rest, full_gql)
        _process_batch(full)

        # 2b. Paginate through ALL activities
        page_start = 100
        while True:
            act_result = self._fetch_batch(
                {
                    f"activities_page_{page_start}": f"/gc-api/activitylist-service/activities/search/activities?limit=100&start={page_start}"
                },
                {},
            )
            page_data = act_result.get(f"activities_page_{page_start}", {})
            if page_data.get("status") != 200 or not page_data.get("data"):
                break
            activities_page = page_data["data"]
            if not isinstance(activities_page, list) or len(activities_page) == 0:
                break
            print(f"    Activities page: fetched {len(activities_page)} more (offset {page_start})")
            if on_batch:
                for a in activities_page:
                    on_batch("activities", a)
            else:
                for a in activities_page:
                    if "activities" not in all_results:
                        all_results["activities"] = {"status": 200, "data": []}
                    all_results["activities"]["data"].append(a)
            page_start += 100
            if len(activities_page) < 100:
                break

        # 3. Monthly-chunked queries
        print("  Fetching monthly-chunked data (sleep stats, HRV, calories, etc.)...")
        chunks = self._date_chunks(s_date, e_date, max_days=28)
        for i, (cs, ce) in enumerate(chunks):
            print(f"    Chunk {i + 1}/{len(chunks)}: {cs} to {ce}")
            m_rest = monthly_rest(self._display_name, cs, ce)
            m_gql = monthly_graphql(self._display_name, cs, ce)
            chunk_result = self._fetch_batch(m_rest, m_gql)
            _process_batch(chunk_result)

        # 4. Daily-chunked REST + GraphQL
        print("  Fetching daily data (stress, HR, sleep, SpO2, body battery)...")
        all_days = []
        d = date.fromisoformat(s_date)
        end = date.fromisoformat(e_date)
        while d <= end:
            all_days.append(d.isoformat())
            d += timedelta(days=1)

        batch_size = 7
        for i in range(0, len(all_days), batch_size):
            batch_days = all_days[i : i + batch_size]
            print(f"    Days {i + 1}-{i + len(batch_days)}/{len(all_days)}: {batch_days[0]} to {batch_days[-1]}")

            rest_batch = {}
            gql_batch = {}
            for day in batch_days:
                for name, url in daily_rest(self._display_name, day).items():
                    rest_batch[f"{name}_{day}"] = url
                for name, query in daily_graphql(self._display_name, day).items():
                    gql_batch[f"{name}_{day}"] = query

            batch_result = self._fetch_batch(rest_batch, gql_batch)

            for full_name, result in batch_result.items():
                if result.get("status") != 200 or not result.get("data"):
                    continue
                parts = full_name.rsplit("_", 1)
                if len(parts) == 2 and len(parts[1]) == 10 and parts[1][4] == "-":
                    base_name = parts[0]
                    day_date = parts[1]
                else:
                    base_name = full_name
                    day_date = None

                flat = _flatten_single(result["data"])

                if on_batch:
                    on_batch(base_name, flat, cal_date=day_date)
                else:
                    if isinstance(flat, dict):
                        entry = {"date": day_date, **flat}
                    else:
                        entry = {"date": day_date, "value": flat}
                    if base_name not in all_results:
                        all_results[base_name] = {"status": 200, "data": []}
                    existing = all_results[base_name]["data"]
                    if isinstance(existing, list):
                        existing.append(entry)
                    else:
                        all_results[base_name] = {"status": 200, "data": [entry]}

        # 5. Per-activity detail data
        activity_ids = []

        for name_key, result in all_results.items():
            if name_key in ("activities", "activities_range"):
                data = result.get("data", [])
                if isinstance(data, list):
                    for a in data:
                        aid = a.get("activityId")
                        if aid:
                            activity_ids.append(aid)

        if not activity_ids and on_batch:
            try:
                act_data = self.api_fetch(
                    "/gc-api/activitylist-service/activities/search/activities?limit=1000&start=0"
                )
                if isinstance(act_data, list):
                    all_api_ids = [a.get("activityId") for a in act_data if a.get("activityId")]
                    activity_ids = [aid for aid in all_api_ids if aid not in (known_activity_ids or set())]
            except Exception as e:
                log.debug("Could not fetch activity IDs: %s", e)
        elif known_activity_ids:
            activity_ids = [aid for aid in activity_ids if aid not in known_activity_ids]

        if activity_ids:
            print(f"  Fetching per-activity details ({len(activity_ids)} new)...")
            for i, aid in enumerate(activity_ids):
                if i % 10 == 0 and i > 0:
                    print(f"    Activity {i}/{len(activity_ids)}")
                detail_eps = activity_detail_endpoints(aid)
                detail_result = self._fetch_batch(detail_eps, {})
                for ep_name, result in detail_result.items():
                    if result.get("status") != 200 or not result.get("data"):
                        continue
                    if on_batch:
                        on_batch(ep_name, result["data"], cal_date=str(aid))
                    else:
                        all_results[f"{ep_name}_{aid}"] = result

        return all_results

    def export_for_ai(
        self,
        output_path: str = "garmin_data_for_ai.json",
        target_date: Optional[str] = None,
        days: int = 30,
    ) -> Path:
        today = target_date or date.today().isoformat()
        start = (date.fromisoformat(today) - timedelta(days=days)).isoformat()

        raw = self.fetch_all(target_date=today, start_date=start, end_date=today)

        export = {
            "_metadata": {
                "exported_at": datetime.now().isoformat(),
                "target_date": today,
                "date_range": {"start": start, "end": today},
                "display_name": self._display_name,
                "endpoints_ok": sum(1 for v in raw.values() if v.get("status") == 200),
                "endpoints_total": len(raw),
            },
            "data": {},
        }

        for name, result in raw.items():
            if result.get("status") == 200 and result.get("data"):
                data = result["data"]
                if isinstance(data, dict) and "data" in data and len(data) == 1:
                    data = data["data"]
                    if isinstance(data, dict) and len(data) == 1:
                        data = list(data.values())[0]
                export["data"][name] = _remove_nulls(data)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(export, f, indent=2)

        size_mb = path.stat().st_size / 1024 / 1024
        print(f"Exported {len(export['data'])} datasets to {path} ({size_mb:.1f} MB)")
        return path

    # ── Shutdown ─────────────────────────────────────────────────

    def close(self):
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                log.debug("driver.quit() error: %s", e)
            self._driver = None
        self._write_sentinel()
        self._stop_xvfb()


# ─── Utility functions ───────────────────────────────────────────


def _merge_data(existing, new):
    """Merge two GraphQL responses (append lists, merge dicts)."""
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = {}
        all_keys = set(list(existing.keys()) + list(new.keys()))
        for k in all_keys:
            if k in existing and k in new:
                merged[k] = _merge_data(existing[k], new[k])
            elif k in existing:
                merged[k] = existing[k]
            else:
                merged[k] = new[k]
        return merged
    if isinstance(existing, list) and isinstance(new, list):
        return existing + new
    return new


def _flatten_single(data):
    """If data is a dict with a single 'data' key wrapping another dict, flatten it."""
    if isinstance(data, dict) and "data" in data and len(data) == 1:
        inner = data["data"]
        if isinstance(inner, dict) and len(inner) == 1:
            return list(inner.values())[0]
        return inner
    return data


def _remove_nulls(obj):
    if isinstance(obj, dict):
        return {k: _remove_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_remove_nulls(item) for item in obj]
    return obj

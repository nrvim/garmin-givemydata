"""
Garmin Connect Client using Playwright for authentication and data fetching.
"""

import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright

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


class _ChromeEngine:
    """Browser engine using Playwright + system Chrome."""

    def launch(self, profile_dir: Path, headless: bool, session_file: Path = None):
        """Launch Chrome. Returns (context, page, playwright_instance, None)."""
        pw = sync_playwright().start()

        cookies_file = profile_dir / "Default" / "Cookies"
        has_valid_session = cookies_file.exists() and cookies_file.stat().st_size > 1024
        use_headless = headless and has_valid_session

        if headless and not has_valid_session:
            print("First login requires a visible browser (Cloudflare verification).")
            print("Subsequent runs will be headless automatically.\n")

        args = [
            "--disable-blink-features=AutomationControlled",
        ]
        if use_headless:
            args.append("--headless=new")

        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            channel="chrome",
            args=args,
            ignore_default_args=["--enable-automation"],
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        return (context, page, pw, None)

    def has_valid_session(self, profile_dir: Path, session_file: Path) -> bool:
        """Check Chrome cookie file exists and is >1024 bytes."""
        cookies_file = profile_dir / "Default" / "Cookies"
        return cookies_file.exists() and cookies_file.stat().st_size > 1024

    def save_session(self, page, session_file: Path):
        """No-op for Chrome -- persists via browser profile automatically."""

    def close(self, context, playwright, browser_ref):
        """Close Chrome context and Playwright."""
        if context:
            context.close()
        if playwright:
            playwright.stop()


class _CamoufoxEngine:
    """Browser engine using Camoufox (anti-detect Firefox) — bypasses Cloudflare headless.

    Uses a persistent browser context (``user_data_dir``) so the full browser
    state — cookies, localStorage, IndexedDB, cache, Cloudflare ``cf_clearance``,
    and the generated fingerprint — is reused across runs. This is the key to
    keeping long-lived Garmin sessions: Cloudflare pins clearance to a specific
    fingerprint + storage combo, and any drift triggers a re-challenge.
    """

    def _resolve_headless(self, headless: bool):
        """Pick the safest headless mode for the current platform.

        On Linux we prefer Camoufox's built-in virtual display (Xvfb) because
        plain ``headless=True`` is still fingerprintable. Falls back to regular
        headless if Xvfb isn't installed.
        """
        if not headless:
            return False
        if sys.platform.startswith("linux"):
            import shutil

            if shutil.which("Xvfb"):
                return "virtual"
            log.info("Xvfb not found — falling back to plain headless. Install xvfb for better Cloudflare bypass.")
        return True

    def _build_kwargs(self, profile_dir: Path, headless: bool) -> dict:
        return dict(
            persistent_context=True,
            user_data_dir=str(profile_dir),
            humanize=True,
            locale=["en-US"],
            os="windows",
            geoip=True,
            headless=self._resolve_headless(headless),
        )

    def launch(self, profile_dir: Path, headless: bool, session_file: Path = None):
        """Launch Camoufox with a persistent context. Returns (context, page, None, cm)."""
        from camoufox.sync_api import Camoufox

        profile_dir.mkdir(parents=True, exist_ok=True)
        kwargs = self._build_kwargs(profile_dir, headless)

        cm = Camoufox(**kwargs)
        try:
            context = cm.__enter__()
        except TypeError:
            # Older Camoufox without persistent_context — degrade gracefully
            log.warning("Camoufox is too old for persistent_context; upgrade with: pip install -U camoufox")
            cm = Camoufox(headless=kwargs["headless"], humanize=True, locale=["en-US"], os="windows", geoip=True)
            browser = cm.__enter__()
            page = browser.new_page()
            self._load_legacy_session(page.context, session_file)
            return (page.context, page, None, cm)

        # With persistent_context=True, __enter__ returns a BrowserContext directly.
        try:
            page = context.pages[0] if context.pages else context.new_page()
        except Exception:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass
            raise

        # Migration: if the persistent profile is fresh but a legacy session.json
        # exists, import those cookies so users upgrading from <0.1.8 don't need
        # to re-login once.
        try:
            profile_has_state = any(profile_dir.rglob("cookies.sqlite")) or any(profile_dir.rglob("places.sqlite"))
        except Exception:
            profile_has_state = False
        if not profile_has_state:
            self._load_legacy_session(context, session_file)

        return (context, page, None, cm)

    def _load_legacy_session(self, context, session_file: Path):
        if not session_file or not session_file.exists():
            return
        try:
            session = json.loads(session_file.read_text())
            age_days = (time.time() - session.get("saved_at", 0)) / 86400
            if age_days < 364 and session.get("cookies"):
                context.add_cookies(session["cookies"])
                log.info(
                    "Migrated %d legacy cookies from session.json (%.0f days old)",
                    len(session["cookies"]),
                    age_days,
                )
        except Exception as e:
            log.debug("Legacy session migration failed: %s", e)

    def has_valid_session(self, profile_dir: Path, session_file: Path) -> bool:
        """Session is valid if either the persistent profile has auth state
        or a legacy session.json file is present and fresh."""
        try:
            if profile_dir and profile_dir.exists():
                if any(profile_dir.rglob("cookies.sqlite")):
                    return True
        except Exception:
            pass
        if not session_file or not session_file.exists():
            return False
        try:
            session = json.loads(session_file.read_text())
            age_days = (time.time() - session.get("saved_at", 0)) / 86400
            return bool(session.get("cookies")) and age_days < 364
        except Exception:
            return False

    def save_session(self, page, session_file: Path):
        """Export cookies to a portable JSON file.

        Primary persistence is the user_data_dir profile; this JSON is an
        extra, portable backup that also powers legacy-migration on upgrade.
        """
        import os

        if not session_file:
            return
        try:
            cookies = page.context.cookies()
        except Exception as e:
            log.debug("Could not read cookies for session export: %s", e)
            return
        garmin_cookies = [
            c for c in cookies if "garmin" in c.get("domain", "") or "cloudflare" in c.get("domain", "")
        ]
        if not garmin_cookies:
            return
        session = {"cookies": garmin_cookies, "saved_at": time.time()}
        fd = os.open(str(session_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(session, f, indent=2)
        log.info("Session saved: %d cookies to %s", len(garmin_cookies), session_file)

    def close(self, context, playwright, browser_ref):
        """Close the Camoufox persistent context and shut down the browser.

        ``browser_ref`` holds the Camoufox context manager; calling ``__exit__``
        properly tears down the browser process AND the virtual display (if any).
        """
        if browser_ref is not None:
            try:
                browser_ref.__exit__(None, None, None)
                return
            except Exception:
                pass
        if context is not None:
            try:
                context.close()
            except Exception:
                pass


class GarminClient:
    def __init__(
        self,
        email: str,
        password: str,
        profile_dir: Optional[Path] = None,
        headless: bool = False,
        engine: str = "auto",
        session_file: Optional[Path] = None,
    ):
        self.email = email
        self.password = password
        self.profile_dir = profile_dir or DEFAULT_PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.session_file = session_file
        self._playwright = None
        self._browser_ref = None  # Camoufox browser reference
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._csrf: Optional[str] = None
        self._display_name: Optional[str] = None

        # Select engine
        if engine == "chrome":
            self._engine = _ChromeEngine()
        elif engine == "camoufox":
            self._engine = _CamoufoxEngine()
        else:  # auto
            try:
                from camoufox.sync_api import Camoufox  # noqa: F401

                self._engine = _CamoufoxEngine()
            except ImportError:
                self._engine = _ChromeEngine()

        engine_name = "Camoufox" if isinstance(self._engine, _CamoufoxEngine) else "Chrome"
        log.info("Browser engine: %s", engine_name)

    def login(self, timeout_ms: int = 600000) -> bool:
        result = self._engine.launch(self.profile_dir, self.headless, self.session_file)
        self._context, self._page, self._playwright, self._browser_ref = result

        log.debug("Navigating to connect.garmin.com/modern/")
        try:
            self._page.goto(
                "https://connect.garmin.com/modern/",
                wait_until="domcontentloaded",
            )
        except Exception as e:
            log.debug("Initial navigation error (expected for fresh profile): %s", e)
        time.sleep(3)

        log.debug("URL after initial navigation: %s", self._page.url)

        if not self._is_on_login_page():
            # Verify we actually have a valid session by trying to extract CSRF
            setup_ok = self._post_login_setup()
            if setup_ok:
                print("Already logged in (session restored)")
                self._engine.save_session(self._page, self.session_file)
                return True
            # CSRF failed — page looks like app but session is invalid
            # Navigate back to SSO for fresh login
            log.debug("On app page but no CSRF — session invalid, proceeding with login")
            try:
                self._page.goto(SSO_LOGIN_URL, wait_until="domcontentloaded")
                time.sleep(3)
            except Exception:
                pass

        print("Logging in...")

        # Clear stale SSO/Garmin cookies to prevent login loops
        try:
            self._context.clear_cookies()
            log.debug("Cleared stale cookies")
        except Exception as e:
            log.debug("Cookie clear error: %s", e)

        # Navigate to SSO — may need retries on fresh profiles
        for attempt in range(3):
            try:
                self._page.goto(SSO_LOGIN_URL, wait_until="domcontentloaded")
                break
            except Exception as e:
                log.debug("SSO navigation attempt %d error: %s", attempt + 1, e)
                time.sleep(3)

        time.sleep(2)
        log.debug("SSO page URL: %s", self._page.url)

        # Wait for login form to be ready
        try:
            email_input = self._page.locator('input[name="email"]').first
            email_input.wait_for(timeout=15000)
        except Exception:
            log.error("Login form not found on page: %s", self._page.url)
            # Dump page content for debugging
            try:
                body = self._page.evaluate("() => document.body?.innerText?.substring(0, 500)")
                print(f"Login form not found. Current URL: {self._page.url}")
                print(f"Page content: {body}")
            except Exception:
                print(f"Login form not found. Current URL: {self._page.url}")
            print("Try running with --visible or deleting browser_profile/")
            return False

        email_input.click()
        self._page.keyboard.type(self.email, delay=30)

        pwd_input = self._page.locator('input[name="password"]').first
        pwd_input.wait_for(timeout=5000)
        pwd_input.click()
        self._page.keyboard.type(self.password, delay=30)

        # Auto-check "Remember Me" on login page
        try:
            self._page.evaluate("""
                () => {
                    const cb = document.querySelector('input[name="remember"], input[id="remember"]');
                    if (cb && !cb.checked) cb.click();
                }
            """)
        except Exception:
            pass

        submit = self._page.locator('button[type="submit"], button:has-text("Sign In")').first
        submit.click()
        print("Credentials submitted, waiting for Garmin...")

        # Poll until we leave SSO — handles both MFA and direct login
        # The user can enter MFA in the browser OR via console (if interactive)
        max_polls = timeout_ms // 1000
        mfa_prompted = False
        mfa_code_thread = None
        mfa_code_result = [None]  # mutable container for thread result

        for poll in range(max_polls):
            time.sleep(1)
            url = self._page.url

            # Log URL periodically
            if poll % 5 == 0:
                log.debug("Poll %d: URL = %s", poll, url)

            # Success: we left SSO entirely
            if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                log.info("Login redirect detected: %s", url)
                break

            # Check if a NEW page/tab opened with the app (Garmin sometimes
            # opens the app in a new tab after MFA)
            for p in self._context.pages:
                p_url = p.url
                if "connect.garmin.com" in p_url and "sso.garmin.com" not in p_url:
                    log.info("Found app in another tab: %s", p_url)
                    self._page = p
                    url = p_url
                    break
            if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                break

            # After MFA prompted: only do lightweight URL checks, don't
            # navigate or run JS that could disrupt the MFA page.
            # The user will complete MFA in the browser — Garmin will
            # redirect to connect.garmin.com automatically.

            # MFA page detected — check URL AND check for MFA input fields on the page
            is_mfa_page = "/mfa" in url.lower() or "verifymfa" in url.lower()
            if not is_mfa_page and not mfa_prompted and "sso.garmin.com" in url:
                try:
                    has_mfa_input = self._page.evaluate("""
                        () => {
                            const inputs = document.querySelectorAll(
                                'input[name="verificationCode"], input[name="securityCode"], input[type="tel"], '
                                + 'input[placeholder*="code"], input[placeholder*="Code"], '
                                + 'input[name="mfaCode"], input[autocomplete="one-time-code"]'
                            );
                            return inputs.length > 0;
                        }
                    """)
                    if has_mfa_input:
                        is_mfa_page = True
                        log.info("MFA input found on page (same URL)")
                except Exception:
                    pass

            if not mfa_prompted and is_mfa_page:
                mfa_prompted = True
                log.info("MFA page detected: %s", url)

                # Auto-check "Remember this browser" if available
                try:
                    self._page.evaluate("""
                        () => {
                            const cb = document.querySelector('input[name="remember"], input[id="remember"], input[type="checkbox"]');
                            if (cb && !cb.checked) cb.click();
                        }
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

            # Show waiting status for MFA
            if mfa_prompted and poll % 15 == 0 and poll > 0:
                print("  Still waiting for MFA code...")

            # If we've been stuck on SSO for 30+ seconds after MFA was prompted,
            # try navigating to the app directly — the session might be valid
            if mfa_prompted and poll > 0 and poll % 30 == 0:
                log.debug("Stuck on SSO after MFA — trying to navigate to app...")
                try:
                    self._page.goto(
                        "https://connect.garmin.com/modern/",
                        wait_until="domcontentloaded",
                        timeout=10000,
                    )
                    time.sleep(2)
                    url = self._page.url
                    if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                        log.info("Navigated to app after MFA: %s", url)
                        break
                except Exception as e:
                    log.debug("Nav attempt error: %s", e)

            # If console MFA code was entered, type it into the browser
            if mfa_code_result[0] is not None:
                code = mfa_code_result[0]
                mfa_code_result[0] = None  # consume it
                log.info("MFA code from console (%d chars), submitting...", len(code))
                self._submit_mfa_code(code)

        # Wait for app to load
        time.sleep(3)
        log.debug("Final URL: %s", self._page.url)

        if self._is_on_login_page():
            print(f"Login failed — still on login page: {self._page.url}")
            return False

        print("Login successful!")
        print("Setting up session...")
        log.info("Login successful, URL: %s", self._page.url)
        self._engine.save_session(self._page, self.session_file)
        return self._post_login_setup()

    def _submit_mfa_code(self, code: str):
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
                mfa_input = self._page.locator(sel).first
                mfa_input.wait_for(timeout=3000)
                mfa_input.click()
                mfa_input.fill(code)
                log.info("MFA code filled via selector: %s", sel)

                submit_btn = self._page.locator(
                    'button[type="submit"], button:has-text("Verify"), '
                    'button:has-text("Submit"), button:has-text("Continue"), '
                    'button:has-text("Next")'
                ).first
                try:
                    submit_btn.click()
                except Exception:
                    self._page.keyboard.press("Enter")

                log.info("MFA code submitted via browser")
                return
            except Exception:
                continue

        log.warning("Could not find MFA input field to fill")

    def _is_on_login_page(self) -> bool:
        url = self._page.url.lower()
        if "connect.garmin.com" in url and "sso.garmin.com" not in url:
            return False
        return "sso.garmin.com" in url or "signin" in url or "sign-in" in url

    def _post_login_setup(self) -> bool:
        # Make sure we're on the /modern/ page which has the CSRF meta tag
        current = self._page.url
        if "/modern/" not in current:
            log.debug("Navigating to /modern/ for CSRF (was on %s)", current)
            try:
                self._page.goto(
                    "https://connect.garmin.com/modern/",
                    wait_until="domcontentloaded",
                )
            except Exception:
                pass
            time.sleep(3)

        setup = self._page.evaluate("""
            async () => {
                const csrf = document.querySelector(
                    'meta[name="csrf-token"], meta[name="_csrf"]'
                )?.content;
                const h = {'connect-csrf-token': csrf};
                const resp = await fetch(
                    '/gc-api/userprofile-service/socialProfile',
                    {credentials: 'include', headers: h}
                );
                const profile = resp.status === 200 ? await resp.json() : null;
                return {csrf, displayName: profile?.displayName};
            }
        """)
        self._csrf = setup.get("csrf")
        self._display_name = setup.get("displayName")
        if not self._csrf:
            log.debug("Could not extract CSRF token")
            return False
        log.info("Display name: %s", self._display_name)
        return True

    def _fetch_batch(self, rest: dict, gql: dict) -> dict:
        """Fetch a batch of REST + GraphQL endpoints in parallel via browser."""
        # Ensure we're on the right page (navigation can destroy context)
        current = self._page.url
        if "connect.garmin.com" not in current or "sso.garmin.com" in current:
            try:
                self._page.goto(
                    "https://connect.garmin.com/modern/",
                    wait_until="domcontentloaded",
                )
                time.sleep(2)
            except Exception:
                pass

        rest_entries = list(rest.items())
        gql_entries = list(gql.items())

        return self._page.evaluate(
            """
            async ([csrf, restEntries, gqlEntries]) => {
                const h = {'connect-csrf-token': csrf, 'Accept': 'application/json'};

                async function get(url) {
                    try {
                        const resp = await fetch(url, {credentials:'include', headers: h});
                        if (resp.status === 200) {
                            const text = await resp.text();
                            try { return {status: 200, data: JSON.parse(text)}; }
                            catch { return {status: 200, data: text}; }
                        }
                        return {status: resp.status, data: null};
                    } catch(e) { return {status: 'error', data: e.message}; }
                }

                async function gql(query) {
                    try {
                        const resp = await fetch('/gc-api/graphql-gateway/graphql', {
                            method: 'POST',
                            credentials: 'include',
                            headers: {...h, 'Content-Type': 'application/json'},
                            body: JSON.stringify({query})
                        });
                        if (resp.status === 200) return {status: 200, data: await resp.json()};
                        return {status: resp.status, data: null};
                    } catch(e) { return {status: 'error', data: e.message}; }
                }

                const promises = [
                    ...restEntries.map(([name, url]) => get(url).then(r => [name, r])),
                    ...gqlEntries.map(([name, query]) => gql(query).then(r => ['gql_' + name, r])),
                ];

                const results = await Promise.all(promises);
                const output = {};
                for (const [name, result] of results) {
                    output[name] = result;
                }
                return output;
            }
        """,
            [self._csrf, rest_entries, gql_entries],
        )

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
    ) -> dict:
        """Fetch all data from Garmin Connect.

        Parameters
        ----------
        on_batch : callable, optional
            ``on_batch(endpoint_name, data, cal_date=None)`` called after each
            successful fetch.  When provided, data is saved immediately (direct-
            to-DB).  When *None*, results accumulate in memory (legacy mode).
        known_activity_ids : set, optional
            Activity IDs that already have detail data (splits, HR zones, weather).
            These will be skipped during per-activity detail fetching.
        """
        today = target_date or date.today().isoformat()
        e_date = end_date or today
        s_date = start_date or (date.fromisoformat(today) - timedelta(days=30)).isoformat()

        all_results = {}

        def _process_batch(batch_result, cal_date=None):
            """Send each endpoint result to on_batch or accumulate in memory."""
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

        # 1. Profile endpoints (no date) + profile GraphQL
        print("  Fetching profile data...")
        profile = self._fetch_batch(
            profile_endpoints(),
            profile_graphql(self._display_name),
        )
        _process_batch(profile)

        # 2. Full-range queries (supports 365+ days)
        print("  Fetching full-range data (activities, HRV, training, VO2max, weight)...")
        full_rest = full_range_rest(self._display_name, s_date, e_date)
        full_gql = full_range_graphql(self._display_name, s_date, e_date)
        full = self._fetch_batch(full_rest, full_gql)
        _process_batch(full)

        # 2b. Paginate through ALL activities (the search endpoint returns max ~100 per page)
        page_start = 100  # first page (0-99) already fetched above
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
                break  # last page

        # 3. Monthly-chunked queries (max 28-day ranges) — REST + GraphQL
        print("  Fetching monthly-chunked data (sleep stats, HRV, calories, etc.)...")
        chunks = self._date_chunks(s_date, e_date, max_days=28)
        for i, (cs, ce) in enumerate(chunks):
            print(f"    Chunk {i + 1}/{len(chunks)}: {cs} to {ce}")
            m_rest = monthly_rest(self._display_name, cs, ce)
            m_gql = monthly_graphql(self._display_name, cs, ce)
            chunk_result = self._fetch_batch(m_rest, m_gql)
            _process_batch(chunk_result)

        # 4. Daily-chunked REST + GraphQL (stress, HR, sleep, SpO2, body battery)
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

            # Daily results: split "endpoint_YYYY-MM-DD" into endpoint + date
            for full_name, result in batch_result.items():
                if result.get("status") != 200 or not result.get("data"):
                    continue
                # Extract base name and date from "stress_2026-03-29" or "gql_heart_rate_detail_2026-03-29"
                # Date is always the last 10 chars after the last underscore
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

        # 5. Per-activity detail data (splits, HR zones, weather, exercise sets)
        # Only fetch details for activities we don't already have.
        # First, collect activity IDs from what was already fetched in this run.
        activity_ids = []

        for name_key, result in all_results.items():
            if name_key in ("activities", "activities_range"):
                data = result.get("data", [])
                if isinstance(data, list):
                    for a in data:
                        aid = a.get("activityId")
                        if aid:
                            activity_ids.append(aid)

        # In on_batch mode, we need to check the API — but only if
        # known_activity_ids suggests there might be new ones.
        if not activity_ids and on_batch:
            # Quick check: compare activity count in DB vs API
            try:
                act_result = self._fetch_batch(
                    {"_activity_ids": "/gc-api/activitylist-service/activities/search/activities?limit=1000&start=0"},
                    {},
                )
                act_data = act_result.get("_activity_ids", {})
                if act_data.get("status") == 200 and isinstance(act_data.get("data"), list):
                    all_api_ids = [a.get("activityId") for a in act_data["data"] if a.get("activityId")]
                    # Only keep IDs that don't have details yet
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

    def close(self):
        self._engine.close(self._context, self._playwright, self._browser_ref)
        self._page = None
        self._context = None
        self._playwright = None
        self._browser_ref = None


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
    # For scalars, keep the newer value
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

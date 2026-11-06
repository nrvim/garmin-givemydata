#!/usr/bin/env python3
"""
keep_alive.py — Houdt de GitHub Codespace wakker door elke 4 minuten
de /health endpoint te pingen. Start dit in een aparte terminal in de Codespace.

Gebruik:
    python3 keep_alive.py
    python3 keep_alive.py --url https://jouw-codespace-url/health
    python3 keep_alive.py --interval 240  # ping elke 240 seconden (default)
"""

import argparse
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

DEFAULT_INTERVAL = 240  # 4 minuten — Codespace timeout is 30 min inactiviteit


def ping(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Codespace keep-alive pinger")
    parser.add_argument(
        "--url",
        default=os.environ.get("KEEPALIVE_URL", "http://localhost:8000/health"),
        help="URL om te pingen (default: http://localhost:8000/health)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Ping interval in seconden (default: {DEFAULT_INTERVAL})",
    )
    args = parser.parse_args()

    print("Keep-alive gestart")
    print(f"  URL:      {args.url}")
    print(f"  Interval: {args.interval}s ({args.interval // 60}m {args.interval % 60}s)")
    print("  Stop:     Ctrl+C\n")

    ok_count = 0
    fail_count = 0

    while True:
        now = datetime.now().strftime("%H:%M:%S")
        success, msg = ping(args.url)

        if success:
            ok_count += 1
            print(f"[{now}] ✓ {msg}  (ok={ok_count}, fail={fail_count})")
        else:
            fail_count += 1
            print(f"[{now}] ✗ {msg}  (ok={ok_count}, fail={fail_count})")
            # Na 3 opeenvolgende fouten: waarschuwing
            if fail_count > 0 and fail_count % 3 == 0:
                print("          ⚠ Server reageert niet — is de MCP server nog actief?")

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\nGestopt. Totaal: {ok_count} ok, {fail_count} mislukt.")
            break


if __name__ == "__main__":
    main()

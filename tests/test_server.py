"""Regression tests for garmin_mcp.server."""

import time
import unittest
from unittest.mock import patch

from garmin_mcp import server


class TestBackgroundSync(unittest.TestCase):
    """Issue #35 bug 3: sync used to block the MCP tool call for ~2 minutes,
    but most MCP clients (Claude Desktop) time out at ~60s, so the result
    was never delivered. _start_background_sync() runs the sync in a
    daemon thread and returns immediately so the tool call completes within
    the client's timeout.
    """

    def setUp(self):
        # Wait for any leftover bg sync thread from a previous test to
        # finish (so it releases the lock on its own — force-releasing
        # while it's still running races with the bg thread's own
        # release in finally and produces a double-release RuntimeError).
        self._wait_for_idle()
        server._sync_state.update(
            running=False,
            started_at=None,
            finished_at=None,
            last_result=None,
        )
        # Belt-and-braces: if a *crashed* prior test somehow left the
        # lock held without a thread to release it, free it here.
        if server._sync_lock.locked():
            try:
                server._sync_lock.release()
            except RuntimeError:
                pass  # bg thread released it between locked() and release()

    def tearDown(self):
        self._wait_for_idle()

    @staticmethod
    def _wait_for_idle(timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not server._sync_state["running"] and not server._sync_lock.locked():
                return
            time.sleep(0.02)

    def test_start_background_sync_returns_quickly(self):
        # Mock incremental_sync to take 2 seconds. The call to
        # _start_background_sync() must still return in < 500ms because
        # the work happens in a daemon thread.
        def slow_sync():
            time.sleep(2)
            return {"status": "ok", "total_upserted": 0}

        with patch("garmin_mcp.sync.incremental_sync", slow_sync):
            t0 = time.monotonic()
            result = server._start_background_sync()
            elapsed = time.monotonic() - t0

        self.assertLess(elapsed, 0.5, f"_start_background_sync took {elapsed:.2f}s")
        self.assertEqual(result["status"], "started")
        self.assertIsNotNone(result["started_at"])
        self.assertTrue(server._sync_state["running"])

        # Wait for it to complete and confirm state transitions correctly
        for _ in range(50):
            if not server._sync_state["running"]:
                break
            time.sleep(0.1)

        self.assertFalse(server._sync_state["running"])
        self.assertIsNotNone(server._sync_state["finished_at"])
        self.assertEqual(server._sync_state["last_result"]["status"], "ok")

    def test_start_background_sync_rejects_concurrent_call(self):
        # First call holds the lock; second call should report in_progress.
        def slow_sync():
            time.sleep(2)
            return {"status": "ok"}

        with patch("garmin_mcp.sync.incremental_sync", slow_sync):
            first = server._start_background_sync()
            second = server._start_background_sync()

        self.assertEqual(first["status"], "started")
        self.assertEqual(second["status"], "in_progress")
        self.assertEqual(second["started_at"], first["started_at"])

    def test_background_sync_records_failure(self):
        def boom():
            raise RuntimeError("simulated browser crash")

        with patch("garmin_mcp.sync.incremental_sync", boom):
            server._start_background_sync()
            self._wait_for_idle()

        self.assertFalse(server._sync_state["running"])
        self.assertEqual(server._sync_state["last_result"]["status"], "error")

    def test_background_sync_enforces_timeout(self):
        # Without a hard timeout, a hung incremental_sync would hold the
        # lock forever. Patch SYNC_TIMEOUT_SEC very low and confirm the
        # bg thread bails out, records an error, and releases the lock.
        def hangs():
            time.sleep(5)
            return {"status": "ok"}

        with (
            patch("garmin_mcp.server.SYNC_TIMEOUT_SEC", 0.2),
            patch("garmin_mcp.sync.incremental_sync", hangs),
        ):
            server._start_background_sync()
            self._wait_for_idle(timeout=3.0)

        self.assertFalse(server._sync_state["running"])
        self.assertFalse(server._sync_lock.locked())
        self.assertEqual(server._sync_state["last_result"]["status"], "error")
        self.assertIn("timeout", server._sync_state["last_result"]["error"].lower())

    def test_thread_start_failure_releases_lock(self):
        # If Thread.start() raises, the lock must not leak. Patch
        # threading.Thread to a stub whose start() raises RuntimeError.
        class FailingThread:
            def __init__(self, *_args, **_kwargs):
                pass

            def start(self):
                raise RuntimeError("simulated: can't start new thread")

        with patch("garmin_mcp.server.threading.Thread", FailingThread):
            result = server._start_background_sync()

        self.assertEqual(result["status"], "error")
        self.assertFalse(server._sync_state["running"])
        self.assertFalse(server._sync_lock.locked())


class TestGarminSyncWait(unittest.TestCase):
    """garmin_sync used to return "started" immediately with pre-sync data,
    so clients read it as "nothing new synced". It now waits (bounded) for
    the bg sync and says clearly whether the data is updated yet.
    """

    def setUp(self):
        TestBackgroundSync._wait_for_idle()
        server._sync_state.update(running=False, started_at=None, finished_at=None, last_result=None)
        server._sync_done.set()
        freshness = patch("garmin_mcp.server._get_data_freshness", return_value={"is_stale": False})
        freshness.start()
        self.addCleanup(freshness.stop)

    def tearDown(self):
        TestBackgroundSync._wait_for_idle()

    def _run(self, sync_secs, wait_secs, refresh=True):
        import json

        def slow_sync():
            time.sleep(sync_secs)
            return {"status": "ok", "total_upserted": 7}

        with (
            patch("garmin_mcp.sync.incremental_sync", slow_sync),
            patch.object(server, "SYNC_WAIT_SEC", wait_secs),
        ):
            return json.loads(server.garmin_sync(refresh=refresh))

    def test_waits_for_a_fast_sync_and_reports_the_result(self):
        result = self._run(sync_secs=0.2, wait_secs=5)
        self.assertFalse(result["sync_state"]["running"])
        self.assertEqual(result["sync_state"]["last_result"]["total_upserted"], 7)
        self.assertIn("up to date", result["message"])

    def test_slow_sync_returns_running_with_explicit_message(self):
        start = time.monotonic()
        result = self._run(sync_secs=1.0, wait_secs=0.2)
        self.assertLess(time.monotonic() - start, 0.9)
        self.assertTrue(result["sync_state"]["running"])
        self.assertIn("BEFORE this sync", result["message"])

    def test_refresh_false_waits_for_running_sync(self):
        self._run(sync_secs=0.5, wait_secs=0.05)
        result = self._run(sync_secs=0, wait_secs=5, refresh=False)
        self.assertFalse(result["sync_state"]["running"])
        self.assertIn("up to date", result["message"])

    def test_refresh_false_when_idle_returns_immediately(self):
        start = time.monotonic()
        result = self._run(sync_secs=0, wait_secs=5, refresh=False)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertNotIn("message", result)


if __name__ == "__main__":
    unittest.main()

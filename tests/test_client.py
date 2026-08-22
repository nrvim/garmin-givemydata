"""Regression tests for garmin_client.client."""

import inspect
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from selenium.common.exceptions import TimeoutException

from garmin_client.client import GarminClient, _ProcessLifecycle


class TestProcessLifecycleThreadSafety(unittest.TestCase):
    """Issue #35 bug 2: _ProcessLifecycle.install() used to call
    signal.signal() unconditionally. The MCP server runs sync in a
    ThreadPoolExecutor worker, so install() runs from a non-main thread
    and signal.signal() raises ValueError("signal only works in main
    thread of the main interpreter").
    """

    def test_install_from_worker_thread_does_not_raise(self):
        errors: list[BaseException] = []

        def worker():
            try:
                lifecycle = _ProcessLifecycle(cleanup_fn=lambda: None)
                lifecycle.install()
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertEqual(errors, [], f"install() raised in worker thread: {errors}")


class TestFetchBatchResilience(unittest.TestCase):
    """A single stalled request used to kill an entire multi-year sync:
    _fetch_batch's execute_async_script would hit Selenium's 120s script
    timeout and the TimeoutException propagated uncaught out of fetch_all.
    """

    def _client(self) -> GarminClient:
        tmp = tempfile.mkdtemp(prefix="garmin-test-profile-")
        return GarminClient("test@example.com", "pw", profile_dir=Path(tmp))

    def test_retries_after_transient_timeout(self):
        client = self._client()
        attempts = []
        payload = {"steps_2025-01-01": {"status": 200, "data": {"steps": 1}}}

        def fake_once(rest, gql):
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutException("script timeout")
            return payload

        client._fetch_batch_once = fake_once
        with patch("garmin_client.client.time.sleep"):
            result = client._fetch_batch({"steps_2025-01-01": "/url"}, {})

        self.assertEqual(result, payload)
        self.assertEqual(len(attempts), 2)

    def test_persistent_failure_returns_empty_instead_of_raising(self):
        client = self._client()
        attempts = []

        def fake_once(rest, gql):
            attempts.append(1)
            raise TimeoutException("script timeout")

        client._fetch_batch_once = fake_once
        with patch("garmin_client.client.time.sleep"):
            result = client._fetch_batch({"steps_2025-01-01": "/url"}, {})

        self.assertEqual(result, {})
        self.assertEqual(len(attempts), 3)

    def test_in_page_fetches_have_abort_timeout(self):
        """Guard: every fetch() inside the batch script must carry an
        AbortSignal timeout, otherwise one stalled request hangs the whole
        script until Selenium's script timeout kills the sync."""
        source = inspect.getsource(GarminClient._fetch_batch_once)
        self.assertIn("AbortSignal.timeout", source)


if __name__ == "__main__":
    unittest.main()

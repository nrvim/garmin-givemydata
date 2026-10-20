"""Regression tests for garmin_client.client."""

import inspect
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from selenium.common.exceptions import TimeoutException

from garmin_client.client import GarminClient, _multisport_child_ids, _ProcessLifecycle
from garmin_client.endpoints import profile_endpoints, workouts_search_url


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


class TestMultisportChildIds(unittest.TestCase):
    """metadataDTO.childIds extraction for multisport parents (#review)."""

    def test_extracts_child_ids(self):
        self.assertEqual(_multisport_child_ids({"metadataDTO": {"childIds": [1, 2, 3]}}), [1, 2, 3])

    def test_non_multisport_returns_empty(self):
        self.assertEqual(_multisport_child_ids({"metadataDTO": {}}), [])
        self.assertEqual(_multisport_child_ids({"activityId": 1}), [])
        self.assertEqual(_multisport_child_ids(None), [])
        self.assertEqual(_multisport_child_ids("x"), [])

    def test_filters_falsy_ids(self):
        self.assertEqual(_multisport_child_ids({"metadataDTO": {"childIds": [1, 0, None, 2]}}), [1, 2])


class TestWorkoutsSearchUrl(unittest.TestCase):
    """Workout-library pagination URL (#review)."""

    def test_url_builder(self):
        self.assertEqual(workouts_search_url(0, 100), "/gc-api/workout-service/workouts?start=0&limit=100")
        self.assertEqual(workouts_search_url(200, 100), "/gc-api/workout-service/workouts?start=200&limit=100")

    def test_profile_endpoint_uses_builder(self):
        self.assertEqual(profile_endpoints()["workouts"], workouts_search_url(0, 100))


class TestFetchAllScraperFixes(unittest.TestCase):
    """fetch_all wiring for the two scraper fixes: multisport-child fetch and
    workout-library pagination (#review)."""

    def _client(self) -> GarminClient:
        tmp = tempfile.mkdtemp(prefix="garmin-test-profile-")
        client = GarminClient("test@example.com", "pw", profile_dir=Path(tmp))
        client._display_name = "u"
        client.api_fetch = lambda url: []  # never hit the browser
        return client

    def test_multisport_children_are_fetched_and_saved(self):
        client = self._client()
        detail_fetched = []

        def fake_batch(rest, gql):
            if "activities" in rest:
                return {"activities": {"status": 200, "data": [{"activityId": 100}]}}
            if "activity_details" in rest:
                aid = int(rest["activity_details"].rstrip("/").split("/")[-1])
                detail_fetched.append(aid)
                data = {"activityId": aid}
                if aid == 100:
                    data["metadataDTO"] = {"childIds": [101, 102]}
                return {"activity_details": {"status": 200, "data": data}}
            return {}

        client._fetch_batch = fake_batch
        saved = []
        client.fetch_all(
            target_date="2026-06-01",
            start_date="2026-06-01",
            end_date="2026-06-01",
            on_batch=lambda name, data, cal_date=None: saved.append((name, cal_date)),
        )
        # parent and both children had their detail endpoints fetched
        self.assertEqual(set(detail_fetched), {100, 101, 102})
        child_saves = {cal for name, cal in saved if name == "activity_details" and cal in ("101", "102")}
        self.assertEqual(child_saves, {"101", "102"})

    def test_children_not_refetched_cycle_guard(self):
        """A child that points back at a seen id must not loop forever."""
        client = self._client()
        detail_fetched = []

        def fake_batch(rest, gql):
            if "activities" in rest:
                return {"activities": {"status": 200, "data": [{"activityId": 100}]}}
            if "activity_details" in rest:
                aid = int(rest["activity_details"].rstrip("/").split("/")[-1])
                detail_fetched.append(aid)
                # 100 -> 101, and 101 -> 100 (cycle)
                children = {100: [101], 101: [100]}.get(aid, [])
                return {
                    "activity_details": {
                        "status": 200,
                        "data": {"activityId": aid, "metadataDTO": {"childIds": children}},
                    }
                }
            return {}

        client._fetch_batch = fake_batch
        client.fetch_all(
            target_date="2026-06-01",
            start_date="2026-06-01",
            end_date="2026-06-01",
            on_batch=lambda name, data, cal_date=None: None,
        )
        self.assertEqual(sorted(detail_fetched), [100, 101])  # each fetched once

    def test_workout_library_is_paginated(self):
        client = self._client()
        probed = []
        full_page = [{"workoutId": i} for i in range(100)]

        def fake_batch(rest, gql):
            if "workouts" in rest:  # the profile batch's first page
                return {"workouts": {"status": 200, "data": full_page}}
            for key in list(rest):
                if key.startswith("workouts_page_"):
                    offset = int(key.rsplit("_", 1)[1])
                    probed.append(offset)
                    data = [{"workoutId": 1000 + offset}] if offset == 100 else []
                    return {key: {"status": 200, "data": data}}
            return {}

        client._fetch_batch = fake_batch
        saved = []
        client.fetch_all(
            target_date="2026-06-01",
            start_date="2026-06-01",
            end_date="2026-06-01",
            on_batch=lambda name, data, cal_date=None: saved.append((name, data)),
        )
        # first page full -> probed offset 100, which returned a short page -> stop
        self.assertEqual(probed, [100])
        paginated = [d for name, d in saved if name == "workouts" and d == [{"workoutId": 1100}]]
        self.assertEqual(len(paginated), 1)

    def test_workouts_pagination_skipped_when_first_page_short(self):
        client = self._client()
        probed = []

        def fake_batch(rest, gql):
            if "workouts" in rest:
                return {"workouts": {"status": 200, "data": [{"workoutId": 1}, {"workoutId": 2}]}}
            for key in list(rest):
                if key.startswith("workouts_page_"):
                    probed.append(key)
                    return {key: {"status": 200, "data": []}}
            return {}

        client._fetch_batch = fake_batch
        client.fetch_all(
            target_date="2026-06-01",
            start_date="2026-06-01",
            end_date="2026-06-01",
            on_batch=lambda name, data, cal_date=None: None,
        )
        self.assertEqual(probed, [])  # a short first page means no extra request


if __name__ == "__main__":
    unittest.main()

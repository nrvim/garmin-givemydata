"""Tests for the pure CDP driver used on Apple Silicon."""

import unittest
from unittest.mock import MagicMock

from selenium.common.exceptions import WebDriverException

from garmin_client.client import _CdpDriver


def _driver(run_until_complete) -> _CdpDriver:
    d = object.__new__(_CdpDriver)
    d._sb = MagicMock()
    d._sb.loop.run_until_complete.side_effect = run_until_complete
    return d


class TestCdpDriver(unittest.TestCase):
    def test_async_script_gets_args_and_callback(self):
        d = _driver(lambda coro: "ok")
        d._sb.page.evaluate = MagicMock()
        d.execute_async_script("arguments[arguments.length - 1](arguments[0]);", "/gc-api/x", None)
        expression = d._sb.page.evaluate.call_args.args[0]
        self.assertIn('["/gc-api/x", null].concat([done])', expression)
        self.assertTrue(d._sb.page.evaluate.call_args.kwargs["await_promise"])

    def test_cdp_errors_become_webdriver_exceptions(self):
        """_fetch_batch only retries WebDriverException."""

        def boom(coro):
            raise RuntimeError("protocol error")

        with self.assertRaises(WebDriverException):
            _driver(boom).execute_script("return 1")


if __name__ == "__main__":
    unittest.main()

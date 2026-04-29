"""Verify base.http_get retries with a browser UA on 403/429 only."""

import sys
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetchers import base  # noqa: E402


def _make_http_error(code: int, msg: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://x", code=code, msg=msg, hdrs=None, fp=BytesIO(b""),
    )


class HttpGetRetryTest(unittest.TestCase):
    def test_403_triggers_browser_ua_retry(self) -> None:
        first_403 = _make_http_error(403, "blocked")
        # Second call (with browser UA) succeeds
        second_ok = (b"<html>real body</html>", {"content-type": "text/html"})

        def fake_do_get(url, headers, timeout):
            if "QDailyTracker" in headers["User-Agent"]:
                raise first_403
            assert "Mozilla/5.0" in headers["User-Agent"], headers
            return second_ok

        with mock.patch.object(base, "_do_get", side_effect=fake_do_get):
            body, headers = base.http_get("https://example.com/", timeout=1.0)
        self.assertEqual(body, b"<html>real body</html>")

    def test_429_triggers_browser_ua_retry(self) -> None:
        first_429 = _make_http_error(429, "too many")
        second_ok = (b"x", {})

        def fake_do_get(url, headers, timeout):
            if "Mozilla" in headers["User-Agent"]:
                return second_ok
            raise first_429

        with mock.patch.object(base, "_do_get", side_effect=fake_do_get):
            body, _ = base.http_get("https://example.com/", timeout=1.0)
        self.assertEqual(body, b"x")

    def test_500_does_not_retry(self) -> None:
        five_hundred = _make_http_error(500, "server error")
        call_count = {"n": 0}

        def fake_do_get(url, headers, timeout):
            call_count["n"] += 1
            raise five_hundred

        with mock.patch.object(base, "_do_get", side_effect=fake_do_get):
            with self.assertRaises(base.HttpError) as ctx:
                base.http_get("https://example.com/", timeout=1.0)
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(call_count["n"], 1)  # no retry

    def test_retry_disabled_via_kwarg(self) -> None:
        first_403 = _make_http_error(403, "")
        call_count = {"n": 0}

        def fake_do_get(url, headers, timeout):
            call_count["n"] += 1
            raise first_403

        with mock.patch.object(base, "_do_get", side_effect=fake_do_get):
            with self.assertRaises(base.HttpError):
                base.http_get("https://example.com/", retry_on_block=False, timeout=1.0)
        self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()

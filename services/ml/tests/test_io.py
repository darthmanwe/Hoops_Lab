"""Bronze cache, rate limiting and retry policy."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest

from hoopslab.ingest.retry import RETRYABLE_STATUS, is_retryable
from hoopslab.io.bronze import BronzeCache, cache_key, frame_digest
from hoopslab.io.rate_limit import RateLimiter


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})


class TestCacheKey:
    def test_is_stable_across_keyword_order(self) -> None:
        assert cache_key("s", "e", {"a": 1, "b": 2}) == cache_key("s", "e", {"b": 2, "a": 1})

    def test_differs_by_parameter_value(self) -> None:
        assert cache_key("s", "e", {"season": "2023-24"}) != cache_key(
            "s", "e", {"season": "2024-25"}
        )

    def test_differs_by_endpoint(self) -> None:
        assert cache_key("s", "one", {}) != cache_key("s", "two", {})

    def test_is_filename_safe(self) -> None:
        key = cache_key("s", "e", {"season": "2023-24", "path": "a/b\\c"})
        assert key.isalnum()


class TestFrameDigest:
    def test_is_stable_for_identical_content(self) -> None:
        assert frame_digest(sample_frame()) == frame_digest(sample_frame())

    def test_changes_when_a_value_changes(self) -> None:
        other = sample_frame()
        other.loc[0, "a"] = 99
        assert frame_digest(sample_frame()) != frame_digest(other)


class TestBronzeCache:
    def test_calls_the_fetcher_once_then_serves_from_disk(self, tmp_path: Path) -> None:
        cache = BronzeCache(tmp_path)
        calls = 0

        def fetcher() -> pd.DataFrame:
            nonlocal calls
            calls += 1
            return sample_frame()

        first = cache.fetch(source="s", endpoint="e", params={"x": 1}, fetcher=fetcher)
        second = cache.fetch(source="s", endpoint="e", params={"x": 1}, fetcher=fetcher)

        assert calls == 1
        assert first.from_cache is False
        assert second.from_cache is True
        pd.testing.assert_frame_equal(first.frame, second.frame)

    def test_refresh_forces_a_refetch(self, tmp_path: Path) -> None:
        cache = BronzeCache(tmp_path)
        calls = 0

        def fetcher() -> pd.DataFrame:
            nonlocal calls
            calls += 1
            return sample_frame()

        cache.fetch(source="s", endpoint="e", params={}, fetcher=fetcher)
        cache.fetch(source="s", endpoint="e", params={}, fetcher=fetcher, refresh=True)

        assert calls == 2

    def test_records_one_manifest_entry_per_real_fetch(self, tmp_path: Path) -> None:
        cache = BronzeCache(tmp_path)
        cache.fetch(source="s", endpoint="e", params={}, fetcher=sample_frame)
        cache.fetch(source="s", endpoint="e", params={}, fetcher=sample_frame)

        manifest = cache.manifest()
        assert len(manifest) == 1
        assert manifest[0]["n_rows"] == 3
        assert manifest[0]["source"] == "s"

    def test_load_never_fetches(self, tmp_path: Path) -> None:
        """The transform layer must work without the optional ingest extra."""
        cache = BronzeCache(tmp_path)
        assert cache.load("s", "e", {"x": 1}) is None

        cache.fetch(source="s", endpoint="e", params={"x": 1}, fetcher=sample_frame)
        assert cache.load("s", "e", {"x": 1}) is not None

    def test_a_failing_fetch_leaves_nothing_behind(self, tmp_path: Path) -> None:
        cache = BronzeCache(tmp_path)

        def broken() -> pd.DataFrame:
            raise RuntimeError("source unavailable")

        with pytest.raises(RuntimeError):
            cache.fetch(source="s", endpoint="e", params={}, fetcher=broken)

        assert cache.load("s", "e", {}) is None
        assert cache.manifest() == []


class TestRateLimiter:
    def test_spaces_consecutive_acquisitions(self) -> None:
        limiter = RateLimiter(requests_per_second=20.0)  # 50 ms apart

        started = time.monotonic()
        for _ in range(3):
            limiter.acquire()
        elapsed = time.monotonic() - started

        # Three acquisitions means two gaps; the first is free.
        assert elapsed >= 0.09

    def test_does_not_delay_the_first_call(self) -> None:
        """The previous implementation slept *before* each request.

        That made the very first call pay the full interval for nothing, and
        spaced calls by sleep time rather than by elapsed wall-clock time.
        """
        assert RateLimiter(requests_per_second=1.0).acquire() == 0.0

    def test_does_not_bank_credit_during_a_quiet_period(self) -> None:
        limiter = RateLimiter(requests_per_second=50.0)
        limiter.acquire()
        time.sleep(0.1)  # much longer than the interval

        # The next call is free (the debt has elapsed), but the one after is not.
        assert limiter.acquire() == 0.0
        assert limiter.acquire() > 0.0

    def test_rejects_a_nonpositive_rate(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            RateLimiter(requests_per_second=0.0)


class TestRetryPolicy:
    @pytest.mark.parametrize("status", sorted(RETRYABLE_STATUS))
    def test_retries_transient_statuses(self, status: int) -> None:
        assert is_retryable(_http_error(status))

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
    def test_does_not_retry_client_errors(self, status: int) -> None:
        """The bug this replaces: a bare @retry around raise_for_status().

        A 404 for a season that does not exist was retried four times with
        exponential backoff before failing anyway, turning a fast clear answer
        into a slow confusing one.
        """
        assert not is_retryable(_http_error(status))

    def test_retries_transport_failures(self) -> None:
        class ConnectTimeout(Exception):
            pass

        assert is_retryable(ConnectTimeout("no route to host"))

    def test_does_not_retry_a_programming_error(self) -> None:
        assert not is_retryable(TypeError("bad argument"))


def _http_error(status: int) -> Exception:
    class Response:
        status_code = status

    class HTTPError(Exception):
        response = Response()

    return HTTPError(f"HTTP {status}")

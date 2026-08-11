"""Client-side rate limiting.

`stats.nba.com` throttles aggressively and, once it decides to, the block
outlasts anything the extra speed bought. The EuroLeague live API returned
HTTP 429 during source probing after roughly 170 sequential requests.

The previous version's NBA client slept *before* each request, which meant the
first call paid the delay for nothing and consecutive calls were not actually
spaced by elapsed work time. This spaces on the real clock instead.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Blocking limiter that guarantees a minimum interval between acquisitions.

    Thread-safe so that a future parallel fetcher cannot accidentally defeat it
    by holding separate copies of the last-request timestamp.
    """

    requests_per_second: float
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _next_allowed_at: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")

    @property
    def min_interval(self) -> float:
        return 1.0 / self.requests_per_second

    def acquire(self) -> float:
        """Block until the next request may be made. Returns seconds waited."""
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_allowed_at - now)
            # Schedule from the later of "now" and the previous slot, so a gap
            # in traffic does not bank credit for a later burst.
            self._next_allowed_at = max(now, self._next_allowed_at) + self.min_interval

        if wait > 0:
            time.sleep(wait)
        return wait

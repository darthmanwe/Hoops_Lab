"""Retry policy shared by every network client.

The rule that matters: **retry transport failures and 429/5xx, never other
4xx**. The previous version's EuroLeague client wrapped ``raise_for_status()``
in a bare ``@retry``, so a 404 for a season that does not exist was retried
four times with exponential backoff before failing anyway — turning a fast,
clear "no such season" into a slow, confusing one.
"""

from __future__ import annotations

import logging
from typing import Any

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_retryable(exc: BaseException) -> bool:
    """True for transport errors and the status codes worth trying again."""
    status = _status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS

    # No status attached: a timeout, DNS failure or reset connection.
    name = type(exc).__name__
    return any(
        marker in name
        for marker in ("Timeout", "ConnectionError", "ConnectError", "ReadError", "RemoteProtocol")
    )


def _status_of(exc: BaseException) -> int | None:
    """Best-effort status extraction across httpx and requests exceptions."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    status = getattr(response, "status_code", None)
    return int(status) if isinstance(status, int) else None


def with_retries(attempts: int = 4) -> Any:
    """Decorator applying the shared policy."""
    return retry(
        retry=retry_if_exception(is_retryable),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=2, max=45),
        reraise=True,
        before_sleep=lambda state: log.warning(
            "retrying %s (attempt %d) after %s",
            state.fn.__name__ if state.fn else "call",
            state.attempt_number,
            state.outcome.exception() if state.outcome else "unknown error",
        ),
    )

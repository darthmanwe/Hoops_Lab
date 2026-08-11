"""Shared fixtures.

The test session must never be able to authenticate against a paid API. Two
separate things have to be neutralised for that to hold, and missing either one
is enough to start spending money on a bare ``pytest``:

1. the process environment, and
2. the ``.env`` file, which ``pydantic-settings`` reads *in addition to* the
   environment — so deleting ``ANTHROPIC_API_KEY`` from ``os.environ`` alone
   still leaves a developer's on-disk key readable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hoopslab.config import Settings

CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "HOOPSLAB_ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee no test can reach a billed or rate-limited external service."""
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)

    # Without this, a developer with a real key in services/ml/.env would have
    # it silently loaded back in despite the delenv above.
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture
def repo_root() -> Path:
    """The workspace root, located by marker file rather than by parent hops."""
    from hoopslab.paths import find_repo_root

    return find_repo_root()

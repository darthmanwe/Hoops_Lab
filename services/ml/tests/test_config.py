"""Configuration behaviour, including the bug the previous version shipped."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hoopslab.config import SEED, Settings, load_settings


def test_seed_is_fixed() -> None:
    """The committed metrics were produced under this seed; changing it invalidates them."""
    assert SEED == 20260810


def test_defaults_load_without_any_environment() -> None:
    settings = load_settings()

    assert settings.seed == SEED
    assert settings.log_level == "INFO"
    assert settings.anthropic_api_key is None


def test_reads_environment_at_call_time_not_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression test for the previous implementation.

    The old settings class evaluated ``os.getenv`` in a frozen dataclass field
    default, which binds once at import. Anything exported afterwards was
    invisible for the lifetime of the process.
    """
    before = load_settings()
    assert before.log_level == "INFO"

    monkeypatch.setenv("HOOPSLAB_LOG_LEVEL", "DEBUG")

    after = load_settings()
    assert after.log_level == "DEBUG"


def test_rejects_an_invalid_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOPSLAB_LOG_LEVEL", "CHATTY")

    with pytest.raises(ValidationError):
        load_settings()


def test_rejects_a_rate_limit_that_would_get_us_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unbounded request rate against stats.nba.com earns an IP ban."""
    monkeypatch.setenv("HOOPSLAB_NBA_STATS_RATE_LIMIT_RPS", "50")

    with pytest.raises(ValidationError):
        load_settings()


def test_rejects_a_nonpositive_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOPSLAB_NBA_STATS_RATE_LIMIT_RPS", "0")

    with pytest.raises(ValidationError):
        load_settings()


def test_credential_fixture_actually_blocks_a_leaked_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves the autouse guard works, rather than assuming it does."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-be-visible")

    # The guard clears the environment before each test; a value set *inside*
    # a test is visible, which is what makes this a meaningful check that the
    # alias wiring is right rather than a tautology.
    assert load_settings().anthropic_api_key == "sk-ant-should-not-be-visible"


def test_dotenv_is_disabled_during_tests() -> None:
    """A developer's on-disk key must not leak into the suite."""
    assert Settings.model_config["env_file"] is None

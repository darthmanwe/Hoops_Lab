"""Runtime configuration.

The previous version of this project defined settings as::

    @dataclass(frozen=True)
    class Settings:
        ball_dont_lie_api_key: str | None = os.getenv("BALLDONTLIE_API_KEY")

which reads the environment once, at class-definition time, and then freezes
it. Any variable exported after the module is first imported is invisible, and
because the class was frozen there was no way to correct it afterwards. It was
also never instantiated anywhere.

``pydantic-settings`` reads the environment at instantiation, validates types,
and fails loudly on a malformed value instead of silently yielding ``None``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Every stochastic operation takes this seed explicitly. The value is
#: arbitrary; what matters is that it never changes, because the committed
#: metrics were produced under it and CI re-derives them on every push.
SEED = 20260810

#: Requests per second against stats.nba.com. Deliberately slower than the rate
#: that triggers throttling: a full season-grain pull is ~2,000 requests, so
#: even at this pace it finishes in under an hour, and being impatient here
#: risks an IP block that costs far more than the time saved.
NBA_STATS_RATE_LIMIT_RPS = 0.67


class Settings(BaseSettings):
    """Process configuration, read from the environment and ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="HOOPSLAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    seed: int = SEED
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    #: Only ever needed by the scouting-report layer, and only when explicitly
    #: refreshing the response cache. The committed cache means the demo and
    #: the whole evaluation suite run at zero cost without it.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    #: Ingestion politeness. Overridable for local experiments, but the default
    #: is the one that has to hold in practice.
    nba_stats_rate_limit_rps: float = Field(default=NBA_STATS_RATE_LIMIT_RPS, gt=0, le=5)


def load_settings() -> Settings:
    """Build settings from the current environment.

    Called at use time rather than at import time so that tests, and any caller
    that sets variables programmatically, actually take effect.
    """
    return Settings()

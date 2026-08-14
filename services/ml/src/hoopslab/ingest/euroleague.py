"""EuroLeague season statistics via `euroleague-api`.

Two things about this source shape the code:

**The library swallows errors.** Its per-game helpers log ``"Skip and
continue"`` and carry on when a request fails, so a rate-limited run returns a
*silently incomplete* table with no exception raised. Source probing hit HTTP
429 after roughly 170 sequential game requests. Only the season-aggregate
endpoint is used here — a single request per season, where a failure is a
failure — and the per-game shot endpoints are left for later, behind a fetcher
that verifies completeness.

**It is GPLv3.** It lives in the optional ``ingest`` extra and is imported
lazily so it is never a runtime dependency of the distributed MIT package. The
repository ships derived data, which is not a derivative work of this code.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from hoopslab.ingest.retry import with_retries
from hoopslab.io.bronze import BronzeCache
from hoopslab.io.rate_limit import RateLimiter
from hoopslab.seasons import Season

log = logging.getLogger(__name__)

SOURCE = "euroleague"


class EuroLeagueClient:
    def __init__(self, cache: BronzeCache, limiter: RateLimiter) -> None:
        self.cache = cache
        self.limiter = limiter

    def player_season_stats(self, season: Season, *, refresh: bool = False) -> pd.DataFrame:
        """Accumulated traditional statistics for every player in a season.

        One request. Returns roughly 300 players per season with counting
        stats, minutes and age, plus the stable ``player.code`` used as the
        EuroLeague identity key.
        """
        params = {"season": season.euroleague_season, "statistic_mode": "Accumulated"}

        def call() -> pd.DataFrame:
            from euroleague_api.player_stats import PlayerStats

            self.limiter.acquire()
            frame = PlayerStats().get_player_stats_single_season(
                endpoint="traditional",
                season=season.euroleague_season,
                phase_type_code=None,
                statistic_mode="Accumulated",
            )
            if frame is None or frame.empty:
                raise RuntimeError(
                    f"EuroLeague returned no player statistics for {season.season_id}"
                )
            return frame

        return self._fetch("player_season_stats", params, call, refresh=refresh)

    def team_season_stats(self, season: Season, *, refresh: bool = False) -> pd.DataFrame:
        params = {"season": season.euroleague_season, "statistic_mode": "Accumulated"}

        def call() -> pd.DataFrame:
            from euroleague_api.team_stats import TeamStats

            self.limiter.acquire()
            frame = TeamStats().get_team_stats_single_season(
                endpoint="traditional",
                season=season.euroleague_season,
                phase_type_code=None,
                statistic_mode="Accumulated",
            )
            if frame is None or frame.empty:
                raise RuntimeError(f"EuroLeague returned no team statistics for {season.season_id}")
            return frame

        return self._fetch("team_season_stats", params, call, refresh=refresh)

    def _fetch(
        self, endpoint: str, params: dict[str, Any], call: Any, *, refresh: bool
    ) -> pd.DataFrame:
        guarded = with_retries()(call)
        result = self.cache.fetch(
            source=SOURCE,
            endpoint=endpoint,
            params=params,
            fetcher=guarded,
            refresh=refresh,
        )
        if not result.from_cache:
            log.info("fetched EuroLeague %s %s (%d rows)", endpoint, params, len(result.frame))
        return result.frame

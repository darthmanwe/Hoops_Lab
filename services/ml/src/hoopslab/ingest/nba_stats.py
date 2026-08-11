"""`stats.nba.com` via nba_api, for NBA and G League season-grain statistics.

Deliberately avoids per-game endpoints. Pulling `boxscoretraditionalv2` for
every game would be ~14,760 requests and several hours; the ESPN bulk mirror
serves the same box scores as one file per season. This module fetches only
what `stats.nba.com` alone provides: official advanced rate statistics, the
player registry, and biographical data.

Total cost for the full season-grain scope is roughly 2,000 requests, which at
the configured rate is a single sitting of under an hour.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import pandas as pd

from hoopslab.ingest.retry import with_retries
from hoopslab.io.bronze import BronzeCache
from hoopslab.io.rate_limit import RateLimiter
from hoopslab.seasons import Season

log = logging.getLogger(__name__)

SOURCE = "nba_stats"

#: `stats.nba.com` league ids. The G League shares the same endpoints.
LEAGUE_IDS: dict[str, str] = {"NBA": "00", "GL": "20"}

MeasureType = Literal["Base", "Advanced"]

#: Requests time out rather than hang forever. `stats.nba.com` will happily
#: hold a connection open indefinitely when it is unhappy with the caller.
TIMEOUT_SECONDS = 60


class NBAStatsClient:
    """Rate-limited, cached, retrying access to `stats.nba.com`."""

    def __init__(self, cache: BronzeCache, limiter: RateLimiter) -> None:
        self.cache = cache
        self.limiter = limiter

    # -- endpoints ---------------------------------------------------------

    def player_season_stats(
        self, season: Season, measure_type: MeasureType, *, refresh: bool = False
    ) -> pd.DataFrame:
        """Per-player totals or advanced rates for one league-season."""
        league_id = LEAGUE_IDS[season.league]
        params = {
            "season": season.nba_stats_season,
            "measure_type": measure_type,
            "league_id": league_id,
        }

        def call() -> pd.DataFrame:
            from nba_api.stats.endpoints import leaguedashplayerstats

            self.limiter.acquire()
            return _first_frame(
                leaguedashplayerstats.LeagueDashPlayerStats(
                    season=season.nba_stats_season,
                    season_type_all_star="Regular Season",
                    measure_type_detailed_defense=measure_type,
                    per_mode_detailed="Totals",
                    league_id_nullable=league_id,
                    timeout=TIMEOUT_SECONDS,
                )
            )

        return self._fetch("player_season_stats", params, call, refresh=refresh)

    def team_season_stats(
        self, season: Season, measure_type: MeasureType, *, refresh: bool = False
    ) -> pd.DataFrame:
        league_id = LEAGUE_IDS[season.league]
        params = {
            "season": season.nba_stats_season,
            "measure_type": measure_type,
            "league_id": league_id,
        }

        def call() -> pd.DataFrame:
            from nba_api.stats.endpoints import leaguedashteamstats

            self.limiter.acquire()
            return _first_frame(
                leaguedashteamstats.LeagueDashTeamStats(
                    season=season.nba_stats_season,
                    season_type_all_star="Regular Season",
                    measure_type_detailed_defense=measure_type,
                    per_mode_detailed="Totals",
                    league_id_nullable=league_id,
                    timeout=TIMEOUT_SECONDS,
                )
            )

        return self._fetch("team_season_stats", params, call, refresh=refresh)

    def player_registry(self, season: Season, *, refresh: bool = False) -> pd.DataFrame:
        """Every player known to the league as of a season.

        Carries ``PERSON_ID``, display name, and the first and last season each
        player appeared — which is what lets bio lookups be restricted to
        players who actually show up in the statistics.
        """
        league_id = LEAGUE_IDS[season.league]
        params = {"season": season.nba_stats_season, "league_id": league_id}

        def call() -> pd.DataFrame:
            from nba_api.stats.endpoints import commonallplayers

            self.limiter.acquire()
            return _first_frame(
                commonallplayers.CommonAllPlayers(
                    is_only_current_season=0,
                    league_id=league_id,
                    season=season.nba_stats_season,
                    timeout=TIMEOUT_SECONDS,
                )
            )

        return self._fetch("player_registry", params, call, refresh=refresh)

    def player_bio_stats(self, season: Season, *, refresh: bool = False) -> pd.DataFrame:
        """Age, height, weight, country and draft position for a whole season.

        One request per season rather than one per player. The obvious route to
        biographical data is ``commonplayerinfo``, which is keyed on a single
        player and would cost roughly 3,000 requests — over an hour of
        rate-limited fetching — for the same information this returns in 25.

        Age is what makes the aging spline in the translation model possible.
        Birth *year* is recovered as ``season start year - age``, which then
        gives age in any other season, including seasons in leagues whose own
        sources do not report it.

        Note: this endpoint rejects ``league_id_nullable``, so there is no
        G League equivalent. G League ages are derived from the NBA
        observation of the same person, which every G League to NBA transition
        by definition has.
        """
        params = {"season": season.nba_stats_season}

        def call() -> pd.DataFrame:
            from nba_api.stats.endpoints import leaguedashplayerbiostats

            self.limiter.acquire()
            return _first_frame(
                leaguedashplayerbiostats.LeagueDashPlayerBioStats(
                    season=season.nba_stats_season,
                    season_type_all_star="Regular Season",
                    timeout=TIMEOUT_SECONDS,
                )
            )

        return self._fetch("player_bio_stats", params, call, refresh=refresh)

    # -- plumbing ----------------------------------------------------------

    def _fetch(
        self,
        endpoint: str,
        params: dict[str, Any],
        call: Any,
        *,
        refresh: bool,
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
            log.info("fetched %s %s (%d rows)", endpoint, params, len(result.frame))
        return result.frame


def _first_frame(endpoint: Any) -> pd.DataFrame:
    frames = endpoint.get_data_frames()
    if not frames:
        raise RuntimeError(f"{type(endpoint).__name__} returned no data frames")
    return frames[0]

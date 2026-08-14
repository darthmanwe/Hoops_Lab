"""NBA box scores from the `sportsdataverse-data` bulk mirror.

One HTTP request per season returns every player box score line for that
season as parquet — roughly 35,000 rows and 750 KB for a recent year. The
equivalent pull from `stats.nba.com` would be around 1,230 requests *per
season* against an endpoint that rate-limits.

This is also the only NBA source in the project that works from CI, because it
is a static file on GitHub releases rather than `stats.nba.com`, which refuses
datacenter IP ranges.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx
import pandas as pd

from hoopslab.ingest.retry import with_retries
from hoopslab.io.bronze import BronzeCache
from hoopslab.seasons import Season

log = logging.getLogger(__name__)

SOURCE = "espn"

RELEASE_BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"

#: Datasets published per season, keyed by the release tag they live under.
#:
#: There is no `schedules` entry: that dataset is published as .rds only and
#: its .parquet URL 404s. Game-level results are derived from `team_box`
#: instead, which carries the same scores, dates and home/away flags.
DATASETS: dict[str, str] = {
    "player_box": "espn_nba_player_boxscores",
    "team_box": "espn_nba_team_boxscores",
}

DOWNLOAD_TIMEOUT = 180


class ESPNMirrorClient:
    """Bulk season files. No rate limiter: these are static release assets."""

    def __init__(self, cache: BronzeCache) -> None:
        self.cache = cache

    def season_file(self, dataset: str, season: Season, *, refresh: bool = False) -> pd.DataFrame:
        """Fetch one dataset for one season.

        ESPN keys seasons by the year they *end*, so the 2023-24 NBA season is
        ``2024``. Getting this wrong shifts every game by a year, which is the
        kind of error that produces a plausible-looking model built on
        misaligned data.
        """
        if dataset not in DATASETS:
            raise ValueError(f"Unknown dataset {dataset!r}. Known: {sorted(DATASETS)}")

        espn_year = season.espn_season
        url = f"{RELEASE_BASE}/{DATASETS[dataset]}/{dataset}_{espn_year}.parquet"
        params = {"dataset": dataset, "espn_season": espn_year}

        def call() -> pd.DataFrame:
            response = httpx.get(url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            return pd.read_parquet(io.BytesIO(response.content))

        return self._fetch(dataset, params, call, refresh=refresh)

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
            log.info("fetched ESPN %s %s (%d rows)", endpoint, params, len(result.frame))
        return result.frame

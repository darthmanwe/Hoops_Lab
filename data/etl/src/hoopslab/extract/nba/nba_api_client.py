from __future__ import annotations

import logging
import time

import pandas as pd
from nba_api.stats.endpoints import leaguegamefinder

log = logging.getLogger(__name__)


class ThrottledNBAClient:
    """Simple rate-limited wrapper around nba_api endpoints."""

    def __init__(self, sleep_seconds: float = 0.8):
        self.sleep_seconds = sleep_seconds

    def _throttle(self) -> None:
        time.sleep(self.sleep_seconds)

    def list_games(self, season: str) -> pd.DataFrame:
        """
        season format example: "2024-25"
        """
        self._throttle()
        endpoint = leaguegamefinder.LeagueGameFinder(season_nullable=season)
        frames = endpoint.get_data_frames()
        if not frames:
            return pd.DataFrame()
        return frames[0]

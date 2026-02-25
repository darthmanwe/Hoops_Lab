from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class EuroLeagueClient:
    base_url: str = "https://api-live.euroleague.net"
    timeout_seconds: int = 30

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        res = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout_seconds)
        res.raise_for_status()
        return res.json()

    def games(self, season_code: str) -> Any:
        return self._get("/v1/games", params={"seasonCode": season_code})

    def players(self, season_code: str) -> Any:
        return self._get("/v1/players", params={"seasonCode": season_code})

    def standings(self, season_code: str) -> Any:
        return self._get("/v1/standings", params={"seasonCode": season_code})

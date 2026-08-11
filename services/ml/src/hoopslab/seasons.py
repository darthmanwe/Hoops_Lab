"""Season identifiers, and conversion between the three formats in play.

Each source names seasons differently:

* NBA (`stats.nba.com`) uses ``"2023-24"``
* EuroLeague uses the integer ``2023``
* ESPN uses the integer ``2024`` — the year the season *ends*

Canonical form here is ``{LEAGUE}_{start_year}``, e.g. ``NBA_2023``,
``EL_2023``, ``GL_2023``, all keyed on the year the season **starts**.

The previous version sorted seasons with ``ORDER BY season_id DESC`` on a text
column, which compares ``"NBA_2025"`` against ``"EL_2025"`` lexically. "Latest
season" was therefore wrong for exactly the players who appear in both leagues
— the cross-league cohort this project exists to study. ``season_order`` below
is an integer for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

League = Literal["NBA", "EL", "GL"]

LEAGUES: tuple[League, ...] = ("NBA", "EL", "GL")

LEAGUE_NAMES: dict[League, str] = {
    "NBA": "National Basketball Association",
    "EL": "EuroLeague",
    "GL": "NBA G League",
}

# Coverage, chosen deliberately rather than "as much as possible".
#
# Season-grain stats go back a long way because the translation model needs the
# years and each season costs a couple of requests. Game and shot grain start
# in 2013-14 because the three-point regime before then is different enough
# that era-adjusting shot-zone clusters becomes its own project.
#
# EuroLeague was verified back to 2007 during source probing (347 players
# returned for that season). G League advanced stats begin in 2015-16.
SEASON_COVERAGE: dict[League, range] = {
    "NBA": range(2000, 2025),
    "EL": range(2007, 2025),
    "GL": range(2015, 2025),
}

#: Game-level and box-score coverage, which is narrower than season grain.
GAME_COVERAGE: dict[League, range] = {
    "NBA": range(2013, 2025),
    "EL": range(2007, 2025),
    "GL": range(0, 0),  # not ingested
}


@dataclass(frozen=True, order=True)
class Season:
    """A single league-season, in canonical form."""

    league: League
    start_year: int

    @property
    def season_id(self) -> str:
        return f"{self.league}_{self.start_year}"

    @property
    def season_order(self) -> int:
        """Chronological sort key that is correct across leagues."""
        return self.start_year

    @property
    def end_year(self) -> int:
        return self.start_year + 1

    @property
    def label(self) -> str:
        """Human-readable, e.g. ``2023-24``."""
        return f"{self.start_year}-{str(self.end_year)[-2:]}"

    # -- source-specific encodings -----------------------------------------

    @property
    def nba_stats_season(self) -> str:
        """``stats.nba.com`` format, e.g. ``2023-24``."""
        return self.label

    @property
    def euroleague_season(self) -> int:
        """EuroLeague API format: the start year as an integer."""
        return self.start_year

    @property
    def espn_season(self) -> int:
        """ESPN format: the year the season *ends*."""
        return self.end_year

    @classmethod
    def parse(cls, season_id: str) -> Season:
        league, _, year = season_id.partition("_")
        if league not in LEAGUES or not year.isdigit():
            raise ValueError(
                f"Malformed season id {season_id!r}. Expected {{NBA|EL|GL}}_<start year>, "
                "for example NBA_2023."
            )
        return cls(league=league, start_year=int(year))


def seasons_for(league: League, *, game_grain: bool = False) -> list[Season]:
    """Every season to ingest for a league, oldest first."""
    coverage = GAME_COVERAGE[league] if game_grain else SEASON_COVERAGE[league]
    return [Season(league=league, start_year=year) for year in coverage]


def all_seasons(*, game_grain: bool = False) -> list[Season]:
    return [s for league in LEAGUES for s in seasons_for(league, game_grain=game_grain)]

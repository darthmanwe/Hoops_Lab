"""Season identifiers and the three encodings the sources use."""

from __future__ import annotations

import pytest

from hoopslab.seasons import SEASON_COVERAGE, Season, seasons_for


class TestEncodings:
    def test_nba_uses_a_hyphenated_label(self) -> None:
        assert Season("NBA", 2023).nba_stats_season == "2023-24"

    def test_euroleague_uses_the_start_year(self) -> None:
        assert Season("EL", 2023).euroleague_season == 2023

    def test_espn_uses_the_year_the_season_ends(self) -> None:
        """Getting this wrong shifts every game by a year.

        The result still looks like a plausible dataset, which is what makes it
        dangerous — a model would fit happily on misaligned data.
        """
        assert Season("NBA", 2023).espn_season == 2024

    def test_the_decade_rollover_formats_correctly(self) -> None:
        assert Season("NBA", 2009).label == "2009-10"
        assert Season("NBA", 1999).label == "1999-00"


class TestOrdering:
    def test_season_order_is_chronological_across_leagues(self) -> None:
        """The bug this replaces: `ORDER BY season_id DESC` on a text column.

        String comparison puts "NBA_2025" above "EL_2025", so "latest season"
        was wrong for precisely the players who appear in both leagues — the
        cross-league cohort this project exists to study.
        """
        nba = Season("NBA", 2020)
        euro = Season("EL", 2021)

        assert euro.season_id < nba.season_id  # text order is misleading
        assert euro.season_order > nba.season_order  # chronological order is right

    def test_seasons_are_returned_oldest_first(self) -> None:
        seasons = seasons_for("NBA")
        assert [s.season_order for s in seasons] == sorted(s.season_order for s in seasons)


class TestParsing:
    def test_round_trips(self) -> None:
        assert Season.parse("NBA_2023") == Season("NBA", 2023)

    @pytest.mark.parametrize("bad", ["NBA2023", "XX_2023", "NBA_", "NBA_abc", "", "2023"])
    def test_rejects_malformed_ids(self, bad: str) -> None:
        with pytest.raises(ValueError, match="Malformed season id"):
            Season.parse(bad)


class TestCoverage:
    def test_every_league_has_coverage(self) -> None:
        for league in ("NBA", "EL", "GL"):
            assert len(seasons_for(league)) > 0  # type: ignore[arg-type]

    def test_nba_history_is_long_enough_for_an_aging_curve(self) -> None:
        """Stage one of the translation model needs thousands of same-league pairs."""
        assert len(SEASON_COVERAGE["NBA"]) >= 20

    def test_euroleague_starts_where_the_data_does(self) -> None:
        """Verified during source probing: 2007 returns 347 players."""
        assert min(SEASON_COVERAGE["EL"]) == 2007

    def test_season_ids_are_unique_across_leagues(self) -> None:
        ids = [s.season_id for league in ("NBA", "EL", "GL") for s in seasons_for(league)]  # type: ignore[arg-type]
        assert len(set(ids)) == len(ids)

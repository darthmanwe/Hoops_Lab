"""Rate formulas, checked against values worked out by hand.

These are the formulas whose correctness the whole cross-league comparison
rests on: if the NBA and the EuroLeague are measured differently, the estimated
translation coefficient absorbs the difference between two formulas along with
the difference between two leagues, and nothing downstream can separate them.
"""

from __future__ import annotations

import polars as pl
import pytest

from hoopslab.transform import rates


def _frame(**columns: float) -> pl.DataFrame:
    return pl.DataFrame({k: [v] for k, v in columns.items()})


class TestTrueShooting:
    def test_matches_a_hand_computed_value(self) -> None:
        # 25 points on 20 FGA and 5 FTA -> 25 / (2 * (20 + 0.44*5)) = 0.5630...
        frame = _frame(pts=25.0, fga=20.0, fta=5.0)
        got = frame.select(rates.true_shooting_pct()).item()
        assert got == pytest.approx(25 / (2 * (20 + 0.44 * 5)), rel=1e-9)

    def test_a_perfect_two_point_game_is_one(self) -> None:
        frame = _frame(pts=20.0, fga=10.0, fta=0.0)
        assert frame.select(rates.true_shooting_pct()).item() == pytest.approx(1.0)

    def test_is_null_not_zero_without_attempts(self) -> None:
        """A player who never shot has undefined efficiency, not zero.

        Coercing this to 0 is how a defensive specialist ends up ranked as the
        worst shooter in the league.
        """
        frame = _frame(pts=0.0, fga=0.0, fta=0.0)
        assert frame.select(rates.true_shooting_pct()).item() is None


class TestUsageRate:
    def test_matches_a_hand_computed_value(self) -> None:
        frame = _frame(
            fga=1000.0,
            fta=300.0,
            tov=200.0,
            minutes=2400.0,
            team_fga=6500.0,
            team_fta=1800.0,
            team_tov=1100.0,
            team_minutes=19800.0,
        )
        expected = (1000 + 0.44 * 300 + 200) * (19800 / 5) / (2400 * (6500 + 0.44 * 1800 + 1100))
        assert frame.select(rates.usage_rate()).item() == pytest.approx(expected, rel=1e-9)

    def test_lands_in_a_plausible_range_for_a_starter(self) -> None:
        frame = _frame(
            fga=1200.0,
            fta=400.0,
            tov=250.0,
            minutes=2500.0,
            team_fga=7000.0,
            team_fta=1900.0,
            team_tov=1150.0,
            team_minutes=19800.0,
        )
        usage = frame.select(rates.usage_rate()).item()
        assert 0.15 < usage < 0.40

    def test_team_minutes_scale_changes_the_answer_fivefold(self) -> None:
        """Guards the bug that made EuroLeague usage five times too large.

        `stats.nba.com` reports team minutes as game-clock minutes; summing
        player minutes gives a figure five times larger. Using one definition
        for one league and the other for another produced rates correlating at
        0.998 with the truth while being wrong by a factor of five.
        """
        common = {
            "fga": 1000.0,
            "fta": 300.0,
            "tov": 200.0,
            "minutes": 2400.0,
            "team_fga": 6500.0,
            "team_fta": 1800.0,
            "team_tov": 1100.0,
        }
        player_minutes = _frame(**common, team_minutes=19800.0).select(rates.usage_rate()).item()
        clock_minutes = _frame(**common, team_minutes=3960.0).select(rates.usage_rate()).item()

        assert player_minutes == pytest.approx(clock_minutes * 5, rel=1e-9)

    def test_is_null_without_minutes(self) -> None:
        frame = _frame(
            fga=0.0,
            fta=0.0,
            tov=0.0,
            minutes=0.0,
            team_fga=6500.0,
            team_fta=1800.0,
            team_tov=1100.0,
            team_minutes=19800.0,
        )
        assert frame.select(rates.usage_rate()).item() is None


class TestPer75:
    def test_scales_to_thirty_six_minutes(self) -> None:
        frame = _frame(pts=500.0, minutes=1000.0)
        assert frame.select(rates.per_75("pts")).item() == pytest.approx(18.0)

    def test_is_null_without_minutes(self) -> None:
        assert _frame(pts=0.0, minutes=0.0).select(rates.per_75("pts")).item() is None


class TestRatio:
    def test_divides(self) -> None:
        assert _frame(a=3.0, b=4.0).select(rates.ratio("a", "b")).item() == pytest.approx(0.75)

    def test_yields_null_rather_than_infinity(self) -> None:
        """NaN and infinity are illegal in gold; they serialise to invalid SQL."""
        assert _frame(a=3.0, b=0.0).select(rates.ratio("a", "b")).item() is None

    def test_never_produces_a_non_finite_value(self) -> None:
        frame = pl.DataFrame({"a": [1.0, 0.0, -1.0], "b": [0.0, 0.0, 0.0]})
        result = frame.select(rates.ratio("a", "b").alias("r"))["r"]
        assert result.is_infinite().sum() == 0
        assert result.is_null().all()

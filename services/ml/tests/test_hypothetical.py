"""Projections for players who have not changed league.

The feature the project exists for, and the one where a wrong answer is hardest
to notice: a counterfactual has no actual value beside it, so nothing in the
data will ever contradict it. These tests pin the properties that keep it
honest.
"""

from __future__ import annotations

import polars as pl
import pytest

from hoopslab.models.hypothetical import (
    ASSUMED_GAP_SEASONS,
    PROJECTED_DIRECTIONS,
    build_counterfactual_frame,
    latest_season_for,
    score_counterfactuals,
    support_range,
)
from hoopslab.paths import DataPaths
from hoopslab.transform.gold import MIN_SOURCE_MINUTES


@pytest.fixture(scope="module")
def gold() -> tuple[pl.DataFrame, pl.DataFrame]:
    paths = DataPaths.discover()
    if not (paths.gold / "transition_pairs.parquet").is_file():
        pytest.skip("no committed gold snapshot")
    return (
        pl.read_parquet(paths.gold / "player_seasons.parquet"),
        pl.read_parquet(paths.gold / "transition_pairs.parquet"),
    )


@pytest.fixture(scope="module")
def projections(gold: tuple[pl.DataFrame, pl.DataFrame]) -> pl.DataFrame:
    player_seasons, pairs = gold
    return score_counterfactuals(
        player_seasons,
        pairs,
        direction="EL->NBA",
        target_season_id=latest_season_for(player_seasons, "NBA"),
        metric="usg_pct",
    )


def test_players_who_already_moved_are_excluded(
    gold: tuple[pl.DataFrame, pl.DataFrame], projections: pl.DataFrame
) -> None:
    """They have a real prediction; a hypothetical one would duplicate it."""
    _, pairs = gold
    moved = set(pairs.filter(pl.col("direction") == "EL->NBA")["person_id"].to_list())
    projected = set(projections["person_id"].to_list())
    assert not (projected & moved)


def test_only_qualifying_seasons_are_projected(projections: pl.DataFrame) -> None:
    """The minutes floor is the one the training pairs had to clear."""
    assert projections["source_minutes"].min() >= MIN_SOURCE_MINUTES


def test_one_row_per_player(projections: pl.DataFrame) -> None:
    """Their most recent qualifying season, not one row per season played."""
    assert projections["person_id"].n_unique() == projections.height


def test_the_most_recent_season_is_the_one_used(
    gold: tuple[pl.DataFrame, pl.DataFrame], projections: pl.DataFrame
) -> None:
    """A projection off a five-year-old line answers a question nobody asked."""
    player_seasons, _ = gold
    subject = projections.row(0, named=True)

    eligible = player_seasons.filter(
        (pl.col("person_id") == subject["person_id"])
        & (pl.col("league") == "EL")
        & (pl.col("minutes") >= MIN_SOURCE_MINUTES)
        & pl.col("z_usg_pct").is_not_null()
        & pl.col("age").is_not_null()
    )
    assert (
        subject["source_season_id"]
        == eligible.sort("season_order", descending=True)["season_id"][0]
    )


def test_every_projection_carries_an_interval(projections: pl.DataFrame) -> None:
    """A point estimate with no interval is the thing this project refuses to ship."""
    for column in ("pi80_low", "pi80_high", "pi95_low", "pi95_high"):
        assert projections[column].null_count() == 0

    assert (projections["pi80_low"] < projections["predicted"]).all()
    assert (projections["predicted"] < projections["pi80_high"]).all()
    # 95% must contain 80%, or one of them is wrong.
    assert (projections["pi95_low"] <= projections["pi80_low"]).all()
    assert (projections["pi95_high"] >= projections["pi80_high"]).all()


def test_out_of_support_players_are_flagged_not_dropped(
    gold: tuple[pl.DataFrame, pl.DataFrame], projections: pl.DataFrame
) -> None:
    """Extrapolation is disclosed rather than hidden — and it does occur.

    Ranking by projected usage puts the highest-usage players first, and those
    are routinely beyond the range where transferring players were observed. If
    this flag were never true the check would be vacuous.
    """
    assert (~projections["in_support"]).any(), "no row was flagged; the check would be vacuous"
    assert projections["in_support"].any(), "every row flagged; the support range is wrong"


def test_the_support_flag_matches_the_observed_range(
    gold: tuple[pl.DataFrame, pl.DataFrame], projections: pl.DataFrame
) -> None:
    z_min, z_max = projections["support_z_min"][0], projections["support_z_max"][0]
    inside = (projections["z_source"] >= z_min) & (projections["z_source"] <= z_max)
    assert (inside == projections["in_support"]).all()


def test_support_range_comes_from_movers_only(gold: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    """Defining support from the projected population would make it meaningless."""
    player_seasons, pairs = gold
    from hoopslab.features.translation import build_transition_frame

    transitions = build_transition_frame(pairs, player_seasons, "usg_pct")
    support = support_range(transitions, "EL->NBA", "usg_pct")

    observed = transitions.filter(pl.col("direction") == "EL->NBA")
    assert support.n_movers == observed.height
    assert support.z_min == pytest.approx(observed["z_source"].min())


def test_the_move_is_assumed_one_season_later(projections: pl.DataFrame) -> None:
    assert (projections["gap_seasons"] == ASSUMED_GAP_SEASONS).all()


def test_an_unknown_destination_season_is_refused(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    """Silently falling back to a pooled mean would change what the number means."""
    player_seasons, _ = gold
    with pytest.raises(ValueError, match="no league moments"):
        build_counterfactual_frame(
            player_seasons,
            direction="EL->NBA",
            target_season_id="NBA_1971",
            metric="usg_pct",
        )


def test_projections_are_ranked_by_the_projection(projections: pl.DataFrame) -> None:
    predicted = projections["predicted"].to_list()
    assert predicted == sorted(predicted, reverse=True)


def test_every_observed_direction_is_projected(gold: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    """A direction the model can fit but does not serve is a silent exclusion.

    The first version projected only the two moves ending in the NBA, which left
    every NBA player out of a feature whose entire subject is players who have
    not moved — and dropped the two *best-evidenced* directions in the data.
    """
    _, pairs = gold
    observed = set(pairs["direction"].unique().to_list())
    assert observed == set(PROJECTED_DIRECTIONS)


def test_players_from_all_three_leagues_are_projected(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    player_seasons, pairs = gold
    covered = set()

    for direction in PROJECTED_DIRECTIONS:
        _, _, target = direction.partition("->")
        frame = score_counterfactuals(
            player_seasons,
            pairs,
            direction=direction,
            target_season_id=latest_season_for(player_seasons, target),
            metric="usg_pct",
        )
        assert not frame.is_empty(), f"{direction} produced nothing"
        covered.update(frame["source_league"].unique().to_list())

    assert covered == {"NBA", "EL", "GL"}


def test_the_mover_count_rides_on_every_row(projections: pl.DataFrame) -> None:
    """It is the number that decides how much a projection is worth."""
    assert projections["support_n_movers"].n_unique() == 1
    assert projections["support_n_movers"][0] > 0


def test_g_league_ages_come_from_the_source_not_inference(
    gold: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    """The G League bio endpoint reports age; a stale comment said it did not.

    Before this was checked, a G League player who never reached the NBA had no
    age anywhere, and every model taking age as a covariate dropped him. That
    silently removed roughly half the G League pool from the projections.
    """
    player_seasons, _ = gold
    gl = player_seasons.filter(
        (pl.col("league") == "GL") & (pl.col("minutes") >= MIN_SOURCE_MINUTES)
    )
    missing = gl["age"].null_count()
    assert missing / gl.height < 0.01, f"{missing} of {gl.height} G League seasons still lack age"

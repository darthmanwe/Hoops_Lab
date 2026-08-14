"""Frames for the two-stage cross-league translation model.

The whole reason a sample of ~96 EuroLeague-to-NBA transitions is usable is
that almost nothing is estimated from it:

**Stage 1** learns how a player's production changes from one season to the
next *within* a league — aging plus regression to the mean — from thousands of
consecutive same-league seasons.

**Stage 2** then estimates only the *additional* offset attributable to
changing league, on the transition pairs. It asks: given what stage 1 predicts
this player would have done had he stayed, what actually happened when he
moved?

Without that split, the small sample would have to carry the aging curve too,
and the league effect would be inseparable from ordinary year-to-year change.
"""

from __future__ import annotations

import logging

import polars as pl

log = logging.getLogger(__name__)

#: Metrics the model estimates a translation coefficient for. These are
#: primitives, never composites: each can be checked against what the player
#: actually did. The previous version served an "nba_equivalent_rating" that
#: was unfalsifiable by construction.
TARGET_METRICS = ("usg_pct", "ts_pct")

#: Minimum minutes for a season to enter the stage-1 persistence fit.
MIN_PERSISTENCE_MINUTES = 500


def build_persistence_frame(
    player_seasons: pl.DataFrame, metric: str, *, min_minutes: int = MIN_PERSISTENCE_MINUTES
) -> pl.DataFrame:
    """Consecutive same-league season pairs for one metric.

    This is where the aging curve and mean reversion come from, and it is large:
    roughly ten thousand NBA pairs against ninety-odd transitions.

    Pairs are strictly within one league. A player's move year is excluded here
    by construction, because that is the effect stage 2 exists to measure.
    """
    eligible = player_seasons.filter(
        pl.col("person_id").is_not_null()
        & (pl.col("minutes") >= min_minutes)
        & pl.col(f"z_{metric}").is_not_null()
        & pl.col("age").is_not_null()
    ).select(
        "person_id",
        "league",
        "season_order",
        "minutes",
        "age",
        pl.col(f"z_{metric}").alias("z_from"),
    )

    following = eligible.select(
        "person_id",
        "league",
        (pl.col("season_order") - 1).alias("season_order"),
        pl.col("z_from").alias("z_to"),
    )

    return (
        eligible.join(following, on=["person_id", "league", "season_order"], how="inner")
        .with_columns(
            pl.col("minutes").log().alias("log_minutes"),
            pl.lit(metric).alias("metric"),
        )
        .sort(["person_id", "season_order"])
    )


def build_transition_frame(
    pairs: pl.DataFrame, player_seasons: pl.DataFrame, metric: str
) -> pl.DataFrame:
    """One row per observed league switch, carrying both sides of the move.

    Joining the source and target seasons onto the pair is the step that makes
    the response variable meaningful — and the step that a person-centric
    identity model is required for. Under the previous schema, where a player
    who changed league became two unrelated rows, this join had no key.
    """
    source_cols = player_seasons.select(
        "person_id",
        pl.col("season_id").alias("source_season_id"),
        pl.col(f"z_{metric}").alias("z_source"),
        pl.col(metric).alias("source_value"),
        pl.col("age").alias("age_at_source"),
    )
    target_cols = player_seasons.select(
        "person_id",
        pl.col("season_id").alias("target_season_id"),
        pl.col(f"z_{metric}").alias("z_target"),
        pl.col(metric).alias("target_value"),
    )

    return (
        pairs.join(source_cols, on=["person_id", "source_season_id"], how="inner")
        .join(target_cols, on=["person_id", "target_season_id"], how="inner")
        .filter(
            pl.col("z_source").is_not_null()
            & pl.col("z_target").is_not_null()
            & pl.col("age_at_source").is_not_null()
        )
        .with_columns(
            pl.col("source_minutes").log().alias("log_source_minutes"),
            pl.lit(metric).alias("metric"),
        )
        .sort(["target_season_order", "person_id"])
    )


def league_season_moments(player_seasons: pl.DataFrame, metric: str) -> pl.DataFrame:
    """Mean and standard deviation per league-season, for mapping z back to rates.

    A prediction is only useful in the units people argue about. Carrying the
    moments explicitly means the inverse transform uses the *target* season's
    distribution rather than a pooled one, which is what makes "a usage rate of
    0.24" mean the same thing in 2008 and 2024.
    """
    qualified = player_seasons.filter(pl.col("qualified") & pl.col(metric).is_not_null())

    weight = pl.col("minutes")
    return qualified.group_by("season_id").agg(
        ((pl.col(metric) * weight).sum() / weight.sum()).alias("mean"),
        pl.col(metric).std().alias("sd"),
        pl.len().alias("n_qualified"),
    )


def attach_moments(frame: pl.DataFrame, moments: pl.DataFrame, season_column: str) -> pl.DataFrame:
    return frame.join(
        moments.rename({"season_id": season_column, "mean": "target_mean", "sd": "target_sd"}),
        on=season_column,
        how="left",
    )

"""Projections for players who have not changed league.

The model is fitted on 414 transfers that happened. This module applies it to
players who have not moved — which is the question a front office actually
asks, and the one place in this project where the estimand has to be handled
with real care rather than merely quoted.

**What the number means.** It is not "this player will post a 21% usage rate in
the NBA". It is "of the players who moved from this league with production like
his, history records this". The conditioning is on *having been signed*, and it
does not go away when the subject has not been signed — it becomes an explicit
assumption instead of an implicit one.

**Why that assumption can fail.** The fitted relationship comes from a cohort
that sits +0.46 sd above its own league, because being good is why they were
offered contracts. Two things could break when the same function is applied to
someone outside that cohort:

1. *Support.* If a player's standing is outside the range where movers were
   actually observed, the estimate is extrapolation rather than interpolation,
   and the interval — computed from the residual spread of the fit — understates
   the real uncertainty because it does not price in being off the end of the
   data. Every row therefore carries ``in_support``, and the API and UI show it.
2. *Selection on unobservables.* If clubs sign players for qualities not in the
   box score, the mapping estimated on those players need not hold for the ones
   nobody signed. This cannot be tested with observational data; the Heckman
   first stage in :mod:`hoopslab.models.selection` bounds it, and no correction
   removes it. It is stated rather than solved.

A projection here is a **ranking instrument over a shortlist**, and the interval
is wide enough that treating it as a valuation would be a misreading the
interface actively works against.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import polars as pl

from hoopslab.features.translation import (
    build_persistence_frame,
    build_transition_frame,
    league_season_moments,
)
from hoopslab.models.translation import fit_persistence, fit_translation
from hoopslab.transform.gold import MIN_SOURCE_MINUTES

log = logging.getLogger(__name__)

#: Every direction with observed transitions to fit an intercept from.
#:
#: An earlier version projected only the two moves ending in the NBA, on the
#: stated grounds that "a current NBA player's hypothetical EuroLeague line is
#: not a question anyone asks". That was wrong twice over. A EuroLeague general
#: manager asks precisely that question, and it is the one this data answers
#: *best*: `NBA->EL` has 115 observed pairs and `NBA->GL` 134, against 61 for
#: the headline `EL->NBA`. Restricting to NBA destinations excluded the whole
#: NBA player pool — 1,670 eligible players — from a feature whose entire
#: purpose is to cover players who have not moved.
#:
#: `EL->GL` is fitted from only 14 pairs. It is served rather than dropped
#: because the count rides on every row and is shown in the interface; a
#: direction the data barely supports should be visibly thin, not absent with
#: no explanation.
PROJECTED_DIRECTIONS = (
    "EL->NBA",
    "GL->NBA",
    "NBA->EL",
    "NBA->GL",
    "GL->EL",
    "EL->GL",
)

#: A hypothetical move is assumed to happen the season after the source one,
#: which is what almost every observed transfer did.
ASSUMED_GAP_SEASONS = 1


@dataclass
class SupportRange:
    """The span of source standing over which the fit was actually observed.

    Outside it the model is extrapolating, and its interval — derived from the
    residual spread inside the fitted range — has no way to know that.
    """

    direction: str
    metric: str
    z_min: float
    z_max: float
    n_movers: int

    def contains(self, z: np.ndarray) -> np.ndarray:
        return (z >= self.z_min) & (z <= self.z_max)


def support_range(transitions: pl.DataFrame, direction: str, metric: str) -> SupportRange:
    """Observed range of source standing among players who actually moved."""
    observed = transitions.filter(pl.col("direction") == direction)
    if observed.is_empty():
        raise ValueError(f"no observed {direction} transitions to define support from")

    z = observed["z_source"].to_numpy()
    return SupportRange(
        direction=direction,
        metric=metric,
        z_min=float(z.min()),
        z_max=float(z.max()),
        n_movers=observed.height,
    )


def build_counterfactual_frame(
    player_seasons: pl.DataFrame,
    *,
    direction: str,
    target_season_id: str,
    metric: str,
    min_minutes: float = MIN_SOURCE_MINUTES,
) -> pl.DataFrame:
    """One row per eligible player who has not made this move.

    Uses each player's **most recent** qualifying season, because a projection
    built from a five-year-old line answers a question nobody asked. Eligibility
    is the same minutes floor the training pairs had to clear: a rate computed
    from a handful of appearances is not an input the model was fitted on.
    """
    source_league, _, _ = direction.partition("->")

    eligible = player_seasons.filter(
        (pl.col("league") == source_league)
        & pl.col("person_id").is_not_null()
        & (pl.col("minutes") >= min_minutes)
        & pl.col(f"z_{metric}").is_not_null()
        & pl.col("age").is_not_null()
    )
    if eligible.is_empty():
        return eligible

    latest = eligible.sort("season_order", descending=True).unique(
        subset=["person_id"], keep="first"
    )

    moments = league_season_moments(player_seasons, metric).filter(
        pl.col("season_id") == target_season_id
    )
    if moments.is_empty():
        raise ValueError(f"no league moments for the assumed destination {target_season_id}")

    target_mean = float(moments["mean"][0])
    target_sd = float(moments["sd"][0])

    return latest.select(
        "person_id",
        "player_name",
        "team_name",
        pl.col("season_id").alias("source_season_id"),
        pl.col("league").alias("source_league"),
        pl.col("minutes").alias("source_minutes"),
        pl.col("age").alias("age_at_source"),
        pl.col(metric).alias("source_value"),
        pl.col(f"z_{metric}").alias("z_source"),
    ).with_columns(
        pl.lit(direction).alias("direction"),
        pl.lit(target_season_id).alias("target_season_id"),
        pl.lit(ASSUMED_GAP_SEASONS).alias("gap_seasons"),
        pl.lit(target_mean).alias("target_mean"),
        pl.lit(target_sd).alias("target_sd"),
        pl.col("source_minutes").log().alias("log_source_minutes"),
        pl.lit(metric).alias("metric"),
    )


def score_counterfactuals(
    player_seasons: pl.DataFrame,
    pairs: pl.DataFrame,
    *,
    direction: str,
    target_season_id: str,
    metric: str,
) -> pl.DataFrame:
    """Project every eligible non-mover, with support and mover flags attached.

    The model is refitted here on the observed transfers rather than loaded, so
    a projection can never be served against coefficients that no longer match
    the committed data.
    """
    moments = league_season_moments(player_seasons, metric)
    transitions = (
        build_transition_frame(pairs, player_seasons, metric)
        .join(
            moments.rename(
                {"season_id": "target_season_id", "mean": "target_mean", "sd": "target_sd"}
            ),
            on="target_season_id",
            how="left",
        )
        .filter(pl.col("target_sd").is_not_null() & (pl.col("target_sd") > 0))
    )

    persistence = fit_persistence(build_persistence_frame(player_seasons, metric), metric)
    model = fit_translation(transitions, persistence, metric)
    support = support_range(transitions, direction, metric)

    frame = build_counterfactual_frame(
        player_seasons, direction=direction, target_season_id=target_season_id, metric=metric
    )
    if frame.is_empty():
        return frame

    # Anyone with an observed transfer in this direction already has a real
    # prediction; a hypothetical one for them would be a duplicate wearing a
    # different name.
    moved = set(pairs.filter(pl.col("direction") == direction)["person_id"].to_list())
    frame = frame.filter(~pl.col("person_id").is_in(list(moved)) if moved else pl.lit(True))
    if frame.is_empty():
        return frame

    predicted = model.predict_rate(frame)
    pi80 = model.prediction_interval(frame, level=0.80)
    pi95 = model.prediction_interval(frame, level=0.95)
    in_support = support.contains(frame["z_source"].to_numpy())

    # Anyone who moved in *some* other direction is still a different case from
    # a player with no cross-league history at all, and the distinction is worth
    # serving: the first has been signed abroad before.
    any_move = set(pairs["person_id"].to_list())

    return frame.with_columns(
        pl.Series("predicted", predicted),
        pl.Series("pi80_low", pi80[:, 0]),
        pl.Series("pi80_high", pi80[:, 1]),
        pl.Series("pi95_low", pi95[:, 0]),
        pl.Series("pi95_high", pi95[:, 1]),
        pl.Series("in_support", in_support),
        pl.col("person_id").is_in(list(any_move)).alias("moved_before")
        if any_move
        else pl.lit(False).alias("moved_before"),
        pl.lit(support.z_min).alias("support_z_min"),
        pl.lit(support.z_max).alias("support_z_max"),
        pl.lit(support.n_movers).alias("support_n_movers"),
    ).sort("predicted", descending=True)


def latest_season_for(player_seasons: pl.DataFrame, league: str) -> str:
    """The most recent season of a league, used as the assumed destination."""
    seasons = player_seasons.filter(pl.col("league") == league)
    if seasons.is_empty():
        raise ValueError(f"no seasons for {league}")
    latest = seasons.sort("season_order", descending=True)["season_id"][0]
    return str(latest)

"""Three-point shooting threat, shrunk toward a prior.

This is what replaces "gravity".

The previous version served a `gravity_overall` figure that was typed by hand.
Gravity means how much defensive attention a player draws, which requires
optical player-tracking data: the NBA does not publish it and the EuroLeague
does not collect it. There is no honest way to compute it here, so it is gone
rather than renamed.

What *is* computable is shooting threat — volume times accuracy — and the
statistical problem it poses is small-sample noise. A player who makes 4 of 6
threes has an observed 66.7%, which is not a measurement of anything. Empirical
Bayes shrinks each observation toward a prior in proportion to how little
evidence supports it, and the shrinkage weight is published alongside so a
reader can see how much of a number is data and how much is prior.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

log = logging.getLogger(__name__)

#: Attempts below this are still reported, but will be almost entirely prior.
MIN_ATTEMPTS_REPORTED = 20


def fit_beta_prior(makes: np.ndarray, attempts: np.ndarray) -> tuple[float, float]:
    """Method-of-moments Beta prior from the population of shooters.

    Estimated per league-season from players with enough attempts to carry
    information, then applied to everyone. Using the observed mean and variance
    of the rate rather than a chosen prior keeps the shrinkage empirical.
    """
    usable = attempts >= 50
    if usable.sum() < 20:
        return (1.0, 1.0)

    rates = makes[usable] / attempts[usable]
    mean = float(rates.mean())
    variance = float(rates.var())

    if variance <= 0 or not 0 < mean < 1:
        return (1.0, 1.0)

    # Beta moment matching: solve for the concentration implied by the spread.
    concentration = mean * (1 - mean) / variance - 1
    concentration = max(concentration, 1.0)
    return (mean * concentration, (1 - mean) * concentration)


def shrink_three_point(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Shrunk three-point percentage and a spacing score, per league-season.

    ``shrinkage_weight`` is the fraction of the posterior coming from the
    player's own attempts. A shooter with 40 attempts sits mostly on the prior,
    and saying so is the point: it is the difference between a measurement and
    an impression.
    """
    frame = player_seasons.filter(
        pl.col("person_id").is_not_null()
        & pl.col("fg3a").is_not_null()
        & pl.col("fg3m").is_not_null()
        & (pl.col("minutes") > 0)
    )
    if frame.is_empty():
        return pl.DataFrame()

    rows: list[dict[str, object]] = []

    for season in frame["season_id"].unique().to_list():
        block = frame.filter(pl.col("season_id") == season)
        makes = block["fg3m"].to_numpy().astype(float)
        attempts = block["fg3a"].to_numpy().astype(float)

        alpha, beta = fit_beta_prior(makes, attempts)
        prior_strength = alpha + beta
        prior_mean = alpha / prior_strength

        posterior = (makes + alpha) / (attempts + prior_strength)
        weight = attempts / (attempts + prior_strength)
        per_75 = np.divide(
            attempts * 36.0,
            block["minutes"].to_numpy().astype(float),
            out=np.zeros_like(attempts),
            where=block["minutes"].to_numpy().astype(float) > 0,
        )

        for i, person in enumerate(block["person_id"].to_list()):
            rows.append(
                {
                    "season_id": season,
                    "person_id": person,
                    "fg3a": float(attempts[i]),
                    "fg3a_per_75": round(float(per_75[i]), 3),
                    "fg3_pct_raw": (
                        round(float(makes[i] / attempts[i]), 4) if attempts[i] > 0 else None
                    ),
                    "fg3_pct_shrunk": round(float(posterior[i]), 4),
                    "shrinkage_weight": round(float(weight[i]), 4),
                    "prior_mean": round(float(prior_mean), 4),
                    # Threat is volume times accuracy: a great shooter who never
                    # shoots does not stretch a defence.
                    "spacing_score": round(float(posterior[i] * per_75[i]), 4),
                    "reportable": bool(attempts[i] >= MIN_ATTEMPTS_REPORTED),
                }
            )

    return pl.DataFrame(rows)

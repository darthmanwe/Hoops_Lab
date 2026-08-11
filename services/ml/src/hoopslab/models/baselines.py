"""Baselines the translation model has to beat.

All four are reported every time, on every metric. A model that does not beat
(3) and (4) has demonstrated nothing, and reporting only the weakest baseline
is the most common way a sports model looks better than it is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

#: The folk rule of thumb: "European production translates at about 75%".
#: Implemented literally so the model is measured against the claim people
#: actually make, rather than a strawman.
FOLK_MULTIPLIER = 0.75


@dataclass(frozen=True)
class Baseline:
    name: str
    description: str
    predictions: np.ndarray


def target_league_mean(frame: pl.DataFrame) -> Baseline:
    """Predict the target league-season average, ignoring the player entirely.

    The scale reference. Any model failing to beat this is not using its input.
    """
    return Baseline(
        name="league_mean",
        description="Target league-season mean, ignoring the player",
        predictions=frame["target_mean"].to_numpy(),
    )


def folk_rule(frame: pl.DataFrame) -> Baseline:
    """Multiply the source-league rate by 0.75."""
    return Baseline(
        name="folk_0.75",
        description=f"Source-league rate multiplied by {FOLK_MULTIPLIER}",
        predictions=frame["source_value"].to_numpy() * FOLK_MULTIPLIER,
    )


def z_preservation(frame: pl.DataFrame) -> Baseline:
    """Assume standing within a league carries over unchanged.

    The strongest naive baseline, and the one the whole exercise is defined
    against: a fitted slope below one means production *compresses* on the way
    up, and this baseline is the slope-equals-one null.
    """
    predicted = frame["z_source"].to_numpy() * frame["target_sd"].to_numpy() + (
        frame["target_mean"].to_numpy()
    )
    return Baseline(
        name="z_preservation",
        description="Same standardised standing in the target league",
        predictions=predicted,
    )


def persistence_only(frame: pl.DataFrame, persisted_z: np.ndarray) -> Baseline:
    """Stage-1 prediction with no league term at all.

    The baseline that actually matters. It isolates what changing league adds
    over ordinary season-to-season change, so beating it is the only evidence
    that a *league* effect has been measured rather than aging and mean
    reversion wearing a different label.
    """
    predicted = persisted_z * frame["target_sd"].to_numpy() + frame["target_mean"].to_numpy()
    return Baseline(
        name="persistence_no_league",
        description="Stage-1 persistence, no league-transition term",
        predictions=predicted,
    )

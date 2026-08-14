"""Selection analysis for the transition cohort.

Players who cross leagues are not a random sample of the league they leave.
EuroLeague-to-NBA moves happen because somebody was good enough to be signed;
NBA-to-EuroLeague moves happen because somebody was not good enough to stay.
Every coefficient here is conditional on that, and pretending otherwise would
be the central dishonesty available to this project.

Three treatments, all reported:

1. **Show it** — how far above their league the movers actually sat.
2. **Bound it** — a Heckman-style correction, with the coefficient reported
   both with and without.
3. **Exploit it** — the two directions are selected oppositely, so agreement
   between their slopes is evidence the effect is not selection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import polars as pl

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectionSummary:
    """How selected the movers were, per direction and metric."""

    direction: str
    metric: str
    n_movers: int
    n_league: int
    mover_mean_z: float
    league_mean_z: float

    @property
    def gap_sd(self) -> float:
        """How many standard deviations above their league the movers sat."""
        return self.mover_mean_z - self.league_mean_z

    def render(self) -> str:
        return (
            f"{self.direction:<10} {self.metric:<8} movers n={self.n_movers:<4} "
            f"mean z={self.mover_mean_z:+.2f} vs league {self.league_mean_z:+.2f} "
            f"(+{self.gap_sd:.2f} sd)"
        )


def summarise_selection(
    transitions: pl.DataFrame, player_seasons: pl.DataFrame, metric: str
) -> list[SelectionSummary]:
    """Compare the movers against everyone who could have moved.

    The comparison set is qualified players in the *source* league-seasons the
    movers actually came from, so the contrast is with genuine peers rather
    than with a pooled all-time average.
    """
    summaries: list[SelectionSummary] = []
    z_column = f"z_{metric}"

    for direction in sorted(transitions["direction"].unique().to_list()):
        subset = transitions.filter(pl.col("direction") == direction)
        source_league = direction.split("->")[0]

        source_seasons = subset["source_season_id"].unique().to_list()
        peers = player_seasons.filter(
            (pl.col("league") == source_league)
            & pl.col("season_id").is_in(source_seasons)
            & pl.col("qualified")
            & pl.col(z_column).is_not_null()
        )
        movers = subset.filter(pl.col("z_source").is_not_null())

        if movers.is_empty() or peers.is_empty():
            continue

        summaries.append(
            SelectionSummary(
                direction=direction,
                metric=metric,
                n_movers=movers.height,
                n_league=peers.height,
                mover_mean_z=float(movers["z_source"].mean()),  # type: ignore[arg-type]
                league_mean_z=float(peers[z_column].mean()),  # type: ignore[arg-type]
            )
        )

    return summaries


def inverse_mills_ratio(
    transitions: pl.DataFrame, player_seasons: pl.DataFrame, metric: str, direction: str
) -> np.ndarray | None:
    """Heckman first stage: the selection hazard for each mover.

    Fits a probit of "did this player move" over every qualified player-season
    in the source league, then evaluates the inverse Mills ratio for the movers.
    Including it as a regressor in the second stage absorbs the part of the
    outcome explained by having been selected at all.

    Returns ``None`` when the first stage cannot be fitted, which is a real
    possibility at these sample sizes and is reported rather than papered over.
    """
    try:
        import statsmodels.api as sm
        from scipy.stats import norm
    except ImportError:  # pragma: no cover - statsmodels is a hard dependency
        return None

    z_column = f"z_{metric}"
    source_league, _, _ = direction.partition("->")
    movers = transitions.filter(pl.col("direction") == direction)
    source_seasons = movers["source_season_id"].unique().to_list()

    pool = player_seasons.filter(
        (pl.col("league") == source_league)
        & pl.col("season_id").is_in(source_seasons)
        & pl.col("qualified")
        & pl.col(z_column).is_not_null()
        & pl.col("age").is_not_null()
    )
    if pool.height < 100 or movers.height < 20:
        return None

    moved_keys = set(
        zip(movers["person_id"].to_list(), movers["source_season_id"].to_list(), strict=True)
    )
    moved = np.array(
        [
            1.0 if (p, s) in moved_keys else 0.0
            for p, s in zip(pool["person_id"].to_list(), pool["season_id"].to_list(), strict=True)
        ]
    )
    if moved.sum() < 10:
        return None

    design = sm.add_constant(
        np.column_stack(
            [
                pool[z_column].to_numpy(),
                pool["age"].to_numpy(),
                np.log(np.maximum(pool["minutes"].to_numpy(), 1.0)),
            ]
        )
    )

    try:
        fitted = sm.Probit(moved, design).fit(disp=0)
    except Exception as exc:
        log.warning("selection probit failed for %s/%s: %s", direction, metric, exc)
        return None

    index = np.asarray(fitted.predict(design, linear=True), dtype=float)
    ratio = norm.pdf(index) / np.maximum(norm.cdf(index), 1e-9)

    lookup = {
        (p, s): float(r)
        for p, s, r in zip(
            pool["person_id"].to_list(), pool["season_id"].to_list(), ratio, strict=True
        )
    }
    return np.array(
        [
            lookup.get((p, s), 0.0)
            for p, s in zip(
                movers["person_id"].to_list(), movers["source_season_id"].to_list(), strict=True
            )
        ]
    )

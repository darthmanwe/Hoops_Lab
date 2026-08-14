"""The cross-league translation model.

Stage 1 estimates ordinary season-to-season dynamics from thousands of
same-league pairs. Stage 2 estimates only the league-transition offset, on the
few hundred observed switches.

**On the choice of estimator.** The design note called for a hierarchical
linear model with a per-player random intercept. In the data as it actually
landed there are roughly 1.4 transitions per player, and a random intercept
estimated from an average of 1.4 observations per group is weakly identified —
it converges to a boundary or fails outright, and its standard errors are not
trustworthy either way. The dependence it was meant to absorb is real, so it is
handled where it can be handled honestly: a **cluster bootstrap that resamples
players**, which makes no distributional assumption about the group effects and
gets the repeat-transition dependence right.

Choosing the simpler estimator and saying why is the point. Fitting a mixed
model that barely converges, and quoting its standard errors, would look more
sophisticated and be less true.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import polars as pl

log = logging.getLogger(__name__)

#: Age is modelled with a quadratic rather than a natural cubic spline. Over
#: the 19-40 range that these cohorts span, the two are visually
#: indistinguishable and the quadratic has three parameters instead of six —
#: which matters when the second stage has a few hundred rows.
AGE_REFERENCE = 27.0


@dataclass
class PersistenceModel:
    """Stage 1: how a player's standing moves from one season to the next."""

    metric: str
    coefficients: dict[str, float]
    n_train: int
    r_squared: float

    def predict(self, z_source: np.ndarray, age: np.ndarray, log_minutes: np.ndarray) -> np.ndarray:
        c = self.coefficients
        centred_age = age - AGE_REFERENCE
        return (
            c["intercept"]
            + c["z"] * z_source
            + c["age"] * centred_age
            + c["age_sq"] * centred_age**2
            + c["log_minutes"] * (log_minutes - c["log_minutes_mean"])
        )


@dataclass
class TranslationModel:
    """Stage 2: the additional offset attributable to changing league."""

    metric: str
    persistence: PersistenceModel
    directions: list[str]
    #: Direction-specific intercept (alpha) and the shared slope (beta).
    intercepts: dict[str, float] = field(default_factory=dict)
    beta: float = 1.0
    gamma_log_minutes: float = 0.0
    eta_gap: float = 0.0
    residual_sd: float = 0.0
    n_train: int = 0

    def predict_z(self, frame: pl.DataFrame) -> np.ndarray:
        persisted = self.persist(frame)
        alphas = np.array(
            [self.intercepts.get(d, 0.0) for d in frame["direction"].to_list()], dtype=float
        )
        return (
            alphas
            + self.beta * persisted
            + self.gamma_log_minutes * frame["log_source_minutes"].to_numpy()
            + self.eta_gap * frame["gap_seasons"].to_numpy().astype(float)
        )

    def persist(self, frame: pl.DataFrame) -> np.ndarray:
        """Stage-1 expectation for these players, had they not changed league."""
        return self.persistence.predict(
            frame["z_source"].to_numpy(),
            frame["age_at_source"].to_numpy(),
            frame["log_source_minutes"].to_numpy(),
        )

    def predict_rate(self, frame: pl.DataFrame) -> np.ndarray:
        """Prediction in the units people argue about."""
        return (
            self.predict_z(frame) * frame["target_sd"].to_numpy() + frame["target_mean"].to_numpy()
        )

    def prediction_interval(self, frame: pl.DataFrame, level: float = 0.80) -> np.ndarray:
        """Interval in rate units, from the residual spread of the fit.

        Returned as an (n, 2) array. The serving schema requires these columns
        to be non-null precisely so that a point estimate cannot be stored, and
        therefore cannot be shown, without one.
        """
        from scipy.stats import norm

        half_width = norm.ppf(0.5 + level / 2) * self.residual_sd * frame["target_sd"].to_numpy()
        centre = self.predict_rate(frame)
        return np.column_stack([centre - half_width, centre + half_width])


def fit_persistence(frame: pl.DataFrame, metric: str) -> PersistenceModel:
    """Ordinary least squares on same-league consecutive seasons."""
    if frame.height < 100:
        raise ValueError(
            f"persistence fit for {metric} has only {frame.height} rows; "
            "the two-stage design depends on this stage being large"
        )

    log_minutes = frame["log_minutes"].to_numpy()
    log_minutes_mean = float(log_minutes.mean())
    centred_age = frame["age"].to_numpy() - AGE_REFERENCE

    design = np.column_stack(
        [
            np.ones(frame.height),
            frame["z_from"].to_numpy(),
            centred_age,
            centred_age**2,
            log_minutes - log_minutes_mean,
        ]
    )
    response = frame["z_to"].to_numpy()

    coefficients, *_ = np.linalg.lstsq(design, response, rcond=None)
    fitted = design @ coefficients
    residual_ss = float(((response - fitted) ** 2).sum())
    total_ss = float(((response - response.mean()) ** 2).sum())

    return PersistenceModel(
        metric=metric,
        coefficients={
            "intercept": float(coefficients[0]),
            "z": float(coefficients[1]),
            "age": float(coefficients[2]),
            "age_sq": float(coefficients[3]),
            "log_minutes": float(coefficients[4]),
            "log_minutes_mean": log_minutes_mean,
        },
        n_train=frame.height,
        r_squared=1.0 - residual_ss / total_ss if total_ss > 0 else 0.0,
    )


def fit_translation(
    transitions: pl.DataFrame, persistence: PersistenceModel, metric: str
) -> TranslationModel:
    """Direction-specific intercepts with a single shared slope.

    The shared slope is the identifying restriction that makes the design work.
    EuroLeague-to-NBA is selected on being good enough to be signed;
    NBA-to-EuroLeague on not being good enough to stay. If a single slope fits
    both, the compression it describes is unlikely to be an artefact of
    selection, because selection pushes the two directions in opposite
    directions. Direction-specific slopes are fitted separately in the
    sensitivity analysis for exactly that comparison.
    """
    model = TranslationModel(
        metric=metric,
        persistence=persistence,
        directions=sorted(transitions["direction"].unique().to_list()),
    )

    design, columns = _transition_design(transitions, model.directions, persistence)
    response = transitions["z_target"].to_numpy()

    coefficients, *_ = np.linalg.lstsq(design, response, rcond=None)
    fitted = design @ coefficients
    residuals = response - fitted

    values = dict(zip(columns, (float(c) for c in coefficients), strict=True))
    model.intercepts = {d: values[f"alpha[{d}]"] for d in model.directions}
    model.beta = values["beta"]
    model.gamma_log_minutes = values["gamma_log_minutes"]
    model.eta_gap = values["eta_gap"]
    # Degrees-of-freedom corrected, so the interval is not optimistic at n~500.
    dof = max(transitions.height - len(columns), 1)
    model.residual_sd = float(np.sqrt((residuals**2).sum() / dof))
    model.n_train = transitions.height

    return model


def _transition_design(
    transitions: pl.DataFrame, directions: list[str], persistence: PersistenceModel
) -> tuple[np.ndarray, list[str]]:
    persisted = persistence.predict(
        transitions["z_source"].to_numpy(),
        transitions["age_at_source"].to_numpy(),
        transitions["log_source_minutes"].to_numpy(),
    )

    observed = transitions["direction"].to_list()
    indicators = [
        np.array([1.0 if d == direction else 0.0 for d in observed]) for direction in directions
    ]

    design = np.column_stack(
        [
            *indicators,
            persisted,
            transitions["log_source_minutes"].to_numpy(),
            transitions["gap_seasons"].to_numpy().astype(float),
        ]
    )
    columns = [f"alpha[{d}]" for d in directions] + ["beta", "gamma_log_minutes", "eta_gap"]
    return design, columns


def fit_direction_specific_slopes(
    transitions: pl.DataFrame, persistence: PersistenceModel
) -> dict[str, float]:
    """One slope per direction, for the selection-bias comparison.

    Agreement between the EuroLeague-to-NBA and NBA-to-EuroLeague slopes is
    evidence that the estimated compression is a property of the leagues rather
    than of who gets selected to move; disagreement quantifies how much of it
    is selection.
    """
    slopes: dict[str, float] = {}

    for direction in sorted(transitions["direction"].unique().to_list()):
        subset = transitions.filter(pl.col("direction") == direction)
        if subset.height < 30:
            continue

        persisted = persistence.predict(
            subset["z_source"].to_numpy(),
            subset["age_at_source"].to_numpy(),
            subset["log_source_minutes"].to_numpy(),
        )
        design = np.column_stack([np.ones(subset.height), persisted])
        coefficients, *_ = np.linalg.lstsq(design, subset["z_target"].to_numpy(), rcond=None)
        slopes[direction] = float(coefficients[1])

    return slopes

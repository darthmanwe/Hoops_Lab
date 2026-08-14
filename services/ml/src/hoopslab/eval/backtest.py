"""Walk-forward backtesting for the translation model.

Every fold trains on seasons strictly before the evaluated one and excludes any
player who appears in it, then scores in rate units so the error is
interpretable — a mean absolute error of 0.03 on usage rate means three
percentage points, which is a quantity people have intuitions about.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from hoopslab.eval.leakage import assert_no_entity_overlap, assert_temporal_disjoint
from hoopslab.models import baselines
from hoopslab.models.translation import PersistenceModel, fit_translation

log = logging.getLogger(__name__)

#: Folds smaller than this are reported but not pooled: a handful of rows gives
#: a mean absolute error dominated by which players happened to move that year.
MIN_FOLD_SIZE = 5

#: Seasons before this are used only as training data. The earliest transitions
#: predate the EuroLeague coverage window, so scoring them would evaluate the
#: model on folds that no plausible training set can support.
FIRST_EVALUATED_SEASON = 2012


@dataclass
class FoldResult:
    target_season: int
    n_test: int
    n_train: int
    errors: np.ndarray
    baseline_errors: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class BacktestResult:
    metric: str
    folds: list[FoldResult]
    model_errors: np.ndarray
    baseline_errors: dict[str, np.ndarray]
    person_ids: list[str]
    shuffled_mae: float

    @property
    def n(self) -> int:
        return int(self.model_errors.size)

    @property
    def mae(self) -> float:
        return float(np.abs(self.model_errors).mean())

    def baseline_mae(self) -> dict[str, float]:
        return {name: float(np.abs(errors).mean()) for name, errors in self.baseline_errors.items()}

    def skill_against(self, baseline: str) -> float:
        """Fractional reduction in mean absolute error against a baseline."""
        reference = self.baseline_mae().get(baseline)
        if not reference:
            return 0.0
        return 1.0 - self.mae / reference


def walk_forward(
    transitions: pl.DataFrame,
    persistence: PersistenceModel,
    metric: str,
    *,
    seed: int,
    first_season: int = FIRST_EVALUATED_SEASON,
    run_shuffled_control: bool = True,
) -> BacktestResult:
    """Leave-one-target-season-out, grouped by player.

    Both exclusions matter. Leaving a season out handles time. Dropping players
    who appear in the test fold handles the fact that roughly a third of this
    cohort transitions more than once, so a season split alone would let a
    player's own later move inform his earlier one.
    """
    seasons = sorted(
        s
        for s in transitions["target_season_order"].unique().to_list()
        if s is not None and s >= first_season
    )

    folds: list[FoldResult] = []
    all_errors: list[np.ndarray] = []
    all_baseline_errors: dict[str, list[np.ndarray]] = {}
    all_persons: list[str] = []

    for season in seasons:
        test = transitions.filter(pl.col("target_season_order") == season)
        if test.height < MIN_FOLD_SIZE:
            continue

        test_persons = set(test["person_id"].to_list())
        train = transitions.filter(
            (pl.col("target_season_order") < season)
            & ~pl.col("person_id").is_in(list(test_persons))
        )
        if train.height < 40:
            continue

        # Asserted here, on real folds, rather than assumed by a test elsewhere.
        assert_temporal_disjoint(train, test)
        assert_no_entity_overlap(train, test)

        model = fit_translation(train, persistence, metric)
        predicted = model.predict_rate(test)
        actual = test["target_value"].to_numpy()
        errors = predicted - actual

        fold_baselines = _baseline_errors(test, model, actual)

        folds.append(
            FoldResult(
                target_season=int(season),
                n_test=test.height,
                n_train=train.height,
                errors=errors,
                baseline_errors=fold_baselines,
            )
        )
        all_errors.append(errors)
        all_persons.extend(test["person_id"].to_list())
        for name, values in fold_baselines.items():
            all_baseline_errors.setdefault(name, []).append(values)

    if not folds:
        raise ValueError(f"no evaluable folds for {metric}")

    return BacktestResult(
        metric=metric,
        folds=folds,
        model_errors=np.concatenate(all_errors),
        baseline_errors={k: np.concatenate(v) for k, v in all_baseline_errors.items()},
        person_ids=all_persons,
        # The control re-enters this function on permuted data, so it must not
        # ask for a control of its own.
        shuffled_mae=(
            _shuffled_control(transitions, persistence, metric, seed=seed)
            if run_shuffled_control
            else float("nan")
        ),
    )


def _baseline_errors(test: pl.DataFrame, model, actual: np.ndarray) -> dict[str, np.ndarray]:  # type: ignore[no-untyped-def]
    persisted = model.persist(test)
    candidates = [
        baselines.target_league_mean(test),
        baselines.folk_rule(test),
        baselines.z_preservation(test),
        baselines.persistence_only(test, persisted),
    ]
    return {b.name: b.predictions - actual for b in candidates}


def _shuffled_control(
    transitions: pl.DataFrame, persistence: PersistenceModel, metric: str, *, seed: int
) -> float:
    """Negative control: permute the response and refit.

    Reported alongside the real score in every results table. If shuffling the
    target does not collapse performance to roughly the league-mean baseline,
    something is leaking, and the headline number is measuring the leak.
    """
    rng = np.random.default_rng(seed)
    shuffled = transitions.with_columns(
        pl.Series("z_target", rng.permutation(transitions["z_target"].to_numpy())),
        pl.Series("target_value", rng.permutation(transitions["target_value"].to_numpy())),
    )

    try:
        result = walk_forward(shuffled, persistence, metric, seed=seed, run_shuffled_control=False)
    except ValueError:
        return float("nan")
    return result.mae


def cluster_bootstrap_ci(
    errors: np.ndarray,
    person_ids: list[str],
    *,
    seed: int,
    n_boot: int = 2000,
    level: float = 0.95,
) -> tuple[float, float]:
    """Confidence interval for mean absolute error, resampling **players**.

    Resampling rows would treat a player's two transitions as two independent
    observations and produce an interval that is too narrow. Players are the
    unit that repeats, so players are the unit that is resampled.
    """
    rng = np.random.default_rng(seed)
    absolute = np.abs(errors)

    by_person: dict[str, list[float]] = {}
    for person, value in zip(person_ids, absolute, strict=True):
        by_person.setdefault(person, []).append(float(value))

    people = list(by_person)
    if len(people) < 2:
        return (float("nan"), float("nan"))

    draws = np.empty(n_boot)
    for i in range(n_boot):
        sampled = rng.choice(len(people), size=len(people), replace=True)
        pooled = [v for index in sampled for v in by_person[people[index]]]
        draws[i] = float(np.mean(pooled))

    tail = (1.0 - level) / 2
    return (float(np.quantile(draws, tail)), float(np.quantile(draws, 1 - tail)))

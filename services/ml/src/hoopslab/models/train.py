"""Training driver: fit, backtest, and write an auditable run log.

A run is only "reported" if it is reproducible. The run log records the git
commit, whether the tree was dirty, the seed, the data contract hashes, and
every metric, so a number quoted in the README can be traced to the exact state
that produced it — and `hoopslab train --verify` refits and fails if any of
them has moved.
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from hoopslab.config import SEED
from hoopslab.eval.backtest import cluster_bootstrap_ci, walk_forward
from hoopslab.features.translation import (
    TARGET_METRICS,
    attach_moments,
    build_persistence_frame,
    build_transition_frame,
    league_season_moments,
)
from hoopslab.models.selection import summarise_selection
from hoopslab.models.translation import (
    fit_direction_specific_slopes,
    fit_persistence,
    fit_translation,
)
from hoopslab.paths import DataPaths

log = logging.getLogger(__name__)

MODEL_NAME = "translation"
MODEL_VERSION_MAJOR_MINOR = "v1.0"

#: Metrics may drift by this much before `--verify` fails. Non-zero because
#: BLAS implementations differ across platforms; far tighter than any change a
#: real modelling difference would produce.
VERIFY_TOLERANCE = 1e-6


@dataclass
class MetricResult:
    metric: str
    n_pairs: int
    n_persistence: int
    persistence_r2: float
    beta: float
    intercepts: dict[str, float]
    direction_slopes: dict[str, float]
    mae: float
    mae_ci: tuple[float, float]
    baseline_mae: dict[str, float]
    shuffled_mae: float
    n_evaluated: int
    n_folds: int
    residual_sd: float

    @property
    def best_baseline(self) -> tuple[str, float]:
        """The baseline that is hardest to beat, which is the one that counts."""
        return min(self.baseline_mae.items(), key=lambda kv: kv[1])

    @property
    def beats_baseline(self) -> bool:
        """Whether the model is actually better than the best trivial alternative.

        Reported per metric and served through the API, because a model that
        loses to the league average should say so rather than let a caller
        assume that being published implies being useful.
        """
        return self.mae < self.best_baseline[1]

    @property
    def skill(self) -> float:
        """Fractional error reduction against the best baseline. Negative means worse."""
        reference = self.best_baseline[1]
        return (reference - self.mae) / reference if reference else 0.0

    def render(self) -> str:
        lines = [
            f"  {self.metric}",
            f"    pairs fitted            {self.n_pairs}",
            f"    persistence rows        {self.n_persistence} (R^2 {self.persistence_r2:.3f})",
            f"    shared slope (beta)     {self.beta:+.3f}",
            f"    out-of-fold MAE         {self.mae:.4f}  "
            f"95% CI [{self.mae_ci[0]:.4f}, {self.mae_ci[1]:.4f}]  n={self.n_evaluated}",
        ]
        for name, value in sorted(self.baseline_mae.items(), key=lambda kv: kv[1]):
            delta = (value - self.mae) / value * 100 if value else 0.0
            lines.append(f"      vs {name:<22} {value:.4f}  ({delta:+.1f}% better)")
        lines.append(f"    shuffled-target control {self.shuffled_mae:.4f} (must be worse)")

        name, value = self.best_baseline
        verdict = (
            f"BEATS best baseline ({name}) by {self.skill:+.1%}"
            if self.beats_baseline
            else f"LOSES to best baseline ({name}) by {-self.skill:.1%} - do not use this metric"
        )
        lines.append(f"    verdict: {verdict}")

        if self.direction_slopes:
            rendered = "  ".join(f"{d}={v:+.3f}" for d, v in sorted(self.direction_slopes.items()))
            lines.append(f"    direction-specific slopes {rendered}")
            lines.append(f"    {self.slope_agreement_note()}")
        return "\n".join(lines)

    def slope_agreement_note(self) -> str:
        """State plainly whether the shared-slope restriction is supported.

        The two headline directions are selected oppositely, so if one slope
        fits both, the compression it describes is unlikely to be an artefact
        of who gets picked to move. If they disagree, that disagreement is the
        size of the selection effect and belongs in the reported result rather
        than behind it.
        """
        forward = self.direction_slopes.get("EL->NBA")
        reverse = self.direction_slopes.get("NBA->EL")
        if forward is None or reverse is None:
            return "slope agreement: not estimable (a direction has too few pairs)"

        gap = abs(forward - reverse)
        verdict = "consistent" if gap < 0.15 else "DIVERGENT"
        return (
            f"slope agreement: EL->NBA {forward:+.3f} vs NBA->EL {reverse:+.3f} "
            f"(gap {gap:.3f}, {verdict})"
        )


@dataclass
class RunLog:
    run_id: str
    model: str
    model_version: str
    created_at: str
    git_sha: str
    git_dirty: bool
    seed: int
    python: str
    platform: str
    data_contract_hashes: dict[str, str]
    metrics: dict[str, Any] = field(default_factory=dict)
    selection: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def train_all(paths: DataPaths, *, seed: int = SEED) -> tuple[RunLog, list[MetricResult]]:
    player_seasons = pl.read_parquet(paths.gold / "player_seasons.parquet")
    pairs = pl.read_parquet(paths.gold / "transition_pairs.parquet")

    results: list[MetricResult] = []
    selection_rows: list[dict[str, Any]] = []

    for metric in TARGET_METRICS:
        moments = league_season_moments(player_seasons, metric)
        persistence_frame = build_persistence_frame(player_seasons, metric)
        transitions = build_transition_frame(pairs, player_seasons, metric)
        transitions = attach_moments(transitions, moments, "target_season_id").filter(
            pl.col("target_sd").is_not_null() & (pl.col("target_sd") > 0)
        )

        persistence = fit_persistence(persistence_frame, metric)
        model = fit_translation(transitions, persistence, metric)
        backtest = walk_forward(transitions, persistence, metric, seed=seed)

        low, high = cluster_bootstrap_ci(backtest.model_errors, backtest.person_ids, seed=seed)

        results.append(
            MetricResult(
                metric=metric,
                n_pairs=transitions.height,
                n_persistence=persistence.n_train,
                persistence_r2=persistence.r_squared,
                beta=model.beta,
                intercepts=model.intercepts,
                direction_slopes=fit_direction_specific_slopes(transitions, persistence),
                mae=backtest.mae,
                mae_ci=(low, high),
                baseline_mae=backtest.baseline_mae(),
                shuffled_mae=backtest.shuffled_mae,
                n_evaluated=backtest.n,
                n_folds=len(backtest.folds),
                residual_sd=model.residual_sd,
            )
        )
        selection_rows.extend(
            asdict(s) | {"gap_sd": s.gap_sd}
            for s in summarise_selection(transitions, player_seasons, metric)
        )

    run = RunLog(
        run_id=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        model=MODEL_NAME,
        model_version=f"{MODEL_NAME}-{MODEL_VERSION_MAJOR_MINOR}",
        created_at=datetime.now(UTC).isoformat(),
        git_sha=_git("rev-parse", "--short", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        seed=seed,
        python=sys.version.split()[0],
        platform=platform.platform(),
        data_contract_hashes=_contract_hashes(paths),
        metrics={r.metric: asdict(r) for r in results},
        selection=selection_rows,
    )
    return run, results


def write_run(run: RunLog, paths: DataPaths) -> Path:
    directory = paths.root / "services" / "ml" / "runs" / run.model
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run.run_id}_{run.git_sha}.json"
    path.write_text(run.to_json(), encoding="utf-8")
    return path


def latest_run(paths: DataPaths, model: str = MODEL_NAME) -> dict[str, Any] | None:
    directory = paths.root / "services" / "ml" / "runs" / model
    runs = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if not runs:
        return None
    return json.loads(runs[-1].read_text(encoding="utf-8"))


def compare_to_committed(results: list[MetricResult], committed: dict[str, Any]) -> list[str]:
    """Differences between a fresh fit and the committed run log."""
    problems: list[str] = []

    for result in results:
        previous = committed.get("metrics", {}).get(result.metric)
        if previous is None:
            problems.append(f"{result.metric}: absent from the committed run log")
            continue

        for field_name in ("beta", "mae", "residual_sd", "persistence_r2"):
            was = float(previous[field_name])
            now = float(getattr(result, field_name))
            if abs(was - now) > VERIFY_TOLERANCE:
                problems.append(f"{result.metric}.{field_name}: {was:.8f} -> {now:.8f}")

        if int(previous["n_pairs"]) != result.n_pairs:
            problems.append(f"{result.metric}.n_pairs: {previous['n_pairs']} -> {result.n_pairs}")

    return problems


def _contract_hashes(paths: DataPaths) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if paths.contracts.is_dir():
        for sidecar in sorted(paths.contracts.glob("*.json")):
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            hashes[sidecar.stem] = payload.get("content_hash", "")
    return hashes


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"

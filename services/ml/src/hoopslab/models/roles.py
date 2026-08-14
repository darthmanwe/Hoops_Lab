"""Fit the archetype and shooting models and produce their serving tables.

Kept separate from the translation model because these answer a different
question — how a player plays, rather than how his production travels — and
because they are descriptive rather than predictive. Nothing here is claimed to
forecast anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from hoopslab.config import SEED
from hoopslab.models import archetypes, shooting

log = logging.getLogger(__name__)

MODEL_NAME = "roles"
MODEL_VERSION = "roles-v1.0"

#: Chosen deliberately, and the reasoning is on the record.
#:
#: Out-of-sample held-out log-likelihood improves monotonically with k but
#: almost flattens after 5 (-6.428 at k=5 against -6.401 at k=10), while
#: bootstrap stability falls off a cliff: mean Jaccard 0.52 at k=5 against 0.40
#: at k=6. Where the criteria disagree the smaller k wins, so k=5.
ARCHETYPE_K = 5

#: Stability below this is reported as "do not read this cluster as a type".
#: The clusters here average ~0.52, which is moderate — real structure, but not
#: the crisp taxonomy a labelled diagram would imply.
STABILITY_FLOOR = 0.45


@dataclass
class RolesResult:
    assignments: pl.DataFrame
    neighbours: pl.DataFrame
    cluster_descriptions: pl.DataFrame
    shooting: pl.DataFrame
    explained_variance: float
    stability: dict[int, float] = field(default_factory=dict)
    k_selection: dict[int, float] = field(default_factory=dict)

    @property
    def mean_stability(self) -> float:
        return float(np.mean(list(self.stability.values()))) if self.stability else 0.0

    def render(self) -> str:
        lines = [
            f"{MODEL_VERSION}",
            f"  archetypes         k={ARCHETYPE_K}, {self.assignments.height:,} player-seasons",
            f"  variance explained {self.explained_variance:.1%} (PCA before clustering)",
            f"  mean stability     {self.mean_stability:.3f} Jaccard under bootstrap",
        ]
        unstable = [c for c, v in self.stability.items() if v < STABILITY_FLOOR]
        if unstable:
            lines.append(
                f"  clusters below {STABILITY_FLOOR}: {sorted(unstable)} "
                "- report these as unclassified rather than as types"
            )
        lines.append(f"  neighbours         {self.neighbours.height:,} precomputed comparables")
        lines.append(f"  shooting           {self.shooting.height:,} shrunk 3PT rows")
        return "\n".join(lines)


def fit_roles(player_seasons: pl.DataFrame, *, seed: int = SEED) -> RolesResult:
    frame = archetypes.build_feature_frame(player_seasons)
    if frame.height < 1000:
        raise ValueError(
            f"only {frame.height} qualified player-seasons for archetypes; "
            "clustering this sample would not be meaningful"
        )

    k_selection = archetypes.out_of_sample_log_likelihood(frame, seed=seed)
    labels, coordinates, explained = archetypes.fit(frame, k=ARCHETYPE_K, seed=seed)
    stability = archetypes.cluster_stability(frame, k=ARCHETYPE_K, seed=seed, n_boot=12)

    assignments = frame.select("season_id", "person_id", "league").with_columns(
        pl.Series("cluster", labels.astype(int)),
        pl.lit(MODEL_VERSION).alias("model_version"),
    )

    return RolesResult(
        assignments=assignments,
        neighbours=archetypes.nearest_neighbours(frame, coordinates),
        cluster_descriptions=archetypes.describe_clusters(frame, labels, stability),
        shooting=shooting.shrink_three_point(player_seasons),
        explained_variance=explained,
        stability={int(k): float(v) for k, v in stability.items()},
        k_selection={int(k): float(v) for k, v in k_selection.items()},
    )


def to_run_payload(result: RolesResult) -> dict[str, Any]:
    """Summary written into the run log, so the choices stay auditable."""
    return {
        "model_version": MODEL_VERSION,
        "k": ARCHETYPE_K,
        "explained_variance": round(result.explained_variance, 4),
        "mean_stability": round(result.mean_stability, 4),
        "stability_per_cluster": {str(k): round(v, 4) for k, v in result.stability.items()},
        "k_selection_log_likelihood": {str(k): round(v, 4) for k, v in result.k_selection.items()},
        "n_assignments": result.assignments.height,
        "n_neighbours": result.neighbours.height,
        "n_shooting_rows": result.shooting.height,
    }

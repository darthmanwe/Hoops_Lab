"""Player archetypes from role statistics, with published cluster stability.

Replaces a hand-written five-element vector that the previous version called an
"archetype vector" and ran cosine similarity over inside the Worker.

Two preprocessing decisions carry most of the weight, and both are the kind of
thing that quietly ruins a clustering:

**Shot mix is compositional data.** The shares of two-point attempts,
three-point attempts and free throws sum to one, so they live on a simplex
where Euclidean distance and PCA are not meaningful — raising one share
mechanically lowers the others, and a method assuming independent dimensions
reads that constraint as structure. A centred log-ratio transform maps them
into a space where those operations are defined.

**Standardisation is within-season.** Three-point rate in 2000-01 and in
2024-25 describe materially different sports. Pooled, the strongest cluster any
method finds is "which era is this" — true, and useless.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import polars as pl

log = logging.getLogger(__name__)

#: Role features. Deliberately excludes raw volume: an archetype is *how* a
#: player plays, not how good or how heavily used, and including totals would
#: mostly recover minutes played.
ROLE_FEATURES = ("usg_pct", "ts_pct", "ast_pct", "tov_rate", "ast_per_75", "reb_per_75")

#: The compositional block: shares of shooting possessions by type.
SHOT_MIX_FEATURES = ("share_2pa", "share_3pa", "share_fta")

#: Small additive count so a player who never attempted a three has a defined
#: log-ratio. Applied uniformly, shifting everyone equally rather than
#: singling out the zeros.
CLR_PSEUDOCOUNT = 0.005

MIN_MINUTES_ARCHETYPE = 500
PCA_VARIANCE_TARGET = 0.90


@dataclass
class ArchetypeModel:
    k: int
    feature_names: list[str]
    explained_variance: float
    stability: dict[int, float] = field(default_factory=dict)
    out_of_sample_log_likelihood: dict[int, float] = field(default_factory=dict)


def build_feature_frame(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Role features plus the compositional shot mix, for qualified seasons."""
    return (
        player_seasons.with_columns((pl.col("fga") - pl.col("fg3a")).alias("_fg2a"))
        .with_columns(
            (pl.col("_fg2a") + pl.col("fg3a") + 0.44 * pl.col("fta")).alias("_shooting_poss")
        )
        .filter(
            (pl.col("minutes") >= MIN_MINUTES_ARCHETYPE)
            & (pl.col("_shooting_poss") > 0)
            & pl.col("person_id").is_not_null()
            & pl.all_horizontal([pl.col(f).is_not_null() for f in ROLE_FEATURES])
        )
        .with_columns(
            (pl.col("_fg2a") / pl.col("_shooting_poss")).alias("share_2pa"),
            (pl.col("fg3a") / pl.col("_shooting_poss")).alias("share_3pa"),
            (0.44 * pl.col("fta") / pl.col("_shooting_poss")).alias("share_fta"),
        )
        .select(
            "person_id",
            "season_id",
            "league",
            "season_order",
            "player_name",
            "minutes",
            *ROLE_FEATURES,
            *SHOT_MIX_FEATURES,
        )
    )


def clr_transform(shares: np.ndarray, pseudocount: float = CLR_PSEUDOCOUNT) -> np.ndarray:
    """Centred log-ratio, mapping a simplex into ordinary Euclidean space.

    Without this, "took more threes" and "took fewer twos" are the same
    direction by construction, and any distance or component built on the raw
    shares measures that constraint rather than the player.
    """
    padded = shares + pseudocount
    padded = padded / padded.sum(axis=1, keepdims=True)
    log_shares = np.log(padded)
    return log_shares - log_shares.mean(axis=1, keepdims=True)


def standardize_within_season(frame: pl.DataFrame, columns: list[str]) -> np.ndarray:
    """Z-score each feature within its own league-season."""
    out = np.zeros((frame.height, len(columns)))
    seasons = frame["season_id"].to_numpy()

    for index, column in enumerate(columns):
        values = frame[column].to_numpy().astype(float)
        standardized = np.zeros_like(values)

        for season in np.unique(seasons):
            mask = seasons == season
            block = values[mask]
            spread = block.std()
            standardized[mask] = (block - block.mean()) / spread if spread > 0 else 0.0

        out[:, index] = standardized

    return out


def design_matrix(frame: pl.DataFrame) -> tuple[np.ndarray, list[str]]:
    role = standardize_within_season(frame, list(ROLE_FEATURES))

    shares = np.column_stack([frame[c].to_numpy().astype(float) for c in SHOT_MIX_FEATURES])
    clr = clr_transform(shares)
    clr_columns = [f"_clr_{i}" for i in range(clr.shape[1])]
    clr_frame = frame.with_columns(
        [pl.Series(name, clr[:, i]) for i, name in enumerate(clr_columns)]
    )
    clr_standardized = standardize_within_season(clr_frame, clr_columns)

    names = [*ROLE_FEATURES, *(f"clr_{c}" for c in SHOT_MIX_FEATURES)]
    return np.column_stack([role, clr_standardized]), names


def fit(frame: pl.DataFrame, *, k: int, seed: int) -> tuple[np.ndarray, np.ndarray, float]:
    """PCA to a variance target, then a full-covariance Gaussian mixture.

    A mixture rather than k-means because archetypes genuinely overlap: a
    stretch big is partly a big and partly a shooter, and that soft membership
    is the informative output.

    Returns ``(hard labels, whitened coordinates, explained variance)``.
    """
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    design, _ = design_matrix(frame)
    scales = design.std(axis=0)
    scales[scales == 0] = 1.0
    scaled = (design - design.mean(axis=0)) / scales

    pca = PCA(n_components=PCA_VARIANCE_TARGET, random_state=seed)
    reduced = pca.fit_transform(scaled)

    mixture = GaussianMixture(n_components=k, covariance_type="full", random_state=seed, n_init=5)
    labels = mixture.fit_predict(reduced)

    return labels, reduced, float(pca.explained_variance_ratio_.sum())


def out_of_sample_log_likelihood(
    frame: pl.DataFrame, *, seed: int, candidates: range = range(3, 11)
) -> dict[int, float]:
    """Fit on earlier seasons, score held-out later ones.

    Genuinely out-of-sample model selection, rather than the in-sample BIC that
    almost every published version of this analysis uses — which rewards
    complexity on the same rows it was fitted to.
    """
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture

    split = int(np.quantile(frame["season_order"].to_numpy(), 0.75))
    train = frame.filter(pl.col("season_order") <= split)
    test = frame.filter(pl.col("season_order") > split)
    if train.height < 500 or test.height < 100:
        return {}

    design_train, _ = design_matrix(train)
    design_test, _ = design_matrix(test)
    means, scales = design_train.mean(axis=0), design_train.std(axis=0)
    scales[scales == 0] = 1.0

    pca = PCA(n_components=PCA_VARIANCE_TARGET, random_state=seed)
    reduced_train = pca.fit_transform((design_train - means) / scales)
    reduced_test = pca.transform((design_test - means) / scales)

    scores: dict[int, float] = {}
    for k in candidates:
        mixture = GaussianMixture(
            n_components=k, covariance_type="full", random_state=seed, n_init=3
        )
        mixture.fit(reduced_train)
        scores[k] = float(mixture.score(reduced_test))

    return scores


def cluster_stability(
    frame: pl.DataFrame, *, k: int, seed: int, n_boot: int = 30
) -> dict[int, float]:
    """Per-cluster Jaccard stability under bootstrap resampling.

    Published per cluster, including the unstable ones. Rim-running centres
    hold together; a "combo forward" bucket usually does not, and a reader
    deserves to know which of the labels shown to them means anything.
    """
    rng = np.random.default_rng(seed)
    reference_labels, _, _ = fit(frame, k=k, seed=seed)
    reference_sets = {c: set(np.flatnonzero(reference_labels == c).tolist()) for c in range(k)}
    scores: dict[int, list[float]] = {c: [] for c in range(k)}

    for _ in range(n_boot):
        sample = rng.choice(frame.height, size=frame.height, replace=True)
        try:
            labels, _, _ = fit(frame[sample.tolist()], k=k, seed=seed)
        except (ValueError, np.linalg.LinAlgError):
            continue

        boot_sets = [
            {int(sample[i]) for i in np.flatnonzero(labels == c).tolist()} for c in range(k)
        ]

        for cluster, reference in reference_sets.items():
            if not reference:
                continue
            scores[cluster].append(
                max(
                    len(reference & b) / len(reference | b) if (reference | b) else 0.0
                    for b in boot_sets
                )
            )

    return {c: float(np.mean(v)) if v else 0.0 for c, v in scores.items()}


def describe_clusters(
    frame: pl.DataFrame, labels: np.ndarray, stability: dict[int, float]
) -> pl.DataFrame:
    """Distinguishing features and exemplar players for each cluster.

    Cluster indices are arbitrary and shuffle between runs, so a name generated
    at runtime would differ every time it was produced. The description is
    derived from the data instead; any human-readable name belongs in a
    committed mapping checked against these centroids.
    """
    design, names = design_matrix(frame)
    labelled = frame.with_columns(pl.Series("cluster", labels))
    overall = design.mean(axis=0)

    rows = []
    for cluster in sorted({int(c) for c in labels.tolist()}):
        mask = labels == cluster
        deviation = design[mask].mean(axis=0) - overall
        order = np.argsort(-np.abs(deviation))[:4]

        exemplars = (
            labelled.filter(pl.col("cluster") == cluster)
            .sort("minutes", descending=True)
            .head(5)["player_name"]
            .to_list()
        )

        rows.append(
            {
                "cluster": cluster,
                "n_members": int(mask.sum()),
                "top_features": ", ".join(
                    f"{names[i]}{'+' if deviation[i] > 0 else '-'}{abs(deviation[i]):.2f}"
                    for i in order
                ),
                "exemplars": ", ".join(str(e) for e in exemplars if e),
                "stability_jaccard": round(stability.get(cluster, 0.0), 3),
            }
        )

    return pl.DataFrame(rows)


def nearest_neighbours(
    frame: pl.DataFrame, coordinates: np.ndarray, *, top_k: int = 10
) -> pl.DataFrame:
    """Precomputed comparables in the reduced archetype space.

    Computed here rather than in the Worker. The previous version scanned a
    whole season table and ran cosine similarity per request, inside a runtime
    capped at 10 ms of CPU — survivable against four hardcoded players,
    impossible against six hundred real ones. Euclidean distance in the whitened
    space is also the right metric; cosine on a simplex was not.
    """
    from sklearn.neighbors import NearestNeighbors

    # Compare within a season, so a comparable is a contemporary rather than
    # someone playing a different sport twenty years earlier.
    rows = []
    for season in frame["season_id"].unique().to_list():
        mask = (frame["season_id"] == season).to_numpy()
        block = frame.filter(pl.col("season_id") == season)
        if block.height < 3:
            continue

        coords = coordinates[mask]
        neighbours = min(top_k + 1, block.height)
        finder = NearestNeighbors(n_neighbors=neighbours).fit(coords)
        distances, indices = finder.kneighbors(coords)

        persons = block["person_id"].to_list()
        for i, person in enumerate(persons):
            for rank, (distance, j) in enumerate(zip(distances[i], indices[i], strict=True)):
                if int(j) == i:
                    continue  # a player is not his own comparable
                rows.append(
                    {
                        "season_id": season,
                        "person_id": person,
                        "rank": rank,
                        "neighbour_person_id": persons[int(j)],
                        "distance": round(float(distance), 5),
                    }
                )

    return pl.DataFrame(rows) if rows else pl.DataFrame()

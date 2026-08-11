"""Build the SQL artefact that loads D1.

Only aggregates go to D1. Raw event data stays in parquet: the free tier caps a
database at 500 MB and row writes at 100,000 a day, so loading three million
shot records would take a month and not fit when it arrived.

Every model-derived row carries a ``model_version`` that resolves in
``model_versions``, so any number the API serves can be traced to the run that
produced it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from hoopslab.features.translation import (
    TARGET_METRICS,
    attach_moments,
    build_persistence_frame,
    build_transition_frame,
    league_season_moments,
)
from hoopslab.models import baselines
from hoopslab.models.train import MODEL_NAME, latest_run
from hoopslab.models.translation import fit_persistence, fit_translation
from hoopslab.paths import DataPaths
from hoopslab.seasons import Season
from hoopslab.serve import sql

log = logging.getLogger(__name__)

TABLES_IN_LOAD_ORDER = (
    "data_snapshots",
    "seasons",
    "persons",
    "player_identities",
    "player_seasons",
    "model_versions",
    "translation_predictions",
    "model_evaluations",
    "selection_summaries",
)


@dataclass
class ExportResult:
    snapshot_id: str
    path: Path
    row_counts: dict[str, int]

    def render(self) -> str:
        lines = [f"snapshot {self.snapshot_id}", f"wrote {self.path.name}"]
        lines.extend(f"  {t:<26} {n:>7,} rows" for t, n in self.row_counts.items())
        lines.append(f"  {'TOTAL':<26} {sum(self.row_counts.values()):>7,} rows")
        return "\n".join(lines)


def snapshot_id(paths: DataPaths) -> str:
    """Identifier derived from the committed contract hashes.

    Deterministic on the data rather than on the clock, so rebuilding
    unchanged data yields the same id and every cache key stays valid.
    """
    digest = hashlib.sha256()
    for sidecar in sorted(paths.contracts.glob("*.json")):
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        digest.update(payload.get("content_hash", "").encode("ascii"))
    return digest.hexdigest()[:12]


def build_export(paths: DataPaths) -> ExportResult:
    player_seasons = pl.read_parquet(paths.gold / "player_seasons.parquet")
    persons = pl.read_parquet(paths.gold / "persons.parquet")
    identities = pl.read_parquet(paths.gold / "player_identities.parquet")
    pairs = pl.read_parquet(paths.gold / "transition_pairs.parquet")

    run = latest_run(paths)
    if run is None:
        raise FileNotFoundError("No committed run log. Run `hoopslab train` first.")

    snapshot = snapshot_id(paths)
    statements: list[str] = [f"DELETE FROM {t};" for t in reversed(TABLES_IN_LOAD_ORDER)]
    counts: dict[str, int] = {}

    def emit(table: str, columns: list[str], rows: list[list[Any]]) -> None:
        counts[table] = len(rows)
        statements.extend(sql.insert_many(table, columns, rows))

    emit(
        "data_snapshots",
        [
            "snapshot_id",
            "built_at",
            "git_sha",
            "n_player_seasons",
            "n_persons",
            "n_transition_pairs",
        ],
        [
            [
                snapshot,
                datetime.now(UTC).isoformat(),
                run["git_sha"],
                player_seasons.height,
                persons.height,
                pairs.height,
            ]
        ],
    )

    emit("seasons", *_season_rows(player_seasons))
    emit("persons", *_person_rows(persons))
    emit("player_identities", *_identity_rows(identities))
    emit("player_seasons", *_player_season_rows(player_seasons, snapshot))

    model_rows, prediction_rows, evaluation_rows, selection_rows = _model_rows(
        player_seasons, pairs, run
    )
    emit("model_versions", *model_rows)
    emit("translation_predictions", *prediction_rows)
    emit("model_evaluations", *evaluation_rows)
    emit("selection_summaries", *selection_rows)

    out_dir = paths.data / "d1"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "load.sql"
    path.write_text(sql.transaction(statements), encoding="utf-8")

    return ExportResult(snapshot_id=snapshot, path=path, row_counts=counts)


def _season_rows(player_seasons: pl.DataFrame) -> tuple[list[str], list[list[Any]]]:
    rows = []
    for record in (
        player_seasons.select("season_id", "league", "start_year", "season_order")
        .unique()
        .sort("season_order")
        .iter_rows(named=True)
    ):
        season = Season.parse(record["season_id"])
        rows.append(
            [
                record["season_id"],
                record["league"],
                int(record["start_year"]),
                int(record["season_order"]),
                season.label,
            ]
        )
    return ["season_id", "league", "start_year", "season_order", "label"], rows


def _person_rows(persons: pl.DataFrame) -> tuple[list[str], list[list[Any]]]:
    from hoopslab.transform.names import normalize_name

    rows = [
        [
            r["person_id"],
            r["display_name"],
            normalize_name(r["display_name"]) if r["display_name"] else None,
            int(r["birth_year"]) if r["birth_year"] is not None else None,
            r["leagues"],
        ]
        for r in persons.iter_rows(named=True)
    ]
    return ["person_id", "display_name", "name_normalized", "birth_year", "leagues"], rows


def _identity_rows(identities: pl.DataFrame) -> tuple[list[str], list[list[Any]]]:
    rows = [
        [r["league"], r["source_player_id"], r["person_id"], r["match_method"], r["confidence"]]
        for r in identities.iter_rows(named=True)
    ]
    return ["league", "source_player_id", "person_id", "match_method", "confidence"], rows


def _player_season_rows(
    player_seasons: pl.DataFrame, snapshot: str
) -> tuple[list[str], list[list[Any]]]:
    columns = [
        "season_id",
        "person_id",
        "league",
        "team_name",
        "games_played",
        "minutes",
        "usg_pct",
        "ts_pct",
        "ast_pct",
        "tov_rate",
        "fg3a_rate",
        "pts_per_75",
        "ast_per_75",
        "reb_per_75",
        "age",
        "qualified",
        "snapshot_id",
    ]
    rows = [
        [
            r["season_id"],
            r["person_id"],
            r["league"],
            r["team_name"],
            _int(r["gp"]),
            _round(r["minutes"], 1),
            _round(r["usg_pct"], 5),
            _round(r["ts_pct"], 5),
            _round(r["ast_pct"], 5),
            _round(r["tov_rate"], 5),
            _round(r["fg3a_rate"], 5),
            _round(r["pts_per_75"], 3),
            _round(r["ast_per_75"], 3),
            _round(r["reb_per_75"], 3),
            _round(r["age"], 1),
            bool(r["qualified"]),
            snapshot,
        ]
        for r in player_seasons.iter_rows(named=True)
        if r["person_id"] is not None
    ]
    return columns, rows


def _model_rows(
    player_seasons: pl.DataFrame,
    pairs: pl.DataFrame,
    run: dict[str, Any],
) -> tuple[tuple[list[str], list[list[Any]]], ...]:
    """Refit and score every observed transition, so predictions carry intervals."""
    model_version = run["model_version"]

    version_rows: list[list[Any]] = []
    prediction_rows: list[list[Any]] = []
    evaluation_rows: list[list[Any]] = []

    headline = run["metrics"]["usg_pct"]
    version_rows.append(
        [
            model_version,
            MODEL_NAME,
            run["created_at"],
            run["git_sha"],
            run["run_id"],
            run["seed"],
            "mae_usg_pct",
            headline["mae"],
            headline["mae_ci"][0],
            headline["mae_ci"][1],
            headline["n_pairs"],
            headline["n_evaluated"],
            "services/ml/src/hoopslab/configs/model_cards/translation.md",
        ]
    )

    for metric in TARGET_METRICS:
        moments = league_season_moments(player_seasons, metric)
        transitions = attach_moments(
            build_transition_frame(pairs, player_seasons, metric), moments, "target_season_id"
        ).filter(pl.col("target_sd").is_not_null() & (pl.col("target_sd") > 0))

        persistence = fit_persistence(build_persistence_frame(player_seasons, metric), metric)
        model = fit_translation(transitions, persistence, metric)

        predicted = model.predict_rate(transitions)
        pi80 = model.prediction_interval(transitions, level=0.80)
        pi95 = model.prediction_interval(transitions, level=0.95)

        league_mean = baselines.target_league_mean(transitions).predictions
        z_preserve = baselines.z_preservation(transitions).predictions
        folk = baselines.folk_rule(transitions).predictions

        for i, record in enumerate(transitions.iter_rows(named=True)):
            prediction_rows.append(
                [
                    record["person_id"],
                    record["source_season_id"],
                    record["target_season_id"],
                    record["direction"],
                    metric,
                    _round(record["source_value"], 5),
                    _round(float(predicted[i]), 5),
                    _round(float(pi80[i, 0]), 5),
                    _round(float(pi80[i, 1]), 5),
                    _round(float(pi95[i, 0]), 5),
                    _round(float(pi95[i, 1]), 5),
                    _round(record["target_value"], 5),
                    _round(float(league_mean[i]), 5),
                    _round(float(z_preserve[i]), 5),
                    _round(float(folk[i]), 5),
                    model_version,
                ]
            )

        metrics = run["metrics"][metric]
        _, best_mae = min(metrics["baseline_mae"].items(), key=lambda kv: kv[1])
        beats = metrics["mae"] < best_mae
        skill = (best_mae - metrics["mae"]) / best_mae if best_mae else 0.0

        for baseline_name, baseline_mae in metrics["baseline_mae"].items():
            evaluation_rows.append(
                [
                    model_version,
                    metric,
                    "overall",
                    metrics["n_evaluated"],
                    metrics["mae"],
                    metrics["mae_ci"][0],
                    metrics["mae_ci"][1],
                    baseline_name,
                    baseline_mae,
                    metrics["shuffled_mae"],
                    beats,
                    _round(skill, 4),
                ]
            )

    selection_rows = [
        [
            model_version,
            s["direction"],
            s["metric"],
            s["n_movers"],
            s["n_league"],
            _round(s["mover_mean_z"], 4),
            _round(s["league_mean_z"], 4),
            _round(s["gap_sd"], 4),
        ]
        for s in run["selection"]
    ]

    return (
        (
            [
                "model_version",
                "model_name",
                "trained_at",
                "git_sha",
                "run_id",
                "seed",
                "primary_metric",
                "primary_value",
                "primary_ci_low",
                "primary_ci_high",
                "n_train",
                "n_evaluated",
                "card_path",
            ],
            version_rows,
        ),
        (
            [
                "person_id",
                "source_season_id",
                "target_season_id",
                "direction",
                "metric",
                "source_value",
                "predicted",
                "pi80_low",
                "pi80_high",
                "pi95_low",
                "pi95_high",
                "actual_value",
                "baseline_league_mean",
                "baseline_z_preservation",
                "baseline_folk_rule",
                "model_version",
            ],
            prediction_rows,
        ),
        (
            [
                "model_version",
                "metric",
                "fold",
                "n_evaluated",
                "mae",
                "mae_ci_low",
                "mae_ci_high",
                "baseline_name",
                "baseline_mae",
                "shuffled_mae",
                "beats_best_baseline",
                "skill_vs_best",
            ],
            evaluation_rows,
        ),
        (
            [
                "model_version",
                "direction",
                "metric",
                "n_movers",
                "n_league",
                "mover_mean_z",
                "league_mean_z",
                "gap_sd",
            ],
            selection_rows,
        ),
    )


def _round(value: Any, places: int) -> float | None:
    """Round once, here, so the Worker never has to.

    Every number is rounded at export rather than at display, which removes a
    class of train/serve mismatch where two callers disagree about a value.
    """
    if value is None:
        return None
    number = float(value)
    if np.isnan(number) or np.isinf(number):
        return None
    return round(number, places)


def _int(value: Any) -> int | None:
    if value is None:
        return None
    number = float(value)
    return None if np.isnan(number) else int(number)


#: People guaranteed to be in the test fixture. Each covers a case that has
#: broken before: a cross-league transition, and a display name carrying
#: diacritics that no user will type.
#:
#: Matched on the *normalised* name rather than the literal string. Spelling
#: these by hand is exactly the mistake the names module exists to prevent —
#: an earlier version of this list said "Luka Doncic" while the feed says
#: "Luka Dončić", so the anchor silently matched nobody.
FIXTURE_ANCHOR_NAMES = (
    "vasilije micic",
    "facundo campazzo",
    "nicolo melli",
    "luka doncic",
)


def build_fixture(paths: DataPaths, out_path: Path, *, n_persons: int = 60) -> dict[str, int]:
    """A small, deterministic slice of the real export, for Worker tests.

    Derived from real data rather than hand-typed. Hand-written fixtures encode
    the author's assumptions about the data; a real slice encodes the data, and
    the previous version of this project is a long argument for the difference.
    """
    player_seasons = pl.read_parquet(paths.gold / "player_seasons.parquet")
    persons = pl.read_parquet(paths.gold / "persons.parquet")
    identities = pl.read_parquet(paths.gold / "player_identities.parquet")
    pairs = pl.read_parquet(paths.gold / "transition_pairs.parquet")

    run = latest_run(paths)
    if run is None:
        raise FileNotFoundError("No committed run log. Run `hoopslab train` first.")

    # Anchor on people with real transitions, then top up deterministically.
    from hoopslab.transform.names import normalize_name

    anchor_ids = (
        persons.filter(pl.col("display_name").is_not_null())
        .with_columns(
            pl.col("display_name")
            .map_elements(normalize_name, return_dtype=pl.Utf8)
            .alias("_normalized")
        )
        .filter(pl.col("_normalized").is_in(list(FIXTURE_ANCHOR_NAMES)))["person_id"]
        .to_list()
    )
    if len(anchor_ids) < len(FIXTURE_ANCHOR_NAMES):
        raise ValueError(
            f"Only {len(anchor_ids)} of {len(FIXTURE_ANCHOR_NAMES)} fixture anchors resolved. "
            "The fixture must contain them, or the tests that rely on them pass vacuously."
        )
    transition_ids = pairs["person_id"].unique().sort().to_list()
    chosen = list(dict.fromkeys([*anchor_ids, *transition_ids]))[:n_persons]

    persons_slice = persons.filter(pl.col("person_id").is_in(chosen))
    seasons_slice = player_seasons.filter(pl.col("person_id").is_in(chosen))
    identities_slice = identities.filter(pl.col("person_id").is_in(chosen))
    pairs_slice = pairs.filter(pl.col("person_id").is_in(chosen))

    snapshot = "fixture01"
    statements: list[str] = [f"DELETE FROM {t};" for t in reversed(TABLES_IN_LOAD_ORDER)]
    counts: dict[str, int] = {}

    def emit(table: str, columns: list[str], rows: list[list[Any]]) -> None:
        counts[table] = len(rows)
        statements.extend(sql.insert_many(table, columns, rows))

    emit(
        "data_snapshots",
        [
            "snapshot_id",
            "built_at",
            "git_sha",
            "n_player_seasons",
            "n_persons",
            "n_transition_pairs",
        ],
        [
            [
                snapshot,
                "2026-01-01T00:00:00Z",
                "fixture",
                seasons_slice.height,
                persons_slice.height,
                pairs_slice.height,
            ]
        ],
    )
    emit("seasons", *_season_rows(seasons_slice))
    emit("persons", *_person_rows(persons_slice))
    emit("player_identities", *_identity_rows(identities_slice))
    emit("player_seasons", *_player_season_rows(seasons_slice, snapshot))

    model_rows, prediction_rows, evaluation_rows, selection_rows = _model_rows(
        player_seasons, pairs_slice, run
    )
    emit("model_versions", *model_rows)
    emit("translation_predictions", *prediction_rows)
    emit("model_evaluations", *evaluation_rows)
    emit("selection_summaries", *selection_rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql.transaction(statements), encoding="utf-8")
    return counts

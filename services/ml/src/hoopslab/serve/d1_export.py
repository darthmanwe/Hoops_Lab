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
from dataclasses import dataclass, field
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
from hoopslab.models.roles import MODEL_VERSION as ROLES_VERSION
from hoopslab.models.roles import STABILITY_FLOOR, RolesResult, fit_roles
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
    "player_archetypes",
    "archetype_definitions",
    "player_comps",
    "player_shooting",
    "player_reports",
    "hypothetical_projections",
)


#: D1's free plan allows this many row writes per day. The demo slice exists to
#: fit under it, and `hoopslab export --demo` refuses to write a file that
#: cannot be loaded in one sitting.
D1_FREE_DAILY_WRITES = 100_000


@dataclass
class ExportResult:
    snapshot_id: str
    path: Path
    row_counts: dict[str, int]
    #: Rows a filter removed, per table. Empty for a full export.
    #:
    #: ADR 8 requires a filter to report what it dropped rather than leave it
    #: to be discovered. That rule was written after a null age silently
    #: removed 22% of the modelling cohort, and it has stood as *proposed* ever
    #: since because nothing enforced it. This is the first filter to comply.
    dropped: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.row_counts.values())

    def render(self) -> str:
        lines = [f"snapshot {self.snapshot_id}", f"wrote {self.path.name}"]
        for table, n in self.row_counts.items():
            lost = self.dropped.get(table, 0)
            suffix = f"   ({lost:,} dropped)" if lost else ""
            lines.append(f"  {table:<26} {n:>7,} rows{suffix}")
        lines.append(f"  {'TOTAL':<26} {self.total:>7,} rows")
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


#: Seasons kept for browsing in the hosted demo. The model cohort is kept in
#: full regardless of age, so this only trims the tail nobody clicks.
DEMO_RECENT_SEASON = 2022

#: Comparables per player-season in the demo. The full export stores every
#: neighbour the archetype model found; the interface shows six.
DEMO_COMPS_PER_SEASON = 6


@dataclass
class DemoSlice:
    """Which rows a free-tier deployment serves.

    D1's free plan allows 100,000 row writes per day and the full export is
    199,439, so a hosted demo has to choose. The choice is made here rather
    than by truncating the load file, because *which* rows go is the whole
    question: a slice that drops Doncic's 2017 EuroLeague season breaks the
    example on the front page, and a slice built by taking recent seasons does
    exactly that.

    So the rule is cohort-first. Every person involved in an observed transfer
    is kept with their **entire** career, because they are what the model is
    about and what every worked example on the site points at. Recent seasons
    are kept on top of that so the projections and browsing are current.
    Comparables, which are the only table large enough to matter and the least
    load-bearing, are capped at what the interface actually displays.

    Applied to emitted rows, never to the frames the models are fitted on.
    Filtering the inputs would refit the archetype mixture on a subset and
    serve clusters that disagree with the published stability figures — a
    hosted demo that quietly contradicts its own model card.
    """

    persons: set[str]
    season_orders: dict[str, int]
    recent_season: int = DEMO_RECENT_SEASON
    comps_per_season: int = DEMO_COMPS_PER_SEASON

    @classmethod
    def build(
        cls,
        player_seasons: pl.DataFrame,
        pairs: pl.DataFrame,
        *,
        recent_season: int = DEMO_RECENT_SEASON,
    ) -> DemoSlice:
        cohort = set(pairs["person_id"].to_list())
        recent = set(
            player_seasons.filter(pl.col("season_order") >= recent_season)["person_id"].to_list()
        )
        orders = dict(player_seasons.select("season_id", "season_order").unique().iter_rows())
        return cls(
            persons=cohort | (recent - {None}),
            season_orders={str(k): int(v) for k, v in orders.items() if k is not None},
            recent_season=recent_season,
        )

    def is_recent(self, season_id: Any) -> bool:
        return self.season_orders.get(str(season_id), 0) >= self.recent_season

    def keep(self, table: str, columns: list[str], rows: list[list[Any]]) -> list[list[Any]]:
        """Filter one table's rows. Unlisted tables are served whole."""
        index = {name: i for i, name in enumerate(columns)}

        def person_of(row: list[Any]) -> Any:
            return row[index["person_id"]] if "person_id" in index else None

        if table in {
            "persons",
            "player_identities",
            "player_seasons",
            "player_archetypes",
            "player_shooting",
            "player_reports",
            "hypothetical_projections",
        }:
            rows = [r for r in rows if person_of(r) in self.persons]

        # Hypothetical projections are ranked by a season the interface already
        # filters to recent by default; older source lines are never shown.
        if table == "hypothetical_projections" and "source_season_order" in index:
            rows = [r for r in rows if int(r[index["source_season_order"]]) >= self.recent_season]

        if table == "player_comps":
            rows = [r for r in rows if person_of(r) in self.persons]
            if "season_id" in index:
                rows = [r for r in rows if self.is_recent(r[index["season_id"]])]
            # Both ends, not just the subject. This removes nothing today:
            # comparables are nearest neighbours *within* a season, so the
            # season filter above already guarantees the neighbour is kept. It
            # is here because `neighbour_person_id` carries no foreign key, so
            # if either rule changes a stray neighbour would not fail the load
            # — it would render as a bare id where a name belongs, which is the
            # silent degradation this project keeps finding in its own output.
            if "neighbour_person_id" in index:
                rows = [r for r in rows if r[index["neighbour_person_id"]] in self.persons]
            if "rank" in index:
                rows = [r for r in rows if int(r[index["rank"]]) <= self.comps_per_season]

        return rows


def build_export(paths: DataPaths, *, demo: bool = False) -> ExportResult:
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

    demo_slice = DemoSlice.build(player_seasons, pairs) if demo else None

    dropped: dict[str, int] = {}

    def emit(table: str, columns: list[str], rows: list[list[Any]]) -> None:
        if demo_slice is not None:
            kept = demo_slice.keep(table, columns, rows)
            if len(kept) != len(rows):
                dropped[table] = len(rows) - len(kept)
            rows = kept
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

    roles = fit_roles(player_seasons)
    for table, columns, rows in _roles_rows(roles, persons):
        emit(table, columns, rows)

    emit("player_reports", *_report_rows(paths, snapshot))
    emit(
        "hypothetical_projections",
        *_hypothetical_rows(player_seasons, pairs, run["model_version"], snapshot),
    )

    out_dir = paths.data / "d1"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("load-demo.sql" if demo else "load.sql")
    path.write_text(sql.transaction(statements), encoding="utf-8")

    return ExportResult(snapshot_id=snapshot, path=path, row_counts=counts, dropped=dropped)


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

    # Roles are fitted on the whole population — clustering a 60-player slice
    # would be meaningless — then filtered to the fixture's people.
    roles = fit_roles(player_seasons)
    for table, columns, rows in _roles_rows(roles, persons_slice):
        emit(table, columns, rows)

    # Same reasoning: projected on the whole population, then narrowed. The
    # fixture must contain both supported and extrapolated rows, or the tests
    # that assert the flag is served would pass without ever seeing it set.
    hypo_columns, hypo_rows = _hypothetical_rows(
        player_seasons, pairs_slice, run["model_version"], snapshot
    )
    keep = set(persons_slice["person_id"].to_list())
    emit(
        "hypothetical_projections",
        hypo_columns,
        [row for row in hypo_rows if row[0] in keep],
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql.transaction(statements), encoding="utf-8")
    return counts


REPORT_COLUMNS = [
    "person_id",
    "target_season_id",
    "direction",
    "named",
    "headline",
    "claims",
    "evidence",
    "numbers_traced",
    "numbers_total",
    "grounded",
    "checks",
    "report_model",
    "generated_at",
    "snapshot_id",
]


def _report_rows(paths: DataPaths, snapshot: str) -> tuple[list[str], list[list[Any]]]:
    """Serving rows for whatever scouting reports have actually been generated.

    Empty until the response cache is populated, and empty is a correct answer:
    the API's report route returns a problem document explaining that no report
    exists for a player rather than inventing one. Nothing here can create a
    report — it only exports what a model already wrote.

    Each row carries its own audit. Serving the groundedness counts beside the
    prose is the only reason prose belongs in this API at all.
    """
    from hoopslab.llm.cache import ResponseCache
    from hoopslab.llm.evidence import BundleSource, build_bundle
    from hoopslab.llm.groundedness import check_report

    cache = ResponseCache(paths.llm_cache)
    entries = cache.entries()
    if not entries:
        log.info("no cached scouting reports; player_reports will be empty")
        return REPORT_COLUMNS, []

    source = BundleSource.load(paths)
    rows: list[list[Any]] = []

    for entry in entries:
        try:
            bundle = build_bundle(
                source,
                entry.person_id,
                entry.target_season_id,
                anonymized=entry.anonymized,
            )
        except KeyError:
            # The snapshot moved and this transition no longer scores. Dropping
            # the row is right: a report whose evidence cannot be rebuilt cannot
            # have its numbers checked, and an unauditable report is the one
            # thing this table must never contain.
            log.warning("dropping stale cached report for %s", entry.person_id)
            continue

        if bundle.digest() != entry.evidence_digest:
            log.warning(
                "dropping cached report for %s: the evidence changed since it was written",
                entry.person_id,
            )
            continue

        audit = check_report(entry.report, bundle)
        rows.append(
            [
                entry.person_id,
                entry.target_season_id,
                bundle.direction,
                not entry.anonymized,
                entry.report.headline,
                json.dumps(entry.report.model_dump(), separators=(",", ":"), ensure_ascii=False),
                bundle.render(),
                audit.n_traced,
                len(audit.tokens),
                audit.grounded,
                json.dumps(
                    [
                        {"name": c.name, "passed": c.passed, "detail": c.detail}
                        for c in audit.checks
                    ],
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
                entry.model,
                entry.created_at,
                snapshot,
            ]
        )

    return REPORT_COLUMNS, rows


HYPOTHETICAL_COLUMNS = [
    "person_id",
    "source_season_id",
    "source_season_order",
    "source_league",
    "target_season_id",
    "direction",
    "metric",
    "source_value",
    "z_source",
    "predicted",
    "pi80_low",
    "pi80_high",
    "pi95_low",
    "pi95_high",
    "in_support",
    "moved_before",
    "minutes",
    "age",
    #: How many observed transfers the direction's intercept was fitted from.
    #: Constant per direction and therefore redundant on every row, but it is
    #: the single number that decides how much weight a projection deserves,
    #: and serving it beside the estimate costs one integer.
    "support_n_movers",
    "model_version",
    "snapshot_id",
]


def _hypothetical_rows(
    player_seasons: pl.DataFrame,
    pairs: pl.DataFrame,
    model_version: str,
    snapshot: str,
) -> tuple[list[str], list[list[Any]]]:
    """Projections for players who have *not* made the move.

    Usage rate only. The rest of this export serves true shooting with a
    `beats_best_baseline: false` flag beside it, which works because an observed
    transition also carries what actually happened — a reader can see the miss.
    A hypothetical has no actual to check against, so a true-shooting number
    here would be an unfalsifiable figure on a metric already known to be worse
    than guessing the league average. It is omitted rather than flagged, and the
    interface says why.
    """
    from hoopslab.models.hypothetical import (
        PROJECTED_DIRECTIONS,
        latest_season_for,
        score_counterfactuals,
    )

    order = dict(player_seasons.select("season_id", "season_order").unique().iter_rows())
    rows: list[list[Any]] = []

    for direction in PROJECTED_DIRECTIONS:
        _, _, target_league = direction.partition("->")
        target_season_id = latest_season_for(player_seasons, target_league)

        frame = score_counterfactuals(
            player_seasons,
            pairs,
            direction=direction,
            target_season_id=target_season_id,
            metric="usg_pct",
        )
        if frame.is_empty():
            continue

        for r in frame.iter_rows(named=True):
            rows.append(
                [
                    r["person_id"],
                    r["source_season_id"],
                    int(order.get(r["source_season_id"], 0)),
                    r["source_league"],
                    r["target_season_id"],
                    direction,
                    "usg_pct",
                    _round(r["source_value"], 5),
                    _round(r["z_source"], 4),
                    _round(r["predicted"], 5),
                    _round(r["pi80_low"], 5),
                    _round(r["pi80_high"], 5),
                    _round(r["pi95_low"], 5),
                    _round(r["pi95_high"], 5),
                    bool(r["in_support"]),
                    bool(r["moved_before"]),
                    _round(r["source_minutes"], 1),
                    _round(r["age_at_source"], 1),
                    int(r["support_n_movers"]),
                    model_version,
                    snapshot,
                ]
            )

    log.info("hypothetical projections: %d rows", len(rows))
    return HYPOTHETICAL_COLUMNS, rows


def _roles_rows(
    roles: RolesResult, persons: pl.DataFrame
) -> list[tuple[str, list[str], list[list[Any]]]]:
    """Serving rows for the archetype, comparable and shooting tables.

    Filtered to people who exist in `persons`, so every foreign key resolves.
    """
    known = set(persons["person_id"].to_list())

    archetypes = [
        [r["season_id"], r["person_id"], r["league"], int(r["cluster"]), ROLES_VERSION]
        for r in roles.assignments.iter_rows(named=True)
        if r["person_id"] in known
    ]

    definitions = [
        [
            ROLES_VERSION,
            int(r["cluster"]),
            int(r["n_members"]),
            r["top_features"],
            r["exemplars"],
            float(r["stability_jaccard"]),
            bool(r["stability_jaccard"] >= STABILITY_FLOOR),
        ]
        for r in roles.cluster_descriptions.iter_rows(named=True)
    ]

    comps = [
        [
            r["season_id"],
            r["person_id"],
            int(r["rank"]),
            r["neighbour_person_id"],
            float(r["distance"]),
            ROLES_VERSION,
        ]
        for r in roles.neighbours.iter_rows(named=True)
        if r["person_id"] in known and r["neighbour_person_id"] in known
    ]

    shooting = [
        [
            r["season_id"],
            r["person_id"],
            float(r["fg3a"]),
            float(r["fg3a_per_75"]),
            _round(r["fg3_pct_raw"], 4),
            float(r["fg3_pct_shrunk"]),
            float(r["shrinkage_weight"]),
            float(r["prior_mean"]),
            float(r["spacing_score"]),
            bool(r["reportable"]),
            ROLES_VERSION,
        ]
        for r in roles.shooting.iter_rows(named=True)
        if r["person_id"] in known
    ]

    return [
        (
            "player_archetypes",
            ["season_id", "person_id", "league", "cluster", "model_version"],
            archetypes,
        ),
        (
            "archetype_definitions",
            [
                "model_version",
                "cluster",
                "n_members",
                "top_features",
                "exemplars",
                "stability_jaccard",
                "reportable",
            ],
            definitions,
        ),
        (
            "player_comps",
            [
                "season_id",
                "person_id",
                "rank",
                "neighbour_person_id",
                "distance",
                "model_version",
            ],
            comps,
        ),
        (
            "player_shooting",
            [
                "season_id",
                "person_id",
                "fg3a",
                "fg3a_per_75",
                "fg3_pct_raw",
                "fg3_pct_shrunk",
                "shrinkage_weight",
                "prior_mean",
                "spacing_score",
                "reportable",
                "model_version",
            ],
            shooting,
        ),
    ]

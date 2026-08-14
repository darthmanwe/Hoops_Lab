"""Build the evidence bundle for one league transition.

Retrieval here is a deterministic, complete query rather than a search: for a
given person and direction the admissible fact set is fixed, so it is assembled
whole and handed over in one turn. Nothing the model can do changes which facts
it sees, which is what lets a missing citation or an untraceable number be read
as a defect in the *output* rather than an accident of retrieval.

Two omissions are deliberate and load-bearing.

**The player's name.** In ``anonymized`` mode — the default for evaluation —
the subject is ``Player A`` and clubs become ``Team X``. Naming the subject
turns the task from reading evidence into recalling a career, and a model
recalling a career writes fluent prose full of numbers that are approximately
right and cited to nothing. Measuring groundedness without this is measuring
nothing. The limit is worth stating plainly: the name and the teams are
removed, not the identity. A reader who knows the era could still work out who
some subjects are from league, season and production, so the anonymised
groundedness figure bounds recall-leakage from below rather than ruling it out.

**What actually happened.** The target season's real production is not in the
bundle at any point. The report is written from the projection and its interval
alone, and the outcome is shown next to it afterwards. A report that had been
told the answer would be graded on transcription, and the interesting question
— does it hedge in proportion to an interval a third of the league wide — would
be unanswerable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
from hoopslab.llm.schemas import EvidenceBundle, Fact, Unit
from hoopslab.models import baselines
from hoopslab.models.train import latest_run
from hoopslab.models.translation import fit_persistence, fit_translation
from hoopslab.paths import DataPaths
from hoopslab.seasons import Season

log = logging.getLogger(__name__)

#: Human-readable metric names, so the bundle reads as basketball rather than
#: as column names. The model has to write prose from these.
METRIC_LABEL = {
    "usg_pct": "usage rate",
    "ts_pct": "true shooting percentage",
    "ast_pct": "assist rate",
    "tov_rate": "turnover rate",
    "pts_per_75": "points per 75 possessions",
}

LEAGUE_LABEL = {
    "NBA": "the NBA",
    "EL": "the EuroLeague",
    "GL": "the G League",
}

#: Redaction placeholders. Deterministic per bundle, so the same subject is
#: "Player A" on every run and cache keys stay stable.
ANON_SUBJECT = "Player A"
ANON_SOURCE_TEAM = "Team X"
ANON_TARGET_TEAM = "Team Y"


@dataclass
class ScoredTransition:
    """One transition with every model output needed to describe it."""

    record: dict[str, Any]
    predicted: float
    pi80: tuple[float, float]
    pi95: tuple[float, float]
    league_mean: float
    z_preservation: float
    folk_rule: float


def score_transitions(
    player_seasons: pl.DataFrame, pairs: pl.DataFrame, metric: str
) -> list[ScoredTransition]:
    """Refit and score every observed transition for one metric.

    The same public functions the export and the backtest use, called in the
    same order. Scoring is refit rather than read back from D1 so the bundle
    never depends on a database being loaded — the report layer works on a
    fresh clone with nothing but committed parquet.
    """
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

    return [
        ScoredTransition(
            record=record,
            predicted=float(predicted[i]),
            pi80=(float(pi80[i, 0]), float(pi80[i, 1])),
            pi95=(float(pi95[i, 0]), float(pi95[i, 1])),
            league_mean=float(league_mean[i]),
            z_preservation=float(z_preserve[i]),
            folk_rule=float(folk[i]),
        )
        for i, record in enumerate(transitions.iter_rows(named=True))
    ]


@dataclass
class BundleSource:
    """Everything loaded once and reused across every bundle built from it."""

    player_seasons: pl.DataFrame
    pairs: pl.DataFrame
    run: dict[str, Any]
    scored: dict[str, dict[tuple[str, str], ScoredTransition]]

    @classmethod
    def load(cls, paths: DataPaths) -> BundleSource:
        player_seasons = pl.read_parquet(paths.gold / "player_seasons.parquet")
        pairs = pl.read_parquet(paths.gold / "transition_pairs.parquet")

        run = latest_run(paths)
        if run is None:
            raise FileNotFoundError(
                "No committed run log. Run `hoopslab train` before building evidence: "
                "a report quoting a model's error needs that error to have been measured."
            )

        scored: dict[str, dict[tuple[str, str], ScoredTransition]] = {}
        for metric in TARGET_METRICS:
            scored[metric] = {
                (t.record["person_id"], t.record["target_season_id"]): t
                for t in score_transitions(player_seasons, pairs, metric)
            }
        return cls(player_seasons=player_seasons, pairs=pairs, run=run, scored=scored)

    def transitions(self) -> list[tuple[str, str]]:
        """Keys of every transition that both headline metrics could score."""
        keys = set(self.scored[TARGET_METRICS[0]])
        for metric in TARGET_METRICS[1:]:
            keys &= set(self.scored[metric])
        return sorted(keys)


def build_bundle(
    source: BundleSource,
    person_id: str,
    target_season_id: str,
    *,
    anonymized: bool = True,
) -> EvidenceBundle:
    """Assemble the admissible fact set for one transition."""
    headline = source.scored[TARGET_METRICS[0]].get((person_id, target_season_id))
    if headline is None:
        raise KeyError(
            f"No scored transition for {person_id} into {target_season_id}. "
            "Only observed league switches clearing the minutes floor have a projection."
        )

    record = headline.record
    source_season = _season_row(source.player_seasons, person_id, record["source_season_id"])
    source_label = Season.parse(record["source_season_id"]).label
    target_label = Season.parse(target_season_id).label

    facts: list[Fact] = []
    counter = _IdCounter()

    facts.extend(
        _context_facts(
            record, source_season, counter, anonymized=anonymized, source_label=source_label
        )
    )
    for metric in TARGET_METRICS:
        facts.extend(
            _metric_facts(
                metric,
                source.scored[metric][(person_id, target_season_id)],
                source_season,
                counter,
            )
        )
    facts.extend(_model_quality_facts(source.run, record["direction"], counter))
    facts.extend(_cohort_facts(source, record, counter))

    real_name = record.get("player_name") or ""
    target_season = _optional_season_row(source.player_seasons, person_id, target_season_id)

    return EvidenceBundle(
        person_id=person_id,
        subject=ANON_SUBJECT if anonymized else (real_name or person_id),
        direction=record["direction"],
        source_season_id=record["source_season_id"],
        target_season_id=target_season_id,
        source_season_label=f"{source_label} {_league_word(record['source_league'])}",
        target_season_label=f"{target_label} {_league_word(record['target_league'])}",
        anonymized=anonymized,
        facts=facts,
        redacted=_redactions(
            real_name,
            source_season.get("team_name"),
            (target_season or {}).get("team_name"),
        ),
    )


def actual_outcome(source: BundleSource, person_id: str, target_season_id: str) -> dict[str, float]:
    """What actually happened, held back from the bundle and shown beside it."""
    outcome: dict[str, float] = {}
    for metric in TARGET_METRICS:
        scored = source.scored[metric].get((person_id, target_season_id))
        if scored is not None and scored.record.get("target_value") is not None:
            outcome[metric] = float(scored.record["target_value"])
    return outcome


# --------------------------------------------------------------- fact builders


class _IdCounter:
    """Sequential, zero-padded fact ids.

    Stable ordering matters more than it looks: the ids are part of the cache
    key, so a counter that depended on dictionary iteration order would
    invalidate every committed response on a Python upgrade.
    """

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"f{self._n:02d}"


def _context_facts(
    record: dict[str, Any],
    source_season: dict[str, Any],
    ids: _IdCounter,
    *,
    anonymized: bool,
    source_label: str,
) -> list[Fact]:
    source_league = LEAGUE_LABEL.get(record["source_league"], record["source_league"])
    target_league = LEAGUE_LABEL.get(record["target_league"], record["target_league"])
    team = source_season.get("team_name")
    team_label = ANON_SOURCE_TEAM if anonymized else (team or "an unnamed club")

    facts = [
        Fact(
            id=ids.next(),
            statement=(
                f"The subject played in {source_league} for {team_label} in "
                f"{source_label} and then moved to {target_league}"
            ),
            unit="season",
            source="transition_pairs",
        ),
        Fact(
            id=ids.next(),
            statement="Age during the source season",
            value=_maybe_float(source_season.get("age")),
            unit="years",
            source="player_seasons.age",
        ),
        Fact(
            id=ids.next(),
            statement="Minutes played in the source season",
            value=_maybe_float(source_season.get("minutes")),
            unit="count",
            source="player_seasons.minutes",
        ),
        Fact(
            id=ids.next(),
            statement="Games played in the source season",
            value=_maybe_float(source_season.get("gp")),
            unit="count",
            source="player_seasons.gp",
        ),
    ]

    for column, label, unit in (
        ("pts_per_75", "Points per 75 possessions in the source season", "per_75"),
        ("ast_per_75", "Assists per 75 possessions in the source season", "per_75"),
        ("reb_per_75", "Rebounds per 75 possessions in the source season", "per_75"),
        ("fg3a_rate", "Share of shot attempts taken from three in the source season", "fraction"),
        ("tov_rate", "Turnover rate in the source season", "fraction"),
        ("ast_pct", "Assist rate in the source season", "fraction"),
    ):
        value = _maybe_float(source_season.get(column))
        if value is not None:
            facts.append(
                Fact(
                    id=ids.next(),
                    statement=label,
                    value=value,
                    unit=unit,  # type: ignore[arg-type]
                    source=f"player_seasons.{column}",
                )
            )

    gap = record.get("gap_seasons")
    if gap is not None and int(gap) > 1:
        facts.append(
            Fact(
                id=ids.next(),
                statement="Seasons between the last source-league season and the move",
                value=float(gap),
                unit="count",
                source="transition_pairs.gap_seasons",
            )
        )
    return facts


def _metric_facts(
    metric: str,
    scored: ScoredTransition,
    source_season: dict[str, Any],
    ids: _IdCounter,
) -> list[Fact]:
    label = METRIC_LABEL.get(metric, metric)
    record = scored.record
    target_league = LEAGUE_LABEL.get(record["target_league"], record["target_league"])
    source_league = LEAGUE_LABEL.get(record["source_league"], record["source_league"])

    facts = [
        Fact(
            id=ids.next(),
            statement=f"Source-season {label}",
            value=float(record["source_value"]),
            unit=_unit_for(metric),
            source=f"player_seasons.{metric}",
        ),
        Fact(
            id=ids.next(),
            statement=(
                f"Source-season {label} standardised within {source_league} that season, "
                "so 0 is the league average"
            ),
            value=float(record["z_source"]),
            unit="sd",
            source=f"player_seasons.z_{metric}",
        ),
        Fact(
            id=ids.next(),
            statement=f"Projected {label} in {target_league}",
            value=scored.predicted,
            unit=_unit_for(metric),
            source="translation model",
        ),
        Fact(
            id=ids.next(),
            statement=f"Lower bound of the 80% prediction interval for {label}",
            value=scored.pi80[0],
            unit=_unit_for(metric),
            source="translation model",
        ),
        Fact(
            id=ids.next(),
            statement=f"Upper bound of the 80% prediction interval for {label}",
            value=scored.pi80[1],
            unit=_unit_for(metric),
            source="translation model",
        ),
        Fact(
            id=ids.next(),
            statement=f"Lower bound of the 95% prediction interval for {label}",
            value=scored.pi95[0],
            unit=_unit_for(metric),
            source="translation model",
        ),
        Fact(
            id=ids.next(),
            statement=f"Upper bound of the 95% prediction interval for {label}",
            value=scored.pi95[1],
            unit=_unit_for(metric),
            source="translation model",
        ),
        Fact(
            id=ids.next(),
            statement=(
                f"Minutes-weighted average {label} among qualified "
                f"{_league_word(record['target_league'])} players in the target season"
            ),
            value=float(record["target_mean"]),
            unit=_unit_for(metric),
            source="league_season_moments.mean",
        ),
        Fact(
            id=ids.next(),
            statement=(
                f"Standard deviation of {label} among qualified "
                f"{_league_word(record['target_league'])} players in the target season"
            ),
            value=float(record["target_sd"]),
            unit=_unit_for(metric),
            source="league_season_moments.sd",
        ),
        Fact(
            id=ids.next(),
            statement=(
                f"What the same {label} would be if the subject held their standing relative "
                f"to the league exactly (the z-preservation baseline)"
            ),
            value=scored.z_preservation,
            unit=_unit_for(metric),
            source="baselines.z_preservation",
        ),
    ]

    if metric == "usg_pct":
        facts.append(
            Fact(
                id=ids.next(),
                statement=(
                    "What the folk rule of thumb — multiply source production by 0.75 — "
                    "gives for usage rate"
                ),
                value=scored.folk_rule,
                unit="fraction",
                source="baselines.folk_rule",
            )
        )

    _ = source_season
    return facts


def _model_quality_facts(run: dict[str, Any], direction: str, ids: _IdCounter) -> list[Fact]:
    """The model's own measured error, so the report can hedge proportionately.

    Including the failures is the point. For true shooting the model loses to
    predicting the league average, and a report that reads confidently about a
    true-shooting projection while that fact sits in its evidence is showing
    exactly the miscalibration the judge rubric is looking for.
    """
    facts: list[Fact] = []
    for metric in TARGET_METRICS:
        metrics = run["metrics"].get(metric)
        if metrics is None:
            continue

        label = METRIC_LABEL.get(metric, metric)
        best_name, best_mae = min(metrics["baseline_mae"].items(), key=lambda kv: kv[1])
        beats = metrics["mae"] < best_mae

        facts.append(
            Fact(
                id=ids.next(),
                statement=(
                    f"Out-of-fold mean absolute error of the {label} projection, measured over "
                    f"{metrics['n_evaluated']} held-out transitions"
                ),
                value=float(metrics["mae"]),
                unit=_unit_for(metric),
                source="run log",
            )
        )
        facts.append(
            Fact(
                id=ids.next(),
                statement=(
                    f"Error of the best trivial baseline for {label} ({best_name}); the model "
                    + ("beats it" if beats else "is WORSE than it and should not be trusted here")
                ),
                value=float(best_mae),
                unit=_unit_for(metric),
                source="run log",
            )
        )

        slope = metrics.get("direction_slopes", {}).get(direction)
        if slope is not None:
            facts.append(
                Fact(
                    id=ids.next(),
                    statement=(
                        f"Slope fitted for {direction} on {label} alone: the fraction of a "
                        "player's standing above their league that carries across"
                    ),
                    value=float(slope),
                    unit="none",
                    source="run log",
                )
            )
    return facts


def _cohort_facts(source: BundleSource, record: dict[str, Any], ids: _IdCounter) -> list[Fact]:
    """How thin the evidence under this direction actually is, and how selected.

    A projection resting on 61 historical moves is a different object from one
    resting on 10,000, and the report should be able to say so.
    """
    direction = record["direction"]
    n_direction = int(
        source.pairs.filter(pl.col("direction") == direction).height  # observed pairs
    )

    facts = [
        Fact(
            id=ids.next(),
            statement=f"Number of historical {direction} transitions the estimate rests on",
            value=float(n_direction),
            unit="count",
            source="transition_pairs",
        )
    ]

    for row in source.run.get("selection", []):
        if row["direction"] == direction and row["metric"] == TARGET_METRICS[0]:
            facts.append(
                Fact(
                    id=ids.next(),
                    statement=(
                        "How far above their own league's average the players who made this "
                        "move already sat, in standard deviations. This estimate is conditional "
                        "on the move having happened: it says what history records for players "
                        "selected to move, not what a randomly chosen player would do"
                    ),
                    value=float(row["gap_sd"]),
                    unit="sd",
                    source="run log selection summary",
                )
            )
            break
    return facts


# --------------------------------------------------------------------- helpers


def _season_row(player_seasons: pl.DataFrame, person_id: str, season_id: str) -> dict[str, Any]:
    row = _optional_season_row(player_seasons, person_id, season_id)
    if row is None:
        raise KeyError(f"No player-season row for {person_id} in {season_id}")
    return row


def _optional_season_row(
    player_seasons: pl.DataFrame, person_id: str, season_id: str
) -> dict[str, Any] | None:
    matches = player_seasons.filter(
        (pl.col("person_id") == person_id) & (pl.col("season_id") == season_id)
    )
    return matches.row(0, named=True) if matches.height else None


def _league_word(league: str) -> str:
    return {"NBA": "NBA", "EL": "EuroLeague", "GL": "G League"}.get(league, league)


#: Below this length a redaction term stops discriminating. Initials, particles
#: like "de" and "van", and three-letter club abbreviations such as "SAC" all
#: occur inside ordinary words, and a check that fires on "sacrifice" is a
#: check people learn to override.
MIN_REDACTION_LENGTH = 4


def _redactions(*values: str | None) -> list[str]:
    """Strings whose appearance in a report would mean the model recalled them.

    Full names and the tokens within them, because a report that says "Dončić"
    without a first name has leaked just as much as one that says both. Matched
    on word boundaries downstream, so "Real" does not fire on "really".
    """
    out: set[str] = set()
    for value in values:
        if not value:
            continue
        candidates = [value.strip(), *value.replace("-", " ").split()]
        out.update(c for c in candidates if len(c) >= MIN_REDACTION_LENGTH)
    return sorted(out)


def _unit_for(metric: str) -> Unit:
    return "per_75" if metric.endswith("per_75") else "fraction"


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if np.isnan(number) else number

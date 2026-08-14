"""Integrity checks that gold must satisfy, beyond per-column contracts.

These are the checks that catch real bugs, and each one exists because of a
specific failure this project already had or narrowly avoided.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

#: Agreement required between rates derived here and the league's own published
#: values, as mean absolute deviation on the 0-1 scale.
#:
#: Not zero, for a known and bounded reason: `stats.nba.com` computes usage
#: per team stint, so a player traded mid-season is measured against each
#: team's possessions separately, while season totals here are measured against
#: the combined denominator. That accounts for roughly half a percentage point.
#: A regression in the formula itself would be far larger — the missing
#: five-fold team-minutes correction showed up as 0.147.
MAX_RATE_DISAGREEMENT = {
    "usg_pct": 0.010,
    "ts_pct": 0.001,
    "ast_pct": 0.010,
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def render(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


def run_all(tables: dict[str, pl.DataFrame]) -> list[CheckResult]:
    players = tables["player_seasons"]
    identities = tables["player_identities"]
    persons = tables["persons"]
    pairs = tables["transition_pairs"]

    return [
        *rate_agreement(players),
        no_non_finite(players),
        rates_in_range(players),
        identities_are_unique(identities),
        every_identity_has_a_person(identities, persons),
        unnamed_persons_are_rare(persons),
        every_player_season_resolves(players),
        pairs_change_league(pairs),
        pairs_respect_gap(pairs),
        pairs_have_one_row_per_landing(pairs),
        pairs_have_one_row_per_departure(pairs),
        pairs_reference_real_seasons(pairs, players),
        minutes_are_non_negative(players),
        shots_made_not_exceed_attempts(players),
    ]


def rate_agreement(players: pl.DataFrame) -> list[CheckResult]:
    """Our formulas must reproduce the league's own published rates.

    The single most valuable check in the project. Cross-league coefficients
    are only meaningful if every league's rates are computed identically, and a
    formula error would otherwise be absorbed silently into the estimate rather
    than surfacing as a failure.
    """
    results: list[CheckResult] = []

    for metric, tolerance in MAX_RATE_DISAGREEMENT.items():
        official = f"official_{metric}"
        if official not in players.columns:
            results.append(
                CheckResult(f"rate_agreement:{metric}", False, "official series missing")
            )
            continue

        cohort = players.filter(
            pl.col("qualified") & pl.col(metric).is_not_null() & pl.col(official).is_not_null()
        )
        if cohort.is_empty():
            results.append(CheckResult(f"rate_agreement:{metric}", False, "no comparable rows"))
            continue

        mad = cohort.select((pl.col(metric) - pl.col(official)).abs().mean()).item()
        results.append(
            CheckResult(
                f"rate_agreement:{metric}",
                mad <= tolerance,
                f"MAD {mad:.5f} against tolerance {tolerance} over n={cohort.height}",
            )
        )

    return results


def no_non_finite(players: pl.DataFrame) -> CheckResult:
    """NaN and infinity are illegal in gold.

    The previous version's SQL writer serialised them as the bare tokens
    ``nan`` and ``inf``, which are not valid SQLite and would abort a load
    partway through, leaving the database half-updated.
    """
    numeric = [c for c, t in zip(players.columns, players.dtypes, strict=True) if t.is_numeric()]
    offenders = {
        c: n
        for c in numeric
        if (n := players.select(pl.col(c).is_infinite().sum()).item() or 0) > 0
    }
    return CheckResult(
        "no_non_finite",
        not offenders,
        "clean" if not offenders else f"infinite values in {offenders}",
    )


def rates_in_range(players: pl.DataFrame) -> CheckResult:
    """Rates that are fractions must lie in [0, 1]."""
    bounds = {"ts_pct": (0.0, 1.2), "usg_pct": (0.0, 1.0), "tov_rate": (0.0, 1.0)}
    problems = []

    qualified = players.filter(pl.col("qualified"))
    for column, (low, high) in bounds.items():
        if column not in players.columns:
            continue
        out = qualified.filter(
            pl.col(column).is_not_null() & ((pl.col(column) < low) | (pl.col(column) > high))
        ).height
        if out:
            problems.append(f"{column}: {out} rows outside [{low}, {high}]")

    return CheckResult("rates_in_range", not problems, "; ".join(problems) or "all within bounds")


def identities_are_unique(identities: pl.DataFrame) -> CheckResult:
    """Each (league, source id) maps to exactly one person.

    Injectivity in this direction is what stops one human being being counted
    twice in a transition cohort.
    """
    duplicated = (
        identities.group_by(["league", "source_player_id"])
        .agg(pl.n_unique("person_id").alias("n"))
        .filter(pl.col("n") > 1)
    )
    return CheckResult(
        "identities_are_unique",
        duplicated.is_empty(),
        "one person per source id"
        if duplicated.is_empty()
        else f"{duplicated.height} source ids map to multiple persons",
    )


def every_identity_has_a_person(identities: pl.DataFrame, persons: pl.DataFrame) -> CheckResult:
    known = set(persons["person_id"].to_list())
    orphans = [p for p in identities["person_id"].unique().to_list() if p not in known]
    return CheckResult(
        "every_identity_has_a_person",
        not orphans,
        "all resolve" if not orphans else f"{len(orphans)} person ids missing from persons",
    )


#: A handful of G League rows arrive from the source with no name at all. They
#: are kept rather than dropped — the statistics are real, only the label is
#: missing, and dropping them would leave dangling identity references. The
#: bound exists so that a regression like the one that silently lost 1,321
#: people fails the build instead of passing quietly.
MAX_UNNAMED_PERSONS = 10


def unnamed_persons_are_rare(persons: pl.DataFrame) -> CheckResult:
    """Missing names are tolerated, but only at the scale the source actually has.

    Inventing a placeholder name would be fabrication; the honest handling is a
    null display name plus a ceiling on how many of them there may be.
    """
    unnamed = persons.filter(
        pl.col("display_name").is_null() | (pl.col("display_name").str.strip_chars() == "")
    ).height
    return CheckResult(
        "unnamed_persons_are_rare",
        unnamed <= MAX_UNNAMED_PERSONS,
        f"{unnamed} of {persons.height} persons have no name (ceiling {MAX_UNNAMED_PERSONS})",
    )


def every_player_season_resolves(players: pl.DataFrame) -> CheckResult:
    unresolved = players.filter(pl.col("person_id").is_null()).height
    return CheckResult(
        "every_player_season_resolves",
        unresolved == 0,
        "all seasons carry a person id"
        if unresolved == 0
        else f"{unresolved} player-seasons have no person id",
    )


def pairs_change_league(pairs: pl.DataFrame) -> CheckResult:
    same = pairs.filter(pl.col("source_league") == pl.col("target_league")).height
    return CheckResult(
        "pairs_change_league",
        same == 0,
        "every pair crosses leagues" if same == 0 else f"{same} pairs share a league",
    )


def pairs_respect_gap(pairs: pl.DataFrame) -> CheckResult:
    """A transition must move forward in time, by one or two seasons.

    A zero or negative gap would mean the target season is being used to
    predict the source, which is leakage in its most direct form.
    """
    bad = pairs.filter(~pl.col("gap_seasons").is_between(1, 2)).height
    return CheckResult(
        "pairs_respect_gap",
        bad == 0,
        "all gaps in [1, 2]" if bad == 0 else f"{bad} pairs have an invalid gap",
    )


def pairs_have_one_row_per_landing(pairs: pl.DataFrame) -> CheckResult:
    """Each observed arrival appears exactly once.

    A player with two qualifying seasons before a move otherwise produces two
    rows sharing one target season, which duplicates the response variable and
    silently doubles that player's weight in the fit.
    """
    duplicated = (
        pairs.group_by(["person_id", "target_season_id", "direction"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
    )
    return CheckResult(
        "pairs_have_one_row_per_landing",
        duplicated.is_empty(),
        "one row per arrival"
        if duplicated.is_empty()
        else f"{duplicated.height} arrivals appear more than once",
    )


def pairs_have_one_row_per_departure(pairs: pl.DataFrame) -> CheckResult:
    """Each source season is used at most once per direction.

    The mirror of the landing check. One source season with both a one- and a
    two-season gap to different targets would otherwise count the same
    departure twice — and would collide with the serving primary key, which is
    how this was found.
    """
    duplicated = (
        pairs.group_by(["person_id", "source_season_id", "direction"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
    )
    return CheckResult(
        "pairs_have_one_row_per_departure",
        duplicated.is_empty(),
        "one row per departure"
        if duplicated.is_empty()
        else f"{duplicated.height} departures appear more than once",
    )


def pairs_reference_real_seasons(pairs: pl.DataFrame, players: pl.DataFrame) -> CheckResult:
    known = set(players["season_id"].unique().to_list())
    missing = {
        s
        for column in ("source_season_id", "target_season_id")
        for s in pairs[column].unique().to_list()
        if s not in known
    }
    return CheckResult(
        "pairs_reference_real_seasons",
        not missing,
        "all seasons exist" if not missing else f"unknown seasons: {sorted(missing)[:5]}",
    )


def minutes_are_non_negative(players: pl.DataFrame) -> CheckResult:
    bad = players.filter(pl.col("minutes") < 0).height
    return CheckResult(
        "minutes_are_non_negative", bad == 0, "clean" if bad == 0 else f"{bad} negative rows"
    )


def shots_made_not_exceed_attempts(players: pl.DataFrame) -> CheckResult:
    bad = players.filter(
        (pl.col("fgm") > pl.col("fga"))
        | (pl.col("fg3m") > pl.col("fg3a"))
        | (pl.col("ftm") > pl.col("fta"))
    ).height
    return CheckResult(
        "shots_made_not_exceed_attempts",
        bad == 0,
        "clean" if bad == 0 else f"{bad} rows make more than they attempt",
    )

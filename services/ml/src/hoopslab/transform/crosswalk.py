"""Resolve one human being across four identifier systems.

This is the join key the whole project depends on. The previous schema stored
``players.league_id`` as a column on the player, which made a player who moved
between leagues **two unrelated rows** — and therefore made the cross-league
translation model, the entire point of the project, impossible to fit or
backtest. There was no key on which "the same person in both leagues" existed.

Three id systems, not four, in practice:

* ``stats.nba.com`` ``PERSON_ID`` covers **both the NBA and the G League**, so
  those two need no matching at all. This is verified rather than assumed — see
  :func:`verify_shared_id_space`.
* ESPN ``athlete_id`` is a fourth system, joined for box scores in a later phase.
* EuroLeague ``player.code`` shares nothing with any of them and must be matched
  on name, corroborated by age.

The asymmetry that governs the thresholds: a **missed** match drops a player
from a transition cohort of a few dozen, which is materially costly. A **false**
match invents a career that never happened and silently corrupts the estimate.
So candidates are generated generously and accepted conservatively, every link
records how it was made, and low-confidence links are kept but flagged rather
than quietly promoted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

log = logging.getLogger(__name__)

#: Implied birth years may differ by this much and still be the same person.
#: Sources disagree on whether age is as-of season start, season end, or the
#: date the page was generated, which is worth about a year of slack.
BIRTH_YEAR_TOLERANCE = 1

#: Confidence assigned per match method. Anything below 0.8 is reported but
#: excluded from the modelling cohort by default.
CONFIDENCE = {
    "manual_override": 1.00,
    "shared_nba_person_id": 1.00,
    "name_and_age": 0.95,
    "name_only_unique": 0.70,
    "name_ambiguous": 0.30,
}

MODELLING_CONFIDENCE_FLOOR = 0.80


@dataclass(frozen=True)
class CrosswalkReport:
    """Auditable summary of a resolution run."""

    n_nba_persons: int
    n_euroleague_players: int
    n_matched_name_and_age: int
    n_matched_name_only: int
    n_ambiguous: int
    n_euroleague_only: int
    n_manual_overrides: int

    def render(self) -> str:
        matched = self.n_matched_name_and_age + self.n_matched_name_only
        rate = matched / self.n_euroleague_players if self.n_euroleague_players else 0.0
        return (
            f"NBA/G League persons:        {self.n_nba_persons:>6}\n"
            f"EuroLeague players:          {self.n_euroleague_players:>6}\n"
            f"  matched on name and age:   {self.n_matched_name_and_age:>6}\n"
            f"  matched on name only:      {self.n_matched_name_only:>6}\n"
            f"  ambiguous (not accepted):  {self.n_ambiguous:>6}\n"
            f"  EuroLeague only:           {self.n_euroleague_only:>6}\n"
            f"  manual overrides applied:  {self.n_manual_overrides:>6}\n"
            f"cross-league match rate:     {rate:>6.1%}"
        )


def implied_birth_year(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """One birth-year estimate per source player, median across their seasons.

    Age is reported per season, so ``start_year - age`` gives a birth year from
    every row. The median across a career is robust to the odd stale or
    off-by-one age that these feeds contain.
    """
    return (
        player_seasons.filter(pl.col("age").is_not_null() & (pl.col("age") > 0))
        .with_columns((pl.col("start_year") - pl.col("age")).alias("_birth_year"))
        .group_by(["league", "source_player_id"])
        .agg(pl.median("_birth_year").alias("birth_year"))
    )


@dataclass(frozen=True)
class SharedIdSpaceEvidence:
    """Evidence that the NBA and G League really do share one identifier space."""

    n_shared_ids: int
    n_gleague_ids: int
    name_agreement: float

    @property
    def overlap(self) -> float:
        return self.n_shared_ids / self.n_gleague_ids if self.n_gleague_ids else 0.0

    @property
    def confirmed(self) -> bool:
        # Overlap alone proves nothing — most G League players never reach the
        # NBA, so a low figure is expected and a high one could be coincidence.
        # Agreement between the *names* behind a shared id is the real test.
        return self.n_shared_ids > 100 and self.name_agreement > 0.95

    def render(self) -> str:
        return (
            f"{self.n_shared_ids} of {self.n_gleague_ids} G League ids also appear as NBA ids "
            f"({self.overlap:.1%}); names agree for {self.name_agreement:.1%} of them"
        )


def verify_shared_id_space(nba: pl.DataFrame, gleague: pl.DataFrame) -> SharedIdSpaceEvidence:
    """Check that a shared id really denotes the same person.

    The G League is treated as needing no name matching at all, on the grounds
    that it uses ``stats.nba.com`` person ids. That assumption carries every
    G League transition pair, so it is tested rather than trusted: for ids
    present in both leagues, the names attached to them must agree.
    """
    if gleague.is_empty() or nba.is_empty():
        return SharedIdSpaceEvidence(0, gleague["source_player_id"].n_unique(), 0.0)

    nba_names = nba.select("source_player_id", "normalized_name").unique(subset="source_player_id")
    gl_names = gleague.select("source_player_id", "normalized_name").unique(
        subset="source_player_id"
    )

    shared = gl_names.join(nba_names, on="source_player_id", how="inner", suffix="_nba")
    if shared.is_empty():
        return SharedIdSpaceEvidence(0, gl_names.height, 0.0)

    agreement = shared.select(
        (pl.col("normalized_name") == pl.col("normalized_name_nba")).mean().cast(pl.Float64)
    ).to_series()[0]

    return SharedIdSpaceEvidence(
        n_shared_ids=shared.height,
        n_gleague_ids=gl_names.height,
        name_agreement=float(agreement or 0.0),
    )


def build_crosswalk(
    nba: pl.DataFrame,
    gleague: pl.DataFrame,
    euroleague: pl.DataFrame,
    overrides: pl.DataFrame | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, CrosswalkReport]:
    """Resolve identities.

    Returns ``(persons, identities, report)``.

    ``persons`` is one row per human being. ``identities`` maps each
    ``(league, source_player_id)`` to a ``person_id``, carrying the method and
    confidence so a consumer can decide what to trust — and so a reviewer can
    see that the decision was made rather than assumed.
    """
    nba = _ensure_player_columns(nba)
    euroleague = _ensure_player_columns(euroleague)
    nba_people = _distinct_players(nba)
    el_people = _distinct_players(euroleague)

    # Diagonal rather than vertical: the two frames need not carry identical
    # columns, which matters when a league is absent and only the minimal
    # schema is present.
    birth_years = implied_birth_year(
        pl.concat(
            [
                f.select("league", "source_player_id", "start_year", "age")
                for f in (nba, euroleague)
            ],
            how="diagonal_relaxed",
        )
    )
    nba_people = _attach_birth_year(nba_people, birth_years)
    el_people = _attach_birth_year(el_people, birth_years)

    overrides = overrides if overrides is not None else _empty_overrides()
    override_map = dict(
        zip(
            overrides["euroleague_player_id"].to_list(),
            overrides["nba_player_id"].to_list(),
            strict=True,
        )
    )

    identities: list[dict[str, object]] = []

    # NBA is the anchor: every NBA player is a person, by definition.
    for row in nba_people.iter_rows(named=True):
        identities.append(
            {
                "person_id": _person_id_for_nba(row["source_player_id"]),
                "league": "NBA",
                "source_player_id": row["source_player_id"],
                "match_method": "anchor",
                "confidence": 1.0,
            }
        )

    # The G League shares the NBA identifier space, so no matching is required.
    gleague = _ensure_player_columns(gleague)
    evidence = verify_shared_id_space(nba, gleague)
    log.info("shared id space: %s", evidence.render())
    if not evidence.confirmed:
        log.warning(
            "The NBA/G League shared-identifier assumption did not hold. "
            "Every G League identity below depends on it."
        )
    for source_id in gleague["source_player_id"].unique().to_list():
        identities.append(
            {
                "person_id": _person_id_for_nba(source_id),
                "league": "GL",
                "source_player_id": source_id,
                "match_method": "shared_nba_person_id",
                "confidence": CONFIDENCE["shared_nba_person_id"],
            }
        )

    counts = {"name_and_age": 0, "name_only": 0, "ambiguous": 0, "el_only": 0, "override": 0}

    nba_by_key: dict[str, list[dict[str, object]]] = {}
    for row in nba_people.iter_rows(named=True):
        nba_by_key.setdefault(str(row["match_key"]), []).append(row)

    for el_row in el_people.iter_rows(named=True):
        el_id = str(el_row["source_player_id"])

        if el_id in override_map:
            identities.append(
                {
                    "person_id": _person_id_for_nba(override_map[el_id]),
                    "league": "EL",
                    "source_player_id": el_id,
                    "match_method": "manual_override",
                    "confidence": CONFIDENCE["manual_override"],
                }
            )
            counts["override"] += 1
            continue

        candidates = nba_by_key.get(str(el_row["match_key"]), [])
        corroborated = [c for c in candidates if _ages_agree(el_row, c)]

        if len(corroborated) == 1:
            method, confidence = "name_and_age", CONFIDENCE["name_and_age"]
            chosen = corroborated[0]
            counts["name_and_age"] += 1
        elif len(candidates) == 1 and not corroborated:
            # A single name match with no usable age on either side. Accepted,
            # but below the modelling floor so it cannot enter the cohort
            # without someone deciding to lower the threshold.
            method, confidence = "name_only_unique", CONFIDENCE["name_only_unique"]
            chosen = candidates[0]
            counts["name_only"] += 1
        elif len(candidates) > 1:
            # Two people share a name and age cannot separate them. Recorded so
            # it can be resolved by hand, never guessed.
            method, confidence = "name_ambiguous", CONFIDENCE["name_ambiguous"]
            chosen = None
            counts["ambiguous"] += 1
        else:
            method, confidence, chosen = "euroleague_only", 1.0, None
            counts["el_only"] += 1

        identities.append(
            {
                "person_id": (
                    _person_id_for_nba(chosen["source_player_id"])
                    if chosen is not None
                    else f"el_{el_id}"
                ),
                "league": "EL",
                "source_player_id": el_id,
                "match_method": method,
                "confidence": confidence,
            }
        )

    identity_frame = pl.DataFrame(
        identities,
        schema={
            "person_id": pl.Utf8,
            "league": pl.Utf8,
            "source_player_id": pl.Utf8,
            "match_method": pl.Utf8,
            "confidence": pl.Float64,
        },
    )

    gl_people = _attach_birth_year(_distinct_players(gleague), birth_years)
    persons = _build_persons(identity_frame, nba_people, gl_people, el_people)

    report = CrosswalkReport(
        n_nba_persons=nba_people.height,
        n_euroleague_players=el_people.height,
        n_matched_name_and_age=counts["name_and_age"],
        n_matched_name_only=counts["name_only"],
        n_ambiguous=counts["ambiguous"],
        n_euroleague_only=counts["el_only"],
        n_manual_overrides=counts["override"],
    )
    return persons, identity_frame, report


def _ensure_player_columns(frame: pl.DataFrame) -> pl.DataFrame:
    """Give a schema to a frame that has none.

    A bare ``pl.DataFrame()`` has no columns at all, so selecting from it raises
    rather than returning nothing. That happens whenever a league is absent —
    a partial ingest, or a caller who only wants two of the three.
    """
    if frame.width:
        return frame
    return pl.DataFrame(
        schema={
            "source_player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "normalized_name": pl.Utf8,
            "match_key": pl.Utf8,
            "league": pl.Utf8,
            "start_year": pl.Float64,
            "age": pl.Float64,
        }
    )


def _person_id_for_nba(source_player_id: object) -> str:
    return f"nba_{source_player_id}"


def _ages_agree(left: dict[str, object], right: dict[str, object]) -> bool:
    """Whether two implied birth years are close enough to be one person.

    Missing age on either side means "not corroborated", never "assume yes" —
    an unverified match is downgraded to name-only rather than accepted.
    """
    a, b = left.get("birth_year"), right.get("birth_year")
    if not isinstance(a, int | float) or not isinstance(b, int | float):
        return False
    return abs(float(a) - float(b)) <= BIRTH_YEAR_TOLERANCE


def _distinct_players(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """One row per source player, keeping their most recent display name."""
    if player_seasons.is_empty():
        return pl.DataFrame(
            schema={
                "source_player_id": pl.Utf8,
                "player_name": pl.Utf8,
                "normalized_name": pl.Utf8,
                "match_key": pl.Utf8,
                "first_season": pl.Float64,
                "last_season": pl.Float64,
            }
        )

    return (
        player_seasons.sort("start_year")
        .group_by("source_player_id")
        .agg(
            pl.last("player_name").alias("player_name"),
            pl.last("normalized_name").alias("normalized_name"),
            pl.last("match_key").alias("match_key"),
            pl.min("start_year").alias("first_season"),
            pl.max("start_year").alias("last_season"),
        )
    )


def _attach_birth_year(people: pl.DataFrame, birth_years: pl.DataFrame) -> pl.DataFrame:
    if people.is_empty():
        return people.with_columns(pl.lit(None).cast(pl.Float64).alias("birth_year"))
    return people.join(
        birth_years.select("source_player_id", "birth_year"),
        on="source_player_id",
        how="left",
    )


def _build_persons(
    identities: pl.DataFrame,
    nba_people: pl.DataFrame,
    gl_people: pl.DataFrame,
    el_people: pl.DataFrame,
) -> pl.DataFrame:
    """One row per person, preferring the NBA spelling of a name when there is one.

    All three leagues contribute names, not just the two that can be matched:
    a G League player who never reached the NBA still has an identity row, and
    omitting him here would leave that row pointing at a person who does not
    exist. The integrity check ``every_identity_has_a_person`` exists precisely
    because an earlier version of this function did exactly that, for 1,321
    players.
    """
    naming = pl.concat(
        [
            people.select("source_player_id", "player_name", "birth_year").with_columns(
                pl.lit(league).alias("league"), pl.lit(priority).alias("_priority")
            )
            for league, priority, people in (
                ("NBA", 0, nba_people),
                ("GL", 1, gl_people),
                ("EL", 2, el_people),
            )
            if not people.is_empty()
        ],
        how="vertical_relaxed",
    )

    # Sort nulls last within each priority so a league that has a name for this
    # person wins over one that does not, then take the first per person.
    #
    # Crucially this does *not* filter out unnamed people. `persons` is derived
    # from `identities`, so every identity is guaranteed a person by
    # construction; a handful of G League rows arrive with no name at all, and
    # dropping them would leave dangling references rather than fixing anything.
    joined = identities.join(naming, on=["league", "source_player_id"], how="left")

    return (
        joined.sort(["_priority", "player_name"], nulls_last=True)
        .group_by("person_id")
        .agg(
            pl.first("player_name").alias("display_name"),
            pl.col("birth_year").drop_nulls().first().alias("birth_year"),
            pl.col("league").unique().sort().alias("leagues"),
        )
        .with_columns(pl.col("leagues").list.join("+").alias("leagues"))
        .sort("person_id")
    )


def _empty_overrides() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "euroleague_player_id": pl.Utf8,
            "nba_player_id": pl.Utf8,
            "note": pl.Utf8,
        }
    )

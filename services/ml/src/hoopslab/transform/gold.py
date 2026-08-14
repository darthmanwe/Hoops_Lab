"""Analysis-ready tables, joined on resolved identities and committed to the repo.

Gold is the only layer in the repository. Committing it is what lets a clean
clone reproduce every reported number with no network access, which matters
here more than usual because the primary source refuses to talk to CI at all.

Every rate is computed here, once, by :mod:`hoopslab.transform.rates`, for all
three leagues.
"""

from __future__ import annotations

import logging

import polars as pl

from hoopslab.transform import rates
from hoopslab.transform.crosswalk import MODELLING_CONFIDENCE_FLOOR

log = logging.getLogger(__name__)

#: Minimum minutes for a player-season to be considered an observation rather
#: than noise. A rate computed from 40 minutes is not a measurement.
MIN_MINUTES_QUALIFIED = 250

#: Thresholds for a league transition to count as a usable pair. Both sides
#: need enough playing time for the source and target rates to mean anything.
MIN_SOURCE_MINUTES = 400
MIN_TARGET_MINUTES = 300

#: A player may take a season out, or move mid-career via a third league, so
#: the target season is allowed to be one or two years after the source.
MAX_GAP_SEASONS = 2


def fill_missing_age(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Recover age for leagues whose source does not report it.

    ``leaguedashplayerstats`` returns no AGE column for the G League, so every
    one of its 4,463 player-seasons carried a null age. Age is a covariate in
    the translation model, and the transition frame drops rows without one — so
    all 90 transitions *originating* in the G League were silently discarded,
    including the entire GL→NBA direction the G League was ingested to provide.
    Nothing failed; the pairs simply were not there, and the count looked
    plausible.

    The recovery is arithmetic, not imputation. These are the same people under
    another league's id, and a person's birth year is already resolved from the
    leagues that do report age, so ``start_year - birth_year`` is the age — with
    the same ±1 ambiguity every season-grain age carries, since a season spans
    two calendar years.

    A person with no age anywhere still has none afterwards. That is correct:
    inventing one would put a fabricated covariate into the flagship model,
    which is the failure this project exists to have removed.
    """
    if "age" not in player_seasons.columns or "person_id" not in player_seasons.columns:
        return player_seasons

    implied = (
        player_seasons.filter(pl.col("age").is_not_null() & pl.col("person_id").is_not_null())
        .with_columns((pl.col("start_year") - pl.col("age")).alias("_implied"))
        .group_by("person_id")
        # Median over the seasons that do report age: a single mistyped age
        # should not move a career's worth of derived ones.
        .agg(pl.median("_implied").alias("_person_birth_year"))
    )

    filled = player_seasons.join(implied, on="person_id", how="left").with_columns(
        pl.coalesce(
            pl.col("age"),
            pl.col("start_year").cast(pl.Float64) - pl.col("_person_birth_year"),
        ).alias("age")
    )

    recovered = int(filled["age"].is_not_null().sum()) - int(
        player_seasons["age"].is_not_null().sum()
    )
    if recovered:
        log.info("recovered age for %d player-seasons from person-level birth years", recovered)

    return filled.drop("_person_birth_year")


def build_player_seasons(
    players: pl.DataFrame,
    teams: pl.DataFrame,
    identities: pl.DataFrame,
    official: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """One row per person-season, with every rate computed the same way."""
    joined = players.join(
        identities.select("league", "source_player_id", "person_id", "confidence"),
        on=["league", "source_player_id"],
        how="left",
    )

    team_cols = [
        "season_id",
        "source_team_id",
        "team_minutes",
        "team_fga",
        "team_fgm",
        "team_fta",
        "team_tov",
    ]
    joined = joined.join(
        teams.select([c for c in team_cols if c in teams.columns]),
        on=["season_id", "source_team_id"],
        how="left",
    )

    joined = fill_missing_age(joined)

    enriched = joined.with_columns(
        rates.true_shooting_pct().alias("ts_pct"),
        rates.usage_rate().alias("usg_pct"),
        rates.ratio(pl.col("tov"), pl.col("fga") + 0.44 * pl.col("fta") + pl.col("tov")).alias(
            "tov_rate"
        ),
        rates.ratio(pl.col("fg3a"), pl.col("fga")).alias("fg3a_rate"),
        rates.ratio(pl.col("fta"), pl.col("fga")).alias("ft_rate"),
        rates.per_75("pts").alias("pts_per_75"),
        rates.per_75("ast").alias("ast_per_75"),
        rates.per_75("reb").alias("reb_per_75"),
        rates.per_75("tov").alias("tov_per_75"),
        # AST% needs team field goals made while the player was on the floor;
        # the standard approximation prorates team makes by minutes share.
        rates.ratio(
            pl.col("ast"),
            (pl.col("minutes") / (pl.col("team_minutes") / 5.0)) * pl.col("team_fgm")
            - pl.col("fgm"),
        ).alias("ast_pct"),
        (pl.col("start_year") - pl.col("age")).alias("birth_year"),
        pl.col("start_year").cast(pl.Int32).alias("season_order"),
        (pl.col("minutes") >= MIN_MINUTES_QUALIFIED).alias("qualified"),
    )

    if official is not None and not official.is_empty():
        enriched = enriched.join(official, on=["season_id", "source_player_id"], how="left")

    return enriched.sort(["person_id", "season_order", "league"])


def standardize_within_league_season(
    player_seasons: pl.DataFrame, metrics: list[str]
) -> pl.DataFrame:
    """Add minutes-weighted z-scores computed within each league-season.

    Standardising within season is not cosmetic. Three-point rate in 2000-01
    and in 2024-25 describe materially different sports, and pooling them would
    make the first thing any model discovers be "which era is this".

    Weighting by minutes stops a twelfth man with 260 minutes from having the
    same influence on the league mean as a starter with 2,800.
    """
    qualified = player_seasons.filter(pl.col("qualified"))

    aggregations = []
    for metric in metrics:
        weight = pl.when(pl.col(metric).is_not_null()).then(pl.col("minutes")).otherwise(0.0)
        weighted_mean = (pl.col(metric).fill_null(0.0) * weight).sum() / weight.sum()
        aggregations.append(weighted_mean.alias(f"_{metric}_mean"))
        aggregations.append(pl.col(metric).std().alias(f"_{metric}_sd"))

    moments = qualified.group_by("season_id").agg(aggregations)
    out = player_seasons.join(moments, on="season_id", how="left")

    for metric in metrics:
        out = out.with_columns(
            pl.when(pl.col(f"_{metric}_sd") > 0)
            .then((pl.col(metric) - pl.col(f"_{metric}_mean")) / pl.col(f"_{metric}_sd"))
            .otherwise(None)
            .alias(f"z_{metric}")
        )

    return out.drop([c for c in out.columns if c.startswith("_")])


def build_transition_pairs(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Every observed league switch, as a (source season, target season) pair.

    A pair requires:

    * at least ``MIN_SOURCE_MINUTES`` in the source league that season,
    * at least ``MIN_TARGET_MINUTES`` in the target league,
    * a gap of one or two seasons,
    * and **no appearance in the target league during the source season**, so
      that a two-way contract splitting one year across two leagues is not
      counted as a transition.

    Both directions of every league combination are produced. Modelling only
    EuroLeague to NBA would leave far too few pairs to fit anything, and the
    reverse direction is selected in the opposite way, which is what makes the
    selection effect measurable rather than merely acknowledged.
    """
    eligible = player_seasons.filter(
        pl.col("person_id").is_not_null()
        & (pl.col("confidence") >= MODELLING_CONFIDENCE_FLOOR)
        & pl.col("minutes").is_not_null()
    ).select(
        "person_id",
        "league",
        "season_id",
        "season_order",
        "minutes",
        "age",
        "player_name",
    )

    source = eligible.filter(pl.col("minutes") >= MIN_SOURCE_MINUTES).rename(
        {
            "league": "source_league",
            "season_id": "source_season_id",
            "season_order": "source_season_order",
            "minutes": "source_minutes",
            "age": "source_age",
        }
    )
    target = (
        eligible.filter(pl.col("minutes") >= MIN_TARGET_MINUTES)
        .rename(
            {
                "league": "target_league",
                "season_id": "target_season_id",
                "season_order": "target_season_order",
                "minutes": "target_minutes",
                "age": "target_age",
            }
        )
        .drop("player_name")
    )

    pairs = (
        source.join(target, on="person_id", how="inner")
        .filter(pl.col("source_league") != pl.col("target_league"))
        .filter(
            (pl.col("target_season_order") - pl.col("source_season_order")).is_between(
                1, MAX_GAP_SEASONS
            )
        )
    )

    # Exclude anyone who was already playing in the target league during the
    # source season: that is a split season, not a move.
    already_there = eligible.select(
        pl.col("person_id"),
        pl.col("league").alias("target_league"),
        pl.col("season_order").alias("source_season_order"),
    ).unique()

    pairs = (
        pairs.join(
            already_there.with_columns(pl.lit(True).alias("_overlap")),
            on=["person_id", "target_league", "source_season_order"],
            how="left",
        )
        .filter(pl.col("_overlap").is_null())
        .drop("_overlap")
        .with_columns(
            (pl.col("target_season_order") - pl.col("source_season_order")).alias("gap_seasons_raw")
        )
    )

    # Reduce candidates to a matching: within a person and direction, each
    # source season and each target season is used at most once.
    #
    # Deduplicating on only one side is not enough, and both failures are real.
    # Two qualifying seasons before a move produce two rows sharing a *target*,
    # which duplicates the response variable. One source season with both a
    # one- and a two-season gap produces two rows sharing a *source*, which
    # counts the same departure twice. Greedy assignment by smallest gap
    # resolves both while still allowing a genuine second transition later in a
    # career (NBA -> EuroLeague -> NBA) to appear as its own pair.
    pairs = _greedy_match(pairs)

    return (
        pairs.with_columns(
            (pl.col("source_league") + "->" + pl.col("target_league")).alias("direction"),
            pl.col("gap_seasons_raw").alias("gap_seasons"),
        )
        .drop("gap_seasons_raw")
        .sort(["direction", "source_season_order", "person_id"])
    )


def _greedy_match(candidates: pl.DataFrame) -> pl.DataFrame:
    """Keep a one-to-one assignment of source seasons to target seasons.

    Sorted by smallest gap first, so the move is attributed to the season
    immediately preceding it rather than to an older one that happens to also
    qualify.
    """
    if candidates.is_empty():
        return candidates

    ordered = candidates.sort(
        ["person_id", "source_league", "target_league", "gap_seasons_raw", "target_season_order"]
    )

    used_sources: set[tuple[str, str, str]] = set()
    used_targets: set[tuple[str, str, str]] = set()
    keep: list[bool] = []

    for row in ordered.iter_rows(named=True):
        direction = (row["person_id"], row["source_league"], row["target_league"])
        source_key = (*direction, row["source_season_id"])
        target_key = (*direction, row["target_season_id"])

        if source_key in used_sources or target_key in used_targets:
            keep.append(False)
            continue

        used_sources.add(source_key)  # type: ignore[arg-type]
        used_targets.add(target_key)  # type: ignore[arg-type]
        keep.append(True)

    return ordered.filter(pl.Series("_keep", keep))


def summarise_pairs(pairs: pl.DataFrame) -> pl.DataFrame:
    """Pair counts per direction — the first real number this project produces."""
    if pairs.is_empty():
        return pl.DataFrame(schema={"direction": pl.Utf8, "n_pairs": pl.UInt32})
    return (
        pairs.group_by("direction")
        .agg(
            pl.len().alias("n_pairs"),
            pl.n_unique("person_id").alias("n_players"),
            pl.min("source_season_order").alias("first_season"),
            pl.max("source_season_order").alias("last_season"),
        )
        .sort("n_pairs", descending=True)
    )

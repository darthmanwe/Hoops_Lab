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

    # One pair per (person, target season, direction), keeping the smallest gap.
    #
    # Without this, a player with two qualifying seasons before he moved
    # produces two rows sharing a target season — the same landing observation
    # counted twice, with a duplicated response variable. Deduplicating on the
    # *target* rather than the source keeps each observed outcome once, while
    # still allowing a genuine second transition later in a career
    # (NBA -> EuroLeague -> NBA) to appear as its own pair.
    pairs = (
        pairs.sort(["person_id", "target_season_order", "gap_seasons_raw"])
        .group_by(["person_id", "target_season_id", "source_league", "target_league"])
        .first()
    )

    return (
        pairs.with_columns(
            (pl.col("source_league") + "->" + pl.col("target_league")).alias("direction"),
            pl.col("gap_seasons_raw").alias("gap_seasons"),
        )
        .drop("gap_seasons_raw")
        .sort(["direction", "source_season_order", "person_id"])
    )


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

"""Bronze payloads to typed, harmonised silver tables.

Silver holds **counting statistics only**, in one shared schema across all
three leagues. Derived rates are computed later, in gold, by a single
implementation — see :mod:`hoopslab.transform.rates` for why that separation
is load-bearing rather than tidiness.

This module imports no client library, so silver and gold can be rebuilt on a
machine that never installed the optional ``ingest`` extra.
"""

from __future__ import annotations

import logging

import pandas as pd
import polars as pl

from hoopslab.io.bronze import BronzeCache
from hoopslab.seasons import Season, seasons_for
from hoopslab.transform import names

log = logging.getLogger(__name__)

#: The harmonised player-season schema every league is mapped into.
PLAYER_SEASON_COLUMNS = [
    "season_id",
    "league",
    "start_year",
    "source_player_id",
    "player_name",
    "normalized_name",
    "match_key",
    "source_team_id",
    "team_name",
    "gp",
    "minutes",
    "pts",
    "fga",
    "fgm",
    "fg3a",
    "fg3m",
    "fta",
    "ftm",
    "oreb",
    "dreb",
    "reb",
    "ast",
    "tov",
    "stl",
    "blk",
    "pf",
    "age",
]


def _empty_player_season() -> pl.DataFrame:
    return pl.DataFrame(
        schema={c: pl.Utf8 if _is_text(c) else pl.Float64 for c in PLAYER_SEASON_COLUMNS}
    )


def _is_text(column: str) -> bool:
    return column in {
        "season_id",
        "league",
        "source_player_id",
        "player_name",
        "normalized_name",
        "match_key",
        "source_team_id",
        "team_name",
    }


# ---------------------------------------------------------------- NBA / G League


def nba_player_seasons(cache: BronzeCache, league: str = "NBA") -> pl.DataFrame:
    """Merge Base, Advanced and (for the NBA) Bio payloads into one row per player-season."""
    frames: list[pl.DataFrame] = []

    for season in seasons_for(league):  # type: ignore[arg-type]
        base = cache.load(
            "nba_stats",
            "player_season_stats",
            {
                "season": season.nba_stats_season,
                "measure_type": "Base",
                "league_id": "00" if league == "NBA" else "20",
            },
        )
        if base is None or base.empty:
            log.warning("no Base payload for %s", season.season_id)
            continue

        frame = _nba_base_to_silver(base, season)

        # Age comes from the bio endpoint, which is NBA-only. G League ages are
        # recovered later from the same person's NBA observation.
        bio = cache.load("nba_stats", "player_bio_stats", {"season": season.nba_stats_season})
        if bio is not None and not bio.empty and league == "NBA":
            ages = pl.from_pandas(bio[["PLAYER_ID", "AGE"]]).select(
                pl.col("PLAYER_ID").cast(pl.Utf8).alias("source_player_id"),
                pl.col("AGE").cast(pl.Float64).alias("age"),
            )
            frame = frame.drop("age").join(ages, on="source_player_id", how="left")

        frames.append(frame.select(PLAYER_SEASON_COLUMNS))

    if not frames:
        return _empty_player_season()
    return pl.concat(frames, how="vertical_relaxed")


def _nba_base_to_silver(base: pd.DataFrame, season: Season) -> pl.DataFrame:
    frame = pl.from_pandas(base)

    return frame.select(
        pl.lit(season.season_id).alias("season_id"),
        pl.lit(season.league).alias("league"),
        pl.lit(season.start_year).cast(pl.Float64).alias("start_year"),
        pl.col("PLAYER_ID").cast(pl.Utf8).alias("source_player_id"),
        pl.col("PLAYER_NAME").cast(pl.Utf8).alias("player_name"),
        pl.col("PLAYER_NAME")
        .cast(pl.Utf8)
        .map_elements(names.normalize_name, return_dtype=pl.Utf8)
        .alias("normalized_name"),
        pl.col("PLAYER_NAME")
        .cast(pl.Utf8)
        .map_elements(names.match_key, return_dtype=pl.Utf8)
        .alias("match_key"),
        pl.col("TEAM_ID").cast(pl.Utf8).alias("source_team_id"),
        pl.col("TEAM_ABBREVIATION").cast(pl.Utf8).alias("team_name"),
        pl.col("GP").cast(pl.Float64).alias("gp"),
        pl.col("MIN").cast(pl.Float64).alias("minutes"),
        pl.col("PTS").cast(pl.Float64).alias("pts"),
        pl.col("FGA").cast(pl.Float64).alias("fga"),
        pl.col("FGM").cast(pl.Float64).alias("fgm"),
        pl.col("FG3A").cast(pl.Float64).alias("fg3a"),
        pl.col("FG3M").cast(pl.Float64).alias("fg3m"),
        pl.col("FTA").cast(pl.Float64).alias("fta"),
        pl.col("FTM").cast(pl.Float64).alias("ftm"),
        pl.col("OREB").cast(pl.Float64).alias("oreb"),
        pl.col("DREB").cast(pl.Float64).alias("dreb"),
        pl.col("REB").cast(pl.Float64).alias("reb"),
        pl.col("AST").cast(pl.Float64).alias("ast"),
        pl.col("TOV").cast(pl.Float64).alias("tov"),
        pl.col("STL").cast(pl.Float64).alias("stl"),
        pl.col("BLK").cast(pl.Float64).alias("blk"),
        pl.col("PF").cast(pl.Float64).alias("pf"),
        pl.lit(None).cast(pl.Float64).alias("age"),
    )


def nba_official_rates(cache: BronzeCache, league: str = "NBA") -> pl.DataFrame:
    """The league's own USG%/TS%, carried through purely to validate ours.

    These are never served and never used as model features. A data-contract
    check compares them against the values :mod:`hoopslab.transform.rates`
    derives from counting stats; a divergence means the shared formula is
    wrong, which would otherwise be invisible inside a fitted coefficient.
    """
    frames: list[pl.DataFrame] = []

    for season in seasons_for(league):  # type: ignore[arg-type]
        advanced = cache.load(
            "nba_stats",
            "player_season_stats",
            {
                "season": season.nba_stats_season,
                "measure_type": "Advanced",
                "league_id": "00" if league == "NBA" else "20",
            },
        )
        if advanced is None or advanced.empty:
            continue

        frames.append(
            pl.from_pandas(advanced).select(
                pl.lit(season.season_id).alias("season_id"),
                pl.col("PLAYER_ID").cast(pl.Utf8).alias("source_player_id"),
                pl.col("USG_PCT").cast(pl.Float64).alias("official_usg_pct"),
                pl.col("TS_PCT").cast(pl.Float64).alias("official_ts_pct"),
                pl.col("AST_PCT").cast(pl.Float64).alias("official_ast_pct"),
                pl.col("OREB_PCT").cast(pl.Float64).alias("official_oreb_pct"),
                pl.col("DREB_PCT").cast(pl.Float64).alias("official_dreb_pct"),
            )
        )

    if not frames:
        return pl.DataFrame(
            schema={
                "season_id": pl.Utf8,
                "source_player_id": pl.Utf8,
                "official_usg_pct": pl.Float64,
                "official_ts_pct": pl.Float64,
                "official_ast_pct": pl.Float64,
                "official_oreb_pct": pl.Float64,
                "official_dreb_pct": pl.Float64,
            }
        )
    return pl.concat(frames, how="vertical_relaxed")


def team_seasons_from_players(player_seasons: pl.DataFrame) -> pl.DataFrame:
    """Team totals aggregated from player rows, for every league identically.

    This exists because the alternative — each league's own team endpoint —
    silently disagrees about what a "team minute" is. ``stats.nba.com`` reports
    team ``MIN`` as game-clock minutes (roughly 3,966 for a season), while
    summing player minutes gives roughly 19,830, five times larger. The usage
    formula's ``TmMP / 5`` term expects the latter.

    Mixing the two definitions across leagues produced usage rates that were
    correct within the NBA and five times too large in the EuroLeague — a
    discrepancy that correlates at 0.998 with the truth and would therefore
    have survived any eyeball check, while landing squarely inside the
    estimated translation coefficient.

    Deriving every denominator from the same player rows that supply the
    numerator removes the possibility by construction.
    """
    if player_seasons.is_empty():
        return pl.DataFrame()

    return player_seasons.group_by(["season_id", "source_team_id"]).agg(
        pl.first("league").alias("league"),
        pl.first("team_name").alias("team_name"),
        pl.max("gp").alias("team_gp"),
        pl.sum("minutes").alias("team_minutes"),
        pl.sum("fga").alias("team_fga"),
        pl.sum("fgm").alias("team_fgm"),
        pl.sum("fta").alias("team_fta"),
        pl.sum("tov").alias("team_tov"),
        pl.sum("pts").alias("team_pts"),
        pl.sum("ast").alias("team_ast"),
        pl.sum("oreb").alias("team_oreb"),
        pl.sum("dreb").alias("team_dreb"),
    )


def nba_team_seasons(cache: BronzeCache, league: str = "NBA") -> pl.DataFrame:
    """Official team totals from `stats.nba.com`.

    Retained only to validate :func:`team_seasons_from_players` — see the note
    there about the two incompatible definitions of team minutes. Not used as
    the usage-rate denominator.
    """
    frames: list[pl.DataFrame] = []

    for season in seasons_for(league):  # type: ignore[arg-type]
        base = cache.load(
            "nba_stats",
            "team_season_stats",
            {
                "season": season.nba_stats_season,
                "measure_type": "Base",
                "league_id": "00" if league == "NBA" else "20",
            },
        )
        if base is None or base.empty:
            continue

        frames.append(
            pl.from_pandas(base).select(
                pl.lit(season.season_id).alias("season_id"),
                pl.lit(season.league).alias("league"),
                pl.col("TEAM_ID").cast(pl.Utf8).alias("source_team_id"),
                pl.col("TEAM_NAME").cast(pl.Utf8).alias("team_name"),
                pl.col("GP").cast(pl.Float64).alias("team_gp"),
                pl.col("MIN").cast(pl.Float64).alias("team_minutes"),
                pl.col("FGA").cast(pl.Float64).alias("team_fga"),
                pl.col("FGM").cast(pl.Float64).alias("team_fgm"),
                pl.col("FTA").cast(pl.Float64).alias("team_fta"),
                pl.col("TOV").cast(pl.Float64).alias("team_tov"),
                pl.col("PTS").cast(pl.Float64).alias("team_pts"),
                pl.col("AST").cast(pl.Float64).alias("team_ast"),
                pl.col("OREB").cast(pl.Float64).alias("team_oreb"),
                pl.col("DREB").cast(pl.Float64).alias("team_dreb"),
            )
        )

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="vertical_relaxed")


# ------------------------------------------------------------------ EuroLeague


def euroleague_player_seasons(cache: BronzeCache) -> pl.DataFrame:
    """EuroLeague accumulated stats, mapped into the shared schema.

    Two source quirks are handled here:

    * Percentage columns arrive as **strings with a ``%`` suffix** (``"33.3%"``).
      They are dropped rather than parsed, because gold recomputes every rate
      from counting stats anyway.
    * ``minutesPlayed`` is a decimal number of minutes, not ``MM:SS``.
    """
    frames: list[pl.DataFrame] = []

    for season in seasons_for("EL"):
        raw = cache.load(
            "euroleague",
            "player_season_stats",
            {"season": season.euroleague_season, "statistic_mode": "Accumulated"},
        )
        if raw is None or raw.empty:
            log.warning("no EuroLeague payload for %s", season.season_id)
            continue

        frame = pl.from_pandas(raw)
        display = (
            pl.col("player.name")
            .cast(pl.Utf8)
            .map_elements(names.from_euroleague, return_dtype=pl.Utf8)
        )

        frames.append(
            frame.select(
                pl.lit(season.season_id).alias("season_id"),
                pl.lit("EL").alias("league"),
                pl.lit(season.start_year).cast(pl.Float64).alias("start_year"),
                pl.col("player.code").cast(pl.Utf8).alias("source_player_id"),
                display.alias("player_name"),
                display.map_elements(names.normalize_name, return_dtype=pl.Utf8).alias(
                    "normalized_name"
                ),
                display.map_elements(names.match_key, return_dtype=pl.Utf8).alias("match_key"),
                pl.col("player.team.code").cast(pl.Utf8).alias("source_team_id"),
                pl.col("player.team.name").cast(pl.Utf8).alias("team_name"),
                pl.col("gamesPlayed").cast(pl.Float64).alias("gp"),
                pl.col("minutesPlayed").cast(pl.Float64).alias("minutes"),
                pl.col("pointsScored").cast(pl.Float64).alias("pts"),
                (
                    pl.col("twoPointersAttempted").cast(pl.Float64)
                    + pl.col("threePointersAttempted").cast(pl.Float64)
                ).alias("fga"),
                (
                    pl.col("twoPointersMade").cast(pl.Float64)
                    + pl.col("threePointersMade").cast(pl.Float64)
                ).alias("fgm"),
                pl.col("threePointersAttempted").cast(pl.Float64).alias("fg3a"),
                pl.col("threePointersMade").cast(pl.Float64).alias("fg3m"),
                pl.col("freeThrowsAttempted").cast(pl.Float64).alias("fta"),
                pl.col("freeThrowsMade").cast(pl.Float64).alias("ftm"),
                pl.col("offensiveRebounds").cast(pl.Float64).alias("oreb"),
                pl.col("defensiveRebounds").cast(pl.Float64).alias("dreb"),
                pl.col("totalRebounds").cast(pl.Float64).alias("reb"),
                pl.col("assists").cast(pl.Float64).alias("ast"),
                pl.col("turnovers").cast(pl.Float64).alias("tov"),
                pl.col("steals").cast(pl.Float64).alias("stl"),
                pl.col("blocks").cast(pl.Float64).alias("blk"),
                pl.col("foulsCommited").cast(pl.Float64).alias("pf"),
                pl.col("player.age").cast(pl.Float64).alias("age"),
            )
        )

    if not frames:
        return _empty_player_season()
    return pl.concat(frames, how="vertical_relaxed").select(PLAYER_SEASON_COLUMNS)


def euroleague_team_seasons(cache: BronzeCache) -> pl.DataFrame:
    """EuroLeague team totals. See :func:`team_seasons_from_players`."""
    return team_seasons_from_players(euroleague_player_seasons(cache))

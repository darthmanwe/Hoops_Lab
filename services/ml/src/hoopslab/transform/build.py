"""Build silver and gold from bronze, then write the committed snapshot.

Runs entirely offline against cached payloads, so it can be re-run after any
change to the transform logic without touching a single source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from hoopslab.io.bronze import BronzeCache
from hoopslab.paths import DataPaths
from hoopslab.transform import crosswalk, gold, silver
from hoopslab.validate import contracts

log = logging.getLogger(__name__)

#: Metrics standardised within league-season and used by the translation model.
STANDARDIZED_METRICS = ["usg_pct", "ts_pct", "ast_pct", "tov_rate", "pts_per_75"]

#: Gold tables, in dependency order.
GOLD_TABLES = (
    "persons",
    "player_identities",
    "player_seasons",
    "team_seasons",
    "transition_pairs",
)


@dataclass
class BuildResult:
    tables: dict[str, pl.DataFrame]
    crosswalk_report: crosswalk.CrosswalkReport
    id_space: crosswalk.SharedIdSpaceEvidence

    def row_counts(self) -> dict[str, int]:
        return {name: frame.height for name, frame in self.tables.items()}


def build_gold(paths: DataPaths) -> BuildResult:
    cache = BronzeCache(paths.bronze)

    log.info("reading silver from bronze")
    nba_players = silver.nba_player_seasons(cache, "NBA")
    gl_players = silver.nba_player_seasons(cache, "GL")
    el_players = silver.euroleague_player_seasons(cache)

    official = silver.nba_official_rates(cache, "NBA")

    log.info(
        "silver: NBA %d, G League %d, EuroLeague %d player-seasons",
        nba_players.height,
        gl_players.height,
        el_players.height,
    )

    evidence = crosswalk.verify_shared_id_space(nba_players, gl_players)

    overrides = _load_overrides(paths)
    persons, identities, report = crosswalk.build_crosswalk(
        nba_players, gl_players, el_players, overrides
    )

    all_players = pl.concat([nba_players, gl_players, el_players], how="vertical_relaxed")
    # One definition of a team total, for every league, derived from the same
    # player rows that supply the numerator of each rate.
    all_teams = silver.team_seasons_from_players(all_players)

    player_seasons = gold.build_player_seasons(all_players, all_teams, identities, official)
    player_seasons = gold.standardize_within_league_season(player_seasons, STANDARDIZED_METRICS)

    pairs = gold.build_transition_pairs(player_seasons)

    tables = {
        "persons": persons,
        "player_identities": identities,
        "player_seasons": player_seasons,
        "team_seasons": all_teams,
        "transition_pairs": pairs,
    }
    return BuildResult(tables=tables, crosswalk_report=report, id_space=evidence)


def write_gold(result: BuildResult, paths: DataPaths, *, write_contracts: bool = True) -> None:
    paths.gold.mkdir(parents=True, exist_ok=True)

    for name in GOLD_TABLES:
        frame = result.tables[name]
        target = paths.gold / f"{name}.parquet"
        frame.write_parquet(target, compression="zstd", compression_level=9)

        if write_contracts:
            contracts.write(contracts.derive(name, frame), paths.contracts)

        log.info("wrote %s (%d rows, %.1f KB)", name, frame.height, target.stat().st_size / 1024)


def verify_gold(paths: DataPaths) -> list[str]:
    """Re-derive every contract and report differences. Empty means clean."""
    problems: list[str] = []

    for name in GOLD_TABLES:
        parquet = paths.gold / f"{name}.parquet"
        sidecar = paths.contracts / f"{name}.json"

        if not parquet.is_file():
            problems.append(f"{name}: gold table missing")
            continue
        if not sidecar.is_file():
            problems.append(f"{name}: contract sidecar missing")
            continue

        expected = contracts.TableContract.from_json(sidecar.read_text(encoding="utf-8"))
        actual = contracts.derive(name, pl.read_parquet(parquet))
        problems.extend(f"{name}: {issue}" for issue in contracts.compare(expected, actual))

    return problems


def _load_overrides(paths: DataPaths) -> pl.DataFrame:
    path = paths.crosswalk / "overrides.csv"
    if not path.is_file():
        return pl.DataFrame(
            schema={
                "euroleague_player_id": pl.Utf8,
                "nba_player_id": pl.Utf8,
                "note": pl.Utf8,
            }
        )
    return pl.read_csv(
        path, schema_overrides={"euroleague_player_id": pl.Utf8, "nba_player_id": pl.Utf8}
    )

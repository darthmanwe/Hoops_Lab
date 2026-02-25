from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from hoopslab.logging import setup_logging
from hoopslab.load.sql_writer import SQLBatchWriter

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/etl_out", help="Output directory for ETL artifacts")
    args = parser.parse_args()

    setup_logging()

    now = datetime.now(timezone.utc).isoformat()
    out_dir = Path(args.out)
    sql_path = out_dir / "d1_upload.sql"

    writer = SQLBatchWriter(sql_path)
    writer.begin()

    writer.insert_many_ignore(
        "leagues",
        [
            {"league_id": "NBA", "name": "National Basketball Association"},
            {"league_id": "EL", "name": "EuroLeague"},
        ],
        ["league_id", "name"],
    )

    writer.insert_many_ignore(
        "seasons",
        [
            {"season_id": "NBA_2025", "league_id": "NBA", "year_start": 2024, "year_end": 2025},
            {"season_id": "EL_2025", "league_id": "EL", "year_start": 2024, "year_end": 2025},
        ],
        ["season_id", "league_id", "year_start", "year_end"],
    )

    writer.insert_many_ignore(
        "teams",
        [
            {
                "team_id": "NBA_1610612747",
                "league_id": "NBA",
                "season_id": "NBA_2025",
                "name": "Los Angeles Lakers",
                "abbrev": "LAL",
                "city": "Los Angeles",
                "country": "USA",
                "home_lat": 34.0522,
                "home_lon": -118.2437,
            },
            {
                "team_id": "NBA_1610612738",
                "league_id": "NBA",
                "season_id": "NBA_2025",
                "name": "Boston Celtics",
                "abbrev": "BOS",
                "city": "Boston",
                "country": "USA",
                "home_lat": 42.3601,
                "home_lon": -71.0589,
            },
            {
                "team_id": "EL_100",
                "league_id": "EL",
                "season_id": "EL_2025",
                "name": "Anadolu Efes",
                "abbrev": "EFS",
                "city": "Istanbul",
                "country": "Turkey",
                "home_lat": 41.0082,
                "home_lon": 28.9784,
            },
            {
                "team_id": "EL_200",
                "league_id": "EL",
                "season_id": "EL_2025",
                "name": "Real Madrid",
                "abbrev": "RMB",
                "city": "Madrid",
                "country": "Spain",
                "home_lat": 40.4168,
                "home_lon": -3.7038,
            },
        ],
        [
            "team_id",
            "league_id",
            "season_id",
            "name",
            "abbrev",
            "city",
            "country",
            "home_lat",
            "home_lon",
        ],
    )

    writer.insert_many_ignore(
        "players",
        [
            {"player_id": "NBA_201939", "league_id": "NBA", "name": "Stephen Curry", "position": "G", "nationality": "USA"},
            {"player_id": "NBA_2544", "league_id": "NBA", "name": "LeBron James", "position": "F", "nationality": "USA"},
            {"player_id": "EL_9001", "league_id": "EL", "name": "Shane Larkin", "position": "G", "nationality": "Turkey"},
            {"player_id": "EL_9002", "league_id": "EL", "name": "Walter Tavares", "position": "C", "nationality": "Cape Verde"},
        ],
        ["player_id", "league_id", "name", "position", "nationality"],
    )

    writer.insert_many_ignore(
        "games",
        [
            {
                "game_id": "NBA_0001",
                "league_id": "NBA",
                "season_id": "NBA_2025",
                "game_date": "2025-11-20",
                "home_team_id": "NBA_1610612738",
                "away_team_id": "NBA_1610612747",
                "home_score": 112,
                "away_score": 108,
                "venue": "TD Garden",
                "attendance": None,
            },
            {
                "game_id": "EL_0001",
                "league_id": "EL",
                "season_id": "EL_2025",
                "game_date": "2025-11-21",
                "home_team_id": "EL_100",
                "away_team_id": "EL_200",
                "home_score": 87,
                "away_score": 90,
                "venue": "Sinan Erdem Dome",
                "attendance": None,
            },
        ],
        [
            "game_id",
            "league_id",
            "season_id",
            "game_date",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
            "venue",
            "attendance",
        ],
    )

    # Reset evolving seed-derived tables so reruns refresh values.
    writer.write_sql("DELETE FROM boxscore_lines;")
    writer.write_sql("DELETE FROM player_season_features;")
    writer.write_sql("DELETE FROM nba_gravity;")
    writer.write_sql("DELETE FROM team_gravity_effect;")
    writer.write_sql("DELETE FROM team_fatigue_effect;")
    writer.write_sql("DELETE FROM game_fatigue_flags;")

    writer.insert_many_ignore(
        "boxscore_lines",
        [
            {"game_id": "NBA_0001", "player_id": "NBA_2544", "team_id": "NBA_1610612747", "minutes": 36, "pts": 28, "ast": 8, "reb": 7},
            {"game_id": "NBA_0001", "player_id": "NBA_201939", "team_id": "NBA_1610612738", "minutes": 34, "pts": 31, "ast": 6, "reb": 5},
            {"game_id": "EL_0001", "player_id": "EL_9001", "team_id": "EL_100", "minutes": 32, "pts": 24, "ast": 9, "reb": 3},
            {"game_id": "EL_0001", "player_id": "EL_9002", "team_id": "EL_200", "minutes": 29, "pts": 18, "ast": 2, "reb": 11},
        ],
        ["game_id", "player_id", "team_id", "minutes", "pts", "ast", "reb"],
    )

    writer.insert_many_ignore(
        "player_season_features",
        [
            {
                "season_id": "NBA_2025",
                "player_id": "NBA_201939",
                "team_id": "NBA_1610612738",
                "gp": 1,
                "minutes": 34,
                "usage_proxy": 0.31,
                "ts_proxy": 0.64,
                "ast_rate_proxy": 0.23,
                "tov_rate_proxy": 0.11,
                "reb_share_proxy": 0.08,
                "clutch_impact": 0.72,
                "archetype_vector_json": "[0.31,0.64,0.23,0.11,0.08]",
            },
            {
                "season_id": "NBA_2025",
                "player_id": "NBA_2544",
                "team_id": "NBA_1610612747",
                "gp": 1,
                "minutes": 36,
                "usage_proxy": 0.33,
                "ts_proxy": 0.61,
                "ast_rate_proxy": 0.28,
                "tov_rate_proxy": 0.12,
                "reb_share_proxy": 0.12,
                "clutch_impact": 0.69,
                "archetype_vector_json": "[0.33,0.61,0.28,0.12,0.12]",
            },
            {
                "season_id": "EL_2025",
                "player_id": "EL_9001",
                "team_id": "EL_100",
                "gp": 1,
                "minutes": 32,
                "usage_proxy": 0.30,
                "ts_proxy": 0.59,
                "ast_rate_proxy": 0.32,
                "tov_rate_proxy": 0.10,
                "reb_share_proxy": 0.06,
                "clutch_impact": 0.67,
                "archetype_vector_json": "[0.30,0.59,0.32,0.10,0.06]",
            },
            {
                "season_id": "EL_2025",
                "player_id": "EL_9002",
                "team_id": "EL_200",
                "gp": 1,
                "minutes": 29,
                "usage_proxy": 0.24,
                "ts_proxy": 0.62,
                "ast_rate_proxy": 0.09,
                "tov_rate_proxy": 0.15,
                "reb_share_proxy": 0.21,
                "clutch_impact": 0.58,
                "archetype_vector_json": "[0.24,0.62,0.09,0.15,0.21]",
            },
        ],
        [
            "season_id",
            "player_id",
            "team_id",
            "gp",
            "minutes",
            "usage_proxy",
            "ts_proxy",
            "ast_rate_proxy",
            "tov_rate_proxy",
            "reb_share_proxy",
            "clutch_impact",
            "archetype_vector_json",
        ],
    )

    writer.insert_many_ignore(
        "nba_gravity",
        [
            {
                "season_id": "NBA_2025",
                "player_id": "NBA_201939",
                "gravity_overall": 82.4,
                "gravity_on_ball": 79.1,
                "gravity_off_ball": 88.7,
                "updated_at": now,
            },
            {
                "season_id": "NBA_2025",
                "player_id": "NBA_2544",
                "gravity_overall": 74.2,
                "gravity_on_ball": 81.0,
                "gravity_off_ball": 62.5,
                "updated_at": now,
            },
        ],
        ["season_id", "player_id", "gravity_overall", "gravity_on_ball", "gravity_off_ball", "updated_at"],
    )

    writer.insert_many_ignore(
        "team_gravity_effect",
        [
            {
                "season_id": "NBA_2025",
                "team_id": "NBA_1610612738",
                "team_gravity_load": 77.8,
                "gravity_adjusted_offense": 118.3,
                "gravity_spillover": 0.22,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
            {
                "season_id": "NBA_2025",
                "team_id": "NBA_1610612747",
                "team_gravity_load": 72.6,
                "gravity_adjusted_offense": 114.7,
                "gravity_spillover": 0.18,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
        ],
        [
            "season_id",
            "team_id",
            "team_gravity_load",
            "gravity_adjusted_offense",
            "gravity_spillover",
            "model_version",
            "computed_at",
        ],
    )

    writer.insert_many_ignore(
        "team_fatigue_effect",
        [
            {
                "season_id": "NBA_2025",
                "team_id": "NBA_1610612738",
                "fatigue_score": 0.34,
                "rest_disadvantage_games": 12,
                "travel_km": 41500,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
            {
                "season_id": "NBA_2025",
                "team_id": "NBA_1610612747",
                "fatigue_score": 0.41,
                "rest_disadvantage_games": 15,
                "travel_km": 46000,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
            {
                "season_id": "EL_2025",
                "team_id": "EL_100",
                "fatigue_score": 0.29,
                "rest_disadvantage_games": 7,
                "travel_km": 21000,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
            {
                "season_id": "EL_2025",
                "team_id": "EL_200",
                "fatigue_score": 0.25,
                "rest_disadvantage_games": 6,
                "travel_km": 19800,
                "model_version": "v0_bootstrap",
                "computed_at": now,
            },
        ],
        [
            "season_id",
            "team_id",
            "fatigue_score",
            "rest_disadvantage_games",
            "travel_km",
            "model_version",
            "computed_at",
        ],
    )

    writer.insert_many_ignore(
        "game_fatigue_flags",
        [
            {
                "game_id": "NBA_0001",
                "home_fatigue_score": 0.34,
                "away_fatigue_score": 0.41,
                "rest_disadvantage_flag": 1,
                "travel_disadvantage_flag": 1,
            },
            {
                "game_id": "EL_0001",
                "home_fatigue_score": 0.29,
                "away_fatigue_score": 0.25,
                "rest_disadvantage_flag": 0,
                "travel_disadvantage_flag": 0,
            },
        ],
        [
            "game_id",
            "home_fatigue_score",
            "away_fatigue_score",
            "rest_disadvantage_flag",
            "travel_disadvantage_flag",
        ],
    )

    writer.insert_many_ignore(
        "etl_runs",
        [{"run_id": f"bootstrap_{now}", "started_at": now, "finished_at": now, "status": "success", "notes": "bootstrap artifact run"}],
        ["run_id", "started_at", "finished_at", "status", "notes"],
    )

    writer.commit()
    log.info("Generated ETL SQL artifact at %s", sql_path)


if __name__ == "__main__":
    main()

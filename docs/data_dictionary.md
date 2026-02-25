# Data Dictionary

## Core IDs

- `league_id`: `NBA` or `EL`
- `season_id`: format `<LEAGUE>_<YEAR>` (for example `NBA_2025`)
- canonical IDs are prefixed (`NBA_...`, `EL_...`)

## Tables

- `leagues`: static league registry
- `seasons`: season registry per league
- `teams`: canonical team metadata + location for travel features
- `players`: canonical player registry
- `games`: game-level metadata and scores
- `boxscore_lines`: one row per player-game
- `shots`: optional shot-level event data
- `player_season_features`: derived player-season modeling features
- `nba_gravity`: NBA gravity metrics (`-100` to `100`, `0` league average)
- `team_gravity_effect`: team-level gravity model outputs
- `team_fatigue_effect`: season-level fatigue and travel-derived impact by team
- `game_fatigue_flags`: per-game fatigue disadvantage flags
- `player_shot_profiles`: player shot mix and efficiency splits
- `team_shot_profiles`: team shot mix and efficiency splits
- `game_momentum`: game-level momentum and clutch swing metrics
- `player_translation_metrics`: cross-league standardized/translated player metrics
- `team_play_style_metrics`: transition (`<=8s`) vs set-play (`>=8s`) performance
- `lineup_impact_snapshots`: five-player comp snapshots with gravity and fit metrics
- `etl_runs`: ETL observability ledger

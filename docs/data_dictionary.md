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
- `etl_runs`: ETL observability ledger

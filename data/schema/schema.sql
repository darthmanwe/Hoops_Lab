PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS leagues (
  league_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
  season_id TEXT PRIMARY KEY,
  league_id TEXT NOT NULL,
  year_start INTEGER NOT NULL,
  year_end INTEGER NOT NULL,
  FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS teams (
  team_id TEXT PRIMARY KEY,
  league_id TEXT NOT NULL,
  season_id TEXT,
  name TEXT NOT NULL,
  abbrev TEXT,
  city TEXT,
  country TEXT,
  home_lat REAL,
  home_lon REAL,
  FOREIGN KEY (league_id) REFERENCES leagues(league_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS players (
  player_id TEXT PRIMARY KEY,
  league_id TEXT NOT NULL,
  name TEXT NOT NULL,
  birthdate TEXT,
  height_cm REAL,
  weight_kg REAL,
  position TEXT,
  nationality TEXT,
  FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY,
  league_id TEXT NOT NULL,
  season_id TEXT NOT NULL,
  game_date TEXT NOT NULL,
  home_team_id TEXT NOT NULL,
  away_team_id TEXT NOT NULL,
  home_score INTEGER,
  away_score INTEGER,
  venue TEXT,
  attendance INTEGER,
  FOREIGN KEY (league_id) REFERENCES leagues(league_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id),
  FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
  FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS boxscore_lines (
  game_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  minutes REAL,
  pts INTEGER,
  ast INTEGER,
  reb INTEGER,
  fgm INTEGER,
  fga INTEGER,
  fg3m INTEGER,
  fg3a INTEGER,
  ftm INTEGER,
  fta INTEGER,
  tov INTEGER,
  stl INTEGER,
  blk INTEGER,
  pf INTEGER,
  plus_minus REAL,
  PRIMARY KEY (game_id, player_id),
  FOREIGN KEY (game_id) REFERENCES games(game_id),
  FOREIGN KEY (player_id) REFERENCES players(player_id),
  FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS shots (
  league_id TEXT NOT NULL,
  game_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  period INTEGER,
  clock_seconds INTEGER,
  shot_made INTEGER,
  shot_value INTEGER,
  x REAL,
  y REAL,
  zone TEXT,
  is_assisted INTEGER,
  PRIMARY KEY (league_id, game_id, player_id, period, clock_seconds, x, y),
  FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS player_season_features (
  season_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  team_id TEXT,
  gp INTEGER,
  minutes REAL,
  usage_proxy REAL,
  ts_proxy REAL,
  ast_rate_proxy REAL,
  tov_rate_proxy REAL,
  reb_share_proxy REAL,
  rim_rate REAL,
  mid_rate REAL,
  corner3_rate REAL,
  abv3_rate REAL,
  clutch_impact REAL,
  fatigue_sensitivity REAL,
  archetype_vector_json TEXT,
  PRIMARY KEY (season_id, player_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id),
  FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS nba_gravity (
  season_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  gravity_overall REAL,
  gravity_on_ball REAL,
  gravity_off_ball REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (season_id, player_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id),
  FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS team_gravity_effect (
  season_id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  team_gravity_load REAL,
  gravity_adjusted_offense REAL,
  gravity_spillover REAL,
  model_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (season_id, team_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id),
  FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS team_fatigue_effect (
  season_id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  fatigue_score REAL,
  rest_disadvantage_games INTEGER,
  travel_km INTEGER,
  model_version TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (season_id, team_id),
  FOREIGN KEY (season_id) REFERENCES seasons(season_id),
  FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS game_fatigue_flags (
  game_id TEXT PRIMARY KEY,
  home_fatigue_score REAL,
  away_fatigue_score REAL,
  rest_disadvantage_flag INTEGER,
  travel_disadvantage_flag INTEGER,
  FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS etl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_players_name ON players(name);
CREATE INDEX IF NOT EXISTS idx_players_league ON players(league_id);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season_id);
CREATE INDEX IF NOT EXISTS idx_teams_season ON teams(season_id);
CREATE INDEX IF NOT EXISTS idx_boxscore_team ON boxscore_lines(team_id);
CREATE INDEX IF NOT EXISTS idx_player_features_team ON player_season_features(team_id);
CREATE INDEX IF NOT EXISTS idx_team_fatigue_season ON team_fatigue_effect(season_id);

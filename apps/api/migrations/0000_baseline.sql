CREATE TABLE `archetype_definitions` (
	`model_version` text NOT NULL,
	`cluster` integer NOT NULL,
	`n_members` integer NOT NULL,
	`top_features` text NOT NULL,
	`exemplars` text NOT NULL,
	`stability_jaccard` real NOT NULL,
	`reportable` integer NOT NULL,
	PRIMARY KEY(`model_version`, `cluster`)
);

CREATE TABLE `data_snapshots` (
	`snapshot_id` text PRIMARY KEY NOT NULL,
	`built_at` text NOT NULL,
	`git_sha` text NOT NULL,
	`n_player_seasons` integer NOT NULL,
	`n_persons` integer NOT NULL,
	`n_transition_pairs` integer NOT NULL
);

CREATE TABLE `model_evaluations` (
	`model_version` text NOT NULL,
	`metric` text NOT NULL,
	`fold` text NOT NULL,
	`n_evaluated` integer NOT NULL,
	`mae` real NOT NULL,
	`mae_ci_low` real,
	`mae_ci_high` real,
	`baseline_name` text NOT NULL,
	`baseline_mae` real NOT NULL,
	`shuffled_mae` real,
	`beats_best_baseline` integer NOT NULL,
	`skill_vs_best` real NOT NULL,
	PRIMARY KEY(`model_version`, `metric`, `fold`, `baseline_name`),
	FOREIGN KEY (`model_version`) REFERENCES `model_versions`(`model_version`) ON UPDATE no action ON DELETE no action
);

CREATE TABLE `model_versions` (
	`model_version` text PRIMARY KEY NOT NULL,
	`model_name` text NOT NULL,
	`trained_at` text NOT NULL,
	`git_sha` text NOT NULL,
	`run_id` text NOT NULL,
	`seed` integer NOT NULL,
	`primary_metric` text NOT NULL,
	`primary_value` real NOT NULL,
	`primary_ci_low` real,
	`primary_ci_high` real,
	`n_train` integer NOT NULL,
	`n_evaluated` integer NOT NULL,
	`card_path` text NOT NULL
);

CREATE TABLE `persons` (
	`person_id` text PRIMARY KEY NOT NULL,
	`display_name` text,
	`name_normalized` text,
	`birth_year` integer,
	`leagues` text NOT NULL
);

CREATE INDEX `idx_persons_name` ON `persons` (`name_normalized`);
CREATE TABLE `player_archetypes` (
	`season_id` text NOT NULL,
	`person_id` text NOT NULL,
	`league` text NOT NULL,
	`cluster` integer NOT NULL,
	`model_version` text NOT NULL,
	PRIMARY KEY(`season_id`, `person_id`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_archetypes_cluster` ON `player_archetypes` (`model_version`,`cluster`);
CREATE TABLE `player_comps` (
	`season_id` text NOT NULL,
	`person_id` text NOT NULL,
	`rank` integer NOT NULL,
	`neighbour_person_id` text NOT NULL,
	`distance` real NOT NULL,
	`model_version` text NOT NULL,
	PRIMARY KEY(`season_id`, `person_id`, `rank`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_comps_person` ON `player_comps` (`person_id`);
CREATE TABLE `player_identities` (
	`league` text NOT NULL,
	`source_player_id` text NOT NULL,
	`person_id` text NOT NULL,
	`match_method` text NOT NULL,
	`confidence` real NOT NULL,
	PRIMARY KEY(`league`, `source_player_id`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_identities_person` ON `player_identities` (`person_id`);
CREATE TABLE `player_seasons` (
	`season_id` text NOT NULL,
	`person_id` text NOT NULL,
	`league` text NOT NULL,
	`team_name` text,
	`games_played` integer,
	`minutes` real,
	`usg_pct` real,
	`ts_pct` real,
	`ast_pct` real,
	`tov_rate` real,
	`fg3a_rate` real,
	`pts_per_75` real,
	`ast_per_75` real,
	`reb_per_75` real,
	`age` real,
	`qualified` integer NOT NULL,
	`snapshot_id` text NOT NULL,
	PRIMARY KEY(`season_id`, `person_id`),
	FOREIGN KEY (`season_id`) REFERENCES `seasons`(`season_id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_player_seasons_person` ON `player_seasons` (`person_id`);
CREATE INDEX `idx_player_seasons_league` ON `player_seasons` (`league`,`season_id`);
CREATE TABLE `player_shooting` (
	`season_id` text NOT NULL,
	`person_id` text NOT NULL,
	`fg3a` real NOT NULL,
	`fg3a_per_75` real NOT NULL,
	`fg3_pct_raw` real,
	`fg3_pct_shrunk` real NOT NULL,
	`shrinkage_weight` real NOT NULL,
	`prior_mean` real NOT NULL,
	`spacing_score` real NOT NULL,
	`reportable` integer NOT NULL,
	`model_version` text NOT NULL,
	PRIMARY KEY(`season_id`, `person_id`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_shooting_season` ON `player_shooting` (`season_id`,`spacing_score`);
CREATE TABLE `seasons` (
	`season_id` text PRIMARY KEY NOT NULL,
	`league` text NOT NULL,
	`start_year` integer NOT NULL,
	`season_order` integer NOT NULL,
	`label` text NOT NULL
);

CREATE TABLE `selection_summaries` (
	`model_version` text NOT NULL,
	`direction` text NOT NULL,
	`metric` text NOT NULL,
	`n_movers` integer NOT NULL,
	`n_league` integer NOT NULL,
	`mover_mean_z` real NOT NULL,
	`league_mean_z` real NOT NULL,
	`gap_sd` real NOT NULL,
	PRIMARY KEY(`model_version`, `direction`, `metric`),
	FOREIGN KEY (`model_version`) REFERENCES `model_versions`(`model_version`) ON UPDATE no action ON DELETE no action
);

CREATE TABLE `translation_predictions` (
	`person_id` text NOT NULL,
	`source_season_id` text NOT NULL,
	`target_season_id` text NOT NULL,
	`direction` text NOT NULL,
	`metric` text NOT NULL,
	`source_value` real NOT NULL,
	`predicted` real NOT NULL,
	`pi80_low` real NOT NULL,
	`pi80_high` real NOT NULL,
	`pi95_low` real NOT NULL,
	`pi95_high` real NOT NULL,
	`actual_value` real,
	`baseline_league_mean` real NOT NULL,
	`baseline_z_preservation` real NOT NULL,
	`baseline_folk_rule` real NOT NULL,
	`model_version` text NOT NULL,
	PRIMARY KEY(`person_id`, `source_season_id`, `direction`, `metric`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`model_version`) REFERENCES `model_versions`(`model_version`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_translation_direction` ON `translation_predictions` (`direction`,`metric`);
CREATE INDEX `idx_translation_person` ON `translation_predictions` (`person_id`);
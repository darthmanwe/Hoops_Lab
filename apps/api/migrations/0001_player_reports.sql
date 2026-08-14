CREATE TABLE `player_reports` (
	`person_id` text NOT NULL,
	`target_season_id` text NOT NULL,
	`direction` text NOT NULL,
	`named` integer NOT NULL,
	`headline` text NOT NULL,
	`claims` text NOT NULL,
	`evidence` text NOT NULL,
	`numbers_traced` integer NOT NULL,
	`numbers_total` integer NOT NULL,
	`grounded` integer NOT NULL,
	`checks` text NOT NULL,
	`report_model` text NOT NULL,
	`generated_at` text NOT NULL,
	`snapshot_id` text NOT NULL,
	PRIMARY KEY(`person_id`, `target_season_id`, `named`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_reports_grounded` ON `player_reports` (`grounded`);
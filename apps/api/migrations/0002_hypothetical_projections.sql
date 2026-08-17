CREATE TABLE `hypothetical_projections` (
	`person_id` text NOT NULL,
	`source_season_id` text NOT NULL,
	`source_season_order` integer NOT NULL,
	`source_league` text NOT NULL,
	`target_season_id` text NOT NULL,
	`direction` text NOT NULL,
	`metric` text NOT NULL,
	`source_value` real NOT NULL,
	`z_source` real NOT NULL,
	`predicted` real NOT NULL,
	`pi80_low` real NOT NULL,
	`pi80_high` real NOT NULL,
	`pi95_low` real NOT NULL,
	`pi95_high` real NOT NULL,
	`in_support` integer NOT NULL,
	`moved_before` integer NOT NULL,
	`minutes` real NOT NULL,
	`age` real,
	`model_version` text NOT NULL,
	`snapshot_id` text NOT NULL,
	PRIMARY KEY(`person_id`, `direction`, `metric`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_hypothetical_rank` ON `hypothetical_projections` (`direction`,`predicted`);
CREATE INDEX `idx_hypothetical_recent` ON `hypothetical_projections` (`direction`,`source_season_order`);
-- Adds `support_n_movers`: how many observed transfers a direction's intercept
-- was fitted from. Ranges from 134 (NBA to G League) down to 14 (EuroLeague to
-- G League), and it is what tells a reader how much weight a row deserves.
--
-- Recreated rather than altered. SQLite rejects `ADD COLUMN ... NOT NULL` with
-- no default whatever the row count, and a default here would have to be a
-- mover count that is not true of any direction. Every row in this table is
-- derived and the loader truncates it before each insert, so there is nothing
-- to preserve.
DROP TABLE IF EXISTS `hypothetical_projections`;

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
	`support_n_movers` integer NOT NULL,
	`model_version` text NOT NULL,
	`snapshot_id` text NOT NULL,
	PRIMARY KEY(`person_id`, `direction`, `metric`),
	FOREIGN KEY (`person_id`) REFERENCES `persons`(`person_id`) ON UPDATE no action ON DELETE no action
);

CREATE INDEX `idx_hypothetical_rank` ON `hypothetical_projections` (`direction`,`predicted`);
CREATE INDEX `idx_hypothetical_recent` ON `hypothetical_projections` (`direction`,`source_season_order`);

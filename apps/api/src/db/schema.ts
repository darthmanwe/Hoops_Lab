import { index, integer, primaryKey, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

/**
 * The serving schema, and the single source of truth for it.
 *
 * Drizzle generates the migrations, the query types and the zod row schemas
 * from this file, so the database, the Worker and the OpenAPI document cannot
 * disagree about what a row looks like.
 *
 * This is deliberately *not* the analytics schema. Feature frames are wide and
 * change with every experiment; these tables are narrow, indexed and stable.
 * Forcing the former into TypeScript would make every modelling change require
 * an edit here.
 */

/**
 * A human being.
 *
 * The fix for the defect that made the whole project impossible: the previous
 * schema hung `league_id` off the player, so a person who moved between
 * leagues became two unrelated rows and there was no key on which "the same
 * person in both leagues" existed — precisely the join the flagship model
 * needs.
 */
export const persons = sqliteTable(
  "persons",
  {
    personId: text("person_id").primaryKey(),
    displayName: text("display_name"),
    /** Lowercased and de-accented, so "Jokic" finds "Jokić". */
    nameNormalized: text("name_normalized"),
    birthYear: integer("birth_year"),
    /** Which leagues this person appears in, e.g. "EL+NBA". */
    leagues: text("leagues").notNull(),
  },
  (table) => [index("idx_persons_name").on(table.nameNormalized)]
);

/** Maps each source system's id onto a person, with an audit trail. */
export const playerIdentities = sqliteTable(
  "player_identities",
  {
    league: text("league").notNull(),
    sourcePlayerId: text("source_player_id").notNull(),
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    /** How the link was made: anchor, shared_nba_person_id, name_and_age, ... */
    matchMethod: text("match_method").notNull(),
    /** Below 0.8 is reported but excluded from the modelling cohort. */
    confidence: real("confidence").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.league, table.sourcePlayerId] }),
    index("idx_identities_person").on(table.personId),
  ]
);

/**
 * Season identifiers, carrying an integer sort key.
 *
 * `ORDER BY season_id DESC` on the old text column compared "NBA_2025" against
 * "EL_2025" lexically, so "latest season" was wrong for exactly the
 * cross-league players this project studies.
 */
export const seasons = sqliteTable("seasons", {
  seasonId: text("season_id").primaryKey(),
  league: text("league").notNull(),
  startYear: integer("start_year").notNull(),
  seasonOrder: integer("season_order").notNull(),
  label: text("label").notNull(),
});

/** Per-person, per-season rates. Every value computed in Python. */
export const playerSeasons = sqliteTable(
  "player_seasons",
  {
    seasonId: text("season_id")
      .notNull()
      .references(() => seasons.seasonId),
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    league: text("league").notNull(),
    teamName: text("team_name"),
    gamesPlayed: integer("games_played"),
    minutes: real("minutes"),
    usgPct: real("usg_pct"),
    tsPct: real("ts_pct"),
    astPct: real("ast_pct"),
    tovRate: real("tov_rate"),
    fg3aRate: real("fg3a_rate"),
    ptsPer75: real("pts_per_75"),
    astPer75: real("ast_per_75"),
    rebPer75: real("reb_per_75"),
    age: real("age"),
    /** Whether the season clears the minutes floor to be treated as a measurement. */
    qualified: integer("qualified", { mode: "boolean" }).notNull(),
    snapshotId: text("snapshot_id").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.seasonId, table.personId] }),
    index("idx_player_seasons_person").on(table.personId),
    index("idx_player_seasons_league").on(table.league, table.seasonId),
  ]
);

/**
 * The model registry. Every model-derived number in the database references a
 * row here, so "which version produced this?" always has an answer.
 *
 * The old schema had a `model_version` column that was always the string
 * "v0_bootstrap" and referenced nothing.
 */
export const modelVersions = sqliteTable("model_versions", {
  modelVersion: text("model_version").primaryKey(),
  modelName: text("model_name").notNull(),
  trainedAt: text("trained_at").notNull(),
  gitSha: text("git_sha").notNull(),
  runId: text("run_id").notNull(),
  seed: integer("seed").notNull(),
  /** Headline metric, its value and its interval, for display alongside output. */
  primaryMetric: text("primary_metric").notNull(),
  primaryValue: real("primary_value").notNull(),
  primaryCiLow: real("primary_ci_low"),
  primaryCiHigh: real("primary_ci_high"),
  nTrain: integer("n_train").notNull(),
  nEvaluated: integer("n_evaluated").notNull(),
  cardPath: text("card_path").notNull(),
});

/**
 * Translation predictions.
 *
 * The interval columns are `NOT NULL` on purpose: a point estimate physically
 * cannot be stored without one, so it cannot be served or displayed without
 * one either. The constraint enforces the modelling commitment rather than
 * relying on everyone downstream to remember it.
 */
export const translationPredictions = sqliteTable(
  "translation_predictions",
  {
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    sourceSeasonId: text("source_season_id").notNull(),
    targetSeasonId: text("target_season_id").notNull(),
    direction: text("direction").notNull(),
    metric: text("metric").notNull(),
    sourceValue: real("source_value").notNull(),
    predicted: real("predicted").notNull(),
    pi80Low: real("pi80_low").notNull(),
    pi80High: real("pi80_high").notNull(),
    pi95Low: real("pi95_low").notNull(),
    pi95High: real("pi95_high").notNull(),
    /** What actually happened, where the move is already in the past. */
    actualValue: real("actual_value"),
    baselineLeagueMean: real("baseline_league_mean").notNull(),
    baselineZPreservation: real("baseline_z_preservation").notNull(),
    baselineFolkRule: real("baseline_folk_rule").notNull(),
    modelVersion: text("model_version")
      .notNull()
      .references(() => modelVersions.modelVersion),
  },
  (table) => [
    primaryKey({
      columns: [table.personId, table.sourceSeasonId, table.direction, table.metric],
    }),
    index("idx_translation_direction").on(table.direction, table.metric),
    index("idx_translation_person").on(table.personId),
  ]
);

/** Per-fold backtest results, so the calibration page shows measured numbers. */
export const modelEvaluations = sqliteTable(
  "model_evaluations",
  {
    modelVersion: text("model_version")
      .notNull()
      .references(() => modelVersions.modelVersion),
    metric: text("metric").notNull(),
    /** "overall" for the pooled row, otherwise the evaluated season. */
    fold: text("fold").notNull(),
    nEvaluated: integer("n_evaluated").notNull(),
    mae: real("mae").notNull(),
    maeCiLow: real("mae_ci_low"),
    maeCiHigh: real("mae_ci_high"),
    baselineName: text("baseline_name").notNull(),
    baselineMae: real("baseline_mae").notNull(),
    shuffledMae: real("shuffled_mae"),
    /**
     * Whether the model beats the *best* baseline for this metric.
     *
     * Served, not just logged. A model that loses to the league average should
     * say so rather than let a caller assume that being published implies
     * being useful — which is exactly what the previous version invited.
     */
    beatsBestBaseline: integer("beats_best_baseline", { mode: "boolean" }).notNull(),
    /** Fractional error reduction against the best baseline; negative is worse. */
    skillVsBest: real("skill_vs_best").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.modelVersion, table.metric, table.fold, table.baselineName] }),
  ]
);

/** How selected the movers were. Served so the UI can show it, not hide it. */
export const selectionSummaries = sqliteTable(
  "selection_summaries",
  {
    modelVersion: text("model_version")
      .notNull()
      .references(() => modelVersions.modelVersion),
    direction: text("direction").notNull(),
    metric: text("metric").notNull(),
    nMovers: integer("n_movers").notNull(),
    nLeague: integer("n_league").notNull(),
    moverMeanZ: real("mover_mean_z").notNull(),
    leagueMeanZ: real("league_mean_z").notNull(),
    gapSd: real("gap_sd").notNull(),
  },
  (table) => [primaryKey({ columns: [table.modelVersion, table.direction, table.metric] })]
);

/** Identifies the committed data snapshot a deployment is serving. */
export const dataSnapshots = sqliteTable("data_snapshots", {
  snapshotId: text("snapshot_id").primaryKey(),
  builtAt: text("built_at").notNull(),
  gitSha: text("git_sha").notNull(),
  nPlayerSeasons: integer("n_player_seasons").notNull(),
  nPersons: integer("n_persons").notNull(),
  nTransitionPairs: integer("n_transition_pairs").notNull(),
});

/** Archetype assignment per player-season. Descriptive, never predictive. */
export const playerArchetypes = sqliteTable(
  "player_archetypes",
  {
    seasonId: text("season_id").notNull(),
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    league: text("league").notNull(),
    cluster: integer("cluster").notNull(),
    modelVersion: text("model_version").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.seasonId, table.personId] }),
    index("idx_archetypes_cluster").on(table.modelVersion, table.cluster),
  ]
);

/**
 * What each cluster is, and how much to trust it.
 *
 * `stabilityJaccard` and `reportable` are served rather than kept internal:
 * clusters are not equally real, and a label presented without its stability
 * implies a crispness the clustering does not have.
 */
export const archetypeDefinitions = sqliteTable(
  "archetype_definitions",
  {
    modelVersion: text("model_version").notNull(),
    cluster: integer("cluster").notNull(),
    nMembers: integer("n_members").notNull(),
    topFeatures: text("top_features").notNull(),
    exemplars: text("exemplars").notNull(),
    stabilityJaccard: real("stability_jaccard").notNull(),
    /** False means "read this as unclassified", not "a type we named". */
    reportable: integer("reportable", { mode: "boolean" }).notNull(),
  },
  (table) => [primaryKey({ columns: [table.modelVersion, table.cluster] })]
);

/**
 * Precomputed comparables, in the whitened archetype space.
 *
 * Computed in Python because the Worker gets 10 ms of CPU per request. The
 * previous version scanned an entire season table and ran cosine similarity
 * per call — survivable against four hardcoded players, impossible against six
 * hundred real ones.
 */
export const playerComps = sqliteTable(
  "player_comps",
  {
    seasonId: text("season_id").notNull(),
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    rank: integer("rank").notNull(),
    neighbourPersonId: text("neighbour_person_id").notNull(),
    distance: real("distance").notNull(),
    modelVersion: text("model_version").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.seasonId, table.personId, table.rank] }),
    index("idx_comps_person").on(table.personId),
  ]
);

/**
 * Three-point shooting threat, shrunk toward an empirical prior.
 *
 * This is what replaces "gravity". `shrinkageWeight` is served so a reader can
 * see how much of a number is the player's own attempts and how much is the
 * prior — a 40-attempt shooter is mostly prior, and that is the difference
 * between a measurement and an impression.
 */
export const playerShooting = sqliteTable(
  "player_shooting",
  {
    seasonId: text("season_id").notNull(),
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    fg3a: real("fg3a").notNull(),
    fg3aPer75: real("fg3a_per_75").notNull(),
    fg3PctRaw: real("fg3_pct_raw"),
    fg3PctShrunk: real("fg3_pct_shrunk").notNull(),
    shrinkageWeight: real("shrinkage_weight").notNull(),
    priorMean: real("prior_mean").notNull(),
    spacingScore: real("spacing_score").notNull(),
    /** False below the attempt floor: reported, but almost entirely prior. */
    reportable: integer("reportable", { mode: "boolean" }).notNull(),
    modelVersion: text("model_version").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.seasonId, table.personId] }),
    index("idx_shooting_season").on(table.seasonId, table.spacingScore),
  ]
);

/**
 * Grounded scouting reports, and the audit that says how far to trust each one.
 *
 * A report is model-written prose, which makes it the least verifiable thing
 * this API serves — so it is the only thing served with its own audit attached.
 * `numbersTraced` over `numbersTotal` is a count of numeric tokens in the prose
 * that resolve to a fact in the evidence the model was given; `grounded` is
 * whether every deterministic check passed. The UI renders those next to the
 * text rather than in a footnote, because a reader deciding whether to believe
 * a sentence needs the audit at the same moment as the sentence.
 *
 * `claims` is the structured report as JSON. It is stored whole rather than
 * normalised into a claims table because it is written once, read whole, and
 * never queried by claim — and D1 charges by the query, not by the row.
 */
export const playerReports = sqliteTable(
  "player_reports",
  {
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    targetSeasonId: text("target_season_id").notNull(),
    direction: text("direction").notNull(),
    /** True when the model was told the subject's name. See `anonymized`. */
    named: integer("named", { mode: "boolean" }).notNull(),
    headline: text("headline").notNull(),
    /** The full `ScoutingReport` as JSON: claims, their fact ids, confidence. */
    claims: text("claims").notNull(),
    /** The evidence bundle the report was written from, rendered as text. */
    evidence: text("evidence").notNull(),
    numbersTraced: integer("numbers_traced").notNull(),
    numbersTotal: integer("numbers_total").notNull(),
    /** False when any deterministic check failed; `checks` says which. */
    grounded: integer("grounded", { mode: "boolean" }).notNull(),
    checks: text("checks").notNull(),
    /** The model that wrote it, so a report is traceable to a generation. */
    reportModel: text("report_model").notNull(),
    generatedAt: text("generated_at").notNull(),
    snapshotId: text("snapshot_id").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.personId, table.targetSeasonId, table.named] }),
    index("idx_reports_grounded").on(table.grounded),
  ]
);

/**
 * What the model says about players who have *not* changed league.
 *
 * The point of the project, and the table that needs the most care. Every other
 * prediction here describes a transfer that happened and can be checked against
 * what the player actually did. These cannot: they are counterfactuals, and a
 * counterfactual has no actual column.
 *
 * Two flags carry the caveats that a number alone would hide.
 *
 * `inSupport` is false when the player's standing in their own league falls
 * outside the range where transferring players were actually observed. The
 * interval is derived from the residual spread *inside* the fitted range, so
 * for these rows it understates the real uncertainty — the model is
 * extrapolating and its error bars cannot know that. In practice the
 * highest-usage players in a league are exactly the ones that trips, which is
 * why the flag is served rather than the rows being quietly dropped.
 *
 * `movedBefore` marks a player with a cross-league transfer in some other
 * direction. They have been signed abroad before, which is different evidence
 * from a player with no such history.
 *
 * Usage rate only. True shooting is omitted because the model loses to
 * predicting the league average on it, and unlike an observed transition there
 * is no actual value beside it to expose that.
 */
export const hypotheticalProjections = sqliteTable(
  "hypothetical_projections",
  {
    personId: text("person_id")
      .notNull()
      .references(() => persons.personId),
    sourceSeasonId: text("source_season_id").notNull(),
    /** Integer key, because season ids do not sort correctly across leagues. */
    sourceSeasonOrder: integer("source_season_order").notNull(),
    sourceLeague: text("source_league").notNull(),
    /** The season the move is assumed into: the most recent one available. */
    targetSeasonId: text("target_season_id").notNull(),
    direction: text("direction").notNull(),
    metric: text("metric").notNull(),
    sourceValue: real("source_value").notNull(),
    zSource: real("z_source").notNull(),
    predicted: real("predicted").notNull(),
    pi80Low: real("pi80_low").notNull(),
    pi80High: real("pi80_high").notNull(),
    pi95Low: real("pi95_low").notNull(),
    pi95High: real("pi95_high").notNull(),
    /** False means the estimate is extrapolation; see the note above. */
    inSupport: integer("in_support", { mode: "boolean" }).notNull(),
    movedBefore: integer("moved_before", { mode: "boolean" }).notNull(),
    minutes: real("minutes").notNull(),
    age: real("age"),
    modelVersion: text("model_version").notNull(),
    snapshotId: text("snapshot_id").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.personId, table.direction, table.metric] }),
    index("idx_hypothetical_rank").on(table.direction, table.predicted),
    index("idx_hypothetical_recent").on(table.direction, table.sourceSeasonOrder),
  ]
);

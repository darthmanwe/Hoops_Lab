/**
 * The endpoint registry: one declaration per public path, and the only place
 * the API's surface is described.
 *
 * The previous version kept a hand-typed route list in `routes/root.ts` that
 * had already drifted from the real router. This array replaced it, and the `/`
 * listing and the reconstruction handlers are built from it — but for a while
 * this comment claimed drift was "not expressible", and that was wrong. Only
 * the pending and gone handlers are mounted from here; the live routers
 * register their own paths. `/models` and `/models/{modelVersion}/evaluation`
 * were served for months while `/` reported thirteen live endpoints and the
 * router answered fifteen.
 *
 * The reason it went unnoticed is worth stating, because it is the general
 * shape of the bug: `routes.test.ts` walked this array and asked whether the
 * router answered. Every declared path did. Nothing ever walked the router and
 * asked whether the registry declared it, so a route could only ever be missing
 * in the direction nobody looked. `registry.test.ts` now checks both.
 */

/** `pending` is coming back once its blocking phase lands; `gone` is not. */
export type EndpointState = "live" | "pending" | "gone";

export type PendingEndpoint = {
  path: string;
  state: "pending";
  /** What this path will return once it is backed by real, fitted output. */
  willServe: string;
  /** The roadmap phase that unblocks it. */
  blockedOn: string;
  /** What it used to do. Stated plainly, because it was not honest. */
  previously: string;
};

export type GoneEndpoint = {
  path: string;
  state: "gone";
  /** Why the underlying metric cannot exist, not merely why it is not built. */
  reason: string;
  /** The nearest honest thing a caller can use instead. */
  instead: string;
};

export type LiveEndpoint = {
  path: string;
  state: "live";
  description: string;
};

export type Endpoint = LiveEndpoint | PendingEndpoint | GoneEndpoint;

const SEED_DATA_NOTE =
  "Served values hand-written into the ETL as Python literals, presented as model output.";

export const ENDPOINTS: readonly Endpoint[] = [
  {
    path: "/health",
    state: "live",
    description: "Liveness plus real D1 and KV reachability checks.",
  },
  {
    path: "/",
    state: "live",
    description: "This listing, generated from the endpoint registry.",
  },

  // ---------------------------------------------------------------------
  // Real entity data. Blocked only on ingestion, not on any model.
  // ---------------------------------------------------------------------
  {
    path: "/players/search",
    state: "live",
    description:
      "Diacritic-insensitive search over 5,347 resolved people; cross-league players ranked first.",
  },
  {
    path: "/players/{personId}",
    state: "live",
    description:
      "A person's whole career across every league they appear in, with identity provenance.",
  },
  {
    path: "/teams/search",
    state: "pending",
    willServe: "Search over real NBA and EuroLeague franchises across seasons.",
    blockedOn: "phase-1-real-data",
    previously: "Searched a table containing four hand-written teams.",
  },
  {
    path: "/teams/{teamId}",
    state: "pending",
    willServe: "Team season ratings and pace computed from real game results.",
    blockedOn: "phase-1-real-data",
    previously: SEED_DATA_NOTE,
  },
  {
    path: "/games",
    state: "pending",
    willServe: "Real NBA (2013-14 onward) and EuroLeague (2007-08 onward) schedules and results.",
    blockedOn: "phase-1-real-data",
    previously: "Listed two hand-written games.",
  },
  {
    path: "/games/{gameId}",
    state: "pending",
    willServe: "Real box scores. Also fixes a bug that ran the same query twice per request.",
    blockedOn: "phase-1-real-data",
    previously: "Returned four hand-written box score lines.",
  },
  {
    path: "/compare",
    state: "pending",
    willServe: "Side-by-side real rate stats for two players, with each value's source season.",
    blockedOn: "phase-1-real-data",
    previously: SEED_DATA_NOTE,
  },

  // ---------------------------------------------------------------------
  // Model-backed. Blocked on a fitted model, not merely on data.
  // ---------------------------------------------------------------------
  {
    path: "/models",
    state: "live",
    description:
      "Every model version this API can serve, each with the data snapshot it was fitted on.",
  },
  {
    path: "/models/{modelVersion}/evaluation",
    state: "live",
    description:
      "One model's held-out metrics against all four baselines, plus the selection gaps " +
      "that condition them — including the metric it loses on.",
  },
  {
    path: "/players/{personId}/translation",
    state: "live",
    description:
      "Cross-league translation predictions, each with 80% and 95% intervals and its model version.",
  },
  {
    path: "/leaderboards/translation",
    state: "live",
    description:
      "Players ranked by projected translated production, with intervals and what actually happened.",
  },
  {
    path: "/projections",
    state: "live",
    description:
      "Projected production for players who have NOT changed league — the counterfactual " +
      "the model exists to answer, with an out-of-support flag on every row.",
  },
  {
    path: "/players/{personId}/report",
    state: "live",
    description:
      "A grounded scouting report, served with the audit of how many of its numbers trace " +
      "back to the evidence the model was given.",
  },
  {
    path: "/players/{personId}/comps",
    state: "live",
    description:
      "Comparables precomputed in whitened archetype space, with the distance metric stated.",
  },
  {
    path: "/players/{personId}/archetype",
    state: "live",
    description: "Archetype assignment per season, carrying that cluster's bootstrap stability.",
  },
  {
    path: "/players/{personId}/shooting",
    state: "live",
    description: "Empirical-Bayes shrunk three-point threat, with the shrinkage weight exposed.",
  },
  {
    path: "/archetypes",
    state: "live",
    description: "The five clusters, their distinguishing features, exemplars and stability.",
  },
  {
    path: "/leaderboards/shooting",
    state: "live",
    description: "Spacing leaderboard, restricted to players above the attempt floor.",
  },
  {
    path: "/players/{personId}/shot-profile",
    state: "pending",
    willServe: "Real shot-zone rates and efficiency from ~2.5M ingested shot events.",
    blockedOn: "phase-4-shot-data",
    previously: `${SEED_DATA_NOTE} The 'shots' table was never written to or read from.`,
  },
  {
    path: "/teams/{teamId}/shot-profile",
    state: "pending",
    willServe: "Team shot-zone distribution and efficiency versus league average.",
    blockedOn: "phase-4-shot-data",
    previously: SEED_DATA_NOTE,
  },
  {
    path: "/teams/{teamId}/play-style",
    state: "pending",
    willServe: "Transition versus set-play splits derived from real possession timing.",
    blockedOn: "phase-4-shot-data",
    previously: SEED_DATA_NOTE,
  },
  {
    path: "/teams/{teamId}/lineup-impact",
    state: "pending",
    willServe:
      "Three exactly computable indices (spacing, archetype balance, usage " +
      "conflict) and an explicit null projection, because lineup offensive " +
      "rating cannot be projected without possession-level data.",
    blockedOn: "phase-4-archetypes",
    previously:
      "An invented linear formula with nine coefficients hardcoded in the route " +
      "handler, reported to users as 'offense_projection'. Nothing fitted them.",
  },
  {
    path: "/teams/{teamId}/lineup-impact/snapshots",
    state: "pending",
    willServe: "Stored lineup evaluations, each stamped with the model version that produced it.",
    blockedOn: "phase-4-archetypes",
    previously: `${SEED_DATA_NOTE} One stored lineup listed the same player twice.`,
  },
  {
    path: "/games/{gameId}/schedule-context",
    state: "pending",
    willServe:
      "Exact rest days, back-to-back flags and travel distance. These are " +
      "arithmetic on the schedule, not a model, and are reported as such.",
    blockedOn: "phase-4-game-model",
    previously:
      "Was '/games/{gameId}/fatigue-flags', which reported a hand-written " +
      "'fatigue_score' on an invented scale.",
  },

  // ---------------------------------------------------------------------
  // Withdrawn. Not on the roadmap, because the data to support them does
  // not exist publicly.
  // ---------------------------------------------------------------------
  {
    path: "/leaderboards/gravity",
    state: "gone",
    reason:
      "'Gravity' measures how much defensive attention a player draws, which " +
      "requires optical player-tracking data. The NBA does not publish it and " +
      "the EuroLeague does not collect it. The previous version of this " +
      "endpoint reported gravity values that were typed by hand.",
    instead:
      "/players/{personId}/shooting serves an empirical-Bayes shrunk 3PT threat " +
      "measure, which is computable from public data and is named for what it " +
      "actually measures.",
  },
  {
    path: "/leaderboards/clutch",
    state: "gone",
    reason:
      "The 'clutch_impact' figure behind this leaderboard was a hand-written " +
      "constant on an undefined scale. Clutch impact estimated from the small " +
      "per-player samples available would be almost entirely noise, and " +
      "publishing a ranking of noise is worse than publishing nothing.",
    instead:
      "Per-game box scores via /games/{gameId}, from which any clutch " +
      "definition can be computed with its own sample size attached.",
  },
  {
    path: "/games/{gameId}/momentum",
    state: "gone",
    reason:
      "'swing_index' and the other momentum figures were hand-written " +
      "constants. Reconstructing genuine run and momentum statistics needs " +
      "play-by-play data that this project does not yet ingest.",
    instead:
      "Play-by-play ingestion is a stretch goal. Until it lands there is no " +
      "honest momentum number to serve.",
  },
] as const;

export const PENDING_ENDPOINTS = ENDPOINTS.filter(
  (e): e is PendingEndpoint => e.state === "pending"
);

export const GONE_ENDPOINTS = ENDPOINTS.filter((e): e is GoneEndpoint => e.state === "gone");

/**
 * Registry paths use OpenAPI-style `{param}` placeholders; Hono matches on
 * `:param`. Converting here keeps the registry readable and keeps the two
 * notations from being maintained separately.
 */
export function toHonoPath(path: string): string {
  return path.replace(/\{(\w+)\}/g, ":$1");
}

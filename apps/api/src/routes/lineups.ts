import { Hono } from "hono";
import type { Env } from "../db";
import { dbAll, dbGet, resolveEntityId, resolveSeasonForEntity } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

function avg(values: number[]): number {
  if (!values.length) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export const lineupsRoute = new Hono<{ Bindings: Env }>();

lineupsRoute.get("/teams/:id/play-style", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) return c.json({ error: "season is required" }, 400);
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) return c.json({ error: "play style record not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "team_play_style_metrics",
    "team_id",
    teamId,
    requestedSeason
  );
  if (!season) return c.json({ error: "play style record not found" }, 404);

  const key = cacheKey(["team", teamId, "play-style", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const row = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT season_id, team_id, transition_poss_rate, set_play_poss_rate, transition_off_rating, set_play_off_rating, pace_proxy, early_offense_rate
      FROM team_play_style_metrics
      WHERE season_id = ? AND team_id = ?
    `,
    [season, teamId]
  );
  if (!row) return c.json({ error: "play style record not found" }, 404);

  const payload = { ...row, resolved: { team_id: teamId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

lineupsRoute.get("/teams/:id/lineup-impact", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  const playersRaw = c.req.query("players");

  if (!requestedSeason || !playersRaw) {
    return c.json({ error: "season and players query params are required" }, 400);
  }
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) return c.json({ error: "team not found" }, 404);
  const season =
    (await resolveSeasonForEntity(
      c.env.DB,
      "team_play_style_metrics",
      "team_id",
      teamId,
      requestedSeason
    )) ?? requestedSeason;

  const requestedPlayers = playersRaw
    .split(",")
    .map((x) => x.trim())
    .filter((x) => x.length > 0);

  if (requestedPlayers.length !== 5) {
    return c.json({ error: "exactly five players are required" }, 400);
  }
  const resolvedPlayers: string[] = [];
  for (const rawPlayer of requestedPlayers) {
    const playerId = await resolveEntityId(c.env.DB, "players", "player_id", rawPlayer);
    if (!playerId) return c.json({ error: `player not found: ${rawPlayer}` }, 404);
    resolvedPlayers.push(playerId);
  }

  const key = cacheKey(["team", teamId, "lineup-impact", season, ...resolvedPlayers]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const placeholders = resolvedPlayers.map(() => "?").join(",");

  const features = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT player_id, usage_proxy, ts_proxy, ast_rate_proxy, tov_rate_proxy
      FROM player_season_features
      WHERE season_id = ? AND player_id IN (${placeholders})
    `,
    [season, ...resolvedPlayers]
  );

  const featureMap = new Map<string, Record<string, unknown>>(
    features.map((f) => [String(f.player_id), f])
  );
  const missing = resolvedPlayers.filter((playerId) => !featureMap.has(playerId));
  if (missing.length > 0) {
    const fallbackPlaceholders = missing.map(() => "?").join(",");
    const fallbackRows = await dbAll<Record<string, unknown>>(
      c.env.DB,
      `
        SELECT player_id, usage_proxy, ts_proxy, ast_rate_proxy, tov_rate_proxy
        FROM player_season_features
        WHERE player_id IN (${fallbackPlaceholders})
      `,
      missing
    );
    for (const row of fallbackRows) {
      const playerId = String(row.player_id);
      if (!featureMap.has(playerId)) {
        featureMap.set(playerId, row);
      }
    }
  }
  for (const playerId of resolvedPlayers) {
    if (!featureMap.has(playerId)) {
      return c.json({ error: `missing player features for ${playerId}` }, 404);
    }
  }

  const gravities = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT player_id, gravity_overall
      FROM nba_gravity
      WHERE season_id = ? AND player_id IN (${placeholders})
    `,
    [season, ...resolvedPlayers]
  );

  const gravityMap = new Map<string, number>(
    gravities.map((g) => [String(g.player_id), Number(g.gravity_overall ?? 0)])
  );

  const avgGravity = avg(resolvedPlayers.map((p) => gravityMap.get(p) ?? 0));
  const avgUsage = avg(resolvedPlayers.map((p) => Number(featureMap.get(p)?.usage_proxy ?? 0)));
  const avgTs = avg(resolvedPlayers.map((p) => Number(featureMap.get(p)?.ts_proxy ?? 0)));
  const avgAst = avg(resolvedPlayers.map((p) => Number(featureMap.get(p)?.ast_rate_proxy ?? 0)));
  const avgTov = avg(resolvedPlayers.map((p) => Number(featureMap.get(p)?.tov_rate_proxy ?? 0)));

  const offenseProjection = Number((102 + avgGravity * 0.12 + avgTs * 25 + avgUsage * 12 - avgTov * 10).toFixed(2));
  const spacingIndex = Number((avgTs * 100 + avgGravity * 0.2).toFixed(2));
  const transitionFit = Number(((avgUsage + avgAst - avgTov) * 100 + avgGravity * 0.05).toFixed(2));
  const setPlayFit = Number((avgTs * 100 + avgAst * 25 - avgTov * 20 + avgGravity * 0.08).toFixed(2));

  const baseline = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT gravity_adjusted_offense
      FROM team_gravity_effect
      WHERE season_id = ? AND team_id = ?
    `,
    [season, teamId]
  );
  const baselineOffense = Number(baseline?.gravity_adjusted_offense ?? 0);
  const gravityDeltaVsTeam = Number((offenseProjection - baselineOffense).toFixed(2));

  const payload = {
    season,
    team_id: teamId,
    players: resolvedPlayers,
    metrics: {
      avg_gravity: Number(avgGravity.toFixed(2)),
      offense_projection: offenseProjection,
      spacing_index: spacingIndex,
      transition_fit: transitionFit,
      set_play_fit: setPlayFit,
      gravity_delta_vs_team: gravityDeltaVsTeam,
      baseline_team_offense: baselineOffense,
    },
    resolved: { team_id: teamId, season_id: season },
  };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 20);
  return c.json(payload);
});

lineupsRoute.get("/teams/:id/lineup-impact/snapshots", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  if (!requestedSeason) return c.json({ error: "season is required" }, 400);
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) return c.json({ error: "team not found" }, 404);
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "lineup_impact_snapshots",
    "team_id",
    teamId,
    requestedSeason
  );
  if (!season) return c.json({ season: requestedSeason, team_id: teamId, results: [] });

  const key = cacheKey(["team", teamId, "lineup-snapshots", season]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const rows = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT lineup_key, player_ids_json, avg_gravity, offense_projection, spacing_index, transition_fit, set_play_fit, gravity_delta_vs_team
      FROM lineup_impact_snapshots
      WHERE season_id = ? AND team_id = ?
      ORDER BY offense_projection DESC
      LIMIT 20
    `,
    [season, teamId]
  );

  const payload = { season, team_id: teamId, results: rows, resolved: { team_id: teamId, season_id: season } };
  await cachePutJson(c.env.CACHE, key, payload, 60 * 30);
  return c.json(payload);
});

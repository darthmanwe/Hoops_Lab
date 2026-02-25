import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbAll, dbGet, resolveEntityId, resolveSeasonForEntity } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const teamsRoute = new Hono<{ Bindings: Env }>();

type TeamSearchRow = {
  team_id: string;
  league_id: string;
  name: string;
  abbrev: string | null;
  city: string | null;
  country: string | null;
};

const SearchSchema = z.object({
  q: z.string().trim().min(1).max(80),
});

teamsRoute.get("/teams/search", async (c) => {
  const parsed = SearchSchema.safeParse({ q: c.req.query("q") ?? "" });
  if (!parsed.success) {
    return c.json({ error: "Invalid search query" }, 400);
  }

  const q = parsed.data.q.toLowerCase();
  const key = cacheKey(["teams", "search", q]);
  const cached = await cacheGetJson<TeamSearchRow[]>(c.env.CACHE, key);
  if (cached) {
    return c.json({ results: cached, cached: true });
  }

  const rows = await dbAll<TeamSearchRow>(
    c.env.DB,
    `
      SELECT team_id, league_id, name, abbrev, city, country
      FROM teams
      WHERE lower(name) LIKE ? OR lower(team_id) LIKE ? OR lower(ifnull(abbrev, '')) LIKE ?
      ORDER BY name ASC
      LIMIT 25
    `,
    [`%${q}%`, `%${q}%`, `%${q}%`]
  );

  await cachePutJson(c.env.CACHE, key, rows, 60 * 30);
  return c.json({ results: rows, cached: false });
});

teamsRoute.get("/teams/:id", async (c) => {
  const requestedTeamId = c.req.param("id");
  const requestedSeason = c.req.query("season");
  const teamId = await resolveEntityId(c.env.DB, "teams", "team_id", requestedTeamId);
  if (!teamId) {
    return c.json({ error: "Team not found" }, 404);
  }
  const season = await resolveSeasonForEntity(
    c.env.DB,
    "team_gravity_effect",
    "team_id",
    teamId,
    requestedSeason
  );

  const key = cacheKey(["teams", teamId, season ?? ""]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) {
    return c.json(cached);
  }

  const team = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT team_id, league_id, season_id, name, abbrev, city, country
      FROM teams
      WHERE team_id = ?
    `,
    [teamId]
  );

  const gravity = season
    ? await dbGet<Record<string, unknown>>(
        c.env.DB,
        `
          SELECT *
          FROM team_gravity_effect
          WHERE team_id = ? AND season_id = ?
        `,
        [teamId, season]
      )
    : null;

  const payload = { team, gravity, resolved: { team_id: teamId, season_id: season ?? null } };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

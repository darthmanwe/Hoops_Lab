import { Hono } from "hono";
import type { Env } from "../db";
import { dbGet } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const teamsRoute = new Hono<{ Bindings: Env }>();

teamsRoute.get("/teams/:id", async (c) => {
  const teamId = c.req.param("id");
  const season = c.req.query("season");

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

  if (!team) {
    return c.json({ error: "Team not found" }, 404);
  }

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

  const payload = { team, gravity };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

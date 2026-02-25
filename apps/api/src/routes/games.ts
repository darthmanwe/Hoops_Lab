import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbAll, dbGet } from "../db";
import { cacheGetJson, cacheKey, cachePutJson } from "../cache";

export const gamesRoute = new Hono<{ Bindings: Env }>();

const GameListQuery = z.object({
  season: z.string().trim().min(1).max(32).optional(),
  league: z.string().trim().min(2).max(8).optional(),
  limit: z
    .string()
    .optional()
    .transform((v) => (v ? Number(v) : 20))
    .pipe(z.number().int().min(1).max(100)),
});

gamesRoute.get("/games", async (c) => {
  const parsed = GameListQuery.safeParse({
    season: c.req.query("season"),
    league: c.req.query("league"),
    limit: c.req.query("limit"),
  });

  if (!parsed.success) {
    return c.json({ error: "Invalid query params" }, 400);
  }

  const { season, league, limit } = parsed.data;
  const key = cacheKey(["games", season ?? "", league ?? "", limit]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  let sql = `
    SELECT game_id, league_id, season_id, game_date, home_team_id, away_team_id, home_score, away_score
    FROM games
  `;
  const args: unknown[] = [];
  const where: string[] = [];

  if (season) {
    where.push("season_id = ?");
    args.push(season);
  }
  if (league) {
    where.push("league_id = ?");
    args.push(league.toUpperCase());
  }
  if (where.length > 0) {
    sql += ` WHERE ${where.join(" AND ")}`;
  }
  sql += " ORDER BY game_date DESC LIMIT ?";
  args.push(limit);

  const games = await dbAll<Record<string, unknown>>(c.env.DB, sql, args);
  const payload = { games };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

gamesRoute.get("/games/:id", async (c) => {
  const gameId = c.req.param("id");
  const key = cacheKey(["game", gameId]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const game = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT game_id, league_id, season_id, game_date, home_team_id, away_team_id, home_score, away_score, venue
      FROM games
      WHERE game_id = ?
    `,
    [gameId]
  );

  if (!game) {
    return c.json({ error: "Game not found" }, 404);
  }

  const boxscore = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT player_id, team_id, minutes, pts, ast, reb, fg3m, fg3a
      FROM boxscore_lines
      WHERE game_id = ?
      ORDER BY team_id ASC, pts DESC
    `,
    [gameId]
  );

  const payload = { game, boxscore };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

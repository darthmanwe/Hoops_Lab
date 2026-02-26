import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../db";
import { dbAll, dbGet, resolveEntityId } from "../db";
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
    SELECT
      g.game_id,
      g.league_id,
      g.season_id,
      g.game_date,
      g.home_team_id,
      g.away_team_id,
      g.home_score,
      g.away_score,
      ht.name AS home_team_name,
      ht.abbrev AS home_team_abbrev,
      at.name AS away_team_name,
      at.abbrev AS away_team_abbrev
    FROM games g
    LEFT JOIN teams ht ON ht.team_id = g.home_team_id AND ht.season_id = g.season_id
    LEFT JOIN teams at ON at.team_id = g.away_team_id AND at.season_id = g.season_id
  `;
  const args: unknown[] = [];
  const where: string[] = [];

  if (season) {
    where.push("g.season_id = ?");
    args.push(season);
  }
  if (league) {
    where.push("g.league_id = ?");
    args.push(league.toUpperCase());
  }
  if (where.length > 0) {
    sql += ` WHERE ${where.join(" AND ")}`;
  }
  sql += " ORDER BY g.game_date DESC LIMIT ?";
  args.push(limit);

  const games = await dbAll<Record<string, unknown>>(c.env.DB, sql, args);
  const payload = { games };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

gamesRoute.get("/games/:id", async (c) => {
  const requestedGameId = c.req.param("id");
  const gameId = await resolveEntityId(c.env.DB, "games", "game_id", requestedGameId);
  if (!gameId) {
    return c.json({ error: "Game not found" }, 404);
  }
  const key = cacheKey(["game", gameId]);
  const cached = await cacheGetJson<unknown>(c.env.CACHE, key);
  if (cached) return c.json(cached);

  const game = await dbGet<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT
        g.game_id,
        g.league_id,
        g.season_id,
        g.game_date,
        g.home_team_id,
        g.away_team_id,
        g.home_score,
        g.away_score,
        g.venue,
        ht.name AS home_team_name,
        ht.abbrev AS home_team_abbrev,
        at.name AS away_team_name,
        at.abbrev AS away_team_abbrev
      FROM games g
      LEFT JOIN teams ht ON ht.team_id = g.home_team_id AND ht.season_id = g.season_id
      LEFT JOIN teams at ON at.team_id = g.away_team_id AND at.season_id = g.season_id
      WHERE g.game_id = ?
    `,
    [gameId]
  );

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

  const boxscoreWithNames = await dbAll<Record<string, unknown>>(
    c.env.DB,
    `
      SELECT
        b.player_id,
        b.team_id,
        b.minutes,
        b.pts,
        b.ast,
        b.reb,
        b.fg3m,
        b.fg3a,
        p.name AS player_name,
        t.name AS team_name,
        t.abbrev AS team_abbrev
      FROM boxscore_lines b
      LEFT JOIN players p ON p.player_id = b.player_id
      LEFT JOIN teams t ON t.team_id = b.team_id
      WHERE b.game_id = ?
      ORDER BY b.team_id ASC, b.pts DESC
    `,
    [gameId]
  );

  const payload = { game, boxscore: boxscoreWithNames.length > 0 ? boxscoreWithNames : boxscore, resolved: { game_id: gameId } };
  await cachePutJson(c.env.CACHE, key, payload);
  return c.json(payload);
});

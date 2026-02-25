import { Hono } from "hono";
import type { Env } from "../db";

export const rootRoute = new Hono<{ Bindings: Env }>();

rootRoute.get("/", (c) => {
  return c.json({
    ok: true,
    service: "hoopslab-api",
    routes: [
      "/health",
      "/players/search?q=<name>",
      "/players/:id?season=<season_id>",
      "/players/:id/comps?season=<season_id>&k=10",
      "/teams/:id?season=<season_id>",
      "/teams/:id/fatigue?season=<season_id>",
      "/games?season=<season_id>&league=<NBA|EL>&limit=20",
      "/games/:id",
      "/games/:id/fatigue-flags",
      "/leaderboards/gravity?season=<season_id>",
      "/leaderboards/clutch?season=<season_id>",
      "/compare?playerA=<id>&playerB=<id>&season=<season_id>"
    ]
  });
});

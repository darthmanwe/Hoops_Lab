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
      "/teams/search?q=<name>",
      "/players/:id?season=<season_id>",
      "/players/:id/comps?season=<season_id>&k=10",
      "/players/:id/shot-profile?season=<season_id>",
      "/players/:id/translation?season=<season_id>",
      "/teams/:id?season=<season_id>",
      "/teams/:id/fatigue?season=<season_id>",
      "/teams/:id/shot-profile?season=<season_id>",
      "/teams/:id/play-style?season=<season_id>",
      "/teams/:id/lineup-impact?season=<season_id>&players=<id1,id2,id3,id4,id5>",
      "/teams/:id/lineup-impact/snapshots?season=<season_id>",
      "/games?season=<season_id>&league=<NBA|EL>&limit=20",
      "/games/:id",
      "/games/:id/momentum",
      "/games/:id/fatigue-flags",
      "/leaderboards/gravity?season=<season_id>",
      "/leaderboards/clutch?season=<season_id>",
      "/leaderboards/translation?season=<season_id>",
      "/compare?playerA=<id>&playerB=<id>&season=<season_id>"
    ]
  });
});

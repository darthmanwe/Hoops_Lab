import { Hono } from "hono";
import type { Env } from "./db";
import { rootRoute } from "./routes/root";
import { healthRoute } from "./routes/health";
import { playersRoute } from "./routes/players";
import { teamsRoute } from "./routes/teams";
import { gamesRoute } from "./routes/games";
import { leaderboardsRoute } from "./routes/leaderboards";
import { compareRoute } from "./routes/compare";
import { fatigueRoute } from "./routes/fatigue";
import { shotProfilesRoute } from "./routes/shotProfiles";
import { momentumRoute } from "./routes/momentum";
import { translationRoute } from "./routes/translation";
import { lineupsRoute } from "./routes/lineups";

const app = new Hono<{ Bindings: Env }>();

app.use("*", async (c, next) => {
  c.header("Access-Control-Allow-Origin", "*");
  c.header("Access-Control-Allow-Methods", "GET,OPTIONS");
  c.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (c.req.method === "OPTIONS") return c.body(null, 204);
  await next();
});

app.route("/", rootRoute);
app.route("/", healthRoute);
app.route("/", playersRoute);
app.route("/", teamsRoute);
app.route("/", gamesRoute);
app.route("/", leaderboardsRoute);
app.route("/", compareRoute);
app.route("/", fatigueRoute);
app.route("/", shotProfilesRoute);
app.route("/", momentumRoute);
app.route("/", translationRoute);
app.route("/", lineupsRoute);

app.notFound((c) => c.json({ error: "Not found" }, 404));

export default app;

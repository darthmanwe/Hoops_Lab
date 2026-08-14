import { defineConfig } from "drizzle-kit";

/**
 * Migrations are generated here and applied with `wrangler d1 migrations
 * apply`, which keeps its own bookkeeping table so it knows what has run.
 *
 * This replaces a single `CREATE TABLE IF NOT EXISTS` script. That file was
 * not a migration system: re-running it after a schema change is a silent
 * no-op, so adding a column did nothing and reported success.
 *
 * Note `breakpoints: false`. drizzle-kit otherwise emits
 * `--> statement-breakpoint` comments that wrangler does not understand.
 */
export default defineConfig({
  dialect: "sqlite",
  driver: "d1-http",
  schema: "./src/db/schema.ts",
  out: "./migrations",
  breakpoints: false,
  strict: true,
});

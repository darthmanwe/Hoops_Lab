export type Env = {
  DB: D1Database;
  CACHE: KVNamespace;
  /**
   * Identifier of the committed data snapshot this deployment serves, e.g.
   * `2026-08-01T09:14Z+a1b2c3`. Every cache key is prefixed with it, so a new
   * data load makes every previous key unreachable without needing a purge API.
   * Set per environment in wrangler.toml.
   */
  DATA_SNAPSHOT: string;
  APP_ENV: "dev" | "staging" | "production";
};

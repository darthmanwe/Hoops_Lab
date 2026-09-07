export type Env = {
  DB: D1Database;
  CACHE: KVNamespace;
  /**
   * Identifier of the committed data snapshot this deployment serves.
   *
   * Reported by `/health` and read back from there by `deploy.yml`, which
   * compares it against the id computed from committed gold to decide whether
   * D1 needs re-seeding. That is its only consumer. Set per environment in
   * wrangler.toml, and `hoopslab snapshot` prints the value it should hold.
   *
   * It is not a cache-key prefix, though this comment and three others said so
   * for months. Nothing in the Worker writes to `CACHE`.
   */
  DATA_SNAPSHOT: string;
  APP_ENV: "dev" | "staging" | "production";
};

import { readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

/**
 * Tests execute inside workerd with real D1 and KV bindings, not against a
 * mock. A test that passes here has exercised the same runtime production
 * uses, including its SQLite semantics and CPU limits.
 *
 * Note: pool-workers 0.21 replaced the old `defineWorkersConfig` helper with
 * this Vite plugin. Older guides still show the helper; it no longer exists.
 */
const migrations = await readD1Migrations("./migrations");

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml", environment: "dev" },
      miniflare: {
        d1Databases: ["DB"],
        kvNamespaces: ["CACHE"],
        // Real migrations, handed to the setup file so the schema under test
        // is the schema that ships.
        bindings: { TEST_MIGRATIONS: migrations },
      },
      // Off explicitly. This defaults to true in 0.21, which would let the
      // suite bind to real Cloudflare resources over the network — tests must
      // be reproducible offline and must never touch a live database.
      remoteBindings: false,
    }),
  ],
  test: {
    setupFiles: ["./test/setup.ts"],
  },
});

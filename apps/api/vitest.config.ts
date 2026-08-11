import { defineConfig } from "vitest/config";
import { cloudflareTest } from "@cloudflare/vitest-pool-workers";

/**
 * Tests execute inside workerd with real D1 and KV bindings, not against a
 * mock. A test that passes here has exercised the same runtime production
 * uses, including its SQLite semantics and CPU limits.
 *
 * Note: pool-workers 0.21 replaced the old `defineWorkersConfig` helper with
 * this Vite plugin. Older guides still show the helper; it no longer exists.
 */
export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml", environment: "dev" },
      miniflare: {
        d1Databases: ["DB"],
        kvNamespaces: ["CACHE"],
      },
      // Off explicitly. This defaults to true in 0.21, which would let the
      // suite bind to real Cloudflare resources over the network — tests must
      // be reproducible offline and must never touch a live database.
      remoteBindings: false,
    }),
  ],
});

import { defineCloudflareConfig } from "@opennextjs/cloudflare";

/**
 * Defaults, deliberately.
 *
 * OpenNext's optional caches — incremental cache, tag cache, queue — all want
 * a KV namespace or an R2 bucket and exist to make ISR and on-demand
 * revalidation work across isolates. This site has neither to revalidate.
 * Every page is either statically rendered from the committed snapshot at
 * build time or fetched client-side from the API Worker, which does its own
 * snapshot-keyed caching in KV. Wiring a second cache layer here would add
 * bindings, a second invalidation story and a second thing to get wrong,
 * in exchange for nothing.
 *
 * If server-rendered pages with `revalidate` ever land, this is where the
 * incremental cache goes.
 */
export default defineCloudflareConfig();

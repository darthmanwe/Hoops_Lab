import { desc } from "drizzle-orm";
import type { createDb } from "../db/client";
import { schema } from "../db/client";

/**
 * The committed data snapshot this database was loaded from.
 *
 * Reported in every response so a stale reply is self-identifying, and used as
 * a cache-key prefix so a new data load makes every previous key unreachable
 * without needing a purge API.
 */
export async function snapshotId(db: ReturnType<typeof createDb>): Promise<string | null> {
  const [row] = await db
    .select({ snapshotId: schema.dataSnapshots.snapshotId })
    .from(schema.dataSnapshots)
    .orderBy(desc(schema.dataSnapshots.builtAt))
    .limit(1);

  return row?.snapshotId ?? null;
}

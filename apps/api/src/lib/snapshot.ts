import { desc } from "drizzle-orm";
import type { createDb } from "../db/client";
import { schema } from "../db/client";

/**
 * The committed data snapshot this database was loaded from.
 *
 * Read from the database rather than from the `DATA_SNAPSHOT` variable, and
 * that distinction is the useful part: this reports what was actually loaded,
 * while the variable reports what someone configured. `/health` serves the
 * variable and every envelope serves this, so the two disagreeing is the
 * signal that a deploy shipped a snapshot id its data does not match.
 *
 * This docstring used to add "and used as a cache-key prefix so a new data
 * load makes every previous key unreachable". No such cache exists. The KV
 * namespace is bound and probed by `/health`; nothing has ever written to it.
 */
export async function snapshotId(db: ReturnType<typeof createDb>): Promise<string | null> {
  const [row] = await db
    .select({ snapshotId: schema.dataSnapshots.snapshotId })
    .from(schema.dataSnapshots)
    .orderBy(desc(schema.dataSnapshots.builtAt))
    .limit(1);

  return row?.snapshotId ?? null;
}

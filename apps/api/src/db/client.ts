import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

export type Database = ReturnType<typeof createDb>;

/**
 * Typed query builder over D1.
 *
 * The previous data layer was `dbAll<Record<string, unknown>>` at thirty-odd
 * call sites, with field access coerced through `Number(x ?? 0)` — which is how
 * a missing value became a confident zero. Every query below is typed from the
 * schema, so a renamed column is a compile error rather than a silent null.
 */
export function createDb(d1: D1Database) {
  return drizzle(d1, { schema });
}

export { schema };

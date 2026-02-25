export type Env = {
  DB: D1Database;
  CACHE: KVNamespace;
  BALLDONTLIE_API_KEY?: string;
};

export async function dbGet<T>(
  db: D1Database,
  sql: string,
  args: unknown[] = []
): Promise<T | null> {
  const stmt = db.prepare(sql).bind(...args);
  const row = await stmt.first<T>();
  return row ?? null;
}

export async function dbAll<T>(
  db: D1Database,
  sql: string,
  args: unknown[] = []
): Promise<T[]> {
  const stmt = db.prepare(sql).bind(...args);
  const res = await stmt.all<T>();
  return res.results ?? [];
}

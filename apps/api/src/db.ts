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

function uniqueValues(values: string[]): string[] {
  return [...new Set(values.filter((v) => v.length > 0))];
}

export function idCandidates(rawId: string): string[] {
  const id = rawId.trim();
  if (!id) return [];
  if (id.includes("_")) {
    return uniqueValues([id, id.toUpperCase()]);
  }
  return uniqueValues([id, id.toUpperCase(), `NBA_${id}`, `EL_${id}`]);
}

export async function resolveEntityId(
  db: D1Database,
  table: "players" | "teams" | "games",
  idColumn: "player_id" | "team_id" | "game_id",
  rawId: string
): Promise<string | null> {
  const candidates = idCandidates(rawId);
  if (candidates.length === 0) return null;

  const placeholders = candidates.map(() => "?").join(",");
  const sql = `
    SELECT ${idColumn} AS id
    FROM ${table}
    WHERE ${idColumn} IN (${placeholders})
    ORDER BY CASE ${idColumn}
      ${candidates.map(() => "WHEN ? THEN 0").join(" ")}
      ELSE 1
    END
    LIMIT 1
  `;
  const row = await dbGet<{ id: string }>(db, sql, [...candidates, ...candidates]);
  return row?.id ?? null;
}

export async function resolveSeasonForEntity(
  db: D1Database,
  table:
    | "player_season_features"
    | "player_shot_profiles"
    | "player_translation_metrics"
    | "team_gravity_effect"
    | "team_fatigue_effect"
    | "team_shot_profiles"
    | "team_play_style_metrics"
    | "lineup_impact_snapshots",
  idColumn: "player_id" | "team_id",
  entityId: string,
  requestedSeason?: string | null
): Promise<string | null> {
  if (requestedSeason) {
    const exact = await dbGet<{ season_id: string }>(
      db,
      `SELECT season_id FROM ${table} WHERE ${idColumn} = ? AND season_id = ? LIMIT 1`,
      [entityId, requestedSeason]
    );
    if (exact?.season_id) return exact.season_id;
  }

  const fallback = await dbGet<{ season_id: string }>(
    db,
    `SELECT season_id FROM ${table} WHERE ${idColumn} = ? ORDER BY season_id DESC LIMIT 1`,
    [entityId]
  );
  return fallback?.season_id ?? null;
}

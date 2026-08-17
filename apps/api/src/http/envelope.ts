import type { Context } from "hono";

/**
 * Every successful response carries provenance.
 *
 * The previous API returned bare payloads, so a caller had no way to tell
 * which season a number came from, which model produced it, or whether the
 * season they asked for was the season they got — and the answer was often
 * "no", because the old code silently substituted a different one.
 */
export type Meta = {
  request_id: string;
  snapshot: string | null;
  generated_at: string;
  resolved?: {
    season_id?: string;
    requested_season_id?: string | null;
    /** `exact` or `latest_available`; never a silent substitution. */
    resolution?: "exact" | "latest_available";
  };
  model?: {
    name: string;
    version: string;
    /** Headline metric for the model, so a number never appears without its error. */
    primary_metric?: string;
    primary_value?: number;
    primary_ci?: [number, number] | null;
    card?: string;
  };
  /**
   * How many rows the filters matched, against how many were returned.
   *
   * A truncated list and a complete one look identical without this, which
   * invites the reader to mistake the first page of a ranking for the whole
   * population — a listing of 60 players reads as "these are the 60", not "these
   * are the top 60 of 196".
   */
  page?: { total: number; limit: number; offset: number; returned: number };
  warnings: string[];
};

export type Envelope<T> = { data: T; meta: Meta };

export function envelope<T>(
  c: Context,
  data: T,
  extra: Partial<Omit<Meta, "request_id" | "generated_at">> = {}
): Envelope<T> {
  return {
    data,
    meta: {
      request_id: c.res.headers.get("X-Request-Id") ?? "unknown",
      snapshot: extra.snapshot ?? null,
      generated_at: new Date().toISOString(),
      warnings: extra.warnings ?? [],
      ...(extra.resolved ? { resolved: extra.resolved } : {}),
      ...(extra.model ? { model: extra.model } : {}),
      ...(extra.page ? { page: extra.page } : {}),
    },
  };
}

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
    },
  };
}

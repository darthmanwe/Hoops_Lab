/**
 * Number formatting that distinguishes "missing" from "zero".
 *
 * The previous frontend rendered `Number(value ?? 0).toFixed(2)`, so a player
 * with no recorded usage rate displayed **0.00** — indistinguishable from a
 * genuine zero. On a page about model calibration that is not a formatting
 * quirk, it is a false claim about the data.
 *
 * Everything here returns an em dash for absent values, and nothing coerces.
 */

/** Shown wherever a value genuinely does not exist. */
export const MISSING = "—";

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING;
  return `${(value * 100).toFixed(digits)}%`;
}

export function decimal(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING;
  return value.toFixed(digits);
}

export function integer(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING;
  return Math.round(value).toLocaleString("en-GB");
}

/** A prediction and its interval, always together. */
export function withInterval(
  point: number | null | undefined,
  low: number | null | undefined,
  high: number | null | undefined,
  digits = 1
): string {
  if (point === null || point === undefined) return MISSING;
  if (low === null || low === undefined || high === null || high === undefined) {
    return percent(point, digits);
  }
  return `${percent(point, digits)}  [${percent(low, digits)} – ${percent(high, digits)}]`;
}

export function signedSd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return MISSING;
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} sd`;
}

/** e.g. "EL->NBA" becomes "EuroLeague → NBA". */
export function directionLabel(direction: string): string {
  const names: Record<string, string> = { EL: "EuroLeague", NBA: "NBA", GL: "G League" };
  const [from, to] = direction.split("->");
  return `${names[from ?? ""] ?? from} → ${names[to ?? ""] ?? to}`;
}

export function metricLabel(metric: string): string {
  const names: Record<string, string> = {
    usg_pct: "Usage rate",
    ts_pct: "True shooting",
    ast_pct: "Assist rate",
  };
  return names[metric] ?? metric;
}

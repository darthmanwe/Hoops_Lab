/**
 * Typed client for the HoopsLab API.
 *
 * Every response is an envelope carrying provenance — the data snapshot, the
 * model version, and that model's own measured error — so a component can
 * always show where a number came from.
 */

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8710").replace(
  /\/+$/,
  ""
);

export type Meta = {
  request_id: string;
  snapshot: string | null;
  generated_at: string;
  resolved?: { season_id?: string; resolution?: "exact" | "latest_available" };
  model?: {
    name: string;
    version: string;
    primary_metric?: string;
    primary_value?: number;
    primary_ci?: [number, number] | null;
    card?: string;
  };
  /** Present on list endpoints, so a page of a ranking never reads as the whole pool. */
  page?: { total: number; limit: number; offset: number; returned: number };
  warnings: string[];
};

export type Envelope<T> = { data: T; meta: Meta };

/** RFC 9457 problem document. The API never returns bare error strings. */
export type Problem = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  [key: string]: unknown;
};

export class ApiError extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail || problem.title);
    this.name = "ApiError";
  }
}

/** A service binding, which exposes the target Worker's `fetch` and nothing else. */
type ServiceBinding = { fetch: (input: string, init?: RequestInit) => Promise<Response> };

/**
 * How to reach the API from wherever this happens to be running.
 *
 * Deployed, every page here is a server component, so the request is made by
 * the web Worker rather than by a browser — and a Worker cannot call another
 * Worker on the same account through its `workers.dev` address. The subrequest
 * never leaves the runtime: it loops back into the caller, which has no
 * `/models` route and returns 404. `curl` against the same URL returns 200, so
 * the symptom points at the address and the address is fine.
 *
 * The `API` service binding declared in `wrangler.jsonc` is the way across.
 * Everywhere else — `next dev`, tests, a plain Node build — there is no binding
 * and the public URL works, so this falls through to global `fetch`. The
 * failure mode of the fallback is a page that renders the API's own "could not
 * reach" explanation, which is the same thing it did before this existed.
 */
async function transport(): Promise<ServiceBinding["fetch"]> {
  // `next dev` is excluded deliberately, and this is not a shortcut.
  //
  // OpenNext's dev context reads `wrangler.jsonc` and materialises the bindings
  // declared there, so `env.API` exists locally too — bound to a Worker that is
  // not running, which answers every request 503. Every page then rendered its
  // "could not reach the API" card while the real dev Worker sat on 8710
  // answering curl, and the API's own log showed no requests at all. The whole
  // local stack looked broken in a way that pointed at the backend.
  //
  // In development the public URL is right and reachable, so the binding buys
  // nothing there; it exists for the deployed Worker, where the public URL is
  // the thing that does not work.
  if (process.env.NODE_ENV !== "development") {
    try {
      const { getCloudflareContext } = await import("@opennextjs/cloudflare");
      const { env } = await getCloudflareContext({ async: true });
      const api = (env as unknown as Record<string, unknown>).API as ServiceBinding | undefined;
      if (api?.fetch) {
        return (input, init) => api.fetch(input, init);
      }
    } catch {
      // Not running on Workers at all. Expected under vitest and a bare build.
    }
  }
  return (input, init) => fetch(input, init);
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const send = await transport();
  const response = await send(`${API_BASE}${path}`, {
    // The data only changes when a new snapshot is deployed, so responses are
    // cacheable; the Worker sets its own cache headers and pages render at
    // request time (see `dynamic` in each route).
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    throw new ApiError(await asProblem(response));
  }
  return (await response.json()) as Envelope<T>;
}

/**
 * Fetch that treats an expected 404 as absence rather than failure.
 *
 * Most "not found" responses here are meaningful — a player who never changed
 * league genuinely has no translation — and the API explains them, so the page
 * can render that explanation instead of an error.
 */
export async function apiGetOptional<T>(path: string): Promise<Envelope<T> | Problem> {
  try {
    return await apiGet<T>(path);
  } catch (error) {
    if (error instanceof ApiError) return error.problem;

    // A transport failure is turned into a problem document too, so an
    // unreachable API renders as an explanation rather than crashing the
    // page — and so a production build does not require a running backend.
    return {
      type: "about:blank",
      title: "The API is unreachable",
      status: 503,
      code: "API_UNREACHABLE",
      detail:
        `Could not reach ${API_BASE}. Start it with \`npm run dev\`, or set ` +
        "NEXT_PUBLIC_API_BASE to a deployed Worker.",
    };
  }
}

export function isProblem(value: unknown): value is Problem {
  return typeof value === "object" && value !== null && "code" in value && "status" in value;
}

/**
 * Turn a failed response into a problem document.
 *
 * The interesting case is a reply that is *not* from this API at all. Every
 * HoopsLab error carries a `code`, so a bare status with no problem document
 * almost always means `NEXT_PUBLIC_API_BASE` points somewhere else — another
 * project's dev server on a port wrangler drifted away from, or nothing at all.
 *
 * Reporting that as "Not Found" would be this project's own original sin in
 * miniature: a confident, specific message that is about the wrong thing
 * entirely. A reader would go looking for a missing player. So the message
 * names the address it actually called and says what is wrong with it.
 */
async function asProblem(response: Response): Promise<Problem> {
  try {
    const body = (await response.json()) as Problem;
    if (body?.code) return body;
  } catch {
    // fall through to a synthetic problem below
  }

  return {
    type: "about:blank",
    title: "That is not the HoopsLab API",
    status: response.status,
    code: "NOT_THE_API",
    detail:
      `A request to ${API_BASE} returned ${response.status} with no problem document. ` +
      "Every error from this API carries one, so the address is most likely serving " +
      "something else — check that the Worker is running and that NEXT_PUBLIC_API_BASE " +
      "matches the port it bound.",
  };
}

// ---------------------------------------------------------------- row types

export type PersonSummary = {
  personId: string;
  displayName: string | null;
  birthYear: number | null;
  leagues: string;
};

export type PlayerSeason = {
  seasonId: string;
  league: string;
  label: string;
  seasonOrder: number;
  teamName: string | null;
  gamesPlayed: number | null;
  minutes: number | null;
  usgPct: number | null;
  tsPct: number | null;
  astPct: number | null;
  ptsPer75: number | null;
  age: number | null;
  qualified: boolean;
};

export type Identity = {
  league: string;
  sourcePlayerId: string;
  matchMethod: string;
  confidence: number;
};

export type TranslationPrediction = {
  personId: string;
  displayName?: string | null;
  sourceSeasonId: string;
  targetSeasonId: string;
  direction: string;
  metric: string;
  sourceValue: number;
  predicted: number;
  pi80Low: number;
  pi80High: number;
  pi95Low: number;
  pi95High: number;
  actualValue: number | null;
  baselineLeagueMean: number;
  baselineZPreservation: number;
  baselineFolkRule: number;
  modelVersion: string;
};

export type HypotheticalProjection = {
  personId: string;
  displayName: string | null;
  sourceSeasonId: string;
  sourceLeague: string;
  targetSeasonId: string;
  direction: string;
  metric: string;
  sourceValue: number;
  zSource: number;
  predicted: number;
  pi80Low: number;
  pi80High: number;
  pi95Low: number;
  pi95High: number;
  /** False means the model is extrapolating beyond where movers were observed. */
  inSupport: boolean;
  movedBefore: boolean;
  minutes: number;
  age: number | null;
  /** Observed transfers behind this direction: 134 at best, 14 at worst. */
  supportNMovers: number;
  modelVersion: string;
};

export type ModelVersion = {
  modelVersion: string;
  modelName: string;
  trainedAt: string;
  gitSha: string;
  seed: number;
  primaryMetric: string;
  primaryValue: number;
  primaryCiLow: number | null;
  primaryCiHigh: number | null;
  nTrain: number;
  nEvaluated: number;
  cardPath: string;
};

export type ModelEvaluation = {
  metric: string;
  fold: string;
  nEvaluated: number;
  mae: number;
  maeCiLow: number | null;
  maeCiHigh: number | null;
  baselineName: string;
  baselineMae: number;
  shuffledMae: number | null;
  beatsBestBaseline: boolean;
  skillVsBest: number;
};

export type SelectionSummary = {
  direction: string;
  metric: string;
  nMovers: number;
  nLeague: number;
  moverMeanZ: number;
  leagueMeanZ: number;
  gapSd: number;
};

export type ArchetypeDefinition = {
  modelVersion: string;
  cluster: number;
  nMembers: number;
  topFeatures: string;
  exemplars: string;
  stabilityJaccard: number;
  reportable: boolean;
};

export type ShootingRow = {
  seasonId: string;
  fg3a: number;
  fg3aPer75: number;
  fg3PctRaw: number | null;
  fg3PctShrunk: number;
  shrinkageWeight: number;
  priorMean: number;
  spacingScore: number;
  reportable: boolean;
};

export type ReportClaim = {
  text: string;
  /** Never empty: the schema the model answered under cannot express an uncited claim. */
  fact_ids: string[];
};

export type ScoutingReportResponse = {
  personId: string;
  targetSeasonId: string;
  direction: string;
  /** True when the model was told the subject's name, which weakens the audit. */
  named: boolean;
  headline: string;
  report: {
    headline: string;
    projection: ReportClaim;
    uncertainty: ReportClaim;
    strengths: ReportClaim[];
    risks: ReportClaim[];
    confidence: "low" | "moderate" | "high";
  };
  /** The exact text the model was given, so a reader can check a citation. */
  evidence: string;
  audit: {
    grounded: boolean;
    numbersTraced: number;
    numbersTotal: number;
    checks: { name: string; passed: boolean; detail: string }[];
  };
  reportModel: string;
  generatedAt: string;
};

export type CompRow = {
  seasonId: string;
  rank: number;
  distance: number;
  neighbourPersonId: string;
  neighbourName: string | null;
};

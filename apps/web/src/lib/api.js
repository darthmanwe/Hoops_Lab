const DEFAULT_API_BASE = "http://127.0.0.1:8787";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ?? DEFAULT_API_BASE;

export async function apiGet(path, options = {}) {
  const finalPath = path.startsWith("/") ? path : `/${path}`;
  if (
    typeof window !== "undefined" &&
    API_BASE.includes("127.0.0.1") &&
    window.location.hostname !== "127.0.0.1" &&
    window.location.hostname !== "localhost"
  ) {
    throw new Error(
      "API base is still set to localhost. Set NEXT_PUBLIC_API_BASE to your deployed Worker URL."
    );
  }
  const res = await fetch(`${API_BASE}${finalPath}`, {
    cache: options.cache ?? "no-store",
    ...options,
  });
  if (!res.ok) {
    throw new Error(await describeFailure(res));
  }
  return res.json();
}

/**
 * Turn an RFC 9457 problem+json body into something a person can read.
 *
 * Every analytics endpoint currently answers 501 or 410 while the fabricated
 * data it used to serve is replaced with fitted models. Dumping the raw JSON
 * into the UI would bury that explanation in punctuation.
 */
async function describeFailure(res) {
  const body = await res.text().catch(() => "");

  try {
    const problem = JSON.parse(body);
    if (!problem?.title) throw new Error("not a problem document");

    const detail = [problem.title, problem.detail].filter(Boolean).join(" — ");
    const context = problem.will_serve
      ? `Will serve: ${problem.will_serve}`
      : problem.instead
        ? `Instead: ${problem.instead}`
        : "";

    return [detail, context].filter(Boolean).join(" ");
  } catch {
    return `API ${res.status}: ${body || res.statusText}`;
  }
}

export function seasonFromLeague(league) {
  return league === "EL" ? "EL_2025" : "NBA_2025";
}

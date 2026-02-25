const DEFAULT_API_BASE = "http://127.0.0.1:8787";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ?? DEFAULT_API_BASE;

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
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

export function seasonFromLeague(league) {
  return league === "EL" ? "EL_2025" : "NBA_2025";
}

const DEFAULT_API_BASE = "http://127.0.0.1:8787";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ?? DEFAULT_API_BASE;

export async function apiGet(path) {
  const finalPath = path.startsWith("/") ? path : `/${path}`;
  const res = await fetch(`${API_BASE}${finalPath}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

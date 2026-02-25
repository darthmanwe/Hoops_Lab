const DEFAULT_TTL_SECONDS = 60 * 10;

export async function cacheGetJson<T>(
  kv: KVNamespace,
  key: string
): Promise<T | null> {
  const raw = await kv.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function cachePutJson(
  kv: KVNamespace,
  key: string,
  value: unknown,
  ttlSeconds = DEFAULT_TTL_SECONDS
): Promise<void> {
  await kv.put(key, JSON.stringify(value), { expirationTtl: ttlSeconds });
}

export function cacheKey(parts: Array<string | number | undefined | null>): string {
  return parts.filter((p) => p !== undefined && p !== null).join(":");
}

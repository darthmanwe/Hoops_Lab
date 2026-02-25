function dot(a: number[], b: number[]): number {
  return a.reduce((acc, v, i) => acc + v * (b[i] ?? 0), 0);
}

function magnitude(a: number[]): number {
  return Math.sqrt(dot(a, a));
}

export function cosineSimilarity(a: number[], b: number[]): number {
  const denom = magnitude(a) * magnitude(b);
  if (denom === 0) return 0;
  return dot(a, b) / denom;
}

export function parseVector(raw: unknown): number[] {
  if (!raw || typeof raw !== "string") return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((x) => Number(x)).filter((n) => Number.isFinite(n));
    }
    return [];
  } catch {
    return [];
  }
}

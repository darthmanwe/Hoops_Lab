"use client";

import { useEffect, useState } from "react";
import { apiGet } from "./api";

export function useApi(path) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!path) {
        setLoading(false);
        setData(null);
        setError("");
        return;
      }
      setLoading(true);
      setError("");
      try {
        const response = await apiGet(path);
        if (!cancelled) setData(response);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [path]);

  return { data, loading, error };
}

"""Content-addressed cache for raw source payloads.

Every fetch is keyed by a hash of its source, endpoint and parameters, so
re-running ingestion is free and interrupting it loses only the request in
flight. An append-only manifest records what was fetched, when, how long it
took and what it contained, which is what makes a partial or silently truncated
pull detectable after the fact.

Payloads are stored as parquet rather than as the raw JSON body. Every source
in use hands back a parsed table, and keeping the parsed form is materially
more useful than keeping bytes we would only ever re-parse the same way. The
manifest records the row count and content hash so the fidelity of that choice
stays checkable.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

MANIFEST_NAME = "manifest.jsonl"


def cache_key(source: str, endpoint: str, params: dict[str, Any]) -> str:
    """Stable 16-character key for a request.

    Parameters are sorted and JSON-encoded so that two calls differing only in
    keyword order share a cache entry.
    """
    canonical = json.dumps(
        {"source": source, "endpoint": endpoint, "params": params},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def frame_digest(frame: pd.DataFrame) -> str:
    """Content hash of a table, used to detect a source changing under us."""
    hashed = pd.util.hash_pandas_object(frame, index=True).to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()[:16]


@dataclass(frozen=True)
class FetchResult:
    frame: pd.DataFrame
    from_cache: bool
    key: str


class BronzeCache:
    """Read-through cache over the bronze layer."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest_path = root / MANIFEST_NAME

    def path_for(self, source: str, endpoint: str, key: str) -> Path:
        return self.root / source / endpoint / f"{key}.parquet"

    def fetch(
        self,
        *,
        source: str,
        endpoint: str,
        params: dict[str, Any],
        fetcher: Callable[[], pd.DataFrame],
        refresh: bool = False,
    ) -> FetchResult:
        """Return a cached payload, or call ``fetcher`` and cache the result."""
        key = cache_key(source, endpoint, params)
        path = self.path_for(source, endpoint, key)

        if path.is_file() and not refresh:
            return FetchResult(frame=pd.read_parquet(path), from_cache=True, key=key)

        started = time.monotonic()
        frame = fetcher()
        elapsed_ms = int((time.monotonic() - started) * 1000)

        path.parent.mkdir(parents=True, exist_ok=True)
        _write_parquet(frame, path)

        self._record(
            {
                "source": source,
                "endpoint": endpoint,
                "params": params,
                "key": key,
                "fetched_at": datetime.now(UTC).isoformat(),
                "n_rows": len(frame),
                "n_cols": int(frame.shape[1]),
                "digest": frame_digest(frame),
                "elapsed_ms": elapsed_ms,
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
            }
        )

        return FetchResult(frame=frame, from_cache=False, key=key)

    def load(self, source: str, endpoint: str, params: dict[str, Any]) -> pd.DataFrame | None:
        """Read a cached payload without any possibility of fetching it.

        The transform layer uses this rather than going through the ingest
        clients, so that building silver and gold works on a machine that has
        never installed the optional ``ingest`` extra — which is every CI
        runner and every fresh clone.
        """
        path = self.path_for(source, endpoint, cache_key(source, endpoint, params))
        return pd.read_parquet(path) if path.is_file() else None

    def _record(self, entry: dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def manifest(self) -> list[dict[str, Any]]:
        if not self.manifest_path.is_file():
            return []
        with self.manifest_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def load_all(self, source: str, endpoint: str) -> list[pd.DataFrame]:
        """Every cached payload for one endpoint, in stable filename order."""
        directory = self.root / source / endpoint
        if not directory.is_dir():
            return []
        return [pd.read_parquet(p) for p in sorted(directory.glob("*.parquet"))]


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    """Write a source table, tolerating the mixed-type object columns these APIs return.

    `stats.nba.com` returns columns that are numeric for most rows and an empty
    string for the rest, which Arrow cannot infer a type for. Falling back to a
    string cast keeps the payload rather than losing the whole fetch; the
    transform layer parses these columns explicitly anyway.
    """
    try:
        frame.to_parquet(path, index=False, compression="zstd")
        return
    except (TypeError, ValueError, pa.ArrowInvalid, pa.ArrowTypeError):
        pass

    coerced = frame.copy()
    for column in coerced.columns:
        if coerced[column].dtype == "object":
            coerced[column] = coerced[column].astype("string")
    coerced.to_parquet(path, index=False, compression="zstd")

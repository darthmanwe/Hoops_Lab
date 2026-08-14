"""Contract sidecars: a committed fingerprint of every gold table.

Each gold parquet ships a JSON sidecar recording its row count, columns and
dtypes, per-column null rate, numeric ranges and a content hash. ``hoopslab
verify`` re-derives all of it and diffs, with no network access.

The point is that data drift becomes a failed build. Without this, a source
quietly changing a unit, dropping a season, or renaming a column produces
different numbers in the README with nothing to indicate that anything moved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

CONTRACT_VERSION = 1


@dataclass
class ColumnContract:
    name: str
    dtype: str
    null_rate: float
    minimum: float | None = None
    maximum: float | None = None


@dataclass
class TableContract:
    table: str
    contract_version: int
    n_rows: int
    n_columns: int
    content_hash: str
    columns: list[ColumnContract] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, payload: str) -> TableContract:
        raw: dict[str, Any] = json.loads(payload)
        columns = [ColumnContract(**c) for c in raw.pop("columns", [])]
        return cls(**raw, columns=columns)


def content_hash(frame: pl.DataFrame) -> str:
    """Order-independent hash of a table's contents.

    Row order is not part of a table's meaning, and polars does not guarantee
    it across versions for grouped operations, so hashing sorted row hashes
    keeps the fingerprint stable against a reordering that changes nothing.
    """
    row_hashes = frame.hash_rows(seed=0).sort().to_list()
    digest = hashlib.sha256()
    for value in row_hashes:
        digest.update(str(value).encode("ascii"))
    return digest.hexdigest()[:32]


def derive(table: str, frame: pl.DataFrame) -> TableContract:
    columns: list[ColumnContract] = []

    for name in frame.columns:
        series = frame[name]
        null_rate = round(series.null_count() / max(frame.height, 1), 6)
        minimum = maximum = None

        if series.dtype.is_numeric() and series.null_count() < frame.height:
            low, high = series.min(), series.max()
            minimum = round(float(low), 6) if low is not None else None  # type: ignore[arg-type]
            maximum = round(float(high), 6) if high is not None else None  # type: ignore[arg-type]

        columns.append(
            ColumnContract(
                name=name,
                dtype=str(series.dtype),
                null_rate=null_rate,
                minimum=minimum,
                maximum=maximum,
            )
        )

    return TableContract(
        table=table,
        contract_version=CONTRACT_VERSION,
        n_rows=frame.height,
        n_columns=frame.width,
        content_hash=content_hash(frame),
        columns=columns,
    )


def write(contract: TableContract, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{contract.table}.json"
    path.write_text(contract.to_json(), encoding="utf-8")
    return path


def compare(expected: TableContract, actual: TableContract) -> list[str]:
    """Human-readable differences. Empty means the table is unchanged."""
    problems: list[str] = []

    if expected.n_rows != actual.n_rows:
        problems.append(f"row count {expected.n_rows} -> {actual.n_rows}")

    expected_cols = {c.name: c for c in expected.columns}
    actual_cols = {c.name: c for c in actual.columns}

    for missing in sorted(set(expected_cols) - set(actual_cols)):
        problems.append(f"column removed: {missing}")
    for added in sorted(set(actual_cols) - set(expected_cols)):
        problems.append(f"column added: {added}")

    for name in sorted(set(expected_cols) & set(actual_cols)):
        want, got = expected_cols[name], actual_cols[name]
        if want.dtype != got.dtype:
            problems.append(f"{name}: dtype {want.dtype} -> {got.dtype}")
        if abs(want.null_rate - got.null_rate) > 1e-6:
            problems.append(f"{name}: null rate {want.null_rate:.4f} -> {got.null_rate:.4f}")

    if expected.content_hash != actual.content_hash and not problems:
        # Same shape, same null rates, different values: a source revised its
        # history. Worth failing on, and worth saying precisely.
        problems.append(
            f"contents changed (hash {expected.content_hash} -> {actual.content_hash}) "
            "with no schema difference"
        )

    return problems

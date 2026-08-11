"""Filesystem layout of the data lake.

Every path in the project is derived from here. Paths are built with
``pathlib`` and never by string concatenation, because the primary development
machine is Windows and the CI runners are Linux; a hand-joined ``"a/" + "b"``
works on both right up until it does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upwards until the directory containing the workspace manifest.

    Anchoring on a marker file rather than on ``__file__`` with a fixed number
    of ``.parent`` hops means the layout survives the package being moved or
    installed as a wheel.
    """
    current = (start or Path(__file__)).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "package.json").is_file() and (candidate / "apps").is_dir():
            return candidate
    raise FileNotFoundError(
        f"Could not locate the repository root above {current}. "
        "Expected an ancestor containing both package.json and apps/."
    )


@dataclass(frozen=True)
class DataPaths:
    """Resolved locations of each medallion layer."""

    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def bronze(self) -> Path:
        """Raw API payloads, exactly as returned. Gitignored, regenerable."""
        return self.data / "bronze"

    @property
    def silver(self) -> Path:
        """Typed, per-league, normalised. Gitignored, regenerable."""
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        """Analysis-ready and committed, so a clean clone needs no network."""
        return self.data / "gold"

    @property
    def contracts(self) -> Path:
        """Per-table row counts, dtypes, null rates and content hashes."""
        return self.gold / "_contracts"

    @property
    def crosswalk(self) -> Path:
        """Manual player-identity overrides that automated matching cannot resolve."""
        return self.data / "crosswalk"

    @classmethod
    def discover(cls, start: Path | None = None) -> DataPaths:
        return cls(root=find_repo_root(start))

"""Data-lake path resolution.

These look trivial and are not: the primary development machine is Windows and
CI runs on Linux, so path handling is the single most likely thing to work
locally and break in the matrix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hoopslab.paths import DataPaths, find_repo_root


def test_finds_the_repo_root_from_the_package() -> None:
    root = find_repo_root()

    assert (root / "package.json").is_file()
    assert (root / "apps").is_dir()


def test_raises_a_useful_error_when_there_is_no_root(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Could not locate the repository root"):
        find_repo_root(tmp_path)


def test_layers_are_nested_under_data(repo_root: Path) -> None:
    paths = DataPaths(root=repo_root)

    assert paths.bronze.parent == paths.data
    assert paths.silver.parent == paths.data
    assert paths.gold.parent == paths.data


def test_contracts_live_beside_the_gold_tables_they_describe(repo_root: Path) -> None:
    paths = DataPaths(root=repo_root)

    assert paths.contracts.parent == paths.gold


def test_paths_are_absolute(repo_root: Path) -> None:
    paths = DataPaths(root=repo_root)

    for layer in (paths.bronze, paths.silver, paths.gold, paths.contracts, paths.crosswalk):
        assert layer.is_absolute()


def test_only_gold_and_crosswalk_are_committed(repo_root: Path) -> None:
    """Bronze and silver must stay ignored; committing them would bloat the clone.

    Gold is committed on purpose, which is what lets a fresh clone reproduce
    every reported number with no network access.
    """
    # Parse real patterns rather than substring-matching the file: the comment
    # above these rules mentions `data/gold/` while explaining why it is *not*
    # ignored, which a naive `in` check reads as the opposite of the truth.
    patterns = {
        line.strip()
        for line in (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "data/bronze/" in patterns
    assert "data/silver/" in patterns
    assert "data/gold/" not in patterns
    assert "data/crosswalk/" not in patterns


def test_discover_matches_explicit_construction(repo_root: Path) -> None:
    assert DataPaths.discover().root == DataPaths(root=repo_root).root

"""The deployed snapshot id must be the committed data's snapshot id.

``DATA_SNAPSHOT`` prefixes every cache key the Worker writes. That is what makes
a re-seed safe without a purge API — new data means a new id, which means the
old keys are never asked for again — and it is also what makes a wrong value
quietly harmful: the Worker keeps serving the previous snapshot's rows out of KV
until the TTL expires, and says so only in ``meta.snapshot``, to whoever is
reading it.

The value lives in ``apps/api/wrangler.toml`` and was maintained by hand. It
started as the empty string, which namespaced the entire cache under a prefix
that never changes; that was noticed during a deployment rather than by anything
checking. This is the check.

Hand-editing stays allowed. Drifting does not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hoopslab.paths import DataPaths, find_repo_root
from hoopslab.serve.d1_export import snapshot_id

#: `[env.production]` is the only environment that serves real data. `[env.dev]`
#: binds a local database, so an empty id there is correct rather than stale.
PRODUCTION_BLOCK = re.compile(r"^\[env\.production\]\s*$(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)


@pytest.fixture(scope="module")
def repo() -> Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def production_vars(repo: Path) -> str:
    config = (repo / "apps" / "api" / "wrangler.toml").read_text(encoding="utf-8")
    block = PRODUCTION_BLOCK.search(config)
    assert block, "wrangler.toml has no [env.production] section"
    return block.group(1)


def test_production_pins_the_committed_snapshot(production_vars: str, repo: Path) -> None:
    if not (repo / "data" / "gold" / "_contracts").is_dir():
        pytest.skip("no committed gold snapshot")

    declared = re.search(r'DATA_SNAPSHOT = "([^"]*)"', production_vars)
    assert declared, "[env.production] does not set DATA_SNAPSHOT"

    expected = snapshot_id(DataPaths.discover())
    assert declared.group(1) == expected, (
        f"wrangler.toml deploys DATA_SNAPSHOT={declared.group(1)!r} but the committed "
        f"data is {expected!r}. Run `hoopslab snapshot` and update [env.production], "
        f"or the deployed Worker will serve the previous snapshot from KV."
    )


def test_production_does_not_ship_an_empty_snapshot(production_vars: str) -> None:
    """The specific failure this file was written after.

    An empty value is not "no caching". It is a cache namespaced under a prefix
    that never changes, so every re-seed inherits the previous deployment's
    entries — the exact behaviour the variable exists to prevent, achieved by
    leaving it at its default.
    """
    declared = re.search(r'DATA_SNAPSHOT = "([^"]*)"', production_vars)
    assert declared and declared.group(1), (
        "[env.production] ships an empty DATA_SNAPSHOT, which namespaces the "
        "entire cache under a prefix that never changes"
    )

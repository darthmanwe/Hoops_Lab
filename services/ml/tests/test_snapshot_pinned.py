"""The deployed snapshot id must be the committed data's snapshot id.

``DATA_SNAPSHOT`` is what ``/health`` reports, and ``deploy.yml`` reads it back
from there to decide whether the data moved and D1 needs re-seeding. A wrong
value is harmful in both directions: too old and the deploy spends ~159,000
billed row writes it did not need, advanced without a matching seed and it skips
one it did. Responses do not depend on it — ``meta.snapshot`` is read from the
``data_snapshots`` table — so the two disagreeing is how a mismatch shows itself.

This docstring used to say the value "prefixes every cache key the Worker
writes". It does not; there is no such cache. That claim lived in six other
places and was corrected in dcc6b2a, and this file was missed.

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

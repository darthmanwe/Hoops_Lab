"""wrangler must not fall below the version that stopped killing the dev server.

Before 4.129.1, ``wrangler dev`` exited when a single request failed
transiently — most often a request arriving just as an idle internal connection
was closed, after roughly five seconds without traffic, which is exactly the gap
while the web dev server boots. It printed an empty ``[ERROR]`` with no message
and unbound the port, so every remaining test in the browser suite failed on
missing page content and nothing named the cause. See
https://github.com/cloudflare/workers-sdk/issues/15317.

That cost three CI runs and a dig through wrangler's own logs to attribute. A
downgrade would bring it back, and it would come back looking like sixty-four
broken pages rather than one broken dependency — which is why this is a test
rather than a comment.

It lives in the Python suite because the Worker suite runs inside workerd, where
reading files from the repository is not the natural thing to do, and because
this is a repository invariant rather than a runtime one. `test_snapshot_pinned`
is here for the same reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hoopslab.paths import find_repo_root

#: The release carrying the ProxyWorker fix.
FLOOR = (4, 129, 1)

MANIFESTS = ("package.json", "apps/api/package.json", "apps/web/package.json")


def _version(text: str) -> tuple[int, ...]:
    """Parse an exact pin. CONTRIBUTING forbids ranges, so there is no caret."""
    return tuple(int(part) for part in text.split("."))


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_the_pinned_wrangler_is_at_least_the_fixed_release(manifest: str) -> None:
    package = json.loads((Path(find_repo_root()) / manifest).read_text(encoding="utf-8"))
    declared = package.get("devDependencies", {}).get("wrangler") or package.get(
        "dependencies", {}
    ).get("wrangler")

    assert declared, (
        f"{manifest} does not declare wrangler. Every one of these needs it: the root "
        "scripts run `wrangler` directly, and each app runs its own."
    )
    assert not declared.startswith(("^", "~", ">")), (
        f"{manifest} pins wrangler as {declared!r}; CONTRIBUTING requires exact versions."
    )
    assert _version(declared) >= FLOOR, (
        f"{manifest} pins wrangler {declared}, below {'.'.join(map(str, FLOOR))}. "
        "Older versions exit the dev server on one transient request "
        "(cloudflare/workers-sdk#15317), which fails the browser suite everywhere "
        "except where the problem is."
    )

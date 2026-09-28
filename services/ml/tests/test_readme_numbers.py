"""The README's numbers must be the run log's numbers.

`hoopslab train --verify` proves the model reproduces its committed metrics. It
says nothing about the roughly thirty figures quoted in prose across the README,
the model card and the ADRs — and those are what a reader actually sees.

They drift. A data fix moved usage beta from 0.7236 to 0.7268 and left nine
stale figures behind: two different Dončić tables disagreeing with each other
and with the API, a baseline MAE of 0.0505 against an actual 0.0504, a direction
slope of 0.982 against 0.986. Every one was found by hand, one at a time, and
the next retrain would have produced a fresh set.

A portfolio that leads with "every number carries its provenance" cannot have a
front page that quotes the model from memory. This test is the check that makes
the claim true: the documents are parsed, the figures are pulled out, and each
is compared to the committed run log at the precision it was written.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from hoopslab.paths import find_repo_root

#: Documents that quote model numbers and are read by a human.
DOCUMENTS = (
    "README.md",
    "services/ml/src/hoopslab/configs/model_cards/translation.md",
    "docs/adr/0004-two-stage-translation.md",
    "docs/adr/0005-report-what-does-not-work.md",
)


@pytest.fixture(scope="module")
def repo() -> Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def run(repo: Path) -> dict[str, Any]:
    """The most recent committed training run, which is what `--verify` pins."""
    runs = sorted((repo / "services" / "ml" / "runs" / "translation").glob("*.json"))
    if not runs:
        pytest.skip("no committed training run")
    return json.loads(runs[-1].read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prose(repo: Path) -> dict[str, str]:
    return {
        name: (repo / name).read_text(encoding="utf-8")
        for name in DOCUMENTS
        if (repo / name).is_file()
    }


def _numbers(text: str) -> set[str]:
    """Every decimal in the text, as written."""
    return set(re.findall(r"\d+\.\d+", text))


def test_every_headline_mae_appears_as_written(run: dict[str, Any], prose: dict[str, str]) -> None:
    """0.0332 and 0.0472, to four places, wherever an MAE is quoted."""
    readme = prose["README.md"]
    for metric, block in run["metrics"].items():
        written = f"{block['mae']:.4f}"
        assert written in readme, f"README does not quote the {metric} MAE {written}"


def test_no_document_quotes_a_stale_mae(run: dict[str, Any], prose: dict[str, str]) -> None:
    """The failure mode is a *near-miss* — 0.0471 for 0.0472 — not an absent number.

    Anything in the neighbourhood of a real MAE but not equal to it is a figure
    from a previous run that was never updated.
    """
    live = {f"{b['mae']:.4f}" for b in run["metrics"].values()}
    for block in run["metrics"].values():
        live.update(f"{v:.4f}" for v in block["baseline_mae"].values())
        # The shuffled-target control is quoted in the model card and is just
        # as much a committed metric as the baselines. Leaving it out made this
        # test report the true-shooting control as a figure from an old run.
        live.update(f"{v:.4f}" for v in (block["shuffled_mae"], *block["mae_ci"]))

    for name, text in prose.items():
        for written in _numbers(text):
            if not written.startswith("0.0") or len(written) != 6:
                continue
            value = float(written)
            near = [x for x in live if abs(float(x) - value) < 5e-4]
            if near and written not in live:
                pytest.fail(
                    f"{name} quotes {written}, which is not a committed metric but sits "
                    f"beside {sorted(near)}. It is a figure from an earlier run."
                )


def test_baseline_maes_match(run: dict[str, Any], prose: dict[str, str]) -> None:
    readme = prose["README.md"]
    for name, value in run["metrics"]["usg_pct"]["baseline_mae"].items():
        written = f"{value:.4f}"
        assert written in readme, f"README does not quote the {name} baseline {written}"


def test_the_shared_slope_matches(run: dict[str, Any], prose: dict[str, str]) -> None:
    beta = run["metrics"]["usg_pct"]["beta"]
    written = f"{beta:.3f}"
    assert any(written in text for text in prose.values()), f"no document quotes beta {written}"


def test_the_direction_slopes_that_carry_the_selection_argument_match(
    run: dict[str, Any], prose: dict[str, str]
) -> None:
    """The EL->NBA / NBA->EL gap is the evidence that compression is partly selection.

    Quoting it from an old run would misstate the size of the effect the whole
    "what this is not" section rests on.
    """
    slopes = run["metrics"]["usg_pct"]["direction_slopes"]
    readme = prose["README.md"]
    for direction in ("EL->NBA", "NBA->EL"):
        written = f"{slopes[direction]:.3f}"
        assert written in readme, f"README does not quote the {direction} slope {written}"


def test_the_sample_sizes_match(run: dict[str, Any], prose: dict[str, str]) -> None:
    readme = prose["README.md"]
    usg = run["metrics"]["usg_pct"]
    assert str(usg["n_pairs"]) in readme, "README does not state the pair count"
    assert f"{usg['n_persistence']:,}" in readme or str(usg["n_persistence"]) in readme


def test_the_badge_total_is_the_sum_of_its_parts(prose: dict[str, str]) -> None:
    """The badge and the two per-suite counts must agree with each other.

    Deliberately an internal-consistency check and not a measurement. The true
    count is a runtime property — 116 test *functions* in this package expand
    to 255 tests through parametrisation, so counting `def test_` would pin the
    wrong number confidently, which is the failure this file exists to prevent
    rather than commit. What is checkable without running anything is that the
    three figures in the README describe the same suite, and the likely mistake
    is updating one of them and not the others.
    """
    readme = prose["README.md"]

    badge = re.search(r"tests-(\d+)%20offline", readme)
    worker = re.search(r"# (\d+) Worker tests", readme)
    python = re.search(r"# (\d+) Python tests", readme)
    assert badge and worker and python, "README no longer states all three test counts"

    total, parts = int(badge.group(1)), int(worker.group(1)) + int(python.group(1))
    assert total == parts, (
        f"badge says {total} tests; the commands table says {worker.group(1)} + "
        f"{python.group(1)} = {parts}"
    )


def test_the_selection_gaps_match(run: dict[str, Any], prose: dict[str, str]) -> None:
    """Including the sign, which is the entire point of the table."""
    readme = prose["README.md"]
    for row in run["selection"]:
        if row["metric"] != "usg_pct":
            continue
        gap = row["gap_sd"]
        written = f"{abs(gap):.2f}"
        assert written in readme, (
            f"README does not quote the {row['direction']} selection gap {gap:+.2f} sd"
        )
        assert str(row["n_movers"]) in readme


#: A roadmap row marked done, and a file that must exist for that to be true.
#:
#: Only phases whose deliverable is a checkable artifact appear here. The rest
#: are judgement calls and a test asserting them would be theatre.
PHASE_ARTIFACTS = {
    "3": ("contracts/openapi.json", "the generated OpenAPI document"),
    "5": ("playwright.config.ts", "the browser suite that checks the pages"),
    "6": ("data/llm_cache", "the committed responses that make the demo free"),
}


def test_a_phase_is_only_done_if_its_artifact_exists(repo: Path, prose: dict[str, str]) -> None:
    """The check that would have caught three overclaims at once.

    Phase 3 was marked done with "OpenAPI" in its deliverables while
    `/openapi.json` returned 404 and the package that would have produced it
    was installed and imported nowhere. Phase 5 was marked done against the
    exit criterion "axe clean at serious/critical on every page", and nothing
    had ever run axe — there was no Playwright dependency.

    Neither was a lie anyone told. Both were rows that stopped being true after
    they were written, in a table nothing checked. Marking a phase done now
    requires the thing it delivered to be on disk.
    """
    readme = prose["README.md"]

    for phase, (artifact, description) in PHASE_ARTIFACTS.items():
        row = re.search(rf"^\| \*\*{phase}\*\* \|(.+)$", readme, re.MULTILINE)
        assert row, f"README roadmap has no row for phase {phase}"

        if "done" not in row.group(1):
            continue

        assert (repo / artifact).exists(), (
            f"phase {phase} is marked done, but {artifact} does not exist — "
            f"that row claims {description}"
        )


#: Spelled out because the README spells it out. A count written as a word is
#: the kind of figure nothing greps for, which is why it goes stale quietly.
COUNT_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
}


def test_the_decision_record_table_and_the_directory_agree(
    repo: Path, prose: dict[str, str]
) -> None:
    """Both directions, for the reason ADR 9 exists.

    The registry drift check stayed green for months while asserting only that
    every declared endpoint had a handler, never that every handler was
    declared — and the drift that existed was in the direction nobody looked.
    The same shape applies here. A README that links eight ADRs while ten are
    on disk is a front page that has quietly stopped describing the project,
    and a table row pointing at a file that was renamed is a dead link on the
    document most readers start from.

    ADR 9 and 10 were written months after the decisions they record shipped.
    That gap is what this test is here to stop happening again.
    """
    readme = prose["README.md"]

    linked = set(re.findall(r"\(docs/adr/(\d{4}-[a-z0-9-]+\.md)\)", readme))
    on_disk = {path.name for path in (repo / "docs" / "adr").glob("[0-9]*.md")}

    assert linked - on_disk == set(), (
        f"the README links decision records that are not on disk: {sorted(linked - on_disk)}"
    )
    assert on_disk - linked == set(), (
        "these decision records exist but the README's table does not list them — "
        f"the direction nobody looks: {sorted(on_disk - linked)}"
    )


def test_the_decision_count_matches_the_table(repo: Path, prose: dict[str, str]) -> None:
    """The prose count, which is written as a word and so is never grepped."""
    readme = prose["README.md"]
    total = len(list((repo / "docs" / "adr").glob("[0-9]*.md")))

    claimed = re.search(r"^The ([a-z]+) decisions that shaped the rest", readme, re.MULTILINE)
    assert claimed, "the README no longer introduces its decision records with a count"

    expected = COUNT_WORDS.get(total)
    assert expected is not None, f"{total} decision records, beyond what this test spells"
    assert claimed.group(1) == expected, (
        f"the README claims {claimed.group(1)} decision records; docs/adr holds {total}"
    )

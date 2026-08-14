"""Evidence bundles built from the committed snapshot.

These run against real gold rather than a stub, because the properties worth
asserting are properties of the actual data: that a real name never survives
redaction, that the outcome never leaks in, and that ids stay stable across
runs so committed cache keys keep resolving.
"""

from __future__ import annotations

import pytest

from hoopslab.llm.evidence import BundleSource, actual_outcome, build_bundle
from hoopslab.llm.harness import select_eval_set
from hoopslab.paths import DataPaths


@pytest.fixture(scope="module")
def source() -> BundleSource:
    paths = DataPaths.discover()
    if not (paths.gold / "transition_pairs.parquet").is_file():
        pytest.skip("no committed gold snapshot")
    return BundleSource.load(paths)


@pytest.fixture(scope="module")
def first_transition(source: BundleSource) -> tuple[str, str]:
    transitions = source.transitions()
    assert transitions, "the snapshot contains no scorable transitions"
    return transitions[0]


def test_a_bundle_carries_the_numbers_a_brief_needs(
    source: BundleSource, first_transition: tuple[str, str]
) -> None:
    bundle = build_bundle(source, *first_transition)
    statements = " | ".join(f.statement for f in bundle.facts)

    for expected in (
        "Source-season usage rate",
        "Projected usage rate",
        "80% prediction interval",
        "Out-of-fold mean absolute error",
        "Number of historical",
    ):
        assert expected in statements, expected


def test_fact_ids_are_unique_and_sequential(
    source: BundleSource, first_transition: tuple[str, str]
) -> None:
    """Ids feed the cache key, so an unstable ordering invalidates every entry."""
    bundle = build_bundle(source, *first_transition)
    ids = [fact.id for fact in bundle.facts]
    assert ids == [f"f{i:02d}" for i in range(1, len(ids) + 1)]


def test_rebuilding_produces_an_identical_digest(
    source: BundleSource, first_transition: tuple[str, str]
) -> None:
    assert (
        build_bundle(source, *first_transition).digest()
        == build_bundle(source, *first_transition).digest()
    )


def test_anonymised_bundles_never_render_the_real_name(source: BundleSource) -> None:
    for person_id, season_id in source.transitions()[:40]:
        bundle = build_bundle(source, person_id, season_id, anonymized=True)
        rendered = bundle.render()
        assert bundle.subject == "Player A"
        for term in bundle.redacted:
            assert term not in rendered, f"{term} survived redaction for {person_id}"


def test_named_mode_uses_the_real_name(
    source: BundleSource, first_transition: tuple[str, str]
) -> None:
    bundle = build_bundle(source, *first_transition, anonymized=False)
    assert bundle.subject != "Player A"
    assert bundle.subject in bundle.render()


def test_the_outcome_is_never_in_the_bundle(source: BundleSource) -> None:
    """The brief is written blind to what happened; that is the whole design.

    Checked numerically rather than by reading the code, because a future fact
    that happened to include the target value would defeat the design silently.
    """
    for person_id, season_id in source.transitions()[:40]:
        bundle = build_bundle(source, person_id, season_id)
        outcome = actual_outcome(source, person_id, season_id)
        values = [f.value for f in bundle.facts if f.value is not None]
        for metric, actual in outcome.items():
            assert not any(abs(v - actual) < 1e-12 for v in values), (
                f"{metric} outcome {actual} appears in the bundle for {person_id}"
            )


def test_the_bundle_tells_the_model_when_it_loses_to_a_baseline(
    source: BundleSource, first_transition: tuple[str, str]
) -> None:
    """A report should be able to say the projection is worthless, if it is."""
    bundle = build_bundle(source, *first_transition)
    quality = [f for f in bundle.facts if "trivial baseline" in f.statement]
    assert quality, "no baseline comparison reached the evidence"
    assert any("WORSE" in f.statement or "beats it" in f.statement for f in quality)


def test_an_unobserved_transition_is_refused(source: BundleSource) -> None:
    with pytest.raises(KeyError, match="No scored transition"):
        build_bundle(source, "person-that-does-not-exist", "NBA_2018")


def test_the_eval_set_is_deterministic(source: BundleSource) -> None:
    assert select_eval_set(source, per_direction=3) == select_eval_set(source, per_direction=3)


def test_the_eval_set_spans_both_headline_directions(source: BundleSource) -> None:
    selection = select_eval_set(source, per_direction=5)
    directions = {
        build_bundle(source, person_id, season_id).direction for person_id, season_id in selection
    }
    assert {"EL->NBA", "NBA->EL"} <= directions

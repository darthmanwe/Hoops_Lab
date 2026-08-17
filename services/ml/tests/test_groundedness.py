"""The groundedness checks, exercised against reports built to break them.

The reports here are fixtures, written by hand and named as such. They are not
in the response cache and never will be: that directory holds what a model
actually said, and putting authored text there would make the demo claim a
provenance it does not have.
"""

from __future__ import annotations

import pytest

from hoopslab.llm.groundedness import (
    check_report,
    trace_numbers,
    unsupported_entities,
)
from hoopslab.llm.schemas import Claim, EvidenceBundle, Fact, ScoutingReport

FACTS = [
    Fact(
        id="f01",
        statement="The subject played in the EuroLeague for Team X in 2017-18",
        unit="season",
        source="transition_pairs",
    ),
    Fact(
        id="f02",
        statement="Minutes played in the source season",
        value=1180.0,
        unit="count",
        source="player_seasons.minutes",
    ),
    Fact(
        id="f03",
        statement="Source-season usage rate",
        value=0.284,
        unit="fraction",
        source="player_seasons.usg_pct",
    ),
    Fact(
        id="f04",
        statement="Projected usage rate in the NBA",
        value=0.214,
        unit="fraction",
        source="translation model",
    ),
    Fact(
        id="f05",
        statement="Lower bound of the 80% prediction interval for usage rate",
        value=0.168,
        unit="fraction",
        source="translation model",
    ),
    Fact(
        id="f06",
        statement="Upper bound of the 80% prediction interval for usage rate",
        value=0.260,
        unit="fraction",
        source="translation model",
    ),
    Fact(
        id="f07",
        statement="Number of historical EL->NBA transitions the estimate rests on",
        value=61.0,
        unit="count",
        source="transition_pairs",
    ),
    Fact(
        id="f08",
        statement="Points per 75 possessions in the source season",
        value=18.4,
        unit="per_75",
        source="player_seasons.pts_per_75",
    ),
]


def bundle(**overrides: object) -> EvidenceBundle:
    defaults: dict[str, object] = {
        "person_id": "p1",
        "subject": "Player A",
        "direction": "EL->NBA",
        "source_season_id": "EL_2017",
        "target_season_id": "NBA_2018",
        "source_season_label": "2017-18 EuroLeague",
        "target_season_label": "2018-19 NBA",
        "anonymized": True,
        "facts": FACTS,
        "redacted": ["Luka Doncic", "Doncic", "Real Madrid", "Madrid"],
    }
    defaults.update(overrides)
    return EvidenceBundle(**defaults)  # type: ignore[arg-type]


def report(**overrides: object) -> ScoutingReport:
    defaults: dict[str, object] = {
        "headline": "A high-usage EuroLeague guard projected into a smaller NBA role",
        "projection": Claim(
            text="Usage rate projects to 21.4%, down from 28.4% in the EuroLeague.",
            fact_ids=["f03", "f04"],
        ),
        "uncertainty": Claim(
            text="The 80% interval runs from 16.8% to 26.0%, which is wide enough to rank "
            "a cohort and too wide to price one contract.",
            fact_ids=["f05", "f06"],
        ),
        "strengths": [
            Claim(text="Carried 1180 minutes of a heavy offensive load.", fact_ids=["f02", "f03"])
        ],
        "risks": [
            Claim(text="The estimate rests on 61 historical moves.", fact_ids=["f07"]),
        ],
        "confidence": "moderate",
    }
    defaults.update(overrides)
    return ScoutingReport(**defaults)  # type: ignore[arg-type]


def named(check_results: object, name: str) -> object:
    return next(c for c in check_results.checks if c.name == name)  # type: ignore[attr-defined]


def test_a_faithful_report_passes_every_check() -> None:
    result = check_report(report(), bundle())
    assert result.grounded, [c.render() for c in result.checks if not c.passed]
    assert result.n_traced == len(result.tokens)


def test_an_invented_number_is_caught() -> None:
    """The number is plausible, adjacent to real ones, and not in the evidence."""
    broken = report(
        projection=Claim(text="Usage rate projects to 23.7%.", fact_ids=["f04"]),
    )
    result = check_report(broken, bundle())
    assert not result.grounded
    assert not named(result, "numbers").passed  # type: ignore[attr-defined]
    assert [t.text for t in result.untraced] == ["23.7%"]


def test_percentages_and_fractions_are_the_same_claim() -> None:
    """0.284 stored, "28.4%" written — a conversion, not a fabrication."""
    tokens = trace_numbers("Usage was 28.4%, or 0.284 as a fraction.", bundle())
    assert all(token.traced for token in tokens)


def test_precision_is_held_to_what_the_model_wrote() -> None:
    """ "21%" is a fair rounding of 0.214; "21.9%" is not."""
    assert trace_numbers("about 21%", bundle())[0].traced
    assert not trace_numbers("about 21.9%", bundle())[0].traced


def test_per_75_converts_to_per_36() -> None:
    tokens = trace_numbers("scoring 8.8 per 36 possessions", bundle())
    assert tokens[0].traced


def test_a_citation_to_a_nonexistent_fact_is_caught() -> None:
    broken = report(risks=[Claim(text="Something.", fact_ids=["f99"])])
    result = check_report(broken, bundle())
    assert not named(result, "fact_ids").passed  # type: ignore[attr-defined]


def test_naming_the_redacted_subject_fails() -> None:
    """Accents must not be a way past the check."""
    for leak in ("Doncic", "Dončić", "real madrid"):
        broken = report(headline=f"{leak} projects into a smaller role")
        result = check_report(broken, bundle())
        assert not named(result, "anonymity").passed, leak  # type: ignore[attr-defined]


def test_a_redacted_name_inside_an_ordinary_word_is_not_a_leak() -> None:
    """ "Real Madrid" must not make "really" a failure."""
    fine = report(
        risks=[Claim(text="The interval is really wide at 61 comparable moves.", fact_ids=["f07"])]
    )
    result = check_report(fine, bundle())
    assert named(result, "anonymity").passed, named(result, "anonymity").detail  # type: ignore[attr-defined]


def test_named_mode_does_not_pretend_to_check_anonymity() -> None:
    check = named(check_report(report(), bundle(anonymized=False)), "anonymity")
    assert check.passed and "not applicable" in check.detail  # type: ignore[attr-defined]


def test_an_invented_team_is_caught_without_a_name_list() -> None:
    broken = report(
        risks=[Claim(text="He struggled against Panathinaikos last year.", fact_ids=["f07"])]
    )
    assert "Panathinaikos" in unsupported_entities(broken.prose(), bundle())
    assert not named(check_report(broken, bundle()), "anonymity").passed  # type: ignore[attr-defined]


def test_sentence_initial_capitals_are_not_proper_nouns() -> None:
    """A check that fires every other sentence is a check nobody reads."""
    prose = "Usage falls. His role narrows. That is the projection."
    assert unsupported_entities(prose, bundle()) == []


def test_an_adjectival_compound_is_not_an_invented_name() -> None:
    """The one failure in a held-out batch of thirty, and it was the checker's.

    "the G League-anchored cohorts" reads as a recalled entity only if every
    part of a compound must appear in the evidence — but "anchored" is a
    participle, not a proper noun, and no capital claims otherwise.
    """
    prose = "The sample is thin next to the G League-anchored cohorts available."
    assert unsupported_entities(prose, bundle()) == []


def test_a_capitalised_part_of_a_compound_is_still_checked() -> None:
    """The fix above must not become a way to smuggle a name past the check."""
    prose = "The move makes him a Panathinaikos-bound target this summer."
    assert "Panathinaikos-bound" in unsupported_entities(prose, bundle())


def test_prose_contradicting_the_sign_of_the_projection_is_caught() -> None:
    broken = report(
        projection=Claim(
            text="He should take on a larger share of possessions at 21.4%.",
            fact_ids=["f03", "f04"],
        )
    )
    result = check_report(broken, bundle())
    assert not named(result, "direction").passed  # type: ignore[attr-defined]


def test_certainty_language_is_caught() -> None:
    broken = report(
        uncertainty=Claim(text="He will definitely settle near 21.4%.", fact_ids=["f04"])
    )
    assert not named(check_report(broken, bundle()), "calibration").passed  # type: ignore[attr-defined]


def test_high_confidence_against_a_losing_model_is_caught() -> None:
    losing = bundle(
        facts=[
            *FACTS,
            Fact(
                id="f09",
                statement=(
                    "Error of the best trivial baseline for true shooting percentage "
                    "(league_mean); the model is WORSE than it and should not be trusted here"
                ),
                value=0.043,
                unit="fraction",
                source="run log",
            ),
        ]
    )
    result = check_report(report(confidence="high"), losing)
    assert not result.grounded
    assert any(c.name == "calibration_vs_baseline" for c in result.checks)


def test_swapping_the_evidence_breaks_the_report() -> None:
    """The negative control, in miniature.

    If a report still passes against a different player's evidence, the checks
    are not reading the evidence and every rate they produce is uninformative.
    """
    other = bundle(
        person_id="p2",
        facts=[
            Fact(
                id="f01",
                statement="Source-season usage rate",
                value=0.191,
                unit="fraction",
                source="player_seasons.usg_pct",
            ),
            Fact(
                id="f02",
                statement="Projected usage rate in the NBA",
                value=0.155,
                unit="fraction",
                source="translation model",
            ),
        ],
    )
    assert not check_report(report(), other).grounded


@pytest.mark.parametrize("text", ["2017-18", "1,180 minutes", "80% interval"])
def test_shapes_that_look_like_fabrication_but_are_not(text: str) -> None:
    """Season labels, thousands separators and the interval's own name."""
    tokens = trace_numbers(text, bundle())
    assert all(token.traced for token in tokens), [t.text for t in tokens if not t.traced]

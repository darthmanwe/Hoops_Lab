"""The report schema is the citation guarantee, so it gets tested as one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hoopslab.llm.schemas import Claim, EvidenceBundle, Fact, ScoutingReport


def _bundle(**overrides: object) -> EvidenceBundle:
    defaults: dict[str, object] = {
        "person_id": "p1",
        "subject": "Player A",
        "direction": "EL->NBA",
        "source_season_id": "EL_2017",
        "target_season_id": "NBA_2018",
        "source_season_label": "2017-18 EuroLeague",
        "target_season_label": "2018-19 NBA",
        "anonymized": True,
        "facts": [
            Fact(id="f01", statement="Source usage", value=0.284, unit="fraction", source="gold"),
            Fact(id="f02", statement="Minutes", value=1234.0, unit="count", source="gold"),
        ],
    }
    defaults.update(overrides)
    return EvidenceBundle(**defaults)  # type: ignore[arg-type]


def test_a_claim_cannot_be_uncited() -> None:
    """The one hard rule of this layer is expressed in the type, not the prompt."""
    with pytest.raises(ValidationError):
        Claim(text="He will be good.", fact_ids=[])


def test_report_requires_at_least_one_strength_and_risk() -> None:
    with pytest.raises(ValidationError):
        ScoutingReport(
            headline="h",
            projection=Claim(text="p", fact_ids=["f01"]),
            uncertainty=Claim(text="u", fact_ids=["f01"]),
            strengths=[],
            risks=[Claim(text="r", fact_ids=["f01"])],
            confidence="low",
        )


def test_cited_ids_covers_every_claim() -> None:
    report = ScoutingReport(
        headline="h",
        projection=Claim(text="p", fact_ids=["f01"]),
        uncertainty=Claim(text="u", fact_ids=["f02"]),
        strengths=[Claim(text="s", fact_ids=["f01", "f02"])],
        risks=[Claim(text="r", fact_ids=["f02"])],
        confidence="moderate",
    )
    assert sorted(set(report.cited_ids())) == ["f01", "f02"]
    assert "h" in report.prose() and "r" in report.prose()


def test_rendered_bundle_states_rates_as_percentages() -> None:
    """The checker knows about this conversion; the rendering has to match it."""
    assert "28.4%" in _bundle().render()


def test_digest_depends_only_on_the_facts() -> None:
    """Cache keys must not move when unrelated metadata does."""
    baseline = _bundle().digest()
    assert _bundle(subject="Someone Real", anonymized=False).digest() == baseline

    changed = _bundle(
        facts=[Fact(id="f01", statement="Source usage", value=0.285, unit="fraction", source="g")]
    )
    assert changed.digest() != baseline


def test_redactions_are_never_rendered() -> None:
    """A leak-detection list that reached the model would create the leak."""
    bundle = _bundle(redacted=["Luka Doncic", "Real Madrid"])
    rendered = bundle.render()
    assert "Doncic" not in rendered
    assert "Madrid" not in rendered

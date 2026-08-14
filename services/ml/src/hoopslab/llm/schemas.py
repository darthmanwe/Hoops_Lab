"""Evidence and report schemas.

The report schema is the enforcement mechanism, not documentation of an
intention. ``Claim.fact_ids`` has ``min_length=1``, so a claim without a
citation is not a report the parser will accept — the failure happens at
validation time rather than being discovered later by a reviewer reading
output.

Structured outputs strip constraints the API's JSON Schema subset cannot
express (array length is one of them) and the SDK re-applies them client side,
so the guarantee holds either way: the model is steered by the schema, and
Pydantic is what actually enforces it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

#: Units a fact can carry. The groundedness checker uses these to decide which
#: conversions of a value count as the same number — a model writing "28.4%"
#: for a stored 0.284 is quoting the evidence, not inventing a figure.
Unit = Literal[
    "fraction",  # 0-1 rates: usage, true shooting, assist share
    "per_75",  # per-75-possession counting stats
    "count",  # games, minutes, cohort sizes
    "years",  # age
    "sd",  # standardised within league-season
    "season",  # a season label, carried as text
    "none",  # unitless: slopes, correlations
]


class Fact(BaseModel):
    """One admissible number, with the provenance that makes it checkable."""

    id: str
    statement: str
    value: float | None = None
    unit: Unit = "none"
    source: str

    def render(self) -> str:
        if self.value is None:
            return f"[{self.id}] {self.statement}"
        return f"[{self.id}] {self.statement}: {_format(self.value, self.unit)}"


class EvidenceBundle(BaseModel):
    """Everything the model is permitted to know about one transition.

    Complete by construction: if a number is not here, no correct report
    contains it. That is what makes the numeric-traceability check meaningful
    rather than a heuristic.
    """

    person_id: str
    subject: str
    direction: str
    source_season_id: str
    target_season_id: str
    source_season_label: str
    target_season_label: str
    anonymized: bool
    facts: list[Fact]

    #: Strings that must not appear in a report written from this bundle: the
    #: subject's real name and the real club names, carried alongside the
    #: redacted bundle so the anonymity check has something to test against.
    #: Never rendered, so it cannot reach the model.
    redacted: list[str] = Field(default_factory=list)

    @property
    def fact_ids(self) -> set[str]:
        return {fact.id for fact in self.facts}

    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def render(self) -> str:
        """The exact text the model sees. Also what the cache key hashes."""
        header = (
            f"Subject: {self.subject}\n"
            f"Move: {self.direction}, from {self.source_season_label} "
            f"to {self.target_season_label}\n"
        )
        return header + "\nEvidence:\n" + "\n".join(f.render() for f in self.facts)

    def digest(self) -> str:
        """Content hash over the facts, stable across runs and platforms."""
        payload = json.dumps(
            [f.model_dump() for f in self.facts],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("ascii")).hexdigest()


class Claim(BaseModel):
    """A sentence and the evidence it rests on.

    ``min_length=1`` is the whole point: there is no way to express an uncited
    claim in this type, so "every claim is cited" is a property of the parse
    rather than a property of the prompt being obeyed.
    """

    text: str
    fact_ids: list[str] = Field(min_length=1)


class ScoutingReport(BaseModel):
    """A structured brief on one league transition."""

    headline: str
    projection: Claim
    uncertainty: Claim
    strengths: list[Claim] = Field(min_length=1, max_length=4)
    risks: list[Claim] = Field(min_length=1, max_length=4)
    confidence: Literal["low", "moderate", "high"]

    def claims(self) -> list[Claim]:
        return [self.projection, self.uncertainty, *self.strengths, *self.risks]

    def prose(self) -> str:
        """Every piece of model-authored text, for the text-level checks."""
        return "\n".join([self.headline, *(claim.text for claim in self.claims())])

    def cited_ids(self) -> list[str]:
        return [fact_id for claim in self.claims() for fact_id in claim.fact_ids]


def _format(value: float, unit: Unit) -> str:
    """Render a value the way the report should quote it back.

    Rates are shown as percentages because that is how basketball writing
    states them, and the checker knows about the conversion — presenting 0.284
    and then flagging "28.4%" as unsupported would be a bug in the harness
    dressed up as a finding about the model.
    """
    if unit == "fraction":
        return f"{value * 100:.1f}%"
    if unit == "sd":
        return f"{value:+.2f} sd"
    if unit == "count":
        return f"{value:,.0f}"
    if unit == "years":
        return f"{value:.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")

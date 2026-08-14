"""Deterministic groundedness checks.

Everything here runs offline, on committed responses, with no key and no
network. That is the point: a groundedness claim that can only be re-measured
by spending money is a claim nobody will re-measure.

Five checks, each answering a question that can be settled by reading:

``citations``      does every claim cite at least one fact?
``fact_ids``       does every cited id exist in the bundle?
``numbers``        is every number in the prose one the bundle contained, or a
                   documented conversion of one?
``anonymity``      did the model name the subject it was not told about?
``direction``      does the prose agree with the sign of the projection?

The numeric check is the one that does the work, and it is deliberately blunt:
extract every numeric token from the report, extract every numeric token from
the rendered bundle, allow a fixed set of unit conversions, and require a match
at the precision the model itself wrote. Its known weaknesses are stated rather
than smoothed over:

* Numbers spelled as words ("two seasons") are invisible to it.
* A bare small integer has a wide rounding window, so "3" matches anything in
  [2.5, 3.5]. Small integers are the weakest case.
* Matching a number is not the same as using it correctly. A report can quote
  the lower interval bound and call it the projection and still pass. That is
  what the judge rubric is for, and why the judge is not redundant even though
  it is worse than a regex at catching fabrication.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from hoopslab.llm.schemas import EvidenceBundle, ScoutingReport

#: A signed decimal, with optional thousands separators and a trailing percent.
#: Scanning is left to right and non-overlapping, so "2018-19" yields 2018 and
#: -19; the bundle text tokenises identically, which is what matters.
NUMERIC = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?%?")

#: Conversions a correct report is allowed to apply to a bundle value. Each is
#: a real unit relationship in this domain, not a tolerance in disguise.
CONVERSIONS: tuple[tuple[str, float], ...] = (
    ("identity", 1.0),
    ("fraction to percent", 100.0),
    ("percent to fraction", 0.01),
    ("per 75 to per 36", 36.0 / 75.0),
    ("per 36 to per 75", 75.0 / 36.0),
)

#: Absolute floor on the rounding window, so a value written to more decimals
#: than it was given does not fail on floating-point noise.
EPSILON = 1e-9

#: Proper nouns a report may use without them appearing in the bundle.
ENTITY_ALLOWLIST = frozenset(
    {
        "nba",
        "euroleague",
        "g league",
        "gleague",
        "europe",
        "european",
        "america",
        "american",
        "player a",
        "team x",
        "team y",
    }
)

_RISE = re.compile(
    r"\b(larger|bigger|greater|increased?|increasing|higher|more)\b[^.]{0,40}"
    r"\b(usage|share|role|volume|possessions)\b",
    re.IGNORECASE,
)
_FALL = re.compile(
    r"\b(smaller|lower|reduced?|reducing|decreased?|decreasing|less|fewer)\b[^.]{0,40}"
    r"\b(usage|share|role|volume|possessions)\b",
    re.IGNORECASE,
)
_CERTAINTY = re.compile(
    r"\b(guaranteed|certainly will|without a doubt|no doubt|will definitely|is certain to)\b",
    re.IGNORECASE,
)


@dataclass
class CheckResult:
    """One named check over one report."""

    name: str
    passed: bool
    detail: str = ""

    def render(self) -> str:
        mark = "ok  " if self.passed else "FAIL"
        return f"    {mark} {self.name}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class NumericToken:
    """A number written in the report, and what supports it."""

    text: str
    value: float
    supported_by: str | None = None
    conversion: str | None = None

    @property
    def traced(self) -> bool:
        return self.supported_by is not None


@dataclass
class GroundednessResult:
    """Every check over one report, plus the traceability detail."""

    person_id: str
    target_season_id: str
    checks: list[CheckResult] = field(default_factory=list)
    tokens: list[NumericToken] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def n_traced(self) -> int:
        return sum(1 for token in self.tokens if token.traced)

    @property
    def untraced(self) -> list[NumericToken]:
        return [token for token in self.tokens if not token.traced]

    def provenance(self) -> str:
        """The line the web UI shows under a report."""
        return f"grounded: {self.n_traced}/{len(self.tokens)} numbers traced to source"

    def render(self) -> str:
        head = f"  {self.person_id} -> {self.target_season_id}  {self.provenance()}"
        return "\n".join([head, *(check.render() for check in self.checks)])


def check_report(report: ScoutingReport, bundle: EvidenceBundle) -> GroundednessResult:
    """Run every deterministic check over one report."""
    result = GroundednessResult(
        person_id=bundle.person_id, target_season_id=bundle.target_season_id
    )
    prose = report.prose()

    result.checks.append(_check_citations(report))
    result.checks.append(_check_fact_ids(report, bundle))

    result.tokens = trace_numbers(prose, bundle)
    untraced = [t for t in result.tokens if not t.traced]
    result.checks.append(
        CheckResult(
            name="numbers",
            passed=not untraced,
            detail=(
                ""
                if not untraced
                else f"{len(untraced)} untraceable: " + ", ".join(t.text for t in untraced[:6])
            ),
        )
    )

    result.checks.append(_check_anonymity(prose, bundle))
    result.checks.extend(_check_direction(report, bundle))
    return result


# ------------------------------------------------------------------ citations


def _check_citations(report: ScoutingReport) -> CheckResult:
    """Re-verify what the schema already guarantees.

    Redundant against a freshly parsed report and not against a cached one: the
    cache is a directory of editable JSON, and a check that only holds for
    responses nobody has touched is not a check.
    """
    uncited = [claim.text[:60] for claim in report.claims() if not claim.fact_ids]
    return CheckResult(
        name="citations",
        passed=not uncited,
        detail="" if not uncited else f"{len(uncited)} claim(s) cite nothing",
    )


def _check_fact_ids(report: ScoutingReport, bundle: EvidenceBundle) -> CheckResult:
    unknown = sorted(set(report.cited_ids()) - bundle.fact_ids)
    return CheckResult(
        name="fact_ids",
        passed=not unknown,
        detail="" if not unknown else f"cites ids not in the bundle: {', '.join(unknown)}",
    )


# --------------------------------------------------------------------- numbers


def trace_numbers(prose: str, bundle: EvidenceBundle) -> list[NumericToken]:
    """Match every number in the prose to something the bundle contained."""
    candidates = _candidate_values(bundle)
    return [_trace_one(match.group(0), candidates) for match in NUMERIC.finditer(prose)]


def _candidate_values(bundle: EvidenceBundle) -> list[tuple[float, str]]:
    """Every number the bundle supports, with the id that carries it.

    Built from two sources: the structured fact values, and every numeric token
    in the rendered bundle text. The second covers figures that live inside a
    statement — cohort counts, the "80%" in an interval's name — which a report
    may legitimately quote and which are just as much part of the evidence.
    """
    values: list[tuple[float, str]] = []

    for fact in bundle.facts:
        if fact.value is None:
            continue
        for _, factor in CONVERSIONS:
            values.append((fact.value * factor, fact.id))
            if fact.value < 0:
                values.append((abs(fact.value) * factor, fact.id))

    for match in NUMERIC.finditer(bundle.render()):
        for value, _ in _readings(match.group(0)):
            values.append((value, "bundle text"))

    return values


def _trace_one(text: str, candidates: list[tuple[float, str]]) -> NumericToken:
    readings = _readings(text)
    if not readings:
        return NumericToken(text=text, value=0.0, supported_by="unparsed")

    for value, window in readings:
        for candidate, source in candidates:
            if abs(value - candidate) <= window:
                return NumericToken(text=text, value=readings[0][0], supported_by=source)
    return NumericToken(text=text, value=readings[0][0])


def _readings(text: str) -> list[tuple[float, float]]:
    """The value(s) a token could denote, each with its own rounding window.

    A percent sign yields two readings — 28.4% is both the number 28.4 and the
    fraction 0.284 — because the bundle may hold either form and both are the
    same claim. The window travels with the reading rather than with the token:
    tolerating half of the last written decimal place is right for 28.4, and
    tolerating the same absolute amount for 0.284 would accept anything from
    0.234 to 0.334, which is most of the league.
    """
    cleaned = text.replace(",", "")
    percent = cleaned.endswith("%")
    cleaned = cleaned.rstrip("%")
    try:
        value = float(cleaned)
    except ValueError:
        return []

    decimals = len(cleaned.partition(".")[2])
    window = 0.5 * (10.0**-decimals) + EPSILON

    readings = [(value, window)]
    if percent:
        readings.append((value / 100.0, window / 100.0))
    return readings


# ------------------------------------------------------------------- anonymity


def _check_anonymity(prose: str, bundle: EvidenceBundle) -> CheckResult:
    """Did the model name someone it was never told about?

    Only meaningful on an anonymised bundle. In named mode the subject's name
    is in the evidence, so its presence proves nothing — which is exactly why
    the reported groundedness figure is the anonymised one.
    """
    if not bundle.anonymized:
        return CheckResult(name="anonymity", passed=True, detail="named mode; not applicable")

    haystack = _fold(prose)
    leaked = sorted({term for term in bundle.redacted if _mentions(haystack, _fold(term))})
    if leaked:
        return CheckResult(
            name="anonymity",
            passed=False,
            detail=f"names the redacted subject: {', '.join(leaked)}",
        )

    invented = unsupported_entities(prose, bundle)
    return CheckResult(
        name="anonymity",
        passed=not invented,
        detail=""
        if not invented
        else f"names entities absent from the bundle: {', '.join(invented)}",
    )


def unsupported_entities(prose: str, bundle: EvidenceBundle) -> list[str]:
    """Capitalised names in the prose that the bundle never mentioned.

    Catches the general case the redaction list cannot: a recalled team, a
    comparison to another player, a competition nobody supplied. Restricted to
    tokens that are *not* sentence-initial, because a capital after a full stop
    carries no information about proper-noun-hood and treating it as if it did
    would fire on every other sentence.
    """
    evidence = _fold(bundle.render())
    found: list[str] = []

    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        tokens = sentence.split()
        for index, raw in enumerate(tokens):
            token = raw.strip(".,;:()\"'")
            if index == 0 or not token[:1].isupper() or len(token) < 3:
                continue
            folded = _fold(token)
            if folded in ENTITY_ALLOWLIST or folded in evidence:
                continue
            found.append(token)

    return sorted(set(found))


def _fold(text: str) -> str:
    """Case-folded and de-accented, so "Doncic" matches "Dončić"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _mentions(haystack: str, needle: str) -> bool:
    """Whole-word containment.

    A plain substring test would flag "really" as leaking "Real Madrid" and
    "sacrifice" as leaking a three-letter club code. The first false positive
    costs the check its credibility; after that nobody reads it.
    """
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


# ------------------------------------------------------------------- direction


def _check_direction(report: ScoutingReport, bundle: EvidenceBundle) -> list[CheckResult]:
    """Committed consistency rules between the numbers and the prose.

    Deliberately few. Each one is a statement that can be settled against the
    evidence, not a style preference — a rule that fires on prose the evidence
    does not contradict teaches a reader to ignore the whole table.
    """
    prose = report.prose()
    checks: list[CheckResult] = []

    source_usage = _fact_value(bundle, "Source-season usage rate")
    projected_usage = _fact_value(bundle, "Projected usage rate in")

    if source_usage is not None and projected_usage is not None:
        falling = projected_usage < source_usage
        wrong_way = _RISE.search(prose) if falling else _FALL.search(prose)
        direction = "fall" if falling else "rise"
        checks.append(
            CheckResult(
                name="direction",
                passed=wrong_way is None,
                detail=(
                    ""
                    if wrong_way is None
                    else f"projection is a {direction} in usage, prose says {wrong_way.group(0)!r}"
                ),
            )
        )

    certainty = _CERTAINTY.search(prose)
    checks.append(
        CheckResult(
            name="calibration",
            passed=certainty is None,
            detail=(
                ""
                if certainty is None
                else f"states a projection as certain: {certainty.group(0)!r}"
            ),
        )
    )

    if report.confidence == "high" and _loses_to_baseline(bundle):
        checks.append(
            CheckResult(
                name="calibration_vs_baseline",
                passed=False,
                detail="claims high confidence while the evidence says the model "
                "loses to a trivial baseline",
            )
        )

    return checks


def _fact_value(bundle: EvidenceBundle, prefix: str) -> float | None:
    for fact in bundle.facts:
        if fact.statement.startswith(prefix):
            return fact.value
    return None


def _loses_to_baseline(bundle: EvidenceBundle) -> bool:
    return any("is WORSE than it" in fact.statement for fact in bundle.facts)

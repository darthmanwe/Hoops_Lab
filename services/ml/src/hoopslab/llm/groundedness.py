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
#:
#: The lookbehind is load-bearing and was added after it fired on real output.
#: A hyphen is only a minus sign when nothing word-like precedes it: in
#: "per-75 possessions" and in the range "16.8%-24.4%" the hyphen is a joiner,
#: and reading it as a sign invents the tokens -75 and -24.4% — numbers that
#: appear nowhere in the evidence, so the report gets failed for quoting a
#: figure it never quoted. A groundedness checker whose failures are mostly its
#: own punctuation handling is worse than none, because it trains the reader to
#: dismiss real findings alongside the noise.
NUMERIC = re.compile(r"(?<![\w%])[-+]?\d[\d,]*(?:\.\d+)?%?")

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

#: Capitalised words a report may use without them appearing in the bundle:
#: the competitions themselves, the redaction placeholders, and the handful of
#: statistical abbreviations a writer will reasonably introduce for terms the
#: bundle spells out ("mean absolute error" becomes MAE on second mention).
#: None of these can name a player or a club, which is what the check is for.
ENTITY_ALLOWLIST = frozenset(
    {
        "nba",
        "euroleague",
        "g",
        "league",
        "gleague",
        "europe",
        "european",
        "america",
        "american",
        "player",
        "team",
        "a",
        "x",
        "y",
        "mae",
        "sd",
        "ts",
        "pi",
        "ci",
        "usg",
        "to",
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

#: Words that turn a comparative into a statement about *spread* rather than
#: about the projection. "A span of more than two standard deviations of NBA
#: usage" contains "more … usage" and says nothing about usage rising; failing a
#: report for describing the width of its own interval is precisely backwards,
#: since describing that width is what the brief is supposed to do.
_ABOUT_SPREAD = re.compile(
    r"\b(standard deviations?|sd|interval|range|span|spread|wide|width|band)\b",
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

    Built from three sources: the structured fact values, every numeric token
    in the rendered bundle text, and a small closed set of named derivations.

    The second covers figures that live inside a statement — cohort counts, the
    "80%" in an interval's name — which a report may legitimately quote and
    which are just as much part of the evidence.

    The third exists because the first version of this check failed real
    reports for arithmetic that was correct. Writing "an 11.1-point spread"
    when the bundle gives bounds of 13.9% and 25.0% is not a fabrication; it is
    the single most useful sentence a brief about an interval can contain. See
    :func:`_derived_values` for why the set is kept to two named forms rather
    than opened up to differences generally.
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

    values.extend(_derived_values(bundle))
    return values


def _derived_values(bundle: EvidenceBundle) -> list[tuple[float, str]]:
    """Quantities a correct report may compute from two bundle facts.

    Deliberately two named forms, not "any difference between any two facts".
    A bundle carries ~39 numbers, so admitting arbitrary pairwise differences
    would add ~1,500 candidates and a fabricated figure would land on one of
    them by luck. Each form here is a specific quantity a scouting brief exists
    to state:

    * **interval width** — how uncertain the projection is, which is the point
      of quoting an interval at all.
    * **standardised distance from the receiving league's mean** — where the
      projection sits in that league, in the units the bundle already uses for
      the source season.
    * **the projected change** — the gap between the source-season value and
      the projection, which is the single thing a brief about a league move
      exists to state. "Usage drops by 6.7 points, from 26.6% to 19.9%" cites
      both endpoints correctly and quotes a third number that is their
      difference.

    Each derivation is computed twice: once from the stored values and once
    from the values **as the bundle rendered them**. That is not belt and
    braces. A rate stored as 0.128443 is shown to the model as "12.8%", so a
    standardised distance the model works out from what it was shown comes to
    1.35 where full precision gives 1.33 — and a checker demanding the
    full-precision figure fails a report for arithmetic that is correct on its
    inputs. The model can only compute from what it can see.

    Whether this broadening cost the check anything is measurable rather than
    arguable: the distractor control re-scores every report against another
    player's evidence, and it still rejects all of them.
    """
    values: list[tuple[float, str]] = []

    bounds: dict[tuple[str, str], dict[str, list[float]]] = {}
    means: dict[str, list[float]] = {}
    sds: dict[str, list[float]] = {}
    points: dict[str, list[float]] = {}

    for fact in bundle.facts:
        if fact.value is None:
            continue
        statement = fact.statement
        metric = _metric_of(statement)
        if metric is None:
            continue

        readings = [fact.value, as_displayed(fact.value, fact.unit)]

        if "bound of the" in statement:
            level = "95" if "95%" in statement else "80"
            side = "low" if statement.startswith("Lower") else "high"
            bounds.setdefault((metric, level), {})[side] = readings
        elif statement.startswith("Minutes-weighted average"):
            means[metric] = readings
        elif statement.startswith("Standard deviation"):
            sds[metric] = readings
        elif statement.startswith(("Projected", "Source-season")) and "standardised" not in (
            statement
        ):
            points.setdefault(metric, []).extend(readings)

    for (metric, level), pair in bounds.items():
        if "low" not in pair or "high" not in pair:
            continue
        for low, high in zip(pair["low"], pair["high"], strict=True):
            for _, factor in CONVERSIONS:
                values.append(((high - low) * factor, f"{metric} {level}% interval width"))

    for metric, readings in points.items():
        # Two point estimates per metric — the source season and the
        # projection — so this is one meaningful difference, not a combinatorial
        # sweep over every pair of facts in the bundle.
        for i, first in enumerate(readings):
            for second in readings[i + 1 :]:
                change = first - second
                for _, factor in CONVERSIONS:
                    values.append((change * factor, f"{metric} projected change"))
                    values.append((abs(change) * factor, f"{metric} projected change"))

    for metric, sd_readings in sds.items():
        mean_readings = means.get(metric)
        if mean_readings is None:
            continue
        for mean, sd in zip(mean_readings, sd_readings, strict=True):
            if sd <= 0:
                continue
            for value in points.get(metric, []):
                distance = (value - mean) / sd
                label = f"{metric} distance from the league mean"
                values.append((distance, label))
                values.append((abs(distance), label))

    return values


def as_displayed(value: float, unit: str) -> float:
    """The value as the bundle showed it, after the renderer's rounding.

    Mirrors :func:`hoopslab.llm.schemas._format`. Kept deliberately in step
    with it: if the rendering gains a decimal place and this does not, the
    checker starts failing correct arithmetic again.
    """
    if unit == "fraction":
        return round(value * 100, 1) / 100
    if unit == "sd":
        return round(value, 2)
    if unit == "count":
        return round(value)
    if unit == "years":
        return round(value, 1)
    return round(value, 3)


def _metric_of(statement: str) -> str | None:
    for metric in ("usage rate", "true shooting percentage"):
        if metric in statement:
            return metric
    return None


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

    leaked = sorted({term for term in bundle.redacted if _leaks(prose, term)})
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

    Within a compound, only the *capitalised* parts are candidates. A held-out
    batch failed on "the G League-anchored cohorts": "League" is in the
    evidence, "anchored" is an ordinary participle that is not, and requiring
    every part to be evidence-backed reported the whole compound as a recalled
    name. Capitalisation is the only signal this check has for proper-noun-hood
    and it has to be applied to compound parts for the same reason it is
    applied to whole tokens. Nothing real is let through: "Panathinaikos-bound"
    still has a capitalised part with no support, and redacted terms are caught
    by :func:`_leaks` regardless of case.
    """
    evidence = _fold(bundle.render())
    found: list[str] = []

    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        tokens = sentence.split()
        for index, raw in enumerate(tokens):
            # The dashes are deliberate: models emit en and em dashes as
            # punctuation around proper nouns, and leaving them attached
            # makes every such word look like an entity the bundle lacks.
            token = raw.strip(".,;:()\"'—–")  # noqa: RUF001
            if index == 0 or not token[:1].isupper() or len(token) < 3:
                continue
            candidates = [part for part in _split_compound(token) if part[:1].isupper()]
            if all(_permitted_word(part, evidence) for part in candidates):
                continue
            found.append(token)

    return sorted(set(found))


def _split_compound(token: str) -> list[str]:
    """Break a compound into the words it is made of.

    "NBA-to-EuroLeague" is two competitions and a preposition, none of which is
    an entity the model could have recalled. So is "NBA->EuroLeague", where the
    writer has borrowed the arrow the bundle uses for a direction. Judging
    either compound whole reports it as an invented name, which is both wrong
    and the kind of wrong that gets a check switched off.
    """
    # Ambiguous-dash lint suppressed on purpose: en and em dashes are
    # exactly what this has to split on, so "normalising" them away would
    # remove the behaviour.
    parts = [re.sub(r"[^\w']", "", part) for part in re.split(r"[-–—/>]+", token)]  # noqa: RUF001
    parts = [part for part in parts if part]
    return parts or [token]


#: Shortest prefix that may stand in for a word the evidence does contain.
#: Five characters is long enough that no club or surname in this data collides
#: with a competition name, and short enough to cover ordinary inflection.
MIN_STEM = 5


def _permitted_word(word: str, evidence: str) -> bool:
    """Is this word one the bundle supports, or an allowed generic?"""
    folded = _fold(word)
    # Possessives: the bundle says "the EuroLeague", a writer says
    # "the EuroLeague's average". The apostrophe is grammar, not a new entity.
    folded = re.sub(r"(?:'|’)s$", "", folded)  # noqa: RUF001 - curly apostrophes are the point
    if not folded or folded in ENTITY_ALLOWLIST or folded in evidence:
        return True

    # An inflected form of a word the evidence uses is not a new entity: the
    # bundle says "League", a writer says "G-Leaguer". Matching on a stem
    # handles the class rather than accumulating one allowlist entry per
    # suffix, and cannot admit a club or surname — "Panathinaikos" has no
    # five-character prefix anywhere in the evidence, and neither does any
    # redacted name, which the separate leak check tests for directly.
    return len(folded) > MIN_STEM and folded[:MIN_STEM] in evidence


def _fold(text: str) -> str:
    """Case-folded and de-accented, so "Doncic" matches "Dončić"."""
    return _strip_accents(text).casefold()


def _leaks(prose: str, term: str) -> bool:
    """Did the report name something it was supposed to have been denied?

    Two rules, both there because a plainer one produced false positives on
    real output:

    * **Whole words only.** Substring matching flags "really" as leaking "Real
      Madrid" and "sacrifice" as leaking a three-letter club code.
    * **Single words match case-sensitively.** Several club and surname tokens
      are ordinary English words — Real, Barcelona aside, think Baskonia versus
      nothing, but Real, Milan, Bourg — and a proper noun in prose is
      capitalised while the adjective is not. Multi-word phrases keep the
      case-insensitive match: "real madrid" in any casing is a leak, because
      the phrase has no innocent reading.

    Accents are folded on both sides either way, so "Doncic" still catches
    "Dončić".
    """
    needle = _strip_accents(term)
    haystack = _strip_accents(prose)
    flags = 0 if " " not in needle else re.IGNORECASE
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack, flags) is not None


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


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
        pattern = _RISE if falling else _FALL
        # Scoped to the claims that state the projection. The rule asks whether
        # the prose contradicts the sign of the projection, and only these two
        # sentences make that claim — a risk noting that an older player has
        # "less runway to grow into a larger role" agrees with a projected fall
        # while containing every word a lexical rule looks for.
        subject = f"{report.headline}\n{report.projection.text}"
        wrong_way = next(
            (m for m in pattern.finditer(subject) if not _ABOUT_SPREAD.search(m.group(0))), None
        )
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

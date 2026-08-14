"""The evaluation harness: which transitions to score, and how to read it.

The eval set is chosen by rule rather than by hand, so it cannot be quietly
curated toward reports that pass. The rule is the one the project cares about:
the biggest moves in each direction, measured by minutes played before the
switch, because those are the transitions a reader would look up.

The negative control is the part that makes the headline number mean something.
A groundedness score of 1.00 proves nothing on its own — a checker that accepts
everything scores 1.00 too. So every report is re-scored against a *different*
player's evidence, and the share of those that fail is reported beside it. If
swapping the evidence does not break the checks, the checks are not reading the
evidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import polars as pl

from hoopslab.llm.cache import ResponseCache
from hoopslab.llm.client import CacheMiss, GenerationFailure, GenerationRefused, ReportGenerator
from hoopslab.llm.evidence import BundleSource, build_bundle
from hoopslab.llm.groundedness import GroundednessResult, check_report
from hoopslab.llm.schemas import EvidenceBundle, ScoutingReport
from hoopslab.paths import DataPaths

log = logging.getLogger(__name__)

#: Directions the eval set draws from, in priority order. EuroLeague to NBA is
#: the flagship; its mirror is included because the two are selected in
#: opposite ways and a report that reads identically for both would be telling
#: on itself.
EVAL_DIRECTIONS = ("EL->NBA", "NBA->EL", "GL->NBA")

#: Per direction. Thirty reports in total is enough for a rate to be worth
#: quoting and small enough that refreshing the cache costs cents.
EVAL_PER_DIRECTION = 10


@dataclass
class ReportRecord:
    """One evaluated report and everything measured about it."""

    bundle: EvidenceBundle
    report: ScoutingReport
    groundedness: GroundednessResult
    distractor: GroundednessResult | None = None
    from_cache: bool = True

    @property
    def distractor_detected(self) -> bool | None:
        """Did the checks reject this report against someone else's evidence?"""
        return None if self.distractor is None else not self.distractor.grounded


@dataclass
class HarnessReport:
    """Aggregate over the eval set."""

    records: list[ReportRecord] = field(default_factory=list)
    failures: list[GenerationFailure] = field(default_factory=list)
    anonymized: bool = True
    model: str = ""
    ledger_summary: str = ""

    @property
    def n(self) -> int:
        return len(self.records)

    @property
    def grounded_rate(self) -> float | None:
        if not self.records:
            return None
        return sum(1 for r in self.records if r.groundedness.grounded) / len(self.records)

    @property
    def numeric_traceability(self) -> tuple[int, int]:
        traced = sum(r.groundedness.n_traced for r in self.records)
        total = sum(len(r.groundedness.tokens) for r in self.records)
        return traced, total

    @property
    def distractor_detection_rate(self) -> float | None:
        scored = [r for r in self.records if r.distractor_detected is not None]
        if not scored:
            return None
        return sum(1 for r in scored if r.distractor_detected) / len(scored)

    def check_rates(self) -> dict[str, tuple[int, int]]:
        """Passes and attempts per named check, so a failure is attributable."""
        rates: dict[str, tuple[int, int]] = {}
        for record in self.records:
            for check in record.groundedness.checks:
                passed, total = rates.get(check.name, (0, 0))
                rates[check.name] = (passed + int(check.passed), total + 1)
        return rates

    def render(self) -> str:
        mode = "anonymized" if self.anonymized else "named"
        lines = [
            f"Groundedness — {self.n} report(s), {mode}, model {self.model or 'unknown'}",
        ]
        if not self.records:
            lines.append("  no reports evaluated")
        else:
            rate = self.grounded_rate
            traced, total = self.numeric_traceability
            lines.append(
                f"  fully grounded        {rate:.2f}"
                f"  ({sum(1 for r in self.records if r.groundedness.grounded)}/{self.n})"
            )
            lines.append(
                f"  numbers traced        {traced}/{total}"
                + (f"  ({traced / total:.3f})" if total else "")
            )
            for name, (passed, attempts) in sorted(self.check_rates().items()):
                lines.append(f"    {name:<24} {passed}/{attempts}")

            detection = self.distractor_detection_rate
            if detection is not None:
                lines.append(
                    f"  distractor detection  {detection:.2f}"
                    "   (share of reports rejected when scored against another "
                    "player's evidence)"
                )
        if self.failures:
            lines.append(f"  generation failures   {len(self.failures)}")
            for failure in self.failures[:5]:
                lines.append(f"    {failure.person_id}: {failure.reason}")
        if self.ledger_summary:
            lines.append("")
            lines.extend(f"  {line}" for line in self.ledger_summary.splitlines())
        if not self.anonymized:
            lines.append(
                "\n  Named mode: the subject's name is in the evidence, so a report cannot "
                "\n  leak it and the anonymity check proves nothing here. The reportable "
                "\n  groundedness figure is the anonymized one."
            )
        return "\n".join(lines)


def select_eval_set(
    source: BundleSource, *, per_direction: int = EVAL_PER_DIRECTION
) -> list[tuple[str, str]]:
    """The transitions to evaluate, chosen by a rule and sorted deterministically."""
    scorable = set(source.transitions())

    frame = source.pairs.filter(
        pl.struct("person_id", "target_season_id").map_elements(
            lambda s: (s["person_id"], s["target_season_id"]) in scorable,
            return_dtype=pl.Boolean,
        )
    )

    selected: list[tuple[str, str]] = []
    for direction in EVAL_DIRECTIONS:
        rows = (
            frame.filter(pl.col("direction") == direction)
            .sort(["source_minutes", "person_id"], descending=[True, False])
            .head(per_direction)
        )
        selected.extend(
            (row["person_id"], row["target_season_id"]) for row in rows.iter_rows(named=True)
        )
    return selected


def run_harness(
    paths: DataPaths,
    *,
    anonymized: bool = True,
    per_direction: int = EVAL_PER_DIRECTION,
    allow_api: bool = False,
    max_calls: int = 0,
    model: str | None = None,
    with_distractor: bool = True,
) -> HarnessReport:
    """Score every report in the eval set against its own evidence, then against another's."""
    source = BundleSource.load(paths)
    generator = ReportGenerator(
        ResponseCache(paths.llm_cache),
        model=model,
        allow_api=allow_api,
        max_calls=max_calls,
    )

    selection = select_eval_set(source, per_direction=per_direction)
    report = HarnessReport(anonymized=anonymized, model=generator.model)

    bundles: dict[tuple[str, str], EvidenceBundle] = {}
    for person_id, target_season_id in selection:
        bundle = build_bundle(source, person_id, target_season_id, anonymized=anonymized)
        bundles[(person_id, target_season_id)] = bundle

        try:
            cached = generator.generate(bundle)
        except (CacheMiss, GenerationRefused) as exc:
            report.failures.append(
                GenerationFailure(
                    person_id=person_id, target_season_id=target_season_id, reason=str(exc)
                )
            )
            continue

        report.records.append(
            ReportRecord(
                bundle=bundle,
                report=cached.report,
                groundedness=check_report(cached.report, bundle),
            )
        )

    if with_distractor and len(report.records) > 1:
        _attach_distractors(report)

    report.ledger_summary = generator.ledger.render()
    return report


def _attach_distractors(report: HarnessReport) -> None:
    """Re-score each report against the next report's evidence.

    Rotating by one rather than sampling keeps the control deterministic, and
    pairs each report with a bundle from a different player — usually a
    different direction too, which is the harder case for the checker.
    """
    for index, record in enumerate(report.records):
        other = report.records[(index + 1) % len(report.records)].bundle
        record.distractor = check_report(record.report, other)

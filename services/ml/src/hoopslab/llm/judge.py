"""LLM-as-judge, and the number that says whether to believe it.

A judge is a measuring instrument, and an uncalibrated instrument is decoration.
So this module reports two things together and refuses to report the first
without the second:

* the judge's scores on a four-dimension rubric, and
* Cohen's κ between the judge and hand-labelled ground truth on the one
  dimension that has a right answer — did the report state a number the
  evidence does not support.

The expected finding is that the judge is *worse* than the regex in
:mod:`hoopslab.llm.groundedness` at catching fabricated numbers, because the
regex has the evidence and the judge has to read it. That is worth publishing.
An LLM judge earns its cost on the dimensions arithmetic cannot reach —
calibration language, whether a claim's cited facts actually support it — and
pretending it is also the fabrication detector is how eval harnesses end up
measuring their own optimism.

The judge is a different, stronger model than the writer. Self-judging is a
known-biased measurement and a weaker judge cannot see what a stronger writer
got wrong.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from hoopslab.llm.client import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_S,
    UsageLedger,
    resolve_model,
    usage_from,
)
from hoopslab.llm.schemas import EvidenceBundle, ScoutingReport

log = logging.getLogger(__name__)

Score = Literal[1, 2, 3, 4]

JUDGE_SYSTEM = """\
You grade short scouting briefs about basketball players who changed leagues.

Each brief was written from an evidence bundle and nothing else. You get the \
same bundle. Grade the brief against it, not against what you know about \
basketball or about any player you think you recognise.

Score four dimensions from 1 to 4, where 1 is unacceptable and 4 is what a \
careful analyst would have written.

**support** — does each claim follow from the facts it cites? A claim citing a \
fact that is merely nearby in the bundle, rather than one that supports it, is \
a 2 at best.

**numeric_accuracy** — is every number stated correctly, and used for what it \
actually measures? Quoting the lower bound of an interval as if it were the \
projection is a numeric error even though the digits appear in the bundle.

**calibration** — does the brief's confidence match the evidence? The bundle \
gives an interval width, a cohort size, and the model's own error against \
trivial baselines. A brief that reports a projection assertively while its \
evidence says the model loses to predicting the league average is badly \
calibrated no matter how well written it is. So is one that hedges everything \
into uselessness when the evidence is reasonably strong.

**usefulness** — could a reader act on this? Concrete, specific, and about the \
numbers that matter, versus fluent prose that could describe anyone.

Then answer one question with a plain yes or no: does the brief state any \
quantity that the bundle does not support? Judge only the numbers, and be \
strict — a figure that is close to a bundle value but not equal to it is \
unsupported.\
"""


class JudgeVerdict(BaseModel):
    """One graded brief."""

    support: Score
    numeric_accuracy: Score
    calibration: Score
    usefulness: Score
    states_unsupported_number: bool
    reasoning: str = Field(default="")

    @property
    def mean_score(self) -> float:
        return (self.support + self.numeric_accuracy + self.calibration + self.usefulness) / 4.0


@dataclass
class JudgeResult:
    key: str
    verdict: JudgeVerdict


@dataclass
class Agreement:
    """Judge against human labels, and the regex against the same labels."""

    n: int
    judge_kappa: float | None
    regex_kappa: float | None
    judge_accuracy: float | None
    regex_accuracy: float | None

    def render(self) -> str:
        if self.n == 0:
            return (
                "  judge agreement       unavailable — no hand-labelled reports committed.\n"
                "                        A judge score with no ground truth behind it is not "
                "a measurement."
            )
        lines = [f"  hand-labelled reports {self.n}"]
        for name, kappa, accuracy in (
            ("judge", self.judge_kappa, self.judge_accuracy),
            ("regex", self.regex_kappa, self.regex_accuracy),
        ):
            if kappa is None:
                lines.append(
                    f"    {name:<6} κ undefined — the labels are all one class, so chance "
                    "agreement is 1"
                )
            else:
                lines.append(f"    {name:<6} κ = {kappa:+.3f}   accuracy = {accuracy:.3f}")
        return "\n".join(lines)


def judge_report(
    report: ScoutingReport,
    bundle: EvidenceBundle,
    *,
    model: str | None = None,
    ledger: UsageLedger | None = None,
    client: object | None = None,
    max_tokens: int = 1024,
) -> JudgeVerdict:
    """Grade one brief. Makes a billed call; never runs by default."""
    model = resolve_model(model, "HOOPSLAB_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)

    if client is None:
        import anthropic

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is not set; the judge cannot run without it.")
        client = anthropic.Anthropic(
            api_key=key, timeout=DEFAULT_TIMEOUT_S, max_retries=DEFAULT_MAX_RETRIES
        )

    turn = (
        "Evidence bundle:\n\n"
        f"{bundle.render()}\n\n"
        "Brief under review:\n\n"
        f"{json.dumps(report.model_dump(), indent=2, ensure_ascii=False)}"
    )

    response = client.messages.parse(  # type: ignore[attr-defined]
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": turn}],
        output_format=JudgeVerdict,
    )
    if ledger is not None:
        ledger.add(usage_from(response, model, "judge"))

    parsed = getattr(response, "parsed_output", None)
    if isinstance(parsed, JudgeVerdict):
        return parsed
    try:
        return JudgeVerdict.model_validate(parsed)
    except ValidationError as exc:  # pragma: no cover - depends on a live call
        raise RuntimeError(f"judge returned an unusable verdict: {exc}") from exc


# ------------------------------------------------------------- human labels


@dataclass
class HumanLabel:
    """One hand-graded brief: the ground truth the judge is scored against."""

    key: str
    states_unsupported_number: bool
    notes: str = ""


def load_labels(directory: Path) -> list[HumanLabel]:
    if not directory.is_dir():
        return []
    labels: list[HumanLabel] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        labels.append(
            HumanLabel(
                key=payload["key"],
                states_unsupported_number=bool(payload["states_unsupported_number"]),
                notes=payload.get("notes", ""),
            )
        )
    return labels


def agreement(
    labels: list[HumanLabel],
    judge: dict[str, bool],
    regex: dict[str, bool],
) -> Agreement:
    """Cohen's κ for both detectors against the same hand labels.

    κ rather than raw accuracy because fabricated numbers are rare: a detector
    that always answers "no" scores well on accuracy and κ = 0, which is the
    honest reading of it.
    """
    paired = [label for label in labels if label.key in judge or label.key in regex]
    if not paired:
        return Agreement(
            n=0, judge_kappa=None, regex_kappa=None, judge_accuracy=None, regex_accuracy=None
        )

    truth = [label.states_unsupported_number for label in paired]

    def score(predictions: dict[str, bool]) -> tuple[float | None, float | None]:
        available = [
            (t, predictions[label.key])
            for t, label in zip(truth, paired, strict=True)
            if label.key in predictions
        ]
        if not available:
            return None, None
        actual = [a for a, _ in available]
        predicted = [p for _, p in available]
        accuracy = sum(a == p for a, p in available) / len(available)
        return _cohen_kappa(actual, predicted), accuracy

    judge_kappa, judge_accuracy = score(judge)
    regex_kappa, regex_accuracy = score(regex)
    return Agreement(
        n=len(paired),
        judge_kappa=judge_kappa,
        regex_kappa=regex_kappa,
        judge_accuracy=judge_accuracy,
        regex_accuracy=regex_accuracy,
    )


def _cohen_kappa(actual: list[bool], predicted: list[bool]) -> float | None:
    """κ for two binary raters. ``None`` when it is undefined.

    Undefined means both raters used a single class, so expected agreement is
    1 and the denominator vanishes. Reporting 0.0 there would read as "no
    better than chance" when the truth is "this sample cannot tell you".
    """
    from sklearn.metrics import cohen_kappa_score

    if len(set(actual)) == 1 and len(set(predicted)) == 1:
        return None
    value = float(cohen_kappa_score(actual, predicted))
    return None if value != value else value  # NaN guard


@dataclass
class JudgeRun:
    """Everything a judged evaluation produced."""

    verdicts: list[JudgeResult] = field(default_factory=list)
    agreement: Agreement | None = None
    ledger: UsageLedger = field(default_factory=UsageLedger)

    def render(self) -> str:
        if not self.verdicts:
            return "  no briefs judged"
        lines = ["  rubric means over " + f"{len(self.verdicts)} brief(s)"]
        for dimension in ("support", "numeric_accuracy", "calibration", "usefulness"):
            mean = sum(getattr(v.verdict, dimension) for v in self.verdicts) / len(self.verdicts)
            lines.append(f"    {dimension:<18} {mean:.2f} / 4")
        flagged = sum(1 for v in self.verdicts if v.verdict.states_unsupported_number)
        lines.append(f"    flagged as unsupported  {flagged}/{len(self.verdicts)}")
        if self.agreement is not None:
            lines.append(self.agreement.render())
        lines.append("")
        lines.extend(f"  {line}" for line in self.ledger.render().splitlines())
        return "\n".join(lines)

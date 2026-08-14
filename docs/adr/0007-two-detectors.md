# 7. Groundedness is measured by two detectors, and neither is reported alone

Accepted.

## Context

This layer was built predicting that a deterministic regex would beat an LLM
judge at catching bad numbers, because the regex has the evidence and the judge
has to read it.

Measured against 30 labelled reports:

| Detector                        | κ          | Accuracy |
| ------------------------------- | ---------- | -------- |
| LLM judge (Opus grading Sonnet) | **+0.783** | 0.967    |
| Deterministic checker           | +0.000     | 0.900    |

The prediction was wrong.

## Decision

Both are run, and both are reported with Cohen's κ against labelled ground
truth beside them.

## Consequences

- **The two answer different questions.** The checker asks _is this number in
  the evidence?_ Across 1,027 numeric tokens the answer was yes every time, so
  it has no positives and κ = 0 is a definition rather than a failure. The judge
  asks _is this number used for what it measures?_, which the checker cannot
  express.
- Every error found was of the second kind: a standing of −0.97 sd described as
  "well above average"; a 15.5% projection called "below 15.0%"; a player's own
  64.7% attached to "the NBA average". The judge caught two of three and missed
  the most debatable.
- **Arithmetic settles provenance and cannot settle meaning.** A harness
  reporting only the traceability figure reads 100% while the prose contains a
  reversed sign. That is the reason both exist.
- κ rather than accuracy, because fabrication is rare: a detector that answers
  "no" to everything reaches 90% accuracy and detects nothing.
- **The labels are not human.** They were produced by a model reading each
  report against its bundle, and the judge is the same model family, so the
  agreement runs higher than it would against an independent reader. Recorded as
  an upper bound; the three flagged reports are the durable part.

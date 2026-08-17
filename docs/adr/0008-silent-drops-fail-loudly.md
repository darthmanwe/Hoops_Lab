# 8. Rows dropped by a filter must be counted, not discovered

Proposed.

## Context

`leaguedashplayerstats` returns no AGE column for the G League. Age is a
covariate in the translation model, and the transition frame drops rows without
one.

The result: **every transition originating in the G League was silently
discarded** — 90 pairs, 22% of the observed total, including the entire GL→NBA
direction the G League had been ingested to provide. Nothing raised, nothing
warned, and the remaining count looked plausible. It survived five phases and
was found by asking why an evaluation set had 20 members instead of 30.

This is precisely the failure this project was rebuilt to eliminate, wearing
different clothes. The original sin was fabricated numbers; this is the opposite
and just as bad — real numbers quietly absent, with a smaller cohort presented
as the whole one.

## Decision

A filter that removes rows on a null covariate must either:

1. recover the value where recovering it is _arithmetic_ rather than imputation
   — G League age is now derived from the same person's seasons in leagues that
   do report it — or
2. report the count it dropped, per reason, in the run log.

A person with no age anywhere still has none, because a fabricated covariate in
the flagship model is worse than a smaller cohort. That residual was 2,129
G League seasons until the source was checked properly:
`leaguedashplayerbiostats` takes `league_id` and reports G League ages
directly, so derivation is now the fallback and 6 seasons remain unaged.

Which sharpens this decision rather than softening it. Recovery worked, and
because it worked nobody asked whether the data had been there all along — the
comment asserting it was not went unexamined for five phases. **A repaired
number is still a number that was missing, and the repair is not the place to
stop looking.**

## Consequences

- 324 → 414 fitted pairs. Usage skill against the best baseline moved 24.0% →
  22.4%: _down_, because the recovered directions are harder. That is the honest
  direction for a number to move when a cohort stops being quietly filtered to
  its easy cases.
- Three regression tests cover the recovery, the no-overwrite guarantee, and the
  case where nothing can be recovered.
- The general rule is not yet enforced mechanically, which is why this ADR is
  **proposed** rather than accepted. A `dropped_rows` block in the run log,
  populated by every filter in the transition pipeline, is the obvious next
  step.

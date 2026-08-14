# Hand labels

The ground truth the LLM judge is scored against. Without these, a judge score
is a number with nothing behind it.

Each file is one hand-graded report:

```json
{
  "key": "<the response-cache key of the report>",
  "states_unsupported_number": true,
  "notes": "quoted 24.1% for usage; the bundle has 21.4% and 26.0%, neither is 24.1%"
}
```

`states_unsupported_number` is the one dimension of the rubric with a right
answer, which is why it is the one that gets labelled. Reading a report against
its bundle and deciding whether every quantity is supported takes a couple of
minutes and is not a judgement call; scoring "usefulness" by hand would be.

## Why Cohen's κ and not accuracy

Fabricated numbers are rare. A detector that answers "no" to everything reaches
high accuracy and detects nothing — κ says so, accuracy does not. Both the
judge and the deterministic regex checker are scored against the same labels,
so the comparison is like for like.

The expected result is that **the regex beats the judge**, because the regex
has the evidence and the judge has to read it. That is worth publishing rather
than hiding: an LLM judge earns its cost on the dimensions arithmetic cannot
reach — calibration language, whether a claim's cited facts actually support it
— and pretending it is also the fabrication detector is how eval harnesses end
up measuring their own optimism.

## Labelling

20 reports is the target: enough for κ to mean something, few enough to grade
carefully in one sitting. Pick them from the eval set after populating the
response cache, read each against `evidence` in the corresponding cache entry,
and record the verdict with a note saying which number failed and why.

"""Anthropic client, cost metering, and the spend gate.

Three properties this module exists to guarantee:

* **Nothing is billed unless it was asked for.** Generation reads the committed
  cache by default and raises on a miss. Spending requires ``allow_api=True``,
  which only ``--refresh-cache`` sets, and even then ``max_calls`` is a hard
  ceiling checked before each request rather than a budget reconciled after.

* **Cost is measured, not estimated.** Token counts come off the response's
  ``usage`` block. A repository that claims prompt caching saves money without
  ever reading ``cache_read_input_tokens`` is claiming an effect it did not
  instrument, and the number is often disappointing — the cacheable prefix has
  to clear the model's minimum before anything caches at all.

* **A bad response degrades rather than aborts.** A refusal or a truncation
  ends one report, not a thirty-report evaluation run. It is recorded as a
  failure with its reason, which is more useful than a traceback anyway.

Model ids resolve at call time — explicit argument, then environment, then
default. Reading them at import time is how a documented override silently
never works.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from hoopslab.llm.cache import CachedResponse, ResponseCache, cache_key, now_iso
from hoopslab.llm.prompt import SYSTEM, system_blocks, user_turn
from hoopslab.llm.schemas import EvidenceBundle, ScoutingReport

log = logging.getLogger(__name__)

#: Reports are written by Sonnet and judged by Opus. The asymmetry is
#: deliberate: a model grading its own output is a known-biased measurement,
#: and a judge weaker than the writer cannot catch what the writer got wrong.
#: Groundedness is a reading-comprehension task, not a frontier-capability one,
#: so the writer does not need to be the strongest model available.
DEFAULT_REPORT_MODEL = "claude-sonnet-5"
DEFAULT_JUDGE_MODEL = "claude-opus-5"

#: Room for a full report plus slack. Measured rather than guessed: a typical
#: report is ~1,700 output tokens, but at 2,048 and at 4,096 real responses were
#: truncated mid-JSON and rejected by the schema. The ceiling has to clear the
#: longest output the schema permits — four strengths and four risks, each with
#: its own text and citations — not the median one.
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_RETRIES = 4

#: USD per million tokens, input and output, at published list rates. Kept
#: beside the code that uses it so a pricing change is a one-line diff with a
#: visible blame line.
#:
#: Promotional rates are deliberately not modelled. Sonnet 5 carries an
#: introductory discount, so the figures this produces are an upper bound on
#: what was actually billed — the safe direction for a number quoted in a
#: README, and the wrong direction to guess in.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class UsageRecord(BaseModel):
    """Token usage and derived cost for a single call."""

    model: str
    kind: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def priced(self) -> bool:
        """False when this model has no published rate recorded here.

        Checked before any total is reported. An unpriced model would otherwise
        make every cost figure read $0.00, which is far worse than reading
        "unknown" — and the environment override is exactly how a caller
        reaches a model this table has never seen.
        """
        return self.model in PRICING_USD_PER_MTOK

    @property
    def cost_usd(self) -> float:
        """USD for this call. Cache reads bill at a tenth of the input rate."""
        rate_in, rate_out = PRICING_USD_PER_MTOK.get(self.model, (0.0, 0.0))
        billed_in = (
            self.input_tokens
            + 1.25 * self.cache_creation_input_tokens
            + 0.10 * self.cache_read_input_tokens
        )
        return (billed_in * rate_in + self.output_tokens * rate_out) / 1_000_000

    @property
    def prompt_tokens(self) -> int:
        """Total prompt size, which ``input_tokens`` alone understates."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


@dataclass
class UsageLedger:
    """Every call made in one run, and what it cost."""

    records: list[UsageRecord] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0

    def add(self, record: UsageRecord) -> None:
        self.records.append(record)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def unpriced_calls(self) -> int:
        return sum(1 for r in self.records if not r.priced)

    @property
    def prompt_cache_hit_rate(self) -> float | None:
        """Share of prompt tokens served from the API's prompt cache.

        ``None`` when no call was made, which is the normal case: the committed
        response cache means a full evaluation run issues zero requests, and
        reporting 0% there would confuse "we did not call" with "caching did
        not work".
        """
        total = sum(r.prompt_tokens for r in self.records)
        if total == 0:
            return None
        return sum(r.cache_read_input_tokens for r in self.records) / total

    def render(self) -> str:
        lines = [
            f"response cache: {self.cache_hits} hit(s), {self.cache_misses} miss(es)",
            f"api calls:      {len(self.records)}",
        ]
        if self.records:
            hit_rate = self.prompt_cache_hit_rate
            lines.append(
                "prompt cache:   "
                + (f"{hit_rate:.1%} of prompt tokens read from cache" if hit_rate else "0%")
            )
            if self.unpriced_calls:
                lines.append(
                    f"cost:           unknown ({self.unpriced_calls} call(s) on an unpriced model)"
                )
            else:
                lines.append(f"cost:           ${self.total_cost_usd:.4f}")
        else:
            lines.append("cost:           $0.0000 (no request was made)")
        return "\n".join(lines)


class BudgetExceeded(RuntimeError):
    """Raised before a request that would exceed the caller's call ceiling."""


class CacheMiss(RuntimeError):
    """Raised when a response is absent and spending was not authorised."""


@dataclass
class GenerationFailure:
    """A call that produced no usable report, and why."""

    person_id: str
    target_season_id: str
    reason: str


def resolve_model(explicit: str | None, env_var: str, default: str) -> str:
    """Resolve a model id at call time: explicit, then environment, then default."""
    return explicit or os.environ.get(env_var) or default


def resolve_api_key() -> str | None:
    """The key, from the environment or the repository's ``.env``.

    Read at call time and through the same settings object the ``config``
    command prints, so "the CLI says my key is set" and "the CLI can use my
    key" cannot disagree. The test session neutralises both sources — see
    ``tests/conftest.py`` — so this path is unreachable under a bare pytest.
    """
    from hoopslab.config import load_settings

    return os.environ.get("ANTHROPIC_API_KEY") or load_settings().anthropic_api_key


def usage_from(response: object, model: str, kind: str) -> UsageRecord:
    usage = getattr(response, "usage", None)

    def read(name: str) -> int:
        return int(getattr(usage, name, 0) or 0)

    return UsageRecord(
        model=model,
        kind=kind,
        input_tokens=read("input_tokens"),
        output_tokens=read("output_tokens"),
        cache_creation_input_tokens=read("cache_creation_input_tokens"),
        cache_read_input_tokens=read("cache_read_input_tokens"),
    )


class ReportGenerator:
    """Turns evidence bundles into reports, from cache or from the API."""

    def __init__(
        self,
        cache: ResponseCache,
        *,
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        allow_api: bool = False,
        max_calls: int = 0,
        client: object | None = None,
    ) -> None:
        self.cache = cache
        self.model = resolve_model(model, "HOOPSLAB_REPORT_MODEL", DEFAULT_REPORT_MODEL)
        self.max_tokens = max_tokens
        self.allow_api = allow_api
        self.max_calls = max_calls
        self.ledger = UsageLedger()
        self._client = client
        self._calls = 0

    def key_for(self, bundle: EvidenceBundle) -> str:
        return cache_key(
            model=self.model,
            system=SYSTEM,
            evidence=bundle.render(),
            schema=ScoutingReport.__name__,
            max_tokens=self.max_tokens,
        )

    def generate(self, bundle: EvidenceBundle) -> CachedResponse:
        """Return the report for this bundle, calling the API only if allowed."""
        key = self.key_for(bundle)

        cached = self.cache.get(key)
        if cached is not None:
            self.ledger.cache_hits += 1
            return cached

        self.ledger.cache_misses += 1
        if not self.allow_api:
            raise CacheMiss(
                f"No cached response for {bundle.person_id} ({key}). "
                "Re-run with --refresh-cache and a key set to generate it; the committed "
                "cache is what keeps the demo and the evaluation free."
            )
        if self._calls >= self.max_calls:
            raise BudgetExceeded(
                f"Call ceiling of {self.max_calls} reached. Raise --max-calls deliberately."
            )

        response = self._call(bundle)
        self.cache.put(response)
        return response

    def _call(self, bundle: EvidenceBundle) -> CachedResponse:
        client = self._ensure_client()
        self._calls += 1

        try:
            response = client.messages.parse(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_blocks(),
                messages=[{"role": "user", "content": user_turn(bundle)}],
                output_format=ScoutingReport,
            )
        except ValidationError as exc:
            # `messages.parse` validates before returning, so a truncated
            # response raises here and the `stop_reason` branch below never
            # runs. Without this, one over-long report aborts a thirty-report
            # run with a traceback about JSON — which reads as a bug in the
            # schema rather than as "raise max_tokens".
            raise GenerationRefused(
                f"response was not parseable, most likely truncated at "
                f"max_tokens={self.max_tokens}: {_first_line(exc)}"
            ) from exc

        record = usage_from(response, self.model, "report")
        self.ledger.add(record)

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise GenerationRefused("the model declined the request")
        if stop_reason == "max_tokens":
            raise GenerationRefused(f"response truncated at max_tokens={self.max_tokens}")

        parsed = getattr(response, "parsed_output", None)
        if not isinstance(parsed, ScoutingReport):
            try:
                parsed = ScoutingReport.model_validate(parsed)
            except ValidationError as exc:
                # The commonest cause is a claim with an empty fact_ids list —
                # the schema refusing an uncitable claim, working as intended.
                raise GenerationRefused(f"schema validation failed: {exc}") from exc

        return CachedResponse(
            key=self.key_for(bundle),
            model=self.model,
            created_at=now_iso(),
            person_id=bundle.person_id,
            target_season_id=bundle.target_season_id,
            anonymized=bundle.anonymized,
            evidence_digest=bundle.digest(),
            report=parsed,
            usage=record.model_dump(exclude={"model", "kind"}),
        )

    def _ensure_client(self) -> object:
        if self._client is not None:
            return self._client

        import anthropic

        key = resolve_api_key()
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set, in the environment or in the repository's "
                ".env. Everything except cache refresh runs without it."
            )
        self._client = anthropic.Anthropic(
            api_key=key, timeout=DEFAULT_TIMEOUT_S, max_retries=DEFAULT_MAX_RETRIES
        )
        return self._client


class GenerationRefused(RuntimeError):
    """The API answered, but with nothing usable."""


def _first_line(exc: Exception) -> str:
    """One line of a Pydantic error, which is otherwise a paragraph per field."""
    return str(exc).splitlines()[0].strip()

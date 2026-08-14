"""The spend gate, the cache, and the cost arithmetic.

The property this file exists to hold: a bare ``pytest`` cannot make a billed
call. That is enforced three ways — the ``llm`` marker is deselected by
default, ``conftest`` strips credentials from both the environment and ``.env``,
and generation refuses to reach the network unless a caller passed
``allow_api=True``. Any one of them failing should still leave the other two.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hoopslab.llm.cache import CachedResponse, ResponseCache, cache_key, now_iso
from hoopslab.llm.client import (
    BudgetExceeded,
    CacheMiss,
    ReportGenerator,
    UsageLedger,
    UsageRecord,
    resolve_model,
)
from hoopslab.llm.schemas import Claim, EvidenceBundle, Fact, ScoutingReport


def make_bundle(person_id: str = "p1") -> EvidenceBundle:
    return EvidenceBundle(
        person_id=person_id,
        subject="Player A",
        direction="EL->NBA",
        source_season_id="EL_2017",
        target_season_id="NBA_2018",
        source_season_label="2017-18 EuroLeague",
        target_season_label="2018-19 NBA",
        anonymized=True,
        facts=[
            Fact(
                id="f01",
                statement="Source-season usage rate",
                value=0.284,
                unit="fraction",
                source="gold",
            )
        ],
    )


def make_report() -> ScoutingReport:
    claim = Claim(text="Usage was 28.4%.", fact_ids=["f01"])
    return ScoutingReport(
        headline="h",
        projection=claim,
        uncertainty=claim,
        strengths=[claim],
        risks=[claim],
        confidence="low",
    )


class FakeResponse:
    """Shaped like an SDK response, including the usage block."""

    def __init__(self, parsed: ScoutingReport | None, stop_reason: str = "end_turn") -> None:
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.usage = type(
            "Usage",
            (),
            {
                "input_tokens": 120,
                "output_tokens": 300,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 1800,
            },
        )()


class FakeMessages:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.messages = FakeMessages(response)


# ------------------------------------------------------------------- the gate


def test_a_cache_miss_without_permission_is_an_error_not_a_charge(tmp_path: Path) -> None:
    generator = ReportGenerator(ResponseCache(tmp_path))
    with pytest.raises(CacheMiss, match="refresh-cache"):
        generator.generate(make_bundle())
    assert generator.ledger.records == []


def test_the_call_ceiling_is_checked_before_the_request(tmp_path: Path) -> None:
    client = FakeClient(FakeResponse(make_report()))
    generator = ReportGenerator(ResponseCache(tmp_path), allow_api=True, max_calls=0, client=client)
    with pytest.raises(BudgetExceeded):
        generator.generate(make_bundle())
    assert client.messages.calls == []


def test_a_generated_response_is_cached_and_replayed(tmp_path: Path) -> None:
    client = FakeClient(FakeResponse(make_report()))
    generator = ReportGenerator(ResponseCache(tmp_path), allow_api=True, max_calls=1, client=client)
    bundle = make_bundle()

    first = generator.generate(bundle)
    assert len(client.messages.calls) == 1
    assert first.evidence_digest == bundle.digest()

    replay = ReportGenerator(ResponseCache(tmp_path))  # no API permitted at all
    second = replay.generate(bundle)
    assert second.report == first.report
    assert replay.ledger.cache_hits == 1


def test_a_refusal_does_not_abort_the_run(tmp_path: Path) -> None:
    from hoopslab.llm.client import GenerationRefused

    client = FakeClient(FakeResponse(None, stop_reason="refusal"))
    generator = ReportGenerator(ResponseCache(tmp_path), allow_api=True, max_calls=1, client=client)
    with pytest.raises(GenerationRefused, match="declined"):
        generator.generate(make_bundle())
    # Usage is still recorded: a refusal that consumed tokens still costs money.
    assert len(generator.ledger.records) == 1


def test_the_system_prompt_carries_a_cache_breakpoint(tmp_path: Path) -> None:
    client = FakeClient(FakeResponse(make_report()))
    generator = ReportGenerator(ResponseCache(tmp_path), allow_api=True, max_calls=1, client=client)
    generator.generate(make_bundle())

    system = client.messages.calls[0]["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}


# ------------------------------------------------------------------ the cache


def test_the_key_changes_with_anything_that_changed_the_answer() -> None:
    base: dict[str, object] = {
        "model": "claude-sonnet-5",
        "system": "S",
        "evidence": "E",
        "schema": "R",
        "max_tokens": 2048,
    }
    baseline = cache_key(**base)  # type: ignore[arg-type]
    for field, value in (
        ("model", "claude-opus-5"),
        ("system", "S2"),
        ("evidence", "E2"),
        ("max_tokens", 4096),
    ):
        assert cache_key(**{**base, field: value}) != baseline  # type: ignore[arg-type]


def test_cache_entries_round_trip(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    entry = CachedResponse(
        key="abc123",
        model="claude-sonnet-5",
        created_at=now_iso(),
        person_id="p1",
        target_season_id="NBA_2018",
        anonymized=True,
        evidence_digest="deadbeef",
        report=make_report(),
        usage={"input_tokens": 1},
    )
    cache.put(entry)
    assert cache.get("abc123") == entry
    assert len(cache) == 1


# ------------------------------------------------------------------ the ledger


def test_cost_prices_cache_reads_at_a_tenth() -> None:
    record = UsageRecord(
        model="claude-sonnet-5",
        kind="report",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_read_input_tokens=1_000_000,
    )
    assert record.priced
    assert record.cost_usd == pytest.approx(3.00 + 0.30)


def test_an_unpriced_model_is_reported_as_unknown_not_as_free() -> None:
    ledger = UsageLedger()
    ledger.add(UsageRecord(model="some-future-model", kind="report", input_tokens=1000))
    assert ledger.unpriced_calls == 1
    assert "unknown" in ledger.render()


def test_no_call_is_distinguished_from_a_zero_hit_rate() -> None:
    """Reporting 0% when nothing was sent would read as caching having failed."""
    ledger = UsageLedger()
    assert ledger.prompt_cache_hit_rate is None
    assert "no request was made" in ledger.render()


def test_prompt_cache_hit_rate_uses_the_whole_prompt() -> None:
    ledger = UsageLedger()
    ledger.add(
        UsageRecord(
            model="claude-sonnet-5",
            kind="report",
            input_tokens=200,
            cache_read_input_tokens=1800,
        )
    )
    assert ledger.prompt_cache_hit_rate == pytest.approx(0.9)


def test_model_ids_resolve_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOPSLAB_REPORT_MODEL", "claude-haiku-4-5")
    assert resolve_model(None, "HOOPSLAB_REPORT_MODEL", "claude-sonnet-5") == "claude-haiku-4-5"
    assert resolve_model("explicit", "HOOPSLAB_REPORT_MODEL", "claude-sonnet-5") == "explicit"

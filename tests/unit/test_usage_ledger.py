"""The ledger's derivation and projections over hand-built states (F25, the cost and usage ledger design v0.2 R4 to
R7; slice 1 of §7): the price table, the bucket mapping by declared semantics, every unpriced reason, the pricing
snapshot, the copy, and the roll-ups with their counts and scope."""

from __future__ import annotations

import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from aew.engine import usage_ops as O
from aew.errors import IntegrityError, ValidationFailed
from aew.harness import contract as K
from aew.harness import runlog
from aew.harness import usage as U
from aew.schemas import validate

TABLE = (b"schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\n"
         b"source: \"the provider's published list prices on the date above\"\nprices:\n"
         b"  openai/gpt-6.1: {input: 2.0, output: 8.0, cache_read: 0.5, cache_write: 2.0}\n"
         b"  openai/gpt-6.1-mini: {input: 0.4, output: 1.6, cache_read: 0.1, cache_write: 0.4, reasoning: 1.6}\n")
PRICES = O.Prices(TABLE, source="pricing.yaml")
GPT = {"provider": "openai", "model": "gpt-6.1", "effort": "high"}
MINI = {"provider": "openai", "model": "gpt-6.1-mini", "effort": None}


def record(*, input: int = 0, output: int = 0, reasoning: int = 0, cache_read: int = 0, cache_write: int = 0,
           semantics: str = U.DISJOINT, effective: list[dict[str, Any]] | None = None, cost: Any = None,
           **extra: Any) -> dict[str, Any]:
    raw = {"input": input, "output": output, "reasoning": reasoning, "cache": {"read": cache_read,
                                                                             "write": cache_write}}
    return U.normalize({"tokens": raw, "cost": cost}, [{}], [GPT] if effective is None else effective, semantics,
                       source="harness:opencode", **extra)


def usd(figure: dict[str, Any]) -> Decimal:
    assert "usd" in figure, figure
    return figure["usd"]


# ---------------------------------------------------------------------------------------------- the price table


def test_a_price_row_carrying_token_semantics_is_refused():
    """R4 rule 1: the table carries no semantics; a hand-edited row cannot know what a harness upgrade changed."""
    bad = TABLE + b"  openai/gpt-7: {input: 1.0, output: 2.0, token_semantics: disjoint}\n"
    with pytest.raises(ValidationFailed):
        O.Prices(bad, source="pricing.yaml")


@pytest.mark.parametrize("line", [b"  openai/x: {input: -1}\n", b"  openai/x: {}\n", b"  no-slash: {input: 1}\n",
                                  b"  openai/x: {unknown: 1}\n"])
def test_a_malformed_price_row_is_refused(line):
    with pytest.raises(ValidationFailed):
        O.Prices(TABLE + line, source="pricing.yaml")


def test_no_price_table_means_unpriced_never_zero(tmp_path):
    assert O.read_price_table(tmp_path / "pricing.yaml") is None
    assert O.derive(record(input=10), None)[0] == {"unpriced": "unpriced_no_price_table"}
    (tmp_path / "pricing.yaml").write_bytes(b"schema: aew/pricing/v1\n")
    with pytest.raises(ValidationFailed):
        O.read_price_table(tmp_path / "pricing.yaml")


# ---------------------------------------------------------------------------------------------- semantics and buckets


R = {"input": 1000, "output": 400, "reasoning": 100, "cache_read": 600, "cache_write": 50}


@pytest.mark.parametrize("semantics, expected", [
    # disjoint: every counter is its own bucket; the row prices no reasoning, so a run with reasoning is unpriced
    (U.DISJOINT, "unpriced_category:reasoning"),
    # cached inside input: input bills 1000-600; reasoning still its own bucket
    (U.INPUT_INCLUDES_CACHE_READ, "unpriced_category:reasoning"),
    # reasoning inside output: billed as output. 1000*2 + 400*8 + 600*0.5 + 50*2 = 5600 per Mtok
    (U.OUTPUT_INCLUDES_REASONING, Decimal("0.0056")),
    # both: (1000-600)*2 + 400*8 + 600*0.5 + 50*2 = 4400 per Mtok
    (U.INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING, Decimal("0.0044")),
    (U.UNKNOWN, "unpriced_token_semantics_unknown"),
])
def test_each_semantics_prices_the_hand_computed_figure(semantics, expected):
    figure, _ = O.derive(record(**R, semantics=semantics), PRICES)
    assert figure == ({"unpriced": expected} if isinstance(expected, str) else {"usd": expected})


@pytest.mark.parametrize("semantics, expected", [
    # the mini row prices reasoning: disjoint is 1000*.4 + 400*1.6 + 100*1.6 + 600*.1 + 50*.4 = 1280 per Mtok
    (U.DISJOINT, Decimal("0.00128")),
    # cached inside input: 400*.4 + 400*1.6 + 100*1.6 + 600*.1 + 50*.4 = 1040
    (U.INPUT_INCLUDES_CACHE_READ, Decimal("0.00104")),
])
def test_overlapping_counters_are_never_billed_twice(semantics, expected):
    assert usd(O.derive(record(**R, semantics=semantics, effective=[MINI]), PRICES)[0]) == expected


def test_unknown_token_semantics_are_never_priced():
    """The fail-closed rule for any harness and provider whose semantics are not qualified."""
    for rec in (record(input=10, semantics=U.UNKNOWN), {**record(input=10), "token_semantics": "made_up"}):
        assert O.derive(rec, PRICES)[0] == {"unpriced": "unpriced_token_semantics_unknown"}
    assert O.billable_buckets(R, U.UNKNOWN) == "unpriced_token_semantics_unknown"


@pytest.mark.parametrize("semantics, counters", [
    (U.INPUT_INCLUDES_CACHE_READ, {"input": 10, "cache_read": 11}),
    (U.OUTPUT_INCLUDES_REASONING, {"output": 10, "reasoning": 11}),
    (U.INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING, {"input": 10, "cache_read": 11}),
])
def test_a_bucket_that_would_go_negative_prices_nothing(semantics, counters):
    assert O.derive(record(**counters, semantics=semantics), PRICES)[0] == {
        "unpriced": "unpriced_inconsistent_counters"}


def test_a_bucket_with_tokens_and_no_price_is_unpriced_and_a_zero_one_is_fine():
    assert O.derive(record(input=10, reasoning=1), PRICES)[0] == {"unpriced": "unpriced_category:reasoning"}
    assert usd(O.derive(record(input=10, reasoning=0), PRICES)[0]) == Decimal("0.00002")
    unknown = {**record(input=10), "tokens": {**record(input=10)["tokens"], "unknown": 3}}
    assert O.derive(unknown, PRICES)[0] == {"unpriced": "unpriced_category:unknown"}


def test_absent_or_partial_counters_are_unpriced():
    assert O.derive(U.absent_record(source="harness:x"), PRICES)[0] == {"unpriced": "unpriced_tokens_absent"}
    partial = U.normalize({"tokens": {"input": 5, "output": 5}}, [{}], [GPT], U.DISJOINT, source="harness:x")
    assert O.derive(partial, PRICES)[0] == {"unpriced": "unpriced_tokens_partial"}


# ---------------------------------------------------------------------------------------------- model attribution


def test_a_match_and_a_mismatch_with_one_effective_model_price_the_effective_model():
    rec = record(input=1000)
    assert usd(O.derive({**rec, "model_check": "match"}, PRICES)[0]) == Decimal("0.002")
    # Requested gpt-6.1, ran mini: priced on mini, never on the requested model.
    mismatch = {**record(input=1000, effective=[MINI]), "model_check": "mismatch",
                "requested": {**GPT, "profile": "implementer"}}
    assert usd(O.derive(mismatch, PRICES)[0]) == Decimal("0.0004")


def test_an_unpartitioned_mix_is_unpriced_never_the_requested_model():
    rec = {**record(input=1000, effective=[GPT, MINI]), "requested": {**GPT, "profile": "implementer"}}
    assert O.derive(rec, PRICES)[0] == {"unpriced": "unpriced_effective_model_mix"}
    capped = {**record(input=1000), "effective_truncated": 1}
    assert O.derive(capped, PRICES)[0] == {"unpriced": "unpriced_effective_model_mix"}


def test_a_partitioned_mix_is_priced_per_partition_and_summed():
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    rec = record(input=2000, effective=[GPT, MINI], tokens_by_model=[
        {**GPT, "tokens": {**tok, "input": 1000}}, {**MINI, "tokens": {**tok, "input": 1000}}])
    figure, parts = O.derive(rec, PRICES)
    assert figure == {"usd": Decimal("0.0024")}
    assert dict(parts) == {"openai/gpt-6.1": Decimal("0.002"), "openai/gpt-6.1-mini": Decimal("0.0004")}


def test_a_truncated_enumeration_is_never_priced_on_the_models_it_saw():
    """#133 review, finding 1: when the harness's message paging stopped short, the models it saw are not all the
    models that ran. Pricing the complete session totals on model A would bill omitted model B at A's rate."""
    rec = record(input=1000, output=400, truncated=True)
    assert rec["truncated"] and rec["effective"] == [GPT]
    assert O.derive(rec, PRICES)[0] == {"unpriced": O.UNPRICED_INCOMPLETE}
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    partitioned = record(input=1000, truncated=True, tokens_by_model=[{**GPT, "tokens": {**tok, "input": 1000}}])
    assert O.derive(partitioned, PRICES)[0] == {"unpriced": O.UNPRICED_INCOMPLETE}


def test_a_partial_partition_is_no_partition_and_partitions_must_add_up_to_the_totals():
    """#133 review, finding 2: a partition reporting only some categories, or partitions that do not reconcile with
    the session totals, never price part of the run's tokens."""
    partial = record(input=1000, output=400, effective=[GPT, MINI],
                     tokens_by_model=[{**GPT, "tokens": {"input": 600}}, {**MINI, "tokens": {"input": 400}}])
    assert partial.get("tokens_by_model") is None  # zeros the harness never reported are not counts
    assert O.derive(partial, PRICES)[0] == {"unpriced": O.UNPRICED_MIX}
    single = record(input=1000, output=400, tokens_by_model=[{**GPT, "tokens": {"input": 1000}}])
    assert usd(O.derive(single, PRICES)[0]) == Decimal("0.0052")  # the complete totals on the one model: 2 + 3.2
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    short = record(input=1000, output=400, effective=[GPT, MINI], tokens_by_model=[
        {**GPT, "tokens": {**tok, "input": 600}}, {**MINI, "tokens": {**tok, "input": 400}}])
    assert O.derive(short, PRICES)[0] == {"unpriced": O.UNPRICED_PARTITION_MISMATCH}  # the 400 output went nowhere


def test_a_model_reported_twice_is_priced_and_counted_once(tmp_path):
    """#133 review (fd571ff), finding 1: two partitions naming one model are that model's two shares of the run.
    400 + 600 input tokens at $2/M is $0.002 and one run, whether the record came through normalize() or not."""
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    rec = record(input=1000, tokens_by_model=[{**GPT, "tokens": {**tok, "input": 400}},
                                              {**GPT, "tokens": {**tok, "input": 600}}])
    assert [p["tokens"]["input"] for p in rec["tokens_by_model"]] == [1000]
    flat = {c: 0 for c in U.CATEGORIES}
    by_hand = {**rec, "tokens_by_model": [{"provider": "openai", "model": "gpt-6.1", "tokens": {**flat, "input": n}}
                                          for n in (400, 600)]}  # schema-valid: the schema cannot forbid the repeat
    validate("run-usage", by_hand, source="test")
    for usage in (rec, by_hand):
        figure, parts = O.derive(usage, PRICES)
        assert figure == {"usd": Decimal("0.002")} and parts == [("openai/gpt-6.1", Decimal("0.002"))]
    run_record(runlog.run_dir(tmp_path, "R-1"), by_hand)
    state = hand_state(("I-1", "T-0001", ["R-1"]))
    O.copy_run_usage(state, "I-1", tmp_path, pricing=PRICES)
    totals = O.Reader(tmp_path, PRICES).invocation("I-1", state["invocations"]["I-1"])["totals"]
    model = totals["by_model"]["openai/gpt-6.1"]
    assert (model["runs"], model["tokens"]["input"]) == (1, 1000)
    assert model["estimated_under_current_prices_usd"] == totals["estimated_under_current_prices"]["usd"] == \
        Decimal("0.002")


def test_merged_partitions_past_the_counter_cap_are_no_partition_never_a_capped_match():
    """#133 review (0e2bae9): capping a merged count at MAX_TOKENS could make partitions that overshoot the totals
    look reconciled, and price them. A merge past the cap is no partition, so the run is unpriced."""
    big = U.MAX_TOKENS
    raw = {"input": big, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    rec = U.normalize({"tokens": raw}, [{}], [GPT, MINI], U.DISJOINT, source="harness:opencode",
                      tokens_by_model=[{**GPT, "tokens": raw}, {**GPT, "tokens": {**raw, "input": 5}}])
    assert rec["tokens_by_model"] is None
    assert "usd" not in O.derive(rec, PRICES)[0]


def test_two_partitions_on_one_price_row_keep_their_whole_cost_in_by_model(tmp_path):
    """#133 review (0e2bae9): ("a/b", "c") and ("a", "b/c") are different pairs but one price row, "a/b/c". The
    run's by_model row must carry both parts' cost, so by_model sums to the run's total."""
    table = TABLE + b"  a/b/c: {input: 1.0, output: 1.0, cache_read: 1.0, cache_write: 1.0}\n"
    prices = O.Prices(table, source="pricing.yaml")
    flat = {c: 0 for c in U.CATEGORIES}
    rec = {**record(input=1000), "effective": [{"provider": "a/b", "model": "c", "effort": None},
                                               {"provider": "a", "model": "b/c", "effort": None}],
           "tokens_by_model": [{"provider": "a/b", "model": "c", "tokens": {**flat, "input": 400}},
                               {"provider": "a", "model": "b/c", "tokens": {**flat, "input": 600}}]}
    assert O.derive(rec, prices)[0] == {"usd": Decimal("0.001")}
    run_record(runlog.run_dir(tmp_path, "R-1"), rec)
    state = hand_state(("I-1", "T-0001", ["R-1"]))
    O.copy_run_usage(state, "I-1", tmp_path, pricing=prices)
    by_model = O.Reader(tmp_path, prices).invocation("I-1", state["invocations"]["I-1"])["totals"]["by_model"]
    assert (by_model["a/b/c"]["runs"], by_model["a/b/c"]["tokens"]["input"]) == (1, 1000)
    assert by_model["a/b/c"]["estimated_under_current_prices_usd"] == Decimal("0.001")


def test_a_model_without_a_row_or_no_effective_model_is_unpriced_model():
    other = {"provider": "anthropic", "model": "x", "effort": None}
    assert O.derive(record(input=5, effective=[other]), PRICES)[0] == {"unpriced": "unpriced_model"}
    assert O.derive(record(input=5, effective=[]), PRICES)[0] == {"unpriced": "unpriced_model"}


# ---------------------------------------------------------------------------------------------- the pricing snapshot


def test_the_first_use_writes_the_snapshot_and_a_second_never_rewrites_it(tmp_path):
    sha = O.write_pricing_snapshot(tmp_path, PRICES)
    path = O.snapshot_path(tmp_path, sha)
    assert path.read_bytes() == TABLE and path.parent == tmp_path / "pricing"
    before = path.stat().st_mtime_ns
    assert O.write_pricing_snapshot(tmp_path, PRICES) == sha
    assert path.stat().st_mtime_ns == before
    path.write_bytes(TABLE + b"# tampered\n")
    with pytest.raises(IntegrityError) as exc:
        O.write_pricing_snapshot(tmp_path, PRICES)
    assert exc.value.details["reason"] == "pricing_snapshot_mismatch"


def run_record(directory: Path, usage_record: Any, *, status: str = K.ENDED_WITH_EVIDENCE,
               model_check: str = "match") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(json.dumps({
        "schema": K.RUN_SCHEMA, "status": status, "result": {"usage_record": usage_record},
        "model_check": {"status": model_check}}), encoding="utf-8")


def hand_state(*invocations: tuple[str, str, list[str]], work: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"work": work or {"T-0001": {"kind": "ticket", "parent": None}},
            "invocations": {inv: {"work_unit": unit, "execution_profile": {**GPT, "profile": "implementer",
                                                                           "harness": "opencode"},
                                  "runs": [{"run": r, "harness": "opencode"} for r in runs]}
                            for inv, unit, runs in invocations}}


def test_a_changed_table_moves_only_the_current_estimate(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=1_000_000))
    state = hand_state(("I-1", "T-0001", ["R-1"]))
    assert O.copy_run_usage(state, "I-1", tmp_path, pricing=PRICES, now="2026-10-05T12:00:00Z") == ["R-1"]
    copied = json.dumps(state["invocations"]["I-1"]["runs"][0]["usage"], sort_keys=True)
    first = O.Reader(tmp_path, PRICES).invocation("I-1", state["invocations"]["I-1"])["rows"][0]
    assert (first["estimated_at_record"], first["estimated_under_current_prices"]) == ({"usd": Decimal(2)},
                                                                                     {"usd": Decimal(2)})
    corrected = O.Prices(TABLE.replace(b"input: 2.0", b"input: 3.0"), source="pricing.yaml")
    later = O.Reader(tmp_path, corrected).invocation("I-1", state["invocations"]["I-1"])["rows"][0]
    assert later["estimated_at_record"] == {"usd": Decimal(2)}
    assert later["estimated_under_current_prices"] == {"usd": Decimal(3)}
    assert json.dumps(state["invocations"]["I-1"]["runs"][0]["usage"], sort_keys=True) == copied  # facts unchanged


def test_a_missing_snapshot_is_a_doctor_failure_and_its_figure_unpriced(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=10))
    state = hand_state(("I-1", "T-0001", ["R-1"]))
    O.copy_run_usage(state, "I-1", tmp_path, pricing=PRICES)
    assert O.snapshot_doctor(state, tmp_path)[0] == "PASS"
    sha = state["invocations"]["I-1"]["runs"][0]["usage"]["pricing_sha256"]
    O.snapshot_path(tmp_path, sha).unlink()
    status, detail = O.snapshot_doctor(state, tmp_path)
    assert status == "FAIL" and sha in detail
    row = O.Reader(tmp_path, PRICES).invocation("I-1", state["invocations"]["I-1"])["rows"][0]
    assert row["estimated_at_record"] == {"unpriced": "unpriced_snapshot_missing"}


# ---------------------------------------------------------------------------------------------- the copy (R5)


def test_the_copy_is_once_and_a_run_without_a_usage_record_is_absent_not_omitted(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=10), model_check="mismatch")
    run_record(runlog.run_dir(tmp_path, "R-2"), None, status=K.CRASHED)
    run_record(runlog.run_dir(tmp_path, "R-3"), {"schema": U.SCHEMA, "tokens": "lots"})  # malformed: absent
    state = hand_state(("I-1", "T-0001", ["R-1", "R-2", "R-3"]))
    assert O.copy_run_usage(state, "I-1", tmp_path, pricing=None, now="2026-10-05T12:00:00Z") == ["R-1", "R-2",
                                                                                                "R-3"]
    one, two, three = (r["usage"] for r in state["invocations"]["I-1"]["runs"])
    assert (one["run"], one["model_check"], one["pricing_sha256"], one["status"]) == ("R-1", "mismatch", None,
                                                                                    K.ENDED_WITH_EVIDENCE)
    assert one["requested"] == {"provider": "openai", "model": "gpt-6.1", "effort": "high", "profile": "implementer"}
    assert (two["tokens_trust"], two["provider_cost_trust"], two["status"]) == ("absent", "absent", K.CRASHED)
    assert three["tokens_trust"] == "absent"
    for rec in (one, two, three):
        validate("run-usage", rec, source="test")
        assert U.serialized_size(rec) <= U.MAX_BYTES
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=99))
    assert O.copy_run_usage(state, "I-1", tmp_path, pricing=PRICES) == []
    assert state["invocations"]["I-1"]["runs"][0]["usage"] == one  # never rewritten
    assert not (tmp_path / "pricing").exists()  # nothing copied, so no snapshot was used


def test_a_requested_id_past_its_bound_is_unknown_and_the_run_keeps_its_counters(tmp_path):
    """#133 review (fd571ff), finding 2: a copy that would not fit is bounded field by field, never by replacing
    the run's token and cost facts with absent usage."""
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=1000, cost=0.5))
    state = hand_state(("I-1", "T-0001", ["R-1"]))
    state["invocations"]["I-1"]["execution_profile"]["model"] = "é" * U.MAX_MODEL  # 48 characters, 96 bytes
    O.copy_run_usage(state, "I-1", tmp_path, pricing=None)
    copied = state["invocations"]["I-1"]["runs"][0]["usage"]
    assert copied["requested"]["model"] is None and copied["requested"]["provider"] == "openai"
    assert (copied["tokens"]["input"], copied["tokens_trust"], copied["provider_cost_usd"]) == (
        1000, "harness_reported", 0.5)
    assert U.serialized_size(copied) <= U.MAX_BYTES


# ---------------------------------------------------------------------------------------------- projections (R6, R7)


def test_rows_are_recorded_provisional_or_missing_and_missing_is_counted(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=1000))
    run_record(runlog.run_dir(tmp_path, "R-2"), record(input=1000, cost=0))
    state = hand_state(("I-1", "T-0001", ["R-1", "R-2", "R-3"]))
    O.copy_run_usage(state, "I-1", tmp_path, pricing=PRICES)
    del state["invocations"]["I-1"]["runs"][1]["usage"]  # R-2 not yet copied, R-3 has no run directory
    del state["invocations"]["I-1"]["runs"][2]["usage"]
    projected = O.Reader(tmp_path, PRICES).invocation("I-1", state["invocations"]["I-1"])
    assert [r["state"] for r in projected["rows"]] == ["recorded", "provisional", "missing"]
    t = projected["totals"]
    assert (t["runs"], t["recorded"], t["provisional"], t["missing"]) == (3, 1, 1, 1)
    assert t["estimated_at_record"]["reasons"] == {"unpriced_not_recorded": 1, "unpriced_usage_missing": 1}
    assert t["estimated_under_current_prices"]["usd"] == Decimal("0.004")
    assert (t["provider_cost"]["zero_with_tokens"], t["provider_cost"]["absent"]) == (1, 2)
    assert t["provider_cost"]["reported_usd"] == 0  # a zero_with_tokens cost is never added into a reported total


def test_an_invocation_without_runs_is_counted_and_contributes_nothing_else(tmp_path):
    state = hand_state(("I-1", "T-0001", []))
    t = O.unit_projection(state, "T-0001", O.Reader(tmp_path, PRICES))["own"]
    assert (t["invocations"], t["invocations_without_runs"], t["runs"]) == (1, 1, 0)
    assert t["estimated_under_current_prices"] == {"usd": 0, "priced": 0, "unpriced": 0, "reasons": {}}


def test_a_mixed_run_counts_under_the_mix_never_the_requested_model(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-1"), record(input=10, effective=[GPT, MINI]))
    run_record(runlog.run_dir(tmp_path, "R-2"), record(input=10, effective=[MINI]))
    state = hand_state(("I-1", "T-0001", ["R-1", "R-2"]))
    by_model = O.Reader(tmp_path, PRICES).invocation("I-1", state["invocations"]["I-1"])["totals"]["by_model"]
    assert set(by_model) == {"unpriced_effective_model_mix", "openai/gpt-6.1-mini"}
    assert by_model["openai/gpt-6.1-mini"]["estimated_under_current_prices_usd"] == Decimal("0.000004")


@pytest.mark.parametrize("kwargs, expected", [
    ({}, {"scope": "recent", "archive_complete": False}),
    ({"walk_all": True, "archive_complete": True}, {"scope": "all", "archive_complete": True}),
    ({"walk_all": True, "archive_complete": False}, {"scope": "all", "archive_complete": False}),
    ({"walk_all": True, "since": "2026-10-01T00:00:00Z", "archive_complete": True},
     {"scope": "window", "archive_complete": False, "since": "2026-10-01T00:00:00Z", "until": None}),
])
def test_every_project_projection_says_what_it_covers(tmp_path, kwargs, expected):
    projected = O.project_projection(hand_state(), O.Reader(tmp_path, PRICES), **kwargs)
    assert {k: projected[k] for k in expected} == expected
    assert projected["scope"] != "recent" or projected["archive_complete"] is False


def test_archived_units_join_the_project_and_unit_projections(tmp_path):
    run_record(runlog.run_dir(tmp_path, "R-9"), record(input=1000))
    archived = [{"id": "T-0002", "unit": {"kind": "ticket", "parent": "S-0001"},
                 "invocations": {"I-9": {"work_unit": "T-0002", "runs": [{"run": "R-9", "harness": "opencode"}]}}}]
    state = hand_state(work={"S-0001": {"kind": "story", "parent": None}})
    reader = O.Reader(tmp_path, PRICES)
    story = O.unit_projection(state, "S-0001", reader, archived)
    assert story["own"]["runs"] == 0 and story["descendants"]["runs"] == 1
    assert O.project_projection(state, reader, archived, walk_all=True)["totals"]["runs"] == 1
    assert json.loads(json.dumps(O.to_json(story)))["descendants"]["estimated_under_current_prices"]["usd"] == 0.002


def test_roll_ups_equal_the_sum_of_their_parts_and_the_counts_partition_the_runs(tmp_path):
    """The property of §7 slice 1, over seeded random worlds: the unit total equals the sum of its invocation totals
    equals the sum of its run figures, and the counts, every unpriced reason included, partition the runs."""
    rng = random.Random(20261005)
    semantics = [*U.TOKEN_SEMANTICS]
    models = [GPT, MINI, {"provider": "anthropic", "model": "x", "effort": None}]
    priced, seen = 0, set()
    for world in range(25):
        root = tmp_path / str(world)
        work = {"E-1": {"kind": "epic", "parent": None}, "S-1": {"kind": "story", "parent": "E-1"},
                "T-1": {"kind": "ticket", "parent": "S-1"}, "T-2": {"kind": "ticket", "parent": "S-1"}}
        invs: list[tuple[str, str, list[str]]] = []
        n = 0
        for i in range(rng.randint(1, 6)):
            runs = []
            for _ in range(rng.randint(0, 4)):
                n += 1
                run = f"R-{n}"
                runs.append(run)
                kind = rng.random()
                if kind < 0.1:
                    continue  # missing: no run directory
                counters = {k: rng.choice([0, rng.randint(1, 10**6)]) for k in R}
                eff = rng.sample(models, rng.randint(0, 2))
                rec = record(**counters, semantics=rng.choice(semantics), effective=eff,
                             cost=rng.choice([None, 0, round(rng.random(), 4)]))
                run_record(runlog.run_dir(root, run), rec)
            invs.append((f"I-{i}", rng.choice(["E-1", "S-1", "T-1", "T-2"]), runs))
        state = hand_state(*invs, work=work)
        for inv_id, _, _ in invs:
            if rng.random() < 0.6:
                O.copy_run_usage(state, inv_id, root, pricing=rng.choice([PRICES, None]))
        reader = O.Reader(root, PRICES)
        epic = O.unit_projection(state, "E-1", reader)
        total = O.add_totals(O.add_totals(O.empty_totals(), epic["own"]), epic["descendants"])
        rows = [r for inv_id in state["invocations"]
                for r in reader.invocation(inv_id, state["invocations"][inv_id])["rows"]]
        per_invocation = O.empty_totals()
        for inv_id in state["invocations"]:
            O.add_totals(per_invocation, reader.invocation(inv_id, state["invocations"][inv_id])["totals"])
        assert total == per_invocation
        assert total == O.project_projection(state, reader)["totals"]
        assert total["runs"] == len(rows) == total["recorded"] + total["provisional"] + total["missing"]
        pc = total["provider_cost"]
        assert pc["reported"] + pc["zero_with_tokens"] + pc["absent"] == len(rows)
        for name in ("estimated_at_record", "estimated_under_current_prices"):
            fig = total[name]
            assert fig["priced"] + fig["unpriced"] == len(rows)
            assert sum(fig["reasons"].values()) == fig["unpriced"]
            assert fig["usd"] == sum((r[name]["usd"] for r in rows if "usd" in r[name]), Decimal(0))
        assert total["invocations"] == len(invs)
        assert total["invocations_without_runs"] == sum(1 for _, _, runs in invs if not runs)
        priced += total["estimated_under_current_prices"]["priced"] + total["estimated_at_record"]["priced"]
        for name in ("estimated_at_record", "estimated_under_current_prices"):
            seen.update(r.split(":")[0] for r in total[name]["reasons"])
    # The worlds exercised what the property is about: priced runs, and every way of being unpriced they can reach.
    assert priced > 0
    assert seen >= {O.UNPRICED_SEMANTICS_UNKNOWN, O.UNPRICED_INCONSISTENT, O.UNPRICED_CATEGORY, O.UNPRICED_MIX,
                    O.UNPRICED_MODEL, O.UNPRICED_NO_TABLE, O.UNPRICED_NOT_RECORDED, O.UNPRICED_USAGE_MISSING}, seen

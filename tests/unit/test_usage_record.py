"""The run-usage record (F25, the cost and usage ledger design v0.2 R1 to R3; slice 1 of §7): the adapter normalizes
OpenCode's reported usage into one bounded ``aew/run-usage/v1`` object, and the supervisor records it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aew.harness import usage as U
from aew.harness.opencode import adapter
from aew.harness.supervisor import Supervisor
from aew.schemas import validate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
SPEC = json.loads((FIXTURES / "openapi-2.0.18.min.json").read_text(encoding="utf-8"))
OPENAI = [{"provider": "openai", "model": "gpt-6.1", "effort": "high"}]


def tokens(input: int = 0, output: int = 0, reasoning: int = 0, read: int = 0, write: int = 0) -> dict[str, Any]:
    """An OpenCode 2.0.18 ``TokenUsage.Info``."""
    return {"input": input, "output": output, "reasoning": reasoning, "cache": {"read": read, "write": write}}


def test_the_record_reads_every_category_of_the_pinned_token_usage_shape():
    """The pinned OpenAPI's ``TokenUsage.Info`` is exactly the shape the record maps onto AEW's five named categories:
    a release that respelled a counter would be caught here, not mispriced later."""
    info = SPEC["components"]["schemas"]["TokenUsage.Info"]
    assert set(info["required"]) == {"input", "output", "reasoning", "cache"}
    assert set(info["properties"]["cache"]["required"]) == {"read", "write"}
    assert "cost" in SPEC["components"]["schemas"]["Session.Info"]["required"]


def test_a_session_with_every_category_is_harness_reported():
    rec = U.normalize({"tokens": tokens(184210, 9120, 30011, 151000, 12000), "cost": 1.25}, [{}] * 23, OPENAI,
                      U.DISJOINT, source="harness:opencode", foreign_sessions=1)
    assert rec["tokens"] == {"input": 184210, "output": 9120, "reasoning": 30011, "cache_read": 151000,
                             "cache_write": 12000, "unknown": 0}
    assert (rec["tokens_trust"], rec["provider_cost_usd"], rec["provider_cost_trust"]) == ("harness_reported", 1.25,
                                                                                          "reported")
    assert (rec["steps"], rec["foreign_sessions"], rec["truncated"], rec["token_semantics"]) == (23, 1, False,
                                                                                               "disjoint")
    validate("run-usage", rec, source="test")


def test_a_zero_cost_against_tokens_is_not_a_price():
    """R3: the subscription-login case the M3 dogfood hit."""
    rec = U.normalize({"tokens": tokens(10, 5), "cost": 0}, [{}], OPENAI, U.DISJOINT, source="harness:opencode")
    assert (rec["provider_cost_usd"], rec["provider_cost_trust"]) == (0.0, "zero_with_tokens")
    nothing = U.normalize({"tokens": tokens(), "cost": 0}, [], [], U.DISJOINT, source="harness:opencode")
    assert nothing["provider_cost_trust"] == "reported"  # a zero against zero tokens is a real zero


def test_a_run_with_no_usage_is_absent_with_all_zeros():
    rec = U.normalize(None, None, [], U.UNKNOWN, source="harness:opencode")
    assert rec["tokens_trust"] == "absent" and set(rec["tokens"].values()) == {0}
    assert (rec["provider_cost_usd"], rec["provider_cost_trust"]) == (None, "absent")
    assert U.absent_record(source="harness:fake")["tokens_trust"] == "absent"
    validate("run-usage", rec, source="test")


def test_fewer_categories_are_partial_and_unnamed_ones_are_summed_as_unknown():
    rec = U.normalize({"tokens": {"input": 7, "output": 3, "audio": 4, "image": {"in": 2}}}, [], OPENAI, U.DISJOINT,
                      source="harness:other")
    assert rec["tokens_trust"] == "partial"
    assert rec["tokens"] == {"input": 7, "output": 3, "reasoning": 0, "cache_read": 0, "cache_write": 0, "unknown": 6}


@pytest.mark.parametrize("bad", [-1, True, float("nan"), 1.5, "12", U.MAX_TOKENS + 1])
def test_a_counter_that_is_not_a_count_is_treated_as_unreported(bad):
    rec = U.normalize({"tokens": {**tokens(1, 1, 1, 1, 1), "input": bad}}, [], OPENAI, U.DISJOINT, source="harness:x")
    assert rec["tokens"]["input"] == 0 and rec["tokens_trust"] == "partial"


def test_session_totals_missing_fall_back_to_the_steps_and_a_truncated_sum_is_partial():
    steps = [{"tokens": tokens(10, 2, 1, 4, 0)}, {"tokens": tokens(5, 1, 0, 0, 3)}]
    whole = U.normalize({"tokens": None}, steps, OPENAI, U.DISJOINT, source="harness:opencode")
    assert whole["tokens"]["input"] == 15 and whole["tokens_trust"] == "harness_reported"
    cut = U.normalize({"tokens": None}, steps, OPENAI, U.DISJOINT, source="harness:opencode", truncated=True)
    assert cut["tokens_trust"] == "partial" and cut["truncated"] is True


def test_effective_is_capped_at_eight_distinct_entries_and_the_excess_is_counted():
    many = [{"provider": "p", "model": f"m{i}", "effort": None} for i in range(11)] + [
        {"provider": "p", "model": "m0", "effort": None}]
    rec = U.normalize(None, None, many, U.UNKNOWN, source="harness:opencode")
    assert len(rec["effective"]) == U.MAX_EFFECTIVE and rec["effective_truncated"] == 3


def test_an_over_long_identifier_becomes_unknown_never_a_shortened_id():
    rec = U.normalize(None, None, [{"provider": "openai", "model": "m" * (U.MAX_MODEL + 1), "effort": "high"}],
                      U.UNKNOWN, source="harness:opencode")
    assert rec["effective"] == [{"provider": "openai", "model": None, "effort": "high"}]


@pytest.mark.parametrize("model, kept", [
    ("é" * (U.MAX_MODEL // 2), True),        # 24 characters, 48 bytes: at the bound
    ("é" * (U.MAX_MODEL // 2 + 1), False),   # 25 characters, 50 bytes
    ("😀" * (U.MAX_MODEL // 4 + 1), False),  # 13 characters, 52 bytes
    ('"' * (U.MAX_MODEL // 2 + 1), False),   # 25 characters, 50 once JSON escapes them
], ids=["two-byte-at-bound", "two-byte-over", "four-byte-over", "escaped-over"])
def test_identifier_bounds_count_serialized_bytes_not_characters(model, kept):
    """#133 review (fd571ff), finding 2: the 2 KiB bound counts UTF-8 bytes of the JSON, so the identifier bounds
    that make it a consequence of the schema count the same unit."""
    rec = U.normalize(None, None, [{"provider": "openai", "model": model, "effort": None}], U.UNKNOWN,
                      source="harness:opencode")
    assert rec["effective"][0]["model"] == (model if kept else None)


def test_an_identifier_with_a_lone_surrogate_is_unknown_never_a_failed_result():
    """#133 review (0e2bae9): JSON's "\\ud800" parses to a lone surrogate, which has no UTF-8 form. The byte bound
    must not raise on it: the id is unknown and the record is still built."""
    model = json.loads('"gpt\\ud800"')
    rec = U.normalize(None, None, [{"provider": "openai", "model": model, "effort": None}], U.UNKNOWN,
                      source="harness:opencode")
    assert rec["effective"] == [{"provider": "openai", "model": None, "effort": None}]
    assert U.serialized_size(rec) <= U.MAX_BYTES


def test_non_ascii_identifiers_at_their_character_bounds_stay_within_two_kib():
    effective = [{"provider": "п" * U.MAX_PROVIDER, "model": "😀" * (U.MAX_MODEL - 1) + str(i),
                  "effort": "é" * U.MAX_EFFORT} for i in range(U.MAX_EFFECTIVE)]
    partitions = [{**e, "tokens": tokens(1, 1)} for e in effective]
    rec = U.normalize({"tokens": tokens(8, 8)}, [{}], effective, U.DISJOINT, source="ü" * U.MAX_SOURCE,
                      tokens_by_model=partitions)
    assert U.serialized_size({**rec, **U.LONGEST_COPY_FIELDS}) <= U.MAX_BYTES


def worst_case(**extra: Any) -> dict[str, Any]:
    big = U.MAX_TOKENS
    effective = [{"provider": "p" * U.MAX_PROVIDER, "model": "m" * (U.MAX_MODEL - 1) + str(i),
                  "effort": "e" * U.MAX_EFFORT} for i in range(U.MAX_EFFECTIVE + 5)]
    raw = {"tokens": {**tokens(big, big, big, big, big), "other": big}, "cost": U.MAX_COST_USD - 0.123456789}
    rec = U.normalize(raw, [{}] * 3, effective, U.INPUT_INCLUDES_CACHE_READ_OUTPUT_INCLUDES_REASONING,
                      source="h" * U.MAX_SOURCE, truncated=True, foreign_sessions=U.MAX_COUNT + 5,
                      wall_s=U.MAX_WALL_S * 2, **extra)
    return {**rec, "steps": U.MAX_COUNT}  # the cap, without building ten million steps


def test_the_largest_record_stays_within_two_kib_once_copied():
    """R1: the bound is a number. With every string at its bound, every counter at its cap and nine models, the
    record the engine would copy (with its own fields at their longest) is at most 2 KiB and schema-valid."""
    copied = {**worst_case(), **U.LONGEST_COPY_FIELDS}
    validate("run-usage", copied, source="test")
    assert U.serialized_size(copied) <= U.MAX_BYTES


def test_a_partition_that_would_break_the_bound_is_dropped_never_the_bound():
    partitions = [{"provider": "p" * U.MAX_PROVIDER, "model": "m" * (U.MAX_MODEL - 1) + str(i),
                   "tokens": tokens(U.MAX_TOKENS, U.MAX_TOKENS)} for i in range(U.MAX_EFFECTIVE)]
    assert worst_case(tokens_by_model=partitions)["tokens_by_model"] is None
    small = U.normalize({"tokens": tokens(3, 2)}, [{}, {}], [{"provider": "a", "model": "x", "effort": None},
                                                           {"provider": "a", "model": "y", "effort": None}],
                        U.DISJOINT, source="harness:x",
                        tokens_by_model=[{"provider": "a", "model": "x", "tokens": tokens(1, 1)},
                                         {"provider": "a", "model": "y", "tokens": tokens(2, 1)}])
    assert [p["model"] for p in small["tokens_by_model"]] == ["x", "y"]
    validate("run-usage", small, source="test")


# ---------------------------------------------------------------------------------------------- the OpenCode adapter


class Pages:
    """A stub of the OpenCode client's GET: ``pages`` pages of one assistant message each, then the session."""

    def __init__(self, pages: int, session: dict[str, Any]) -> None:
        self.pages, self.session, self.served = pages, session, 0

    def get(self, path: str, params: Any = None, **_: Any) -> dict[str, Any]:
        if path.endswith("/message"):
            self.served += 1
            last = self.served >= self.pages
            return {"data": [{"type": "assistant", "model": {"providerID": "openai", "id": "gpt-6.1",
                                                             "variant": "high"},
                              "tokens": tokens(1, 1), "cost": 0}],
                    "cursor": {} if last else {"next": f"c{self.served}"}}
        if path == "/api/session":
            return {"data": []}
        return {"data": self.session}


def collected(tmp_path: Path, pages: int, session: dict[str, Any], version: str = "2.0.18") -> dict[str, Any]:
    a = adapter.OpenCodeAdapter(None, tmp_path, lambda _: None)  # type: ignore[arg-type]  (no process tree needed)
    a.client = Pages(pages, session)  # type: ignore[assignment]
    a.session, a.directory, a.health = "ses_1", str(tmp_path), {"version": version}
    a._take_snapshot()
    return a.collect()


def test_collect_reports_a_usage_record_with_the_declared_semantics(tmp_path):
    out = collected(tmp_path, 2, {"outcome": "succeeded", "tokens": tokens(40, 8, 3, 30, 2), "cost": 0.02})
    rec = out["usage_record"]
    assert rec["source"] == "harness:opencode" and rec["steps"] == 2 and rec["truncated"] is False
    assert rec["token_semantics"] == "disjoint"  # openai under 2.0.18 is qualified (the conformance test pins it)
    assert rec["tokens"]["cache_read"] == 30 and rec["provider_cost_trust"] == "reported"
    assert out["usage"]["cost"] == 0.02  # the raw facts stay beside the record for diagnosis (R2)
    validate("run-usage", rec, source="test")


def test_a_run_whose_messages_outrun_the_paging_bound_is_marked_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "PAGES", 3)
    out = collected(tmp_path, 5, {"tokens": tokens(5, 5, 0, 0, 0), "cost": 0})
    assert out["usage_record"]["truncated"] is True and out["usage_record"]["steps"] == 3
    assert out["usage_record"]["provider_cost_trust"] == "zero_with_tokens"


def test_an_unqualified_opencode_version_declares_unknown_semantics(tmp_path):
    out = collected(tmp_path, 1, {"tokens": tokens(5, 5), "cost": 0}, version="2.0.19")
    assert out["usage_record"]["token_semantics"] == "unknown"


def test_collect_without_a_snapshot_reports_absent_usage_never_zero(tmp_path):
    a = adapter.OpenCodeAdapter(None, tmp_path, lambda _: None)  # type: ignore[arg-type]
    rec = a.collect()["usage_record"]
    assert (rec["tokens_trust"], rec["provider_cost_trust"], rec["token_semantics"]) == ("absent", "absent",
                                                                                        "unknown")


# ---------------------------------------------------------------------------------------------- the supervisor


def bare_supervisor(result: Any, started: float | None) -> Supervisor:
    sup = Supervisor.__new__(Supervisor)  # only the record and the start time: no engine, no process
    sup.record = {"result": result}
    sup._started_mono = started
    return sup


def test_the_supervisor_records_the_usage_record_with_the_wall_time(monkeypatch):
    rec = U.normalize({"tokens": tokens(1, 1, 0, 0, 0)}, [{}], OPENAI, U.DISJOINT, source="harness:opencode")
    sup = bare_supervisor({"usage": {"cost": 0}, "usage_record": rec}, 100.0)
    monkeypatch.setattr("aew.harness.supervisor.time.monotonic", lambda: 512.64)
    sup._record_usage()
    assert sup.record["result"]["usage_record"]["wall_s"] == 412.6
    assert sup.record["result"]["usage"] == {"cost": 0}


@pytest.mark.parametrize("bad", ["text", {"schema": "something/else"}, None])
def test_the_supervisor_drops_a_usage_record_that_is_not_one(bad):
    sup = bare_supervisor({"usage_record": bad}, 1.0)
    sup._record_usage()
    assert "usage_record" not in sup.record["result"]


def test_a_run_that_never_started_has_no_wall_time():
    rec = U.absent_record(source="harness:opencode")
    sup = bare_supervisor({"usage_record": rec}, None)
    sup._record_usage()
    assert sup.record["result"]["usage_record"]["wall_s"] is None

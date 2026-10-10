"""Live run usage (F25 for M4-H, slice L1): one sample shape, ``aew/usage-live/v1``, and one meter for every OpenCode
server (``aew.harness.usage_live``).

The meter is driven against the fake V2 server in process (``fake_opencode.local_app``), whose usage facts are probe
P1's, and against P1's own cited cases (``tests/fixtures/opencode/live-usage-2.0.18.json``): CI has no OpenCode source,
so the fixture's citations are checked for their shape, as ``test_usage_conformance`` checks its own."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import fake_opencode as F
import pytest

from aew import schemas
from aew.engine import usage_ops as O
from aew.harness import usage as U
from aew.harness import usage_live as L
from aew.harness.opencode.adapter import OpenCodeAdapter, _effective
from aew.harness.opencode.capabilities import TESTED_VERSIONS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
P1 = json.loads((FIXTURES / "live-usage-2.0.18.json").read_text(encoding="utf-8"))
OPENAPI = json.loads((FIXTURES / "openapi-2.0.18.min.json").read_text(encoding="utf-8"))
GPT = {"providerID": "openai", "id": "gpt-6.1", "variant": "default"}
MINI = {"providerID": "openai", "id": "gpt-6.1-mini", "variant": "low"}
PRICES = O.Prices(b"schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: test\nprices:\n"
                  b"  openai/gpt-6.1: {input: 1, output: 4, reasoning: 4, cache_read: 0.5, cache_write: 1}\n"
                  b"  openai/gpt-6.1-mini: {input: 0.25, output: 1, reasoning: 1, cache_read: 0.125, "
                  b"cache_write: 0.25}\n",
                  source="test")


def tok(i: int = 0, o: int = 0, r: int = 0, cr: int = 0, cw: int = 0) -> dict[str, Any]:
    return {"input": i, "output": o, "reasoning": r, "cache": {"read": cr, "write": cw}}


def flat(i: int = 0, o: int = 0, r: int = 0, cr: int = 0, cw: int = 0) -> dict[str, int]:
    return {"input": i, "output": o, "reasoning": r, "cache_read": cr, "cache_write": cw, "unknown": 0}


def parts(sample: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {f"{p['provider']}/{p['model']}" if p["model"] else "-": p["tokens"]
            for p in sample["tokens_by_model"] or []}


def as_record(sample: dict[str, Any]) -> dict[str, Any]:
    """The R1 fields of a sample as a record ``derive`` prices (what L3's total does per source)."""
    return {**{k: sample[k] for k in ("effective", "effective_truncated", "tokens_by_model", "token_semantics",
                                      "tokens", "tokens_trust", "truncated")}}


def valid(sample: dict[str, Any]) -> dict[str, Any]:
    schemas.validate("usage-live", sample, source="live sample")
    assert U.serialized_size(sample) <= L.MAX_SAMPLE_BYTES
    return sample


class Lab:
    """A fake server in process, its client, and meters on it."""

    def __init__(self, root: Path, **knobs: Any) -> None:
        self.root = root
        self.app = F.local_app(root, knobs)
        self.client = F.LocalClient(self.app)
        self.n = 0

    def meter(self, root_session: str | None = None, *, pinned: dict[str, Any] | None = GPT, s_pot: int = 1,
              state: str = "state.json", version: str = "2.0.18") -> L.Meter:
        return L.OpenCodeMeter(self.client, root_session=root_session or "ses_root", version=version, s_pot=s_pot,
                               state_path=self.root / state, pinned_model=pinned)

    def call(self, sid: str, tokens: dict[str, Any], *, model: dict[str, Any] | None = None, cost: float = 0.0,
             duration_ms: float = 1000.0) -> str:
        self.n += 1
        mid = self.app.start_call(sid, model=model, created=1000.0 * self.n)
        self.app.end_call(sid, mid, tokens=tokens, cost=cost, completed=1000.0 * self.n + duration_ms)
        return mid


@pytest.fixture
def lab(tmp_path: Path) -> Lab:
    return Lab(tmp_path)


# ---------------------------------------------------------------------------------------------- the figure


def test_a_live_sample_sums_every_session_in_the_server(lab: Lab):
    root = lab.app.add_session(model=GPT)
    child = lab.app.add_session(model=GPT, parent=root)
    other = lab.app.add_session(model=GPT)  # a session nobody started from the root: still the server's spend
    lab.call(root, tok(1000, 100, 10, 500, 5))
    lab.call(child, tok(200, 20))
    lab.call(other, tok(30, 3))
    sample = valid(lab.meter(root).poll())
    assert sample["sessions"] == 3 and sample["steps"] == 3 and not sample["truncated"]
    assert sample["tokens"] == flat(1230, 123, 10, 500, 5)
    assert sample["foreign_tokens"] == flat(230, 23)
    assert sample["tokens_trust"] == "harness_reported" and sample["token_semantics"] == "disjoint"


def test_a_child_session_is_never_counted_twice(lab: Lab):
    root = lab.app.add_session(model=GPT)
    child = lab.app.add_session(model=GPT, parent=root)
    lab.call(root, tok(1000, 100))
    lab.call(child, tok(400, 40))
    meter = lab.meter(root)
    first = meter.poll()
    lab.app.sessions[child].info["time"]["updated"] += 10_000  # it moves in the list's order while being paged
    again = valid(meter.poll())
    # A session's totals are its own (P1(b)): the parent's never include the child's, and a session listed twice is
    # one session.
    assert first["tokens"] == again["tokens"] == flat(1400, 140)
    assert again["steps"] == 2 and again["sessions"] == 2


def test_a_session_on_another_model_is_partitioned_never_a_mix(lab: Lab):
    root = lab.app.add_session(model=GPT)
    child = lab.app.add_session(model=MINI, parent=root)
    lab.call(root, tok(1_000_000, 100_000))
    lab.call(child, tok(1_000_000, 0), model=MINI)
    sample = valid(lab.meter(root).poll())
    assert parts(sample) == {"openai/gpt-6.1": flat(1_000_000, 100_000), "openai/gpt-6.1-mini": flat(1_000_000)}
    assert {(e["provider"], e["model"], e["effort"]) for e in sample["effective"]} == {
        ("openai", "gpt-6.1", None), ("openai", "gpt-6.1-mini", "low")}
    figure, priced = O.derive(as_record(sample), PRICES)
    assert figure == {"usd": Decimal("1.4") + Decimal("0.25")}
    assert dict(priced) == {"openai/gpt-6.1": Decimal("1.4"), "openai/gpt-6.1-mini": Decimal("0.25")}


@pytest.mark.parametrize("pinned, session_model, priced_on", [
    (GPT, GPT, "openai/gpt-6.1"),
    (None, GPT, "-"),              # no proven pin: the remainder prices nothing
    (GPT, MINI, "-"),              # the session runs another model than the pin: never priced on the pin
])
def test_the_remainder_goes_to_the_pinned_model_only_when_pinned(lab: Lab, pinned, session_model, priced_on):
    sid = lab.app.add_session(model=session_model)
    lab.call(sid, tok(1000, 100), model=session_model)
    lab.app.record_usage(sid, tok(50, 5))  # a title call: on the totals, on no message (P1(b))
    sample = valid(lab.meter(sid, pinned=pinned).poll())
    own = "openai/" + session_model["id"]
    assert sample["tokens"] == flat(1050, 105)
    if priced_on == own:
        assert parts(sample) == {own: flat(1050, 105)}
        assert O.derive(as_record(sample), PRICES)[0] == {"usd": Decimal("0.00147")}
    else:
        assert parts(sample)[priced_on] == flat(50, 5)
        assert O.derive(as_record(sample), PRICES)[0] == {"unpriced": O.UNPRICED_MODEL}


def test_a_call_counts_once_when_completed(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    mid = lab.app.start_call(sid, created=1000)
    lab.app.set_running(sid, True)
    assert meter.poll()["steps"] == 0 and meter.poll()["tokens"] == flat()  # tokens move only at the end (P1(c))
    lab.app.end_call(sid, mid, tokens=tok(300, 30), completed=2500)
    lab.app.set_running(sid, False)
    samples = [valid(meter.poll()) for _ in range(3)]
    assert [s["steps"] for s in samples] == [1, 1, 1]
    assert all(s["tokens"] == flat(300, 30) for s in samples)
    assert samples[0]["d_min_s"] == 1.5 and samples[0]["max_step_tokens"]["input"] == 300


def test_an_aborted_message_never_stalls_the_cursor(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    aborted = lab.app.start_call(sid, created=1000)
    meter.poll()
    # Interrupted before the provider's finish: completed, an error, no usage, the totals unmoved (P1(c), E10).
    lab.app.end_call(sid, aborted, tokens=None, error={"type": "aborted", "message": "interrupted"}, completed=1100)
    after = lab.call(sid, tok(700, 70))
    sample = valid(meter.poll())
    assert sample["steps"] == 2 and sample["tokens"] == flat(700, 70)
    assert parts(sample) == {"openai/gpt-6.1": flat(700, 70)}
    st = meter.state["sessions"][sid]["types"]["assistant"]
    assert st["last"] == after and not st["held"]
    assert sample["d_min_s"] == 1.0  # the aborted call billed nothing: it is not the shortest call


def test_an_incomplete_message_holds_the_cursor(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    slow = lab.app.start_call(sid, created=1000)
    fast = lab.app.start_call(sid, created=1100)  # two calls at once in one session (A2's k = 2)
    lab.app.end_call(sid, fast, tokens=tok(200, 20), completed=1500)
    lab.app.set_running(sid, True)
    held = valid(meter.poll())
    # The later call waits behind the earlier one, and its tokens are still in the figure through the totals.
    assert held["steps"] == 0 and held["tokens"] == flat(200, 20)
    assert meter.state["sessions"][sid]["types"]["assistant"]["held"]
    lab.app.end_call(sid, slow, tokens=tok(900, 90), completed=3000)
    lab.app.set_running(sid, False)
    done = valid(meter.poll())
    assert done["steps"] == 2 and done["tokens"] == flat(1100, 110)
    assert parts(done) == {"openai/gpt-6.1": flat(1100, 110)}


def test_a_compaction_call_is_partitioned_by_its_own_model(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(1000, 100))
    meter = lab.meter(sid)
    mid = lab.app.start_call(sid, kind="compaction", created=50_000)
    lab.app.end_call(sid, mid, tokens=tok(400, 40), parts=("totals",))  # its usage is recorded first (P1(e))
    lead = valid(meter.poll())
    assert lead["compactions"] == 0 and lead["tokens"] == flat(1400, 140)
    lab.app.end_call(sid, mid, tokens=tok(400, 40), parts=("message",), model=MINI)
    sample = valid(meter.poll())
    assert sample["compactions"] == 1 and sample["steps"] == 1
    assert sample["tokens"] == flat(1400, 140)
    assert parts(sample) == {"openai/gpt-6.1": flat(1000, 100), "openai/gpt-6.1-mini": flat(400, 40)}


@pytest.mark.parametrize("first", ["message", "totals"])
def test_a_one_poll_reconciliation_skew_is_not_an_integrity_breach(lab: Lab, first):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    mid = lab.app.start_call(sid, created=1000)
    lab.app.end_call(sid, mid, tokens=tok(500, 50), parts=(first,), completed=2000)
    skewed = valid(meter.poll())
    # Either half alone gives the same figure: messages above the totals are read skew, totals above the messages a
    # remainder on the pinned model; neither is a decrease.
    assert skewed["tokens"] == flat(500, 50)
    assert skewed["integrity_pending"] == 0 and skewed["integrity"] == 0
    lab.app.end_call(sid, mid, tokens=tok(500, 50), parts=("totals",) if first == "message" else ("message",),
                     completed=2000)
    whole = valid(meter.poll())
    assert whole["tokens"] == flat(500, 50) and whole["steps"] == 1
    assert whole["integrity_pending"] == 0 and whole["integrity"] == 0
    assert parts(whole) == parts(skewed) == {"openai/gpt-6.1": flat(500, 50)}


def test_the_figure_is_recomputed_never_accumulated(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    mid = lab.app.start_call(sid, created=1000)
    lab.app.end_call(sid, mid, tokens=tok(600, 60), parts=("totals",))
    figures = [meter.poll()["tokens"] for _ in range(3)]  # a call in progress, its usage on the totals
    lab.app.end_call(sid, mid, tokens=tok(600, 60), parts=("message",), completed=2000)
    figures += [valid(meter.poll())["tokens"] for _ in range(3)]  # then completed: counted once, never again
    assert figures == [flat(600, 60)] * 6
    assert meter.poll()["steps"] == 1


def test_a_token_regression_is_flagged_never_lowers_the_total(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(1000, 100))
    meter = lab.meter(sid)
    meter.poll()
    lab.app.set_totals(sid, tok(10, 1))  # the REST store is model-writable: the totals are lowered
    once = valid(meter.poll())
    assert (once["integrity_pending"], once["integrity"]) == (1, 0)
    twice = valid(meter.poll())
    assert (twice["integrity_pending"], twice["integrity"]) == (1, 1)
    thrice = valid(meter.poll())
    assert thrice["integrity"] == 1  # one breach per persisting decrease, not one per poll
    assert once["tokens"] == twice["tokens"] == thrice["tokens"] == flat(1000, 100)


def test_a_decrease_seen_once_then_gone_clears_pending(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(1000, 100))
    meter = lab.meter(sid)
    meter.poll()
    lab.app.set_totals(sid, tok(10, 1))
    assert meter.poll()["integrity_pending"] == 1
    lab.app.set_totals(sid, tok(1000, 100))
    cleared = valid(meter.poll())
    assert (cleared["integrity_pending"], cleared["integrity"]) == (0, 0)


def test_a_vanished_session_keeps_its_last_totals(lab: Lab):
    root = lab.app.add_session(model=GPT)
    child = lab.app.add_session(model=GPT, parent=root)
    lab.call(root, tok(1000, 100))
    lab.call(child, tok(400, 40))
    meter = lab.meter(root)
    before = meter.poll()
    lab.app.remove(child)  # session.deleted: the row and its messages go (P1(d))
    after = valid(meter.poll())
    assert after["tokens"] == before["tokens"] == flat(1400, 140)
    assert after["sessions"] == 2 and after["integrity"] == 0


def test_a_fork_and_a_revert_never_double_count_or_lower_the_figure(lab: Lab):
    sid = lab.app.add_session(model=GPT, created=1)
    first = lab.call(sid, tok(1000, 100))
    lab.call(sid, tok(500, 50))
    meter = lab.meter(sid)
    meter.poll()
    fork = lab.app.fork(sid, created=900_000)  # copies of both finished messages, zero totals
    lab.app.revert(sid, first)  # both messages deleted from the source; its totals stay
    forked = valid(meter.poll())
    assert forked["tokens"] == flat(1500, 150) and forked["steps"] == 2
    mid = lab.app.start_call(fork, created=1_000_000)
    lab.app.end_call(fork, mid, tokens=tok(70, 7), completed=1_001_000)
    grown = valid(meter.poll())
    assert grown["tokens"] == flat(1570, 157) and grown["steps"] == 3
    assert grown["integrity"] == grown["integrity_pending"] == 0


# ---------------------------------------------------------------------------------------------- bounds


def test_a_session_list_past_the_page_cap_is_truncated(lab: Lab, monkeypatch):
    monkeypatch.setattr(L, "SESSION_PAGE", 2)
    monkeypatch.setattr(L, "SESSION_PAGES", 2)
    for _ in range(4):  # exactly two full pages: the end cannot be confirmed within the cap
        sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(10, 1))
    sample = valid(lab.meter().poll())
    assert sample["truncated"] and sample["sessions"] == 4
    assert O.derive(as_record(sample), PRICES)[0] == {"unpriced": O.UNPRICED_INCOMPLETE}
    monkeypatch.setattr(L, "SESSION_PAGES", 3)
    fresh = lab.meter(state="fresh.json").poll()
    assert not fresh["truncated"] and fresh["sessions"] == 4


def test_a_257th_session_is_truncated(lab: Lab, monkeypatch):
    monkeypatch.setattr(L, "MAX_SESSIONS", 3)
    for _ in range(4):
        lab.app.add_session(model=GPT)
    sample = valid(lab.meter().poll())
    assert sample["truncated"] and sample["sessions"] == 3


def test_a_state_past_its_cap_is_truncated(lab: Lab, monkeypatch):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(10, 1))
    monkeypatch.setattr(L, "MAX_STATE_BYTES", 200)
    meter = lab.meter(sid)
    sample = valid(meter.poll())
    assert sample["truncated"]
    restarted = lab.meter(sid).poll()  # the state that was not kept is not trusted after a restart either
    assert restarted["truncated"]


def test_the_state_stays_bounded_after_ten_thousand_calls(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    meter = lab.meter(sid)
    msgs = lab.app.sessions[sid].messages
    for n in range(10_000):  # appended directly: the shape of 10,000 finished calls, written fast
        msgs.append({"id": f"msg_{n:08d}", "type": "assistant", "agent": "aew", "model": GPT, "content": [],
                     "time": {"created": 1000.0 * n, "completed": 1000.0 * n + 500}, "tokens": tok(10, 1),
                     "finish": "stop"})
        if n == 999:
            lab.app.set_totals(sid, tok(10_000, 1000))
            while meter.poll()["steps"] < 1000:
                pass
            small = (lab.root / "state.json").stat().st_size
    lab.app.set_totals(sid, tok(100_000, 10_000))
    polls = 0
    while (sample := meter.poll())["steps"] < 10_000:
        polls += 1
        assert polls < 100
    large = (lab.root / "state.json").stat().st_size
    assert sample["tokens"] == flat(100_000, 10_000) and not sample["truncated"]
    # The state holds cursors, counts and per-model sums, never message ids: its size does not grow with the calls.
    assert large <= small + 64 and large < 2048


@pytest.mark.parametrize("id_len, per_model", [(1, 10**6), (8, 10**9), (16, U.MAX_TOKENS // 8),
                                               (U.MAX_MODEL - 1, U.MAX_TOKENS // 8)])
def test_a_live_sample_stays_within_4_kib(tmp_path: Path, id_len: int, per_model: int):
    meter = L.Meter(None, source={"kind": "run", "id": "R" * L.MAX_ID}, version="v" * L.MAX_VERSION,
                    semantics_table={}, s_pot=U.MAX_COUNT, k_assumed=U.MAX_COUNT, state_path=tmp_path / "s.json",
                    main_session="ses_main")
    meter.server_version = "v" * L.MAX_VERSION
    big = U.MAX_TOKENS
    state = meter.state
    state.update({"steps": U.MAX_COUNT, "compactions": U.MAX_COUNT, "retries": U.MAX_COUNT, "integrity": U.MAX_COUNT,
                  "d_min_ms": 9_999_999_999.0, "max_step": dict.fromkeys(L.NAMED, big)})
    # The worst case: 8 models, every count at its maximum, every tracked session pending, and foreign tokens. R1's
    # part is bounded by normalize() (2 KiB with its copy fields: a partition that does not fit is dropped there,
    # which leaves a multi-model source unpriced), and the live fields are bounded here.
    for s_no in range(L.MAX_SESSIONS):
        s = L._empty_session()
        s["pending"] = True
        if s_no == 0:
            s["types"]["assistant"]["by_model"] = [
                ["p" * min(id_len, U.MAX_PROVIDER), "m" * id_len + str(i), "e" * min(id_len, U.MAX_EFFORT),
                 dict.fromkeys(L.CATEGORIES, per_model)] for i in range(U.MAX_EFFECTIVE)]
        state["sessions"][f"ses_{s_no:04d}"] = s
    sample = meter._build(state, "server_gone", U.MAX_COUNT)
    sample["observed_at"] = "2026-10-10T12:00:00.000Z"
    assert len(sample["effective"]) == U.MAX_EFFECTIVE and sample["integrity_pending"] == L.MAX_SESSIONS
    assert U.serialized_size(sample) <= L.MAX_SAMPLE_BYTES
    valid(sample)


def test_the_live_sample_holds_no_text_path_or_credential(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    mid = lab.app.start_call(sid, created=1)
    lab.app.end_call(sid, mid, tokens=None, completed=2,
                     error={"type": "provider.auth", "message": "Incorrect API key provided: sk-abc***wxyz"})
    text = json.dumps(valid(lab.meter(sid).poll()))
    assert "sk-" not in text and "Incorrect" not in text and str(lab.root) not in text


# ---------------------------------------------------------------------------------------------- the operations


def _operation(path: str) -> dict[str, Any]:
    if path in OPENAPI["paths"]:
        return OPENAPI["paths"][path]["get"]
    for template, item in OPENAPI["paths"].items():
        if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), path):
            return item["get"]
    raise AssertionError(f"{path} is no pinned operation")


def test_every_query_parameter_the_meter_sends_is_in_the_pinned_operation(lab: Lab, monkeypatch):
    monkeypatch.setattr(L, "SESSION_PAGE", 2)
    monkeypatch.setattr(L, "MESSAGE_PAGE", 2)
    root = lab.app.add_session(model=GPT)
    for _ in range(4):
        lab.app.add_session(model=GPT, parent=root)
    for _ in range(5):
        lab.call(root, tok(10, 1))
    meter = lab.meter(root)
    for _ in range(4):
        meter.poll()
    assert meter.poll()["steps"] == 5
    used = set()
    for _method, path, params in lab.client.requests:
        op = _operation(path)
        used.add(op["operationId"])
        allowed = {p["name"] for p in op.get("parameters", []) if p["in"] == "query"}
        assert set(params) <= allowed, (path, params)
        if op["operationId"] == "session.message.list":
            # The pinned description: pass the same type when following cursors; never combine a cursor with order.
            assert params["type"] in ("assistant", "compaction")
            assert not ("cursor" in params and "order" in params)
            assert int(params["limit"]) <= 200
    assert used == {"server.info", "session.list", "session.active", "session.message.list"}
    assert any("cursor" in p for _m, path, p in lab.client.requests if path == "/api/session")
    assert any("cursor" in p for _m, path, p in lab.client.requests if path.endswith("/message"))


def test_the_meter_resolves_semantics_from_the_adapter_table_and_server_version(tmp_path: Path):
    def semantics(*, server: str = "2.0.18", declared: str = "2.0.18", model: dict[str, Any] = GPT) -> str:
        lab = Lab(tmp_path / f"{server}-{declared}-{model['providerID']}", version=server)
        sid = lab.app.add_session(model=model)
        lab.call(sid, tok(10, 1), model=model)
        return lab.meter(sid, version=declared, pinned=model).poll()["token_semantics"]

    assert dict(OpenCodeAdapter.token_semantics["2.0.18"]) == {"openai": "disjoint"}
    assert semantics() == "disjoint"
    assert semantics(server="2.0.19", declared="2.0.19") == "unknown"   # a version the table does not name
    assert semantics(server="2.0.19") == "unknown"                       # the server is not the declared version
    assert semantics(model={"providerID": "anthropic", "id": "m", "variant": "default"}) == "unknown"


# ---------------------------------------------------------------------------------------------- lifecycle


def test_a_restarted_meter_carries_its_high_water_forward(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(1000, 100))
    first = lab.meter(sid)
    one = first.poll()
    lab.call(sid, tok(500, 50))
    second = lab.meter(sid)  # the same state file: a restart
    two = valid(second.poll())
    assert two["epoch"] != one["epoch"] and two["seq"] == 0
    assert two["epoch"].split(":", 1)[1] >= one["epoch"].split(":", 1)[1]  # ordered by (epoch start, seq)
    assert two["steps"] == 2 and two["tokens"] == flat(1500, 150)  # nothing counted twice
    lab.app.set_totals(sid, tok(10, 1))
    second.poll()
    assert second.poll()["integrity"] == 1  # the decrease is against the high-water mark carried forward


def test_a_run_meter_writes_its_prompt_state_and_seq_in_order(tmp_path: Path):
    live = tmp_path / "usage.live.json"
    meter = L.Meter(None, source={"kind": "run", "id": "R-0007"}, version="2.0.18",
                    semantics_table=OpenCodeAdapter.token_semantics, s_pot=1, state_path=tmp_path / "s.json",
                    live_path=live)
    meter.set_prompt_state("unsent")  # before the server exists (L2 writes this first)
    seq0 = valid(json.loads(live.read_text(encoding="utf-8")))
    assert (seq0["seq"], seq0["prompt_state"], seq0["state"]) == (0, "unsent", "live")
    meter.set_prompt_state("posting")
    meter.set_prompt_state("posted")
    assert json.loads(live.read_text(encoding="utf-8"))["seq"] == 2
    with pytest.raises(ValueError):
        meter.set_prompt_state("sent")
    unsent = L.Meter(None, source={"kind": "run", "id": "R-0008"}, version="2.0.18", semantics_table={}, s_pot=1,
                     state_path=tmp_path / "s2.json")
    assert valid(unsent.final())["state"] == "final"  # never launched: nothing could be spent


def test_a_server_gone_before_the_final_sample_keeps_the_last_figures(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    lab.call(sid, tok(300, 30))
    meter = lab.meter(sid)
    live = meter.poll()
    lab.client.down = True
    stale = meter.poll()
    assert stale is live and meter.errors == 1  # no sample is taken: its age shows the staleness
    gone = valid(meter.final())
    assert gone["state"] == "server_gone" and gone["tokens"] == flat(300, 30) and gone["seq"] == live["seq"] + 1
    assert gone["observed_at"] == live["observed_at"]


def test_the_final_sample_equals_the_run_record_for_a_run_without_foreign_sessions(lab: Lab):
    sid = lab.app.add_session(model=GPT)
    for n in range(3):
        lab.call(sid, tok(1000 + n, 100, 10, 400, 4), cost=0.01)
    meter = lab.meter(sid)
    meter.poll()
    final = valid(meter.final())
    # The run record as the adapter builds it from the same server (OpenCodeAdapter._usage_record's inputs).
    info = lab.client.get(f"/api/session/{sid}")["data"]
    assistant = [m for m in lab.app.sessions[sid].messages if m["type"] == "assistant"]
    effective = _effective([m["model"] for m in assistant])
    record = U.normalize({k: info.get(k) for k in ("outcome", "tokens", "cost")}, assistant, effective,
                         U.resolve_semantics(OpenCodeAdapter.token_semantics, "2.0.18", ["openai"]),
                         source="harness:opencode")
    assert final["state"] == "final" and final["foreign_tokens"] == flat()
    for field in ("tokens", "tokens_trust", "token_semantics", "provider_cost_usd", "provider_cost_trust", "steps"):
        assert final[field] == record[field], field
    assert O.derive(as_record(final), PRICES)[0] == O.derive({**record, "truncated": False}, PRICES)[0]


def test_a_malformed_reply_is_read_as_nothing_never_a_crash(tmp_path: Path):
    class Garbage:
        def get(self, path: str, params: Any = None, **_kw: Any) -> Any:
            return 7 if path == "/api/info" else {"data": 5, "cursor": "x"} if path == "/api/session" else ["x"]

    sample = valid(L.OpenCodeMeter(Garbage(), root_session="ses_root", version="2.0.18", s_pot=1,
                                   state_path=tmp_path / "s.json").poll())
    assert sample["sessions"] == 0 and sample["in_flight"] == 0 and sample["token_semantics"] == "unknown"


@pytest.mark.parametrize("order", ["message_first", "totals_first"])
def test_the_fake_v2_server_adds_each_model_step_to_its_session_totals(tmp_path: Path, order: str):
    lab = Lab(tmp_path, live_usage={"order": order})
    sid = lab.app.add_session(model=GPT)
    lab.app.assistant(lab.app.sessions[sid], 0, "stop")  # a scripted model step, as a launched run's would be
    sample = valid(lab.meter(sid).poll())
    assert sample["steps"] == 1 and sample["tokens"] == flat(100, 10)
    assert lab.app.sessions[sid].info["tokens"] == tok(100, 10)


# ---------------------------------------------------------------------------------------------- probe P1


class FixtureClient:
    """One poll's server state from a P1 case, served on the pinned operations."""

    def __init__(self) -> None:
        self.poll: dict[str, Any] = {}

    def get(self, path: str, params: dict[str, str] | None = None, **_kw: Any) -> Any:
        params = params or {}
        if path == "/api/info":
            return {"version": P1["version"], "pid": 1, "urls": [], "paths": {"tmp": "/tmp"}}
        if path == "/api/session":
            return {"data": self.poll["sessions"], "cursor": {}}
        if path == "/api/session/active":
            return {"data": {sid: {"type": "running"} for sid in self.poll["active"]}}
        sid = path.split("/")[3]
        items = [m for m in self.poll["messages"].get(sid, []) if m["type"] == params["type"]]
        if "cursor" in params:
            anchor, created = params["cursor"].split("|")
            ids = [m["id"] for m in items]
            items = items[ids.index(anchor) + 1:] if anchor in ids else [
                m for m in items if m["time"]["created"] > float(created)]
        page = items[:int(params["limit"])]
        return {"data": page,
                "cursor": {"next": f"{page[-1]['id']}|{page[-1]['time']['created']}"} if page else {}}


def test_live_usage_fixture_is_self_consistent_and_cites_the_pinned_commit():
    source = P1["source"]
    assert P1["version"] in TESTED_VERSIONS and source["tag"] == f"v{P1['version']}"
    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]) and re.fullmatch(r"[0-9a-f]{64}", source["binary_sha256"])
    ids = {e["id"] for e in source["evidence"]}
    assert len(ids) == len(source["evidence"])
    for e in source["evidence"]:
        assert e["file"] and len(e["identifier"]) >= 12 and e["says"]  # a searchable identifier, not a line number
        assert set(e["items"]) <= set("abcdef")
    # Every item (a) to (f) has a finding, verified or unverified, backed by cited evidence.
    by_item = {f["item"][0]: f for f in P1["findings"]}
    assert set(by_item) == set("abcdef")
    for f in P1["findings"]:
        assert f["status"] in ("verified", "unverified") and f["evidence"] and set(f["evidence"]) <= ids
    for case in P1["cases"]:
        assert case["evidence"] and set(case["evidence"]) <= ids, case["name"]


@pytest.mark.parametrize("case", P1["cases"], ids=[c["name"] for c in P1["cases"]])
def test_each_p1_case_holds_against_the_meter(case: dict[str, Any], tmp_path: Path):
    client = FixtureClient()
    meter = L.OpenCodeMeter(client, root_session=case["main"], version=P1["version"], s_pot=1,
                            state_path=tmp_path / "s.json", pinned_model=case["pinned"])
    for n, poll in enumerate(case["polls"]):
        client.poll = poll
        sample = valid(meter.poll())
        want = poll["expect"]
        assert sample["seq"] == n
        assert sample["tokens"] == {**want["tokens"], "unknown": 0}, n
        for field in ("steps", "compactions", "integrity_pending", "integrity", "d_min_s"):
            if field in want:
                assert sample[field] == want[field], (n, field)
        if "foreign_tokens" in want:
            assert sample["foreign_tokens"] == {**want["foreign_tokens"], "unknown": 0}
        if "partitions" in want:
            assert parts(sample) == {k: {**v, "unknown": 0} for k, v in want["partitions"].items()}, n

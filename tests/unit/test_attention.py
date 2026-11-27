"""The one attention module (A-44 BOY-02 to BOY-05; register E101), on every platform: one truthful state per approval
record with an injected clock and liveness, the source's coverage and its absence, the tier table's order, and that
neither it nor the dashboard reaches G3.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aew import g3client as C
from aew import g3records as R
from aew.engine import attention as AT

SRC = Path(C.__file__).resolve().parent
T0 = datetime(2026, 11, 27, 12, tzinfo=UTC)
LIFE = 300


def plant(directory: Path, ref: str = "g3:approval:one", *, project: str | None = "calc", **fields: Any) -> Path:
    """A record as the client writes it at T0, with ``fields`` changed after."""
    pending = {"approval_ref": ref, "state": "PENDING", "expires_at": R._iso(T0 + timedelta(seconds=LIFE)),
               "rendering": [{"template_id": "g3:action:SET_STEERING_MODE", "values": {},
                              "source": {"kind": "TEMPLATE"}}]}
    w = R.Writer(pending, project=project, directory=directory, now=lambda: T0)
    record = json.loads(w.path.read_text()) | fields
    w.path.write_text(json.dumps(record), encoding="utf-8")
    return w.path


def view(directory: Path, now: datetime, *, alive: bool = True, established: bool = True,
         platform: str = "linux") -> tuple[list[dict[str, Any]], AT.Source]:
    sock = directory.parent / "request.sock"
    sock.touch()
    return AT.approval_items(now, platform=platform, sock=str(sock), directory=directory, alive=lambda c: alive,
                             established=lambda: established)


def at(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


# One row per state (BOY-05.b, BOY-Q03): what the record holds, when it is read, the client's liveness; the class
CASES = [
    ("pending, live, read in time", {}, 10, True, "g3_approval.waiting", AT.BLOCKED_ON_YOU),
    ("client gone", {}, 10, False, "g3_approval.client_gone", AT.FYI),
    ("client exited without an outcome", {"exited_at": R._iso(at(5))}, 10, True, "g3_approval.client_gone", AT.FYI),
    ("approved and submitted", {"outcome": "approved_submitted"}, 10, False, "g3_approval.decided", AT.FYI),
    ("approved, not submitted", {"outcome": "approved_not_submitted"}, 10, True, "g3_approval.decided", AT.FYI),
    ("declined", {"outcome": "declined", "state": "DECLINED"}, 10, False, "g3_approval.decided", AT.FYI),
    ("expired", {"outcome": "expired", "state": "EXPIRED"}, 10, False, "g3_approval.decided", AT.FYI),
    ("a 404", {"state": "NOT_FOUND"}, 10, True, "g3_approval.not_found", AT.FYI),
    ("no answer", {"state": "NO_ANSWER"}, 10, True, "g3_approval.unknown", AT.ATTENTION),
    ("a stale read", {}, C.STALE_READ_S + 1, True, "g3_approval.unknown", AT.ATTENTION),
    ("past expiry, live", {}, LIFE + 1, True, "g3_approval.expired_unknown", AT.FYI),
    ("past expiry, gone: expiry decides first", {}, LIFE + 1, False, "g3_approval.expired_unknown", AT.FYI),
    ("never answered until expiry", {"outcome": "unanswered"}, 10, False, "g3_approval.expired_unknown", AT.FYI),
]


@pytest.mark.parametrize("name, fields, after, alive, source, tier", CASES, ids=[c[0] for c in CASES])
def test_each_record_shows_one_truthful_state_and_only_a_live_timely_pending_one_waits_on_you(
        tmp_path: Path, name: str, fields: dict[str, Any], after: float, alive: bool, source: str, tier: str) -> None:
    plant(tmp_path / "requests", **fields)
    [item], _ = view(tmp_path / "requests", at(after), alive=alive)
    assert (item["source"], item["tier"]) == (source, tier)
    assert item["since"] == R._iso(T0), "since is the record's start, never the read's time (BOY-01)"
    assert (item["state"] == "?") == (source == "g3_approval.unknown")
    assert item["title"].endswith("SET_STEERING_MODE") and item["key"] == "g3:approval:one"


def test_the_states_words_are_the_designs(tmp_path: Path) -> None:
    plant(tmp_path / "r")
    [gone], _ = view(tmp_path / "r", at(10), alive=False)
    assert "Nothing will submit this. Decline it in AEW approvals, or let it expire at 12:05:00 UTC." in gone["summary"]
    plant(tmp_path / "s", state="NO_ANSWER")
    [unknown], _ = view(tmp_path / "s", at(10))
    assert "G3 last answered at 2026-11-27T12:00:00Z" in unknown["summary"] and unknown["title"].startswith(
        "G3 approval (?)")
    [late], _ = view(tmp_path / "s", at(LIFE + 1))
    assert "Unknown whether decided. Nothing waits on it." in late["summary"]
    plant(tmp_path / "t", state="NOT_FOUND")
    [lost], _ = view(tmp_path / "t", at(10))
    assert "No longer known to G3. Request it again if still wanted." in lost["summary"]
    assert lost["where"] == "g3_request"


def test_the_stale_read_bound_moves_with_the_clients_constants(tmp_path: Path, monkeypatch) -> None:
    """BOY-14: the bound is the client's ``TIMEOUT_S`` plus two ``POLL_S``, read from ``aew.g3client``."""
    plant(tmp_path / "r")
    assert view(tmp_path / "r", at(C.STALE_READ_S))[0][0]["source"] == "g3_approval.waiting"
    monkeypatch.setattr(C, "STALE_READ_S", 5)
    assert view(tmp_path / "r", at(6))[0][0]["source"] == "g3_approval.unknown"


def test_a_waiting_item_shows_what_the_confirmer_lists_and_where_to_decide_and_nothing_decides(tmp_path: Path) -> None:
    """BOY-05.d, BOY-06, BOY-00: G3's raw action names, the ref and its expiry, the held line, the starter's role as
    the client's own claim, and AEW approvals as the place; no link, no control."""
    plant(tmp_path / "r")
    [item], source = view(tmp_path / "r", at(10))
    assert item["kind"] == "decision_required" and item["severity"] == "high"
    assert "g3:approval:one" in item["summary"] and "expires 12:05:00 UTC" in item["summary"]
    assert "The action stays held until you decide." in item["summary"]
    assert item["who"] == "started by the operator (the client's own claim)" and "in calc" in item["summary"]
    assert AT.WHERE[item["where"]].startswith("Decide in AEW approvals") and "://" not in json.dumps(item)
    assert source.line == AT.COVERAGE
    assert item["record"] == "host record: g3/requests/g3_approval_one.json"


def test_before_g3_is_established_each_item_says_approving_admits_nothing_yet(tmp_path: Path) -> None:
    plant(tmp_path / "r")
    assert AT.NOT_ESTABLISHED not in view(tmp_path / "r", at(10))[0][0]["summary"]
    assert view(tmp_path / "r", at(10), established=False)[0][0]["summary"].endswith(AT.NOT_ESTABLISHED)


def test_approvals_from_another_checkout_and_from_outside_any_project_both_show_with_their_labels(
        tmp_path: Path) -> None:
    plant(tmp_path / "r", "g3:approval:one", project="calc")
    plant(tmp_path / "r", "g3:approval:two", project="other")
    plant(tmp_path / "r", "g3:approval:three", project=None)
    items, _ = view(tmp_path / "r", at(10))
    assert sorted(i["subject"]["title"] for i in items) == ["calc", "other", "outside a project"]


def test_unsupported_unreadable_and_empty_each_show_as_themselves_and_never_as_zero_pending(tmp_path: Path) -> None:
    """BOY-04: Windows or no request.sock is "G3 is not on this host" and no record is read; an empty directory states
    its coverage; an unreadable record is an unknown item of its own."""
    plant(tmp_path / "r")
    items, source = view(tmp_path / "r", at(10), platform="win32")
    assert items == [] and (source.outcome, source.line) == ("unsupported", AT.NOT_ON_HOST)
    items, source = AT.approval_items(at(10), platform="linux", sock=str(tmp_path / "absent.sock"),
                                      directory=tmp_path / "r")
    assert items == [] and source.outcome == "unsupported"
    items, source = view(tmp_path / "empty", at(10))
    assert items == [] and (source.outcome, source.line) == ("available", AT.NOTHING_WAITING)
    (tmp_path / "r" / "torn.json").write_text("{", encoding="utf-8")
    (tmp_path / "r" / "extra.json").write_text(json.dumps(json.loads((tmp_path / "r" / "g3_approval_one.json")
                                                                     .read_text()) | {"pin": "1"}), encoding="utf-8")
    items, _ = view(tmp_path / "r", at(10))
    unknown = [i for i in items if i["source"] == "g3_approval.unknown"]
    assert len(unknown) == 2 and all(i["state"] == "?" and i["tier"] == AT.ATTENTION for i in unknown)
    assert source.read_at == R._iso(at(10))


def test_a_record_leaves_the_view_at_its_expiry_plus_g3_06s_window(tmp_path: Path) -> None:
    plant(tmp_path / "r", outcome="declined")
    assert view(tmp_path / "r", at(LIFE + R.window_s()))[0]
    assert view(tmp_path / "r", at(LIFE + R.window_s() + 1))[0] == []


def _engine_state() -> dict[str, Any]:
    work = {f"T-{n:04d}": {"state": "ESCALATED", "title": f"t{n}", "created_at": "2026-11-27T11:00:00Z"}
            for n in range(1, 8)}
    return {"work": work, "invocations": {}}


def test_a_waiting_approval_sits_first_owner_items_before_agent_items_and_fyi_counts_nothing(tmp_path: Path) -> None:
    """BOY-03.b, BOY-Q06: with seven existing items a waiting approval is first within the overview's six; an unknown
    approval comes in the attention tier; FYI items are last and in no count."""
    plant(tmp_path / "r", "g3:approval:a", outcome="declined")
    plant(tmp_path / "r", "g3:approval:b")
    plant(tmp_path / "r", "g3:approval:c", state="NO_ANSWER")
    project = {"id": "calc", "kind": "project", "title": "calc"}
    sock = tmp_path / "request.sock"
    sock.touch()

    def approvals(now: datetime, **kw: Any) -> Any:
        return AT.approval_items(now, platform="linux", sock=str(sock), directory=tmp_path / "r",
                                 alive=lambda c: True, **kw)

    out = AT.view(_engine_state(), project=project, contradictions=["x"], observe=lambda r: "running",
                  notifier=None, now=at(10), approvals=approvals)
    tiers = [i["tier"] for i in out["items"]]
    assert out["items"][0]["key"] == "g3:approval:b" and tiers[0] == AT.BLOCKED_ON_YOU
    assert tiers == sorted(tiers, key=AT.TIERS.index) and tiers[-1] == AT.FYI
    assert out["items"][1]["key"] == "g3:approval:c"  # unknown: attention, the approvals' place kept first
    assert len(AT.counted(out["items"])) == len(out["items"]) - 1
    agent = AT.item("work.blocker", "x", key="x", subject=project, title="x", record="r") | {"lane": AT.AGENT}
    assert AT.ordered([agent, *out["items"]])[-2] is agent  # after every owner item of its tier, before FYI
    assert {i["lane"] for i in out["items"]} == {AT.OWNER}


def test_every_source_class_sits_in_one_row_of_the_one_table() -> None:
    assert all(r.tier in AT.TIERS and r.lane in AT.LANES for r in AT.TABLE.values())
    assert set(AT.WORK_STATES.values()) <= set(AT.TABLE)
    assert {k for k in AT.TABLE if k.startswith("g3_approval.")} == set(AT._CODES)  # noqa: SLF001
    assert [k for k, r in AT.TABLE.items() if r.tier == AT.BLOCKED_ON_YOU] == ["g3_approval.waiting"]


def _imports(path: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out |= {n.module} | {f"{n.module}.{a.name}" for a in n.names}
    return out


def test_the_dashboard_imports_no_g3_client_and_the_attention_module_only_reads_the_clients_constants() -> None:
    """BOY-Q01, statically: no module of src/aew/dashboard imports the G3 client or G3's own package; the attention
    module and the record reader use none of the client's calls that reach the service."""
    for path in sorted((SRC / "dashboard").rglob("*.py")):
        found = _imports(path)
        assert not {m for m in found if m in ("aew.g3client", "aew.g3", "aew_g3") or m.startswith("aew_g3.")}, path
    reach = {"_g3", "_UnixHTTP", "request_approval", "await_decision", "consume", "probe", "submit"}
    for path in (SRC / "engine" / "attention.py", SRC / "g3records.py"):
        used = {n.attr for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ("C", "g3client")}
        assert not used & reach, (path, used & reach)


def test_status_renders_each_item_with_its_tier_time_left_and_where_and_each_sources_coverage(tmp_path: Path) -> None:
    plant(tmp_path / "r")
    items, source = view(tmp_path / "r", at(10))
    lines = AT.render({"items": items, "sources": [source.as_dict()]}, now=at(10))
    assert lines[0] == "Waiting on you (1 counted; FYI items are not)"
    assert lines[1] == "  [blocked-on-you] G3 approval: SET_STEERING_MODE, since 2026-11-27T12:00:00Z, 4m50s left"
    assert lines[3] == "    " + AT.WHERE["aew_approvals"]
    assert lines[-1].startswith("  g3_approvals: available, read 2026-11-27T12:00:10Z: Approvals that AEW started")

"""ADR-0011 P2c: the history surface and the integrity audit (implementation plan §3, §4 and R2; ADR invariants 11, 12
and 14).

A fresh Lead finds and reconstructs finished work by stable id without knowing storage paths, loads an exact record as
labelled reference context, and audits the history; Epic closeout requires the audit. Every test ends on the invariant
oracle.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from aewflow import (  # noqa: E402
    close_parent,
    complete_investigation,
    create_investigation,
    create_unit,
    dispatch,
    plan_unit,
    sample_project,
    submit_record,
)
from conftest import IS_WINDOWS, clean_env, run_aew  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402

from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402
from aew.engine.store import serialize_control  # noqa: E402
from aew.util import dump_yaml, load_yaml  # noqa: E402


def hot(p) -> dict:
    return load_control(p.root)


def finished_ticket(p, tmp_path, title: str = "Investigate calc.core", **kw) -> tuple[str, str, str]:
    """An investigation dispatched, submitted, ingested and accepted (so archived): its id, invocation and record."""
    wid = create_investigation(p, tmp_path, title=title, **kw)
    role, out = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    return wid, out["invocation"], rec


def audit(p, *extra: str) -> dict:
    return p.ok("history", "audit", *extra, "--token", p.token, "--expect-rev", str(p.rev()))


# ---------------------------------------------------------------------------------------------- show, list, links

def test_finished_work_is_found_by_stable_id_without_knowing_storage_paths(tmp_path):
    p = sample_project(tmp_path)
    wid, inv, rec = finished_ticket(p, tmp_path)
    shown = p.ok("history", "show", wid)
    assert (shown["kind"], shown["record"]["unit"]["state"], shown["current_parent"]) == ("unit", "DONE", None)
    assert shown["trust"]["source"] == "engine" and "not current evidence" in shown["trust"]["label"]
    assert all(t["verifier"] == "<redacted>" for t in shown["record"]["tokens"].values())  # never a secret's hash
    held = p.ok("history", "show", inv)  # a record inside the bundle, through the link its unit recorded
    assert (held["kind"], held["held_by"], held["record"]["status"]) == ("invocation", wid, "completed")
    credential = held["record"]["token_id"]
    shown = p.ok("history", "show", credential)
    assert shown["kind"] == "credential" and shown["record"]["verifier"] == "<redacted>"
    evidence = p.ok("history", "show", rec)
    assert evidence["kind"] == "evidence" and evidence["record"]["meta"]["kind"] == "discovery_record"
    assert evidence["trust"]["source"] == "model"  # model-authored text keeps its classification (invariant 14)
    assert_control_invariants(p)


def test_records_are_listed_by_kind_and_bounded_date_range(tmp_path):
    p = sample_project(tmp_path)
    first, _, _ = finished_ticket(p, tmp_path, title="First")
    second, _, _ = finished_ticket(p, tmp_path, title="Second")
    units = p.ok("history", "list", "--kind", "unit")
    assert [i["id"] for i in units["items"]] == [second, first] and units["truncated"] is False  # newest first
    assert units["items"][0]["title"] == "Second" and units["items"][0]["state"] == "DONE"
    one = p.ok("history", "list", "--kind", "unit", "--limit", "1")
    assert [i["id"] for i in one["items"]] == [second] and one["truncated"] is True
    assert p.ok("history", "list", "--until", "2000-01-01T00:00:00Z")["items"] == []
    assert len(p.ok("history", "list", "--since", "2000-01-01T00:00:00Z")["items"]) >= 2
    for bad in (("--kind", "ticket"), ("--limit", "0"), ("--since", "yesterday")):
        assert p.aew("history", "list", *bad).error["code"] == "USAGE"
    assert_control_invariants(p)


def test_links_are_followed_to_a_bounded_depth(tmp_path):
    p = sample_project(tmp_path)
    survey, inv, rec = finished_ticket(p, tmp_path)
    consumer = create_investigation(p, tmp_path, title="Consumer", extra=("--depends-on", f"{survey}:evidence"))
    complete_investigation(p, consumer)
    links = p.ok("history", "links", survey)
    assert {"from": consumer, "rel": "depends_on", "to": survey} in links["edges"]
    assert {"from": survey, "rel": "invocations", "to": inv} in links["edges"]
    assert links["nodes"][consumer] == "history" and links["nodes"][inv] == "other"
    deeper = p.ok("history", "links", survey, "--depth", "2")
    assert len(deeper["edges"]) > len(links["edges"])  # the consumer's own links, one step further
    assert p.aew("history", "links", survey, "--depth", "9").error["code"] == "USAGE"
    assert_control_invariants(p)


def test_an_unknown_or_current_id_is_not_historical(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    res = p.aew("history", "show", wid)
    assert res.error["code"] == "NOT_FOUND" and "current work" in res.error["message"]
    assert p.aew("history", "show", "T-9999").error["code"] == "NOT_FOUND"


def test_a_v1_project_has_no_cold_history(tmp_path):
    p = sample_project(tmp_path)
    control = p.root / ".aew/state/control.yaml"
    state = load_control(p.root)
    state["schema"] = "aew/control/v1"
    state.pop("cold")
    control.write_bytes(serialize_control(state))
    for args in (("show", "T-0001"), ("list",), ("audit",)):
        assert p.aew("history", *args).error["code"] == "USAGE"


# ---------------------------------------------------------------------------------------------- load (invariant 14)

def test_a_loaded_record_is_labelled_reference_context_pinned_per_invocation(tmp_path):
    p = sample_project(tmp_path)
    survey, _, _ = finished_ticket(p, tmp_path, title="Earlier survey")
    other, _, _ = finished_ticket(p, tmp_path, title="Another survey")
    wid = create_investigation(p, tmp_path, title="Follow-up")
    loaded = p.lead("history", "load", survey, "--into", wid, "--reason", "it surveyed the same module")["loaded"]
    assert (loaded["id"], loaded["kind"], loaded["source"]) == (survey, "unit", "engine")
    _, out = dispatch(p, wid)
    inv = hot(p)["invocations"][out["invocation"]]
    source = next(s for s in inv["pack"]["sources"] if s["name"] == f"history:{survey}")
    assert source == {"name": f"history:{survey}", "path": None, "sha256": loaded["sha256"], "trust": "engine",
                      "reference": True}  # recorded in the invocation's context provenance
    text = (p.root / ".aew" / inv["pack"]["path"]).read_text(encoding="utf-8")
    assert "## Historical reference context" in text and f"history:{survey}@{loaded['sha256'][:12]}" in text
    assert "not current evidence" in text and "Earlier survey" in text
    # A later load changes later packs only: this invocation's pack still regenerates exactly.
    p.lead("history", "load", other, "--into", wid, "--reason", "and this one")
    assert p.ok("context", "pack", out["invocation"])["matches_recorded"] is True
    assert_control_invariants(p)


def test_load_refuses_what_it_cannot_load(tmp_path):
    p = sample_project(tmp_path)
    survey, _, _ = finished_ticket(p, tmp_path)
    wid = create_investigation(p, tmp_path, title="Follow-up")
    p.lead("history", "load", survey, "--into", wid, "--reason", "context")
    rev = str(p.rev())
    cases = {
        (survey, wid): "USAGE",  # already loaded
        ("T-9999", wid): "NOT_FOUND",
        (survey, survey): "ILLEGAL_TRANSITION",  # finished work does not change
    }
    for (record, into), code in cases.items():
        res = p.aew("history", "load", record, "--into", into, "--reason", "x", "--token", p.token, "--expect-rev", rev)
        assert res.error["code"] == code, (record, into, res.stderr)
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- the audit (R2)

def test_an_advisory_audit_reports_and_records_nothing(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    rev = p.rev()
    report = p.ok("history", "audit")
    assert report["recorded"] is False and report["ok"] is True and report["entries"] >= 1
    assert p.rev() == rev and "verified" not in hot(p)["cold"]


def test_a_recorded_audit_leaves_no_backlog_and_the_next_one_is_incremental(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    first = audit(p)
    cold = hot(p)["cold"]
    assert first["recorded"] is True and first["mode"] == "incremental" and first["from"]["count"] == 0
    # R2: current == verified == the root this commit made, the audit's own entry included.
    assert cold["verified"]["count"] == cold["root"]["count"] and cold["verified"]["h"] == cold["root"]["head_h"]
    assert p.ok("status", "--json")["history_audit"]["unverified"]["entries"] == 0
    record = p.ok("history", "show", first["audit"])
    assert record["record"]["result"] == "pass" and record["record"]["target"] == first["through"]
    assert record["record"]["target"]["count"] == cold["root"]["count"] - 1  # it never claims to audit itself
    finished_ticket(p, tmp_path, title="Later")
    second = audit(p)
    assert second["from"]["count"] == cold["verified"]["count"]  # only what was appended since
    assert second["entries"] == second["through"]["count"] - cold["verified"]["count"]
    full = audit(p, "--full")
    assert full["mode"] == "full" and full["from"]["count"] == 0
    cold = hot(p)["cold"]
    assert cold["last_full"]["audit"] == full["audit"] == cold["verified"]["audit"]
    assert [i["id"] for i in p.ok("history", "list", "--kind", "audit")["items"]] == [full["audit"], second["audit"],
                                                                                      first["audit"]]
    assert_control_invariants(p)


def test_damage_fails_the_audit_records_a_finding_and_keeps_the_verified_root(tmp_path):
    p = sample_project(tmp_path)
    wid, _, _ = finished_ticket(p, tmp_path)
    audit(p)
    verified = hot(p)["cold"]["verified"]
    finished_ticket(p, tmp_path, title="Later")
    bundle = p.root / ".aew/work" / wid / "archive.yaml"
    bundle.write_text(bundle.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8", newline="\n")
    advisory = p.aew("history", "audit", "--full")
    assert advisory.returncode != 0 and advisory.error["code"] == "INTEGRITY_ERROR"
    res = p.aew("history", "audit", "--full", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and res.error["details"]["audit"]["recorded"] is True
    assert hot(p)["cold"]["verified"] == verified  # a failed audit never advances the verified root
    audit_id = res.error["details"]["audit"]["audit"]
    assert p.ok("history", "show", audit_id)["record"]["result"] == "fail"
    annotations = hot_annotations(p, wid)  # the damaged unit gets a finding; its bundle is not rewritten
    assert [(a["rel"], a["subject"]) for a in annotations] == [("audit_finding", wid)]


def hot_annotations(p, wid: str) -> list[dict]:
    """The annotations about ``wid``, from the index (its bundle is damaged, so `history show` refuses it)."""
    from aew.history.index import HistoryIndex

    index = HistoryIndex(p.root / ".aew")
    index.sync(hot(p)["cold"]["root"])
    return index.annotations(wid)


def test_an_audit_continues_incrementally_when_the_root_moves_before_it_records(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    gate = tmp_path / "hold"
    gate.write_text("", encoding="utf-8")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(
        [sys.executable, "-m", "aew", "-C", str(p.root), "history", "audit", "--token", p.token, "--expect-rev",
         str(p.rev())], env=clean_env({"AEW_PAUSE": f"history.audit_after_verify={gate}"}),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
        **kwargs)
    try:
        deadline = time.monotonic() + 120
        while not Path(f"{gate}.reached").exists():  # it verified the root it copied and is holding
            assert proc.poll() is None and time.monotonic() < deadline, proc.communicate()
            time.sleep(0.1)
        moved, _, _ = finished_ticket(p, tmp_path, title="Landed during the audit")  # the root moves
    finally:
        gate.unlink()
    out, err = proc.communicate(timeout=180)
    assert proc.returncode == 0, err
    cold = hot(p)["cold"]
    # It recorded only after verifying the new entries too: still no backlog.
    assert cold["verified"]["count"] == cold["root"]["count"] and cold["verified"]["h"] == cold["root"]["head_h"]
    record = p.ok("history", "show", cold["verified"]["audit"])["record"]
    assert record["target"]["count"] == cold["root"]["count"] - 1
    assert moved in {i["id"] for i in p.ok("history", "list", "--kind", "unit")["items"]}
    assert_control_invariants(p)


def test_a_crash_before_the_audit_is_recorded_leaves_the_history_as_it_was(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    before = hot(p)
    res = run_aew("-C", str(p.root), "history", "audit", "--token", p.token, "--expect-rev", str(p.rev()),
                  env={"AEW_FAULT": "history.audit_before_record"})
    assert res.returncode == CRASH_EXIT_CODE
    after = hot(p)
    assert after["revision"] == before["revision"] and after["cold"] == before["cold"]
    audits = p.root / ".aew/history/audits"
    assert not audits.exists() or not any(audits.glob("*.yaml"))
    assert audit(p)["recorded"] is True  # and the next attempt records it
    assert_control_invariants(p)


def test_recording_needs_the_lead_and_the_revision(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    assert p.aew("history", "audit", "--token", p.token).error["code"] == "USAGE"
    stale = p.aew("history", "audit", "--token", p.token, "--expect-rev", str(p.rev() - 1))
    assert stale.error["code"] == "STALE_REVISION"
    forged = p.aew("history", "audit", "--token", "aew1.T-0000.nope", "--expect-rev", str(p.rev()))
    assert forged.returncode != 0 and "verified" not in hot(p)["cold"]


# ---------------------------------------------------------------------------------------------- Epic closeout, status

def test_an_epic_closes_only_once_the_history_is_audited_through_the_current_root(tmp_path):
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    plan_unit(p, tmp_path, epic)
    story = create_unit(p, "story", "Objective", parent=epic)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    close_parent(p, story)
    from aewflow import parent_review, parent_verify

    p.lead("review", "ingest", epic, "--evidence", parent_review(p, epic))
    p.lead("verify", "ingest", epic, "--evidence", parent_verify(p, epic))
    actions = p.ok("status", "--json")["next_actions"]
    assert any(a.startswith(f"{epic}:") and "aew history audit" in a for a in actions)
    refused = p.aew("work", "close", epic, "--reason", "done", "--token", p.token, "--expect-rev", str(p.rev()))
    assert refused.error["code"] == "GATE_UNSATISFIED" and "history audit" in refused.error["message"]
    audit(p)
    p.lead("work", "close", epic, "--reason", "acceptance gates passed")
    assert epic not in hot(p)["work"]
    assert_control_invariants(p)


def test_status_reports_the_audit_backlog_against_policy_not_as_an_alarm(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    status = p.ok("status", "--json")
    block = status["history_audit"]
    assert block["unverified"]["entries"] >= 1 and block["verified"] is None and block["over_policy"] == []
    assert not any("history audit" in a for a in status["next_actions"])  # a fresh backlog is not an alarm
    gates = p.root / ".aew/policy/gates.yaml"
    policy = load_yaml(gates.read_text(encoding="utf-8"))
    policy["history_audit"] = {"max_unverified_entries": 0}
    gates.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    status = p.ok("status", "--json")
    assert status["history_audit"]["policy"]["max_unverified_entries"] == 0
    assert status["history_audit"]["over_policy"] and any("history audit is behind policy" in a
                                                          for a in status["next_actions"])
    audit(p)
    assert p.ok("status", "--json")["history_audit"]["over_policy"] == []
    assert_control_invariants(p)


def test_reindex_rebuilds_the_derived_index(tmp_path):
    p = sample_project(tmp_path)
    finished_ticket(p, tmp_path)
    out = p.ok("history", "reindex")
    assert out["mode"] == "rebuilt" and out["entries"] == hot(p)["cold"]["root"]["count"]
    os.remove(out["path"])  # losing it loses nothing
    assert p.ok("history", "list", "--kind", "unit")["items"]

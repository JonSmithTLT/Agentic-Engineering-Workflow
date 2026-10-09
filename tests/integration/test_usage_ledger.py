"""F25 slice 2a (the cost and usage ledger design v0.2 R5, §7): a run's usage reaches control state in the engine's
next Lead transaction on its invocation, exactly once, and travels with the unit into the cold state.

Each test drives real runs through the fake harness (a real supervisor and adapter, a scripted agent), whose script
can declare the session totals the adapter reports, as the OpenCode adapter reads them from OpenCode."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import SUBTRACT_PATCH, create_planned_ticket, review, sample_project  # noqa: E402
from fake_harness import IMPL_REPORT, SCRIPTS_ENV, HarnessLab  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402

from aew.engine import outbox  # noqa: E402
from aew.engine import usage_ops as O  # noqa: E402
from aew.harness import contract as K  # noqa: E402
from aew.harness import runlog  # noqa: E402

IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
TOKENS = {"input": 1000, "output": 400, "reasoning": 0, "cache": {"read": 0, "write": 0}}
TABLE = ("schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: \"recorded for the tests\"\n"
         "prices:\n  fakeprov/fake-model: {input: 2.0, output: 8.0, cache_read: 0.5, cache_write: 2.0}\n")


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def script(lab: HarnessLab, name: str, steps: list[dict[str, Any]], usage: dict[str, Any] | None = None) -> None:
    spec: Any = {"steps": steps, "usage": usage} if usage is not None else steps
    (Path(lab.env[SCRIPTS_ENV]) / f"{name}.json").write_text(json.dumps(spec), encoding="utf-8")


def runs(lab: HarnessLab, inv: str) -> list[dict[str, Any]]:
    return load_control(lab.root)["invocations"][inv].get("runs") or []


def adopt_prices(lab: HarnessLab) -> None:
    """The operator records a price table and adopts it, as `aew manifest adopt` does for any policy edit."""
    import yaml

    (lab.aew_root / "policy" / "pricing.yaml").write_text(TABLE, encoding="utf-8", newline="\n")
    manifest = lab.aew_root / "project.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["policy"]["pricing"] = "policy/pricing.yaml"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    lab.project.adopt_policy()


def launched(lab: HarnessLab, tmp_path: Path, steps: list[dict[str, Any]], usage: dict[str, Any] | None = None,
             **kw: Any) -> tuple[str, str, str]:
    """A planned Ticket assigned with --launch; its run 1 performs ``steps`` and reports ``usage``."""
    wid = create_planned_ticket(lab.project, tmp_path, **kw)
    script(lab, "default", steps, usage)
    out = lab.lead("work", "assign", wid, "--launch")
    return wid, out["invocation"], out["launch"]["run"]


def test_accepting_a_report_copies_the_run_usage_once(lab, tmp_path):
    """R5: the transaction that accepts the implementation report copies the ended run's usage into control state,
    with the price table's digest; a later transaction never rewrites it."""
    adopt_prices(lab)
    wid, inv, run = launched(lab, tmp_path, IMPLEMENT, {"tokens": TOKENS, "cost": 0.004})
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    assert lab.wait(run)["status"] == K.ENDED_WITH_EVIDENCE
    assert "usage" not in runs(lab, inv)[0]  # provisional until a Lead transaction on the invocation (R6)
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    usage = runs(lab, inv)[0]["usage"]
    assert (usage["run"], usage["status"], usage["tokens_trust"]) == (run, K.ENDED_WITH_EVIDENCE, "harness_reported")
    assert usage["tokens"]["input"] == 1000 and usage["provider_cost_usd"] == 0.004
    assert usage["requested"]["model"] == "fake-model" and usage["pricing_sha256"] is not None
    assert (lab.aew_root / "pricing" / f"{usage['pricing_sha256']}.yaml").read_text(encoding="utf-8") == TABLE
    figure, _ = O.derive(usage, O.Prices(TABLE.encode(), source="t"))
    assert figure == {"usd": __import__("decimal").Decimal("0.0052")}  # 1000 x $2/M + 400 x $8/M
    review(lab.project, wid)
    assert runs(lab, inv)[0]["usage"] == usage  # never rewritten
    assert_control_invariants(lab.project)


def test_a_relaunch_copies_the_ended_run_and_leaves_the_new_one_provisional(lab, tmp_path):
    """R5: `harness launch` adds a run and copies the earlier run's usage in the same commit. A run that reported no
    usage is copied as absent, never omitted."""
    wid, inv, run1 = launched(lab, tmp_path, [], {"tokens": TOKENS})
    lab.wait(run1)  # ended without evidence
    script(lab, "default", [{"do": "wait_file", "path": str(tmp_path / "never"), "timeout": 300}])  # no usage
    run2 = lab.lead("harness", "launch", inv)["run"]
    first, second = runs(lab, inv)
    assert first["usage"]["run"] == run1 and first["usage"]["tokens"]["input"] == 1000
    assert first["usage"]["pricing_sha256"] is None  # the project has no price table: no derived cost, ever
    assert "usage" not in second and second["run"] == run2  # running: provisional, never fixed as absent
    lab.project.lead("invoke", "cancel", inv, "--reason", "stop the test run")
    assert "usage" not in runs(lab, inv)[1]  # still running while the cancel commits
    lab.until(lambda: runlog.observed_status(runlog.run_dir(lab.aew_root, run2))[0] in K.TERMINAL,
              what="the cancelled run to end")
    lab.project.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "abandoned")
    archived = O.Reader(lab.aew_root, None).invocation(inv, archived_invocation(lab, wid, inv))
    assert [r["usage"]["tokens_trust"] for r in archived["rows"]] == ["harness_reported", "absent"]
    assert archived["totals"]["recorded"] == 2  # archival copied the last run: the bundle is complete
    assert_control_invariants(lab.project)


def archived_invocation(lab: HarnessLab, wid: str, inv: str) -> dict[str, Any]:
    from aew.util import load_yaml

    bundle = load_yaml((lab.aew_root / "work" / wid / "archive.yaml").read_text(encoding="utf-8"), source="bundle")
    return bundle["invocations"][inv]


def test_a_usage_copy_derives_no_event(lab, tmp_path):
    """R5, ADR-0012 D2: `run.added` compares run ids and `invocation.status` the status field, so a commit whose only
    effect on an invocation is a usage copy publishes no event, and a wait-any consumer never reads one as a run."""
    import copy

    wid, inv, run = launched(lab, tmp_path, IMPLEMENT, {"tokens": TOKENS})
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.wait(run)
    before = load_control(lab.root)
    after = copy.deepcopy(before)
    assert O.copy_run_usage(after, inv, lab.aew_root, pricing=None) == [run]
    assert outbox.derive_events(before, after, after) == []


def test_a_usage_that_is_not_a_bounded_record_of_its_own_run_is_refused(lab, tmp_path):
    """§7: the control schema refuses a usage that is not a run-usage record (a ninth effective entry included), and
    the invariants refuse one that names another run or outgrows 2 KiB."""
    import copy

    from invariants import usage_violations

    from aew.errors import ValidationFailed
    from aew.schemas import validate

    wid, inv, run = launched(lab, tmp_path, IMPLEMENT, {"tokens": TOKENS})
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.wait(run)
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    state = load_control(lab.root)
    good = state["invocations"][inv]["runs"][0]["usage"]
    assert usage_violations(state) == []
    nine = copy.deepcopy(state)
    nine["invocations"][inv]["runs"][0]["usage"]["effective"] = [
        {"provider": "p", "model": f"m{i}", "effort": None} for i in range(9)]
    with pytest.raises(ValidationFailed):
        validate("control", nine, source="test")
    other = copy.deepcopy(state)
    other["invocations"][inv]["runs"][0]["usage"] = {**good, "run": "R-INV-0009-1"}
    assert usage_violations(other) == [f"{inv} run {run} holds the usage of R-INV-0009-1"]
    big = copy.deepcopy(state)
    big["invocations"][inv]["runs"][0]["usage"]["source"] = "harness:" + "é" * 20  # valid, and over 2 KiB with...
    big["invocations"][inv]["runs"][0]["usage"]["effective"] = [
        {"provider": "é" * 24, "model": "é" * 47 + str(i), "effort": "é" * 12} for i in range(8)]
    assert any("over 2 KiB" in p for p in usage_violations(big)), usage_violations(big)


def test_prices_are_operational_policy_adopted_like_any_other(lab, tmp_path):
    """The price table is a manifest policy file whose every field is operational (classes.CLASSIFIED): a price
    edit moves the operational digest only, so it never makes a dispatch decision stale; a malformed table is refused
    at adoption, never pinned."""
    from aew.engine.api import Engine
    from aew.errors import AEWError

    adopt_prices(lab)
    before = Engine.discover(lab.root)._k.policy_digests()
    (lab.aew_root / "policy" / "pricing.yaml").write_text(TABLE.replace("2.0, output", "3.0, output"),
                                                          encoding="utf-8", newline="\n")
    lab.project.adopt_policy()
    after = Engine.discover(lab.root)._k.policy_digests()
    assert after["legality_digest"] == before["legality_digest"]
    assert after["operational_digest"] != before["operational_digest"]
    (lab.aew_root / "policy" / "pricing.yaml").write_text(TABLE + "  fakeprov/x: {input: 1, semantics: 2}\n",
                                                          encoding="utf-8", newline="\n")
    with pytest.raises(AEWError):
        lab.project.adopt_policy()



def archived_usage(lab: HarnessLab, wid: str, inv: str) -> list[dict[str, Any]]:
    from aew.schemas import validate

    usages = [r["usage"] for r in archived_invocation(lab, wid, inv)["runs"]]
    for usage in usages:  # the bundle is never seen by commit validation: each record is checked here
        validate("run-usage", usage, source="bundle")
    return usages


@pytest.mark.parametrize("record, beat, status", [
    ([], False, K.UNCONFIRMED),  # not an object: no record at all
    ({"status": K.CRASHED, "model_check": "x", "result": ["x"]}, False, K.CRASHED),  # fields of the wrong shape
    ({"status": "bogus"}, True, K.LOST),  # a status the record schema does not know, with a fresh heartbeat
    ({"status": ["x"]}, True, K.STARTING),  # a status that is not a string: no status, so possibly live (observers)
    ('{"status": "crashed", "result": ' + "[" * 200_000 + "]" * 200_000 + "}", False, K.UNCONFIRMED),  # too deep
    ({"status": K.CRASHED, "result": "NAN-USAGE"}, False, K.CRASHED),  # a usage with a NaN in it (#137 re-review)
], ids=["not-an-object", "wrong-shapes", "unknown-status", "status-not-a-string", "nested-too-deep", "nan"])
def test_a_malformed_run_record_never_blocks_a_cancel_or_archival(lab, tmp_path, record, beat, status):
    """#137 review, F1 and F2: the run record is written where the run's own user can write. Whatever it holds, a
    cancel and the unit's archival still commit, and the copy they archive is a valid run-usage record."""
    wid, inv, run = launched(lab, tmp_path, [], {"tokens": TOKENS})
    lab.wait(run)
    directory = runlog.run_dir(lab.aew_root, run)
    if isinstance(record, dict) and record.get("result") == "NAN-USAGE":  # the run's own record, with wall_s NaN
        usage = runlog.read_record(directory)["result"]["usage_record"]  # type: ignore[index]
        record = {**record, "result": {"usage_record": {**usage, "wall_s": float("nan")}}}
    text = record if isinstance(record, str) else json.dumps(record)
    (directory / "run.json").write_text(text, encoding="utf-8")
    if beat:
        runlog.beat(directory)
    lab.project.lead("invoke", "cancel", inv, "--reason", "stop the test run")
    lab.project.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "abandoned")
    [usage] = archived_usage(lab, wid, inv)
    assert (usage["run"], usage["status"], usage["tokens_trust"], usage["model_check"]) == (
        run, status, "absent", "unreported")
    assert_control_invariants(lab.project)


def test_a_run_still_live_at_archival_is_recorded_with_its_observed_status_and_absent_usage(lab, tmp_path):
    """R5: archival copies every run that still lacks a usage. A Ticket cancelled while its agent works archives the
    run as it was observed then, with absent usage; what the run reports later stays in local/ and the bundle is never
    rewritten (#137 review, F3)."""
    wid, inv, run = launched(lab, tmp_path, [{"do": "wait_file", "path": str(tmp_path / "never"), "timeout": 300}],
                             {"tokens": TOKENS})
    lab.until(lambda: runlog.observed_status(runlog.run_dir(lab.aew_root, run))[0] == K.RUNNING,
              what="the run to start")
    lab.project.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "abandoned")
    [usage] = archived_usage(lab, wid, inv)
    assert (usage["status"], usage["tokens_trust"]) == (K.RUNNING, "absent")
    lab.until(lambda: runlog.observed_status(runlog.run_dir(lab.aew_root, run))[0] in K.TERMINAL,
              what="the cancelled run to end")
    assert archived_usage(lab, wid, inv) == [usage]
    assert_control_invariants(lab.project)


def test_a_damaged_price_snapshot_never_blocks_a_copy(lab, tmp_path):
    """#137 review, F4: a snapshot whose bytes no longer match its digest is damage for `aew doctor` to report. The
    transaction that copies a run's usage still commits, with the usage facts and no table (`pricing_sha256: null`)."""
    adopt_prices(lab)
    wid, inv, run = launched(lab, tmp_path, IMPLEMENT, {"tokens": TOKENS})
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.wait(run)
    snapshot = O.snapshot_path(lab.aew_root, O.Prices(TABLE.encode(), source="t").sha256)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("damaged\n", encoding="utf-8")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    usage = runs(lab, inv)[0]["usage"]
    assert (usage["tokens"]["input"], usage["pricing_sha256"]) == (1000, None)
    assert snapshot.read_text(encoding="utf-8") == "damaged\n"  # never repaired by overwriting
    assert_control_invariants(lab.project)

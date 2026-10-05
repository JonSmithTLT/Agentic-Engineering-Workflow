"""The evaluation instrument's first slice (register F19; the evaluation component design v0.2, §3, §4, §8 and §9).

The slice proves, against the M3 corpus, the invariants the design asks for before any runner is generalized: a
preregistration is frozen with its schedule and a canonical hash, and refuses changed inputs; an attempt is registered
durably before it runs and counted once; a result is immutable; a runner that dies leaves a visible attempt; every
historical M3 record maps to aew/eval-run/v1 deterministically, unchanged.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import compat, prereg  # noqa: E402
from aew_eval.canonical import sha256_of, tree_sha256  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

M3 = ROOT / "eval/m3/dogfood/results.jsonl"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
H = "a" * 64


def plan(**over) -> dict:
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": "Does AEW reach DONE more often than raw?",
        "arms": [{"id": "aew", "kind": "aew", "description": "headless Lead", "config": {"routing": "default"}},
                 {"id": "raw", "kind": "raw", "description": "harness alone", "config": {}}],
        "cases": [{"id": "T1", "family": "m3", "sha256": H, "hidden_sha256": "b" * 64, "control_of": None},
                  {"id": "T1C", "family": "m3", "sha256": "c" * 64, "hidden_sha256": None, "control_of": "T1"}],
        "profiles": {"roles": {"lead": "provider/model#medium"}, "budget_usd": 5.0},
        "runs_per_cell": 2, "assignment": {"method": "randomized_blocked", "seed": 7},
        "primary_measure": "reached_done", "metrics": [{"name": "done_rate", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": ["provider outage"], "counted_failures": ["timeout"],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["runner_lost", "environment_blocked"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "all cells once", "held_out": ["T1"],
        "scoring": {"hidden_channel": "aew-private/eval/demo/", "who_scores": "automated", "blinding": "arm_hidden",
                    "adjudication_policy": "operator on disagreement"},
        "exposure_policy": "an exposed case leaves the held-out set", "amendment_policy": "a change is a new id",
    }
    record.update(over)
    return record


def frozen(**over) -> dict:
    return prereg.freeze(plan(**over), by="tester")


def result(f: dict, line: dict, *, validity: str = "valid") -> dict:
    case = next(c for c in f["cases"] if c["id"] == line["case"])
    arm = next(a for a in f["arms"] if a["id"] == line["arm"])
    return {"schema": "aew/eval-run/v1", "experiment": f["experiment"], "preregistration_sha256": f["canonical_sha256"],
            "run_id": line["run_id"],
            "case": {"id": line["case"], "sha256": case["sha256"], "hidden_sha256": case["hidden_sha256"]},
            "arm": {"id": line["arm"], "kind": arm["kind"], "config_sha256": sha256_of(arm["config"])},
            "profile": {"requested": line["requested_profile"], "observed": [], "mismatch": False},
            "aew": {}, "harness": {}, "environment": {},
            "assignment": {**line["assignment"], "randomization_seed": f["assignment"]["seed"]},
            "validity": {"status": validity, "reason_code": None}, "started_at": None, "ended_at": None,
            "wall_s": None, "limits": {}, "outcome": {}, "aew_facts": {}, "cost": {}, "notes": None}


# ------------------------------------------------------------------------------------------------ preregistration

def test_freezing_materializes_the_schedule_from_the_seed_and_hashes_everything():
    f = frozen()
    order = f["assignment"]["order"]
    assert len(order) == 2 * 2 * 2 and [o["order_index"] for o in order] == list(range(8))
    assert {o["cell"] for o in order} == {f"{c}/{a}/{r}" for c in ("T1", "T1C") for a in ("aew", "raw") for r in (1, 2)}
    assert prereg.verify(f) == f["canonical_sha256"] == prereg.digest(f)
    assert frozen()["assignment"]["order"] == order  # the seed alone decides the order
    assert frozen(assignment={"method": "randomized_blocked", "seed": 8})["assignment"]["order"] != order


@pytest.mark.parametrize("method", ["fixed", "counterbalanced", "randomized_blocked"])
def test_every_method_runs_each_cell_once_and_keeps_blocks_together(method):
    order = frozen(assignment={"method": method, "seed": 3})["assignment"]["order"]
    assert sorted(o["cell"] for o in order) == sorted({o["cell"] for o in order})
    for i in range(0, len(order), 2):  # a block is one case and repetition, every arm once
        block = order[i:i + 2]
        assert len({(o["case"], o["repetition"]) for o in block}) == 1 and {o["arm"] for o in block} == {"aew", "raw"}
    if method == "counterbalanced":
        assert [o["arm"] for o in order[:4]] == ["aew", "raw", "raw", "aew"]


def test_the_hash_ignores_key_order_and_survives_a_yaml_round_trip(tmp_path):
    f = frozen()
    path = tmp_path / "prereg.yaml"
    prereg.dump(f, path)
    again = prereg.load(path)
    assert prereg.verify(again) == f["canonical_sha256"]
    assert sha256_of(dict(reversed(list(f.items())))) == sha256_of(f)


def test_a_frozen_record_is_never_edited_or_refrozen():
    f = frozen()
    edited = copy.deepcopy(f)
    edited["stopping_rule"] = "stop when it looks good"
    with pytest.raises(Invalid, match="edited after it was frozen"):
        prereg.verify(edited)
    with pytest.raises(Invalid, match="already frozen"):
        prereg.freeze(f, by="tester")
    reordered = copy.deepcopy(f)
    reordered["assignment"]["order"].reverse()
    reordered["canonical_sha256"] = prereg.digest(reordered)
    with pytest.raises(Invalid, match="not the schedule"):
        prereg.verify(reordered)
    with pytest.raises(Invalid, match="materialized by freezing"):
        prereg.freeze(plan(assignment={"method": "fixed", "seed": 1, "order": []}), by="tester")


@pytest.mark.parametrize("bad, match", [
    ({"held_out": ["T9"]}, "not cases"),
    ({"cases": [{"id": "T1", "family": "m3", "sha256": H, "hidden_sha256": None, "control_of": "T7"}]}, "not a case"),
    ({"arms": [{"id": "aew", "kind": "aew", "description": "", "config": {}}] * 2}, "duplicate arm"),
    ({"assignment": {"method": "by-hand", "seed": 1}}, "eval-prereg"),
])
def test_an_inconsistent_preregistration_cannot_freeze(bad, match):
    with pytest.raises(Invalid, match=match):
        prereg.freeze(plan(**bad), by="tester")


def test_a_run_whose_material_inputs_changed_is_refused():
    f = frozen()
    ok = {"case": "T1", "arm": "aew", "case_sha256": H, "hidden_sha256": "b" * 64,
          "roles": {"lead": "provider/model#medium"}, "arm_config": {"routing": "default"}}
    prereg.require_inputs(f, **ok)
    for change, match in ((("case_sha256", "d" * 64), "fixture of T1 changed"),
                          (("hidden_sha256", None), "oracle commitment of T1 changed"),
                          (("roles", {"lead": "provider/other#high"}), "role profiles changed"),
                          (("arm_config", {"routing": "cheap"}), "configuration of arm aew changed"),
                          (("case", "T9"), "not a cell")):
        with pytest.raises(prereg.Mismatch, match=match):
            prereg.require_inputs(f, **{**ok, change[0]: change[1]})


def test_the_cli_freezes_and_verifies(tmp_path):
    path = tmp_path / "plan.yaml"
    prereg.dump(plan(), path)
    assert prereg.main(["freeze", str(path), "--by", "tester"]) == 0
    assert prereg.main(["verify", str(path)]) == 0
    assert prereg.main(["freeze", str(path), "--by", "tester"]) == 1  # already frozen


def test_a_tree_hash_covers_paths_and_bytes(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a/x.txt").write_bytes(b"1")
    first = tree_sha256(tmp_path)
    (tmp_path / "a/x.txt").write_bytes(b"2")
    assert tree_sha256(tmp_path) != first
    (tmp_path / "a/x.txt").write_bytes(b"1")
    (tmp_path / "a/x.txt").rename(tmp_path / "a/y.txt")
    assert tree_sha256(tmp_path) != first


# ------------------------------------------------------------------------------------------------ the attempt ledger

def test_an_attempt_is_registered_durably_before_it_runs_and_counted_once(tmp_path):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    cell = f["assignment"]["order"][0]["cell"]
    line = ledger.register(run_id="demo/r1", cell=cell, requested_profile={"lead": "provider/model#medium"})
    on_disk = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8"))
    assert on_disk == line and on_disk["preregistration_sha256"] == f["canonical_sha256"]
    assert ledger.status() == {"demo/r1": "runner_lost"}  # registered, not finalized: visible, never vanished
    with pytest.raises(Invalid, match="already registered"):
        ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][1]["cell"], requested_profile={})
    with pytest.raises(Invalid, match="already has attempt"):
        ledger.register(run_id="demo/r2", cell=cell, requested_profile={})
    with pytest.raises(Invalid, match="not a cell"):
        ledger.register(run_id="demo/r3", cell="T9/aew/1", requested_profile={})
    with pytest.raises(Invalid, match="must be demo/"):
        ledger.register(run_id="other/r4", cell=f["assignment"]["order"][1]["cell"], requested_profile={})


def test_a_result_is_finalized_once_and_immutably(tmp_path):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    line = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"], requested_profile={})
    rec = result(f, line)
    digest = ledger.finalize(rec)
    assert ledger.status() == {"demo/r1": "valid"} and ledger.verify() == []
    with pytest.raises(Invalid, match="already finalized"):
        ledger.finalize(rec)
    path = tmp_path / "runs/r1.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"valid"', '"invalid_measurement"'), encoding="utf-8")
    assert ledger.verify() == ["demo/r1: r1.json changed after it was finalized"]
    assert len(digest) == 64


def test_a_result_must_match_its_registration(tmp_path):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    line = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"], requested_profile={})
    with pytest.raises(Invalid, match="never registered"):
        ledger.finalize({**result(f, line), "run_id": "demo/r9"})
    wrong = result(f, line)
    wrong["arm"]["id"] = "raw" if line["arm"] == "aew" else "aew"
    with pytest.raises(Invalid, match="does not match its registration"):
        ledger.finalize(wrong)
    with pytest.raises(Invalid, match="eval-run"):
        ledger.finalize({**result(f, line), "validity": None})  # only a mapped historical record may lack one


@pytest.mark.parametrize("field, mangle", [
    ("assignment order", lambda r: r["assignment"].update(order_index=999)),
    ("randomization seed", lambda r: r["assignment"].update(randomization_seed=999)),
    ("requested profile", lambda r: r["profile"].update(requested={"lead": "other/model#high"})),
    ("case fixture hash", lambda r: r["case"].update(sha256="d" * 64)),
    ("case oracle hash", lambda r: r["case"].update(hidden_sha256="e" * 64)),
    ("arm configuration hash", lambda r: r["arm"].update(config_sha256="f" * 64)),
])
def test_a_result_contradicting_its_pinned_metadata_is_refused(tmp_path, field, mangle):
    """Independent review of #75: beyond the ids and cell, a result must agree with its registration (order,
    requested profile) and the frozen experiment (seed, case and oracle hashes, arm configuration)."""
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    line = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"],
                           requested_profile={"lead": "provider/model#medium"})
    wrong = result(f, line)
    mangle(wrong)
    with pytest.raises(Invalid, match=field):
        ledger.finalize(wrong)
    observed = result(f, line)
    observed["profile"].update(observed=[{"lead": "provider/model-2026#medium"}], mismatch=True)
    ledger.finalize(observed)  # what was observed is free to differ from what was requested
    assert ledger.verify() == []


def test_concurrent_registrations_of_one_cell_admit_exactly_one(tmp_path):
    """Independent review of #75: the read-check-append is one locked transaction, across processes."""
    f = frozen()
    path = tmp_path / "prereg.yaml"
    prereg.dump(f, path)
    cell = f["assignment"]["order"][0]["cell"]
    script = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(ROOT / 'eval')!r})\n"
        "from pathlib import Path\n"
        "from aew_eval import prereg\n"
        "from aew_eval.ledger import AttemptLedger\n"
        "from aew_eval.schemas import Invalid\n"
        f"f = prereg.load(Path({str(path)!r}))\n"
        f"while not Path({str(tmp_path / 'go')!r}).exists():\n"
        "    time.sleep(0.001)\n"
        "try:\n"
        f"    AttemptLedger(Path({str(tmp_path / 'exp')!r}), f).register(run_id='demo/' + sys.argv[1], "
        f"cell={cell!r}, requested_profile={{}})\n"
        "    print('registered')\n"
        "except Invalid:\n"
        "    print('refused')\n")
    procs = [subprocess.Popen([sys.executable, "-c", script, f"r{i}"], stdout=subprocess.PIPE, text=True,
                              creationflags=NO_WINDOW) for i in range(6)]
    time.sleep(1.0)
    (tmp_path / "go").write_text("", encoding="utf-8")
    outcomes = sorted(p.communicate(timeout=120)[0].strip() for p in procs)
    assert outcomes == ["refused"] * 5 + ["registered"], outcomes
    assert len(AttemptLedger(tmp_path / "exp", f).attempts()) == 1


def test_an_inconsistent_ledger_is_refused_on_reading(tmp_path):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    line = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"], requested_profile={})
    text = (tmp_path / "attempts.jsonl").read_text(encoding="utf-8")
    twice = json.dumps({**line, "run_id": "demo/r2"}, sort_keys=True) + "\n"
    (tmp_path / "attempts.jsonl").write_text(text + twice, encoding="utf-8", newline="\n")
    with pytest.raises(Invalid, match="two first attempts"):
        ledger.status()
    (tmp_path / "attempts.jsonl").write_text(text + text, encoding="utf-8", newline="\n")
    with pytest.raises(Invalid, match="registered twice"):
        ledger.status()


def test_a_short_write_completes_and_a_failed_append_leaves_a_repairable_tail(tmp_path, monkeypatch):
    """Independent review of #75: os.write may write fewer bytes than asked. A write that makes progress is
    finished; one that stops raises, so the caller takes no provider action, and its torn tail is ignored by readers
    and truncated by the next append."""
    from aew_eval import ledger as L

    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    real = os.write

    def short(fd, data):
        return real(fd, bytes(data[:20]))

    monkeypatch.setattr(L.os, "write", short)
    first = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"], requested_profile={})
    assert ledger.attempts()["demo/r1"].registered == first  # 20 bytes at a time, but every byte
    calls = []

    def stops(fd, data):
        calls.append(1)
        if len(calls) > 1:
            raise OSError(28, "No space left on device")
        return real(fd, bytes(data[:20]))

    monkeypatch.setattr(L.os, "write", stops)
    with pytest.raises(OSError):
        ledger.register(run_id="demo/r2", cell=f["assignment"]["order"][1]["cell"], requested_profile={})
    assert not (tmp_path / "attempts.jsonl").read_bytes().endswith(b"\n")  # the torn tail is there...
    assert ledger.status() == {"demo/r1": "runner_lost"}  # ...and readers ignore it
    monkeypatch.setattr(L.os, "write", real)
    ledger.register(run_id="demo/r2", cell=f["assignment"]["order"][1]["cell"], requested_profile={})
    assert ledger.status() == {"demo/r1": "runner_lost", "demo/r2": "runner_lost"}
    assert all(json.loads(x) for x in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines())


def test_a_finalize_interrupted_after_publishing_is_completed_by_the_same_record(tmp_path, monkeypatch):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    line = ledger.register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"], requested_profile={})
    rec = result(f, line)
    monkeypatch.setattr(ledger, "_append", lambda _line: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        ledger.finalize(rec)
    monkeypatch.undo()
    assert ledger.status() == {"demo/r1": "runner_lost"} and (tmp_path / "runs/r1.json").is_file()
    other = result(f, line, validity="invalid_measurement")
    with pytest.raises(Invalid, match="differs from this result"):
        ledger.finalize(other)
    ledger.finalize(rec)
    assert ledger.status() == {"demo/r1": "valid"} and ledger.verify() == []
    assert not list((tmp_path / "runs").glob(".*partial"))


def test_a_retry_is_linked_and_allowed_only_by_the_frozen_policy(tmp_path):
    f = frozen()
    ledger = AttemptLedger(tmp_path, f)
    cell = f["assignment"]["order"][0]["cell"]
    first = ledger.register(run_id="demo/r1", cell=cell, requested_profile={})
    second = ledger.register(run_id="demo/r2", cell=cell, requested_profile={}, retry_of="demo/r1")  # lost: allowed
    assert ledger.attempts()["demo/r1"].retries == ["demo/r2"]
    with pytest.raises(Invalid, match="used its 1 preregistered retries"):  # r2 is lost too, but the budget is spent
        ledger.register(run_id="demo/r3", cell=cell, requested_profile={}, retry_of="demo/r2")
    ledger.finalize(result(f, second, validity="invalid_measurement"))
    with pytest.raises(Invalid, match="latest attempt"):
        ledger.register(run_id="demo/r4", cell=cell, requested_profile={}, retry_of=first["run_id"])
    other = f["assignment"]["order"][1]["cell"]
    done = ledger.register(run_id="demo/r5", cell=other, requested_profile={})
    ledger.finalize(result(f, done, validity="invalid_measurement"))
    with pytest.raises(Invalid, match="allows a retry only of"):  # the policy does not name invalid_measurement
        ledger.register(run_id="demo/r6", cell=other, requested_profile={}, retry_of="demo/r5")


def test_a_runner_killed_after_registering_leaves_a_visible_attempt(tmp_path):
    """Completion criterion: killing the runner after launch, before finalization, leaves an unfinished attempt."""
    f = frozen()
    path = tmp_path / "prereg.yaml"
    prereg.dump(f, path)
    script = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'eval')!r})\n"
        "from pathlib import Path\n"
        "from aew_eval import prereg\n"
        "from aew_eval.ledger import AttemptLedger\n"
        f"f = prereg.load(Path({str(path)!r}))\n"
        f"AttemptLedger(Path({str(tmp_path)!r}), f).register(run_id='demo/r1', "
        "cell=f['assignment']['order'][0]['cell'], requested_profile={})\n"
        "os._exit(9)  # the provider action would start here; the runner dies\n")
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                          creationflags=NO_WINDOW)
    assert proc.returncode == 9, proc.stderr
    assert AttemptLedger(tmp_path, prereg.load(path)).status() == {"demo/r1": "runner_lost"}


def test_a_ledger_refuses_lines_of_another_preregistration(tmp_path):
    f = frozen()
    AttemptLedger(tmp_path, f).register(run_id="demo/r1", cell=f["assignment"]["order"][0]["cell"],
                                        requested_profile={})
    other = frozen(question="A different question?")
    with pytest.raises(Invalid, match="another preregistration"):
        AttemptLedger(tmp_path, other).status()


# ------------------------------------------------------------------------------------------------ the M3 corpus

def test_every_m3_record_maps_deterministically_and_unchanged():
    records = compat.read(M3)
    assert len(records) >= 68
    mapped = [compat.from_dogfood(r) for r in records]
    assert [compat.from_dogfood(r) for r in records] == mapped  # deterministic
    assert len({m["run_id"] for m in mapped}) == len(mapped)  # one sample each
    for original, m in zip(records, mapped, strict=True):
        validate("aew/eval-run/v1", m)
        assert m["legacy"]["record"] == original and m["legacy"]["sha256"] == sha256_of(original)
        assert m["case"]["id"] == original["task"] and m["arm"]["kind"] == original["mode"]
        assert m["outcome"]["hidden"] == original["hidden"] and m["limits"]["cap_usd"] == original["cap_usd"]
        assert m["cost"]["provider_reported_usd"] == original["totals"].get("cost_usd")
        assert m["preregistration_sha256"] is None and m["validity"] is None  # nothing invented


def test_the_mapping_accounts_for_every_m3_field():
    seen = {k for r in compat.read(M3) for k in r}
    assert seen <= set(compat.FIELDS), seen - set(compat.FIELDS)
    with pytest.raises(ValueError, match="no place in the mapping"):
        compat.from_dogfood({**compat.read(M3)[0], "new_field": 1})


def test_the_schemas_are_valid_json_schema():
    from aew_eval import schemas

    for schema_id in schemas.FILES:
        schemas._validator(schema_id)  # check_schema raises on an invalid schema
    validate("aew/eval-case/v1", {"schema": "aew/eval-case/v1", "id": "T1", "family": "m3",
                                  "fixture": {"base": "fixture/base", "overlay": "overlays/T1"},
                                  "hidden_sha256": H, "control_of": None})

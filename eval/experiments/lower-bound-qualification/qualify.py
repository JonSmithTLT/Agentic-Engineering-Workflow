"""The lower-bound qualification lane (agent-effectiveness adoption, delta D3; synthesis §13.4): one driver.

Evaluation tooling, not product code. It drives the shared F19 instrument (``eval/aew_eval``) and AEW's live lane;
the only measurement it adds is the tree-observable half of the rubric's behaviours (``rubric.md`` §4).

The model runs happen on an **arm host that holds no oracle** (the Rocky 8 VM by default, contained by bubblewrap);
the oracles reach that host only to score, after every model run has ended (``README.md``, "Operator steps")::

    python qualify.py check            # the dry run: no provider is called, nothing is spent
    python qualify.py fetch            # downloads the pinned upstream fixture (Python-Markdown 3.11.0, ~2.5 MB)
    python qualify.py freeze --by NAME # freezes prereg.yaml (needs the fetched fixture and oracle-validation.json)
    python qualify.py floor            # the live lane: bridge handshake + typed submit (calls the provider)
    python qualify.py ceiling          # the preregistered raw cells, scoring deferred (calls the provider)
    python qualify.py run --by NAME    # fetch, check, freeze, floor, ceiling: everything that runs a model
    python qualify.py score            # with AEW_EVAL_HIDDEN_ROOT, after every model run: scores, behaviours
    python qualify.py purge            # the retention step: deletes kept session databases past their window

``check`` validates the profiles (and that the frozen arm pins them), the cases, the overlay and, with the hidden
root and the fetched fixture, runs every oracle against the seeded start (exactly its criteria fail) and the
reference solution (every check passes), recording the result in ``oracle-validation.json`` (committed: ``freeze``
needs it, so a host without the oracles can freeze). It records the upstream suite's baseline, starts the pinned
OpenCode as far as resolving each profile's model (no session, no prompt), and on Linux builds and verifies a raw
run's containment layout.

A model run (``floor``, ``ceiling``, ``run``) refuses while an oracle is on this host: ``AEW_EVAL_HIDDEN_ROOT`` set,
or the lane's documented copy (``<out>/../hidden``) present. Every attempt counts against ``budget_usd``: a run's
reported cost, or its cap when that is unknown or the run was lost; the floor's trials are capped by a watcher that
ends the trial (its processes and its runs' supervisors) when the floor's cap is reached.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # the AEW checkout
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))

from aew_eval import arms, fixture, hidden, prereg, profiles, raw, retention, runner  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PLAN = HERE / "prereg.yaml"
FROZEN = HERE / "prereg.frozen.yaml"
PROFILES = HERE / "profiles.yaml"
RUBRIC = HERE / "rubric.md"
UPSTREAM = HERE / "upstream.yaml"
BEHAVIOURS = HERE / "behaviours.yaml"
ORACLE_RECEIPT = HERE / "oracle-validation.json"
FIXTURE = HERE / "fixture"
BASE = FIXTURE / "base"
RECEIPT = FIXTURE / "base.receipt.json"  # written by fetch, next to the base (both git-ignored)
CASES = {cid: FIXTURE / f"{cid}.yaml" for cid in ("LBQ-1", "LBQ-2", "LBQ-3")}
PLACEHOLDER = "placeholder-not-a-credential"  # lets the catalog list a paid provider's models; never sent anywhere
LIVE_TEST = "tests/live/test_opencode_model_live.py::test_a_free_model_carries_out_real_launch_contracts"
POLL_S = 10.0  # the floor's cost watcher

# What each oracle must report on the seeded starting point: these checks fail, every other one passes. On the
# reference solution every check passes. (rubric.md §3: an oracle is exercised before the experiment freezes.)
SEED_FAILS = {
    "LBQ-1": {"criterion: mixed-case blocked schemes are blocked end to end",
              "criterion: a blocked scheme after leading whitespace is blocked",
              "criterion: a regression test covers a mixed-case scheme"},
    "LBQ-2": {"criterion: external links get rel='nofollow noopener' by default",
              "criterion: an empty rel_external turns it off; another value is used as given",
              "site: rel_external is an option like the others (constructor, makeExtension, extension_configs)",
              "site: the documentation's option table has rel_external"},
    "LBQ-3": {"criterion 1: md.reset() empties report(); a document's report holds only its links",
              "criterion 2: each blocked URL once, in first-appearance order",
              "criterion 3: strict mode's LinkPolicyError names the URL and carries it as .url",
              "criterion 4: the documentation describes report() and md.reset()"},
}
SEED_COPIES = {"seed/linkpolicy_support.py": "tests/test_syntax/extensions/linkpolicy_support.py",
               "seed/test_link_policy.py": "tests/test_syntax/extensions/test_link_policy.py"}


# ---------------------------------------------------------------------------------------------- helpers


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_out(experiment: str) -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "aew-eval" / experiment


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def say(**fields: Any) -> None:
    print(json.dumps(fields, sort_keys=True, default=str), flush=True)


def overlay_paths() -> list[str]:
    root = FIXTURE / "overlay"
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def base_present() -> bool:
    return BASE.is_dir() and RECEIPT.is_file()


def write_files(files: dict[str, bytes], dest: Path) -> Path:
    for rel, data in files.items():
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return dest


def reference_files(root: Path, case: str) -> dict[str, bytes]:
    ref = root / "reference" / case
    return {p.relative_to(ref).as_posix(): fixture.normalized(p.read_bytes()) for p in ref.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def case_hashes() -> dict[str, dict[str, str]]:
    """Each case's fixture hash (the fetched base, the overlay, the manifest) and its oracle commitment."""
    out = {}
    for cid, path in CASES.items():
        case = fixture.load(path)
        if case.manifest["hidden_sha256"] is None:
            raise Invalid(f"case {cid} has no oracle commitment (hidden_sha256)")
        out[cid] = {"sha256": fixture.case_sha256(case), "hidden_sha256": case.manifest["hidden_sha256"]}
    return out


def plan_with_hashes(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan with every case's fixture hash and oracle commitment, and the rubric's hash, filled in."""
    out = json.loads(json.dumps(plan))
    hashes = case_hashes()
    for c in out["cases"]:
        c.update(hashes[c["id"]])
    out["scoring"]["rubric_sha256"] = fixture._digest({"rubric.md": RUBRIC.read_bytes()})  # noqa: SLF001
    return out


def arm_host_clean(out: Path, hidden_root: Path | None) -> None:
    """A model runs only on a host that holds no oracle (held-out isolation decision of 2026-10-06, applied to this
    lane's oracles): the hidden root is not set, and the lane's documented copy beside the run state is absent."""
    if hidden_root is not None:
        raise SystemExit("refused: AEW_EVAL_HIDDEN_ROOT is set: a model never runs on a host holding the oracles. "
                         "Unset it; scoring comes after every model run (`qualify.py score`)")
    copy = out.parent / "hidden"
    if copy.exists():
        raise SystemExit(f"refused: {copy} exists: the oracles are on this host. Remove it before any model runs")


def frozen_record() -> dict[str, Any]:
    if not FROZEN.exists():
        raise SystemExit(f"refused: {FROZEN.name} does not exist: freeze the preregistration first")
    frozen = load_yaml(FROZEN)
    prereg.verify(frozen)
    return frozen


def charged(record: dict[str, Any] | None, cap: float) -> float:
    """What an attempt is charged against the budget: its charged cost, else its reported cost, else its cap (a lost
    run, an arm that raised before reporting anything)."""
    cost = (record or {}).get("cost") or {}
    if cost.get("charged_usd") is not None:
        return float(cost["charged_usd"])
    return raw.charged(cost.get("provider_reported_usd"), cap)


# ---------------------------------------------------------------------------------------------- check (no provider)


def check_cases(report: dict[str, Any]) -> None:
    for cid, path in CASES.items():
        manifest = load_yaml(path)
        validate("aew/eval-case/v1", manifest, what=f"case {cid}")
        if manifest["id"] != cid or not manifest.get("task"):
            raise Invalid(f"{path.name}: id {manifest['id']!r}, task present: {bool(manifest.get('task'))}")
    report["cases"] = {"valid": sorted(CASES)}


def check_overlay(report: dict[str, Any]) -> None:
    """Every overlay path is portable and new: the seeded files add to the upstream tree and never replace a file."""
    paths = overlay_paths()
    for rel in paths:
        fixture.safe_relative(rel, "overlay")
    stray = [p for p in paths if "__pycache__" in p or p.endswith(".pyc")]
    if stray:  # running a seeded file leaves bytecode beside it, and the case hash would include it
        raise Invalid(f"bytecode in the overlay: {stray[:3]}; delete the __pycache__ directories")
    clash = sorted(set(paths) & set(load_yaml(UPSTREAM)["paths_touching_overlay_dirs"]))
    if base_present():
        clash = sorted(set(clash) | {p for p in paths if (BASE / p).exists()})
    if clash:
        raise Invalid(f"overlay files would replace upstream files: {clash}")
    report["overlay"] = {"files": len(paths), "collisions_with_upstream": 0,
                         "checked_against": "the fetched base" if base_present() else "upstream.yaml's listing"}


def check_profiles(report: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The profile records, and the arm's pins agreeing with the record of the profile it runs (adoption record §9:
    provider, model, effort, harness and effective profile pinned at preregistration)."""
    records = profiles.load(PROFILES)
    by_ref = {r["ref"]: r for r in records}
    for arm in plan["arms"]:
        config = arm["config"]
        ref = plan["profiles"]["roles"][config["role"]]
        record = by_ref.get(ref)
        if record is None:
            raise Invalid(f"role {config['role']} runs {ref}, which has no profile record in {PROFILES.name}")
        pins = {"model": (config["model"], record["ref"]), "profile.id": (config["profile"]["id"], record["id"]),
                "effective_profile": (config["profile"]["effective_profile"], record["effective_profile"]),
                "qualification_state": (config["profile"]["qualification_state"],
                                        record["qualification_state"] if not FROZEN.exists()
                                        else config["profile"]["qualification_state"]),  # pinned as it was then
                "provider_env": (sorted(config["provider_env"]), sorted(record["credential_env"])),
                "harness.version": (config["harness"]["version"], record["harness"]["version"]),
                "harness.artifact_sha256": (config["harness"]["artifact_sha256"],
                                            record["harness"]["artifact_sha256"])}
        wrong = {k: v for k, v in pins.items() if v[0] != v[1]}
        if wrong:
            raise Invalid(f"arm {arm['id']} does not pin profile {record['id']} as its record states: {wrong}")
    report["profiles"] = {r["id"]: r["qualification_state"] for r in records}
    return records


def check_oracles(report: dict[str, Any], hidden_root: Path | None) -> None:
    if hidden_root is None:
        report["oracles"] = "not on this host (validated where they live: oracle-validation.json)"
        return
    out: dict[str, Any] = {}
    for cid, path in CASES.items():
        oracle = hidden.Oracle.locate(hidden_root, cid)
        committed = load_yaml(path)["hidden_sha256"]
        if committed != oracle.sha256:
            raise Invalid(f"case {cid} commits to oracle {committed[:12]}, the hidden root holds {oracle.sha256[:12]}")
        for seed_rel, overlay_rel in SEED_COPIES.items():
            if oracle.files.get(seed_rel) != fixture.normalized((FIXTURE / "overlay" / overlay_rel).read_bytes()):
                raise Invalid(f"oracle {cid}: its copy {seed_rel} is not the overlay's {overlay_rel}")
        out[cid] = {"sha256": oracle.sha256, "committed": True}
    report["oracles"] = out


def validate_oracles(report: dict[str, Any], hidden_root: Path | None) -> None:
    """Each oracle against the seeded starting point and against the reference solution (needs the fixture), and the
    receipt that lets a host without the oracles freeze."""
    if hidden_root is None or not base_present():
        report["oracle_validation"] = "skipped here: needs the fetched fixture and AEW_EVAL_HIDDEN_ROOT"
        return
    results: dict[str, Any] = {}
    hashes = case_hashes()
    for cid, path in CASES.items():
        snap = fixture.snapshot(fixture.load(path))
        start = fixture.starting_files(snap, seeded=False)
        oracle = hidden.Oracle.locate(hidden_root, cid)
        with tempfile.TemporaryDirectory(prefix=f"aew-lbq-{cid}-") as tmp:
            seeded = hidden.score(oracle, write_files(start, Path(tmp) / "seeded"))
            ref = hidden.score(oracle, write_files({**start, **reference_files(hidden_root, cid)}, Path(tmp) / "ref"))
        failed = {c["name"] for c in seeded["checks"] if not c["ok"]}
        ref_failed = {c["name"]: c["detail"] for c in ref["checks"] if not c["ok"]}
        results[cid] = {**hashes[cid], "oracle_sha256": oracle.sha256,
                        "seed_fails_as_designed": failed == SEED_FAILS[cid], "seed_failed": sorted(failed),
                        "reference_passes": ref["passed"], "reference_failed": ref_failed,
                        "contained": seeded.get("contained")}
        if failed != SEED_FAILS[cid] or not ref["passed"]:
            report["oracle_validation"] = results
            raise Invalid(f"oracle {cid} does not behave as designed: {results[cid]}")
    receipt = {"validated_at": now(), "aew_commit": fixture.git(ROOT, "rev-parse", "HEAD"), "cases": results}
    ORACLE_RECEIPT.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    report["oracle_validation"] = {"receipt": ORACLE_RECEIPT.name, "cases": results}


def upstream_baseline(report: dict[str, Any]) -> None:
    """The upstream suite on the seeded starting point: which tests fail before any model works (the seeded
    distractor is expected; anything else is the environment's, recorded here before freezing)."""
    if not base_present():
        report["upstream_suite"] = "skipped: the fixture is not fetched"
        return
    snap = fixture.snapshot(fixture.load(CASES["LBQ-1"]))
    with tempfile.TemporaryDirectory(prefix="aew-lbq-suite-") as tmp:
        tree = write_files(fixture.starting_files(snap, seeded=False), Path(tmp) / "tree")
        res = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=tree,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                             stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONPATH": str(tree)},
                             creationflags=NO_WINDOW)
    tail = res.stderr.strip().splitlines()[-1:] if res.stderr else []
    failing = sorted({line.split(" ")[1] for line in res.stderr.splitlines()
                      if line.startswith(("FAIL: ", "ERROR: ")) and len(line.split(" ")) > 1})
    report["upstream_suite"] = {"exit": res.returncode, "summary": tail, "failing": failing}


def harness_launch(report: dict[str, Any], plan: dict[str, Any], records: list[dict[str, Any]]) -> None:
    """Start the pinned OpenCode as each profile's arm would, as far as resolving the model and its effort in the
    served catalog. No session is created and no prompt is sent: nothing reaches a model. A paid provider's variable
    is replaced by a placeholder, whether or not a real one is set, so the catalog lists that provider's models and no
    real credential reaches the dry run's server."""
    from aew.harness.opencode.adapter import HarnessIncompatible

    headless = raw._headless()  # noqa: SLF001 (the raw arm's own session class)
    binary = raw.harness_binary()
    out: dict[str, Any] = {"binary": str(binary), "binary_sha256": raw._sha256_file(binary),  # noqa: SLF001
                           "platform": raw.host_platform()}
    worker_refs = set(plan["profiles"]["roles"].values())
    for record in records:
        profile = arms.model_ref(record["ref"])
        names = record["credential_env"]
        saved = {n: os.environ.get(n) for n in names}
        os.environ.update({n: PLACEHOLDER for n in names})
        state = Path(tempfile.mkdtemp(prefix="aew-lbq-launch-"))
        (state / "repo").mkdir()
        session = headless.HeadlessSession(state / "raw")
        entry: dict[str, Any] = {"in_prereg": record["ref"] in worker_refs,
                                 "credential": "placeholder" if names else "none needed"}
        try:
            t0 = time.monotonic()
            session._start(directory=state / "repo", profile=profile,  # noqa: SLF001 (stop before a session)
                           config=headless.raw_config(profile, 5), provider_env=names)
            entry.update(offered=True, version=session.version, catalog=session.model_info,
                         start_s=round(time.monotonic() - t0, 1))
        except HarnessIncompatible as exc:
            entry.update(offered=False, version=session.version, reason=str(exc)[:300])
        finally:
            session.terminate()
            session.tree.kill()
            for n, v in saved.items():
                if v is None:
                    os.environ.pop(n, None)
                else:
                    os.environ[n] = v
            shutil.rmtree(state, ignore_errors=True)
        out[record["id"]] = entry
    report["harness_launch"] = out


def containment_check(report: dict[str, Any], out: Path, plan: dict[str, Any]) -> None:
    """Linux: a raw run's layout, built where the runs will live and verified (launch self-test and confidentiality
    probe), then the pinned OpenCode started inside it as far as resolving the arm's model and effort in its served
    catalog: no session is created and no prompt is sent (the provider variable is a placeholder)."""
    if not sys.platform.startswith("linux"):
        report["containment"] = "not checked here: contained raw runs are Linux-only (the arm host is the VM)"
        return
    from aew.harness import procs

    config = plan["arms"][0]["config"]
    profile = arms.model_ref(config["model"])
    names = list(config["provider_env"])
    scratch = out / "work" / "containment-check"
    (scratch / "repo").mkdir(parents=True, exist_ok=True)
    saved = {n: os.environ.get(n) for n in names}
    try:
        layout = raw.contained_layout(scratch / "repo", scratch, binary=raw.harness_binary())
        report["containment"] = raw.verify_layout(layout, scratch)
        if report["containment"]["ok"]:
            headless = raw._headless()  # noqa: SLF001
            session = headless.HeadlessSession(scratch / "harness")
            session.tree = procs.ProcessTree(layout=layout)
            os.environ.update({n: PLACEHOLDER for n in names})
            try:
                session._start(directory=scratch / "repo", profile=profile,  # noqa: SLF001 (stop before a session)
                               config=headless.raw_config(profile, 5), provider_env=names)
                report["containment"]["contained_launch"] = {"version": session.version, "model": config["model"],
                                                             "catalog": session.model_info}
            finally:
                session.terminate()
                session.tree.kill()
    finally:
        for n, v in saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
        shutil.rmtree(scratch, ignore_errors=True)
        (scratch.parent / f".{scratch.name}.aew-mask").unlink(missing_ok=True)
    if not report["containment"]["ok"]:
        raise Invalid(f"a raw run cannot be contained here: {report['containment']['reason']}")


def cmd_check(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    report: dict[str, Any] = {"at": now(), "aew_commit": fixture.git(ROOT, "rev-parse", "HEAD")[:12],
                              "platform": raw.host_platform()}
    plan = load_yaml(PLAN)
    try:
        check_cases(report)
        check_overlay(report)
        records = check_profiles(report, plan)
        check_oracles(report, hidden_root)
        if base_present():
            receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
            report["fixture"] = {"receipt": receipt, "base_matches_receipt": receipt["content_sha256"] ==
                                 fixture._digest(fixture._read_tree(BASE, "base"))}  # noqa: SLF001
            if not report["fixture"]["base_matches_receipt"]:
                raise Invalid("the fetched base changed since it was fetched: fetch it again")
            hashed = plan_with_hashes(plan)
            prereg.check(hashed)
            report["prereg"] = {"valid": True, "schedule": [o["cell"] for o in prereg.schedule(hashed)]}
        else:
            report["fixture"] = "not fetched: `qualify.py fetch` downloads it"
            report["prereg"] = "schema checked after the fixture is fetched (its case hashes come from it)"
        validate_oracles(report, hidden_root)
        upstream_baseline(report)
        if not args.no_launch:
            harness_launch(report, plan, records)
            containment_check(report, out, plan)
    except Invalid as exc:
        report["refused"] = str(exc)
        say(**report)
        return 1
    say(**report)
    return 0


# ---------------------------------------------------------------------------------------------- fetch (downloads)


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download the pinned upstream at its tag, prove the commit and tree, and export its files as the fixture base."""
    up = load_yaml(UPSTREAM)
    if base_present() and not args.again:
        say(fetched=False, reason="already fetched", receipt=json.loads(RECEIPT.read_text(encoding="utf-8")))
        return 0
    with tempfile.TemporaryDirectory(prefix="aew-lbq-fetch-") as tmp:
        clone = Path(tmp) / "clone"
        subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=", "clone", "--quiet", "--depth",
                        "1", "--branch", up["tag"], "--no-tags", up["url"], str(clone)], check=True,
                       env=fixture.git_env(), stdin=subprocess.DEVNULL, capture_output=True, creationflags=NO_WINDOW)
        commit = fixture.git(clone, "rev-parse", "HEAD")
        tree = fixture.git(clone, "rev-parse", "HEAD^{tree}")
        if (commit, tree) != (up["commit"], up["tree"]):
            raise SystemExit(f"refused: {up['url']} {up['tag']} is commit {commit} tree {tree}, not the pinned "
                             f"{up['commit']} {up['tree']}")
        files = [p for p in fixture.git(clone, "ls-files", "-z").split("\0") if p]
        if len(files) != up["file_count"]:
            raise SystemExit(f"refused: {len(files)} files at the pinned tree, expected {up['file_count']}")
        if BASE.exists():
            shutil.rmtree(BASE)
        for rel in files:
            target = BASE / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(clone / rel, target)
    receipt = {"url": up["url"], "tag": up["tag"], "commit": commit, "tree": tree, "files": len(files),
               "content_sha256": fixture._digest(fixture._read_tree(BASE, "base")), "fetched_at": now()}  # noqa: SLF001
    RECEIPT.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    say(fetched=True, receipt=receipt)
    return 0


# ---------------------------------------------------------------------------------------------- freeze


def cmd_freeze(args: argparse.Namespace) -> int:
    """Freeze the plan: the oracles must have been validated (oracle-validation.json) against exactly these case
    hashes and oracle commitments, so a host that never holds the oracles can freeze."""
    if FROZEN.exists():
        say(frozen=False, reason=f"{FROZEN.name} exists: a frozen preregistration is never refrozen",
            canonical_sha256=prereg.verify(load_yaml(FROZEN)))
        return 0
    if not base_present():
        raise SystemExit("refused: freezing needs the fetched fixture (`qualify.py fetch`)")
    if not ORACLE_RECEIPT.exists():
        raise SystemExit(f"refused: no {ORACLE_RECEIPT.name}: the oracles have not been validated")
    validated = json.loads(ORACLE_RECEIPT.read_text(encoding="utf-8"))["cases"]
    for cid, h in case_hashes().items():
        v = validated.get(cid) or {}
        if (v.get("sha256"), v.get("oracle_sha256")) != (h["sha256"], h["hidden_sha256"]) \
                or not v.get("seed_fails_as_designed") or not v.get("reference_passes"):
            raise SystemExit(f"refused: the oracle validation of {cid} does not cover these hashes or did not pass")
    frozen = prereg.freeze(plan_with_hashes(load_yaml(PLAN)), by=args.by)
    prereg.dump(frozen, FROZEN)
    say(frozen=True, file=str(FROZEN), canonical_sha256=frozen["canonical_sha256"])
    return 0


# ---------------------------------------------------------------------------------------------- floor (provider)


def worker_profile(frozen: dict[str, Any]) -> dict[str, Any]:
    ref = frozen["profiles"]["roles"]["worker"]
    return next(r for r in profiles.load(PROFILES) if r["ref"] == ref)


def floor_verdict(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """rubric.md §2: the floor passes when, in at least one trial, the implementer's run ended with its typed
    submission accepted as evidence (``implementation_report``) after at least one request through the run's bridge."""
    passing = []
    for t in trials:
        impl = next((r for r in t.get("runs") or [] if r.get("role") == "implementer"), None)
        if impl and impl.get("status") == "ended_with_evidence" and (impl.get("bridge") or {}).get("requests") \
                and any(e.get("kind") == "implementation_report" for e in impl.get("evidence") or []):
            passing.append(t.get("trial"))
    return {"state": "passed" if passing else "failed", "trials": len(trials), "passing_trials": passing}


def session_costs(root: Path) -> float | None:
    """The cost every OpenCode session under ``root`` reports so far (its assistant messages), read-only; ``None``
    when a database cannot be read."""
    total = 0.0
    for db in root.rglob("opencode.db"):
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                rows = con.execute("select data from session_message where type = 'assistant'").fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            return None
        for (data,) in rows:
            try:
                total += float(json.loads(data).get("cost") or 0)
            except (ValueError, TypeError, AttributeError):
                return None
    return total


def end_trial(tree: Any, basetemp: Path) -> list[int]:
    """End a floor trial: its test process tree, then every run supervisor it started (a supervisor outlives the
    test by design; its own process tree ends the harness when it dies)."""
    tree.kill()
    killed = []
    for record in basetemp.rglob("run.json"):
        try:
            pid = int(json.loads(record.read_text(encoding="utf-8")).get("supervisor_pid") or 0)
        except (OSError, ValueError, TypeError):
            continue
        if pid:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                killed.append(pid)
            except OSError:
                pass
    return killed


def floor_state(out: Path) -> dict[str, Any]:
    path = out / "floor" / "floor.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"trials": [], "charged_usd": 0.0}


def cmd_floor(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    arm_host_clean(out, hidden_root)
    frozen = frozen_record()
    record = worker_profile(frozen)
    cap = float(frozen["thresholds"]["budget"]["floor_cap_usd"])
    trials_max = int(frozen["thresholds"]["floor"]["trials"])
    names = record["credential_env"]
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"refused: {', '.join(missing)} is not set (profile {record['id']} needs it)")
    state = floor_state(out)
    if any(t.get("verdict") == "passed" for t in state["trials"]):
        say(floor="passed earlier", trials=state["trials"], charged_usd=state["charged_usd"])
        return 0
    from aew.harness import procs

    (out / "floor").mkdir(parents=True, exist_ok=True)
    while len(state["trials"]) < trials_max:
        if state["charged_usd"] >= cap:
            break
        n = len(state["trials"]) + 1
        where = out / "floor" / f"trial-{n}"
        where.mkdir(parents=True, exist_ok=True)
        results = where / "results.jsonl"
        env = {k: v for k, v in os.environ.items() if k != hidden.ENV}
        env.update(AEW_LIVE_OPENCODE_MODEL=record["ref"], AEW_LIVE_RESULTS=str(results), AEW_LIVE_MODEL_TRIALS="1",
                   PYTHONPATH=os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep))
        if names:
            env["AEW_LIVE_PROVIDER_KEY_ENV"] = names[0]
        tree = procs.ProcessTree()
        log = (where / "pytest.log").open("w", encoding="utf-8")
        proc = tree.spawn([sys.executable, "-m", "pytest", "--live", LIVE_TEST, "-p", "no:xdist", "-p",
                           "no:cacheprovider", "-q", "--basetemp", str(where / "tmp")], cwd=str(ROOT), env=env,
                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        stopped: list[str] = []

        def watch(tree: Any = tree, proc: Any = proc, where: Path = where, stopped: list[str] = stopped) -> None:
            while proc.poll() is None:
                spent = session_costs(where / "tmp") or 0.0
                if state["charged_usd"] + spent >= cap:
                    stopped.append(f"floor cap {cap} reached at {state['charged_usd'] + spent:.4f}")
                    end_trial(tree, where / "tmp")
                    return
                time.sleep(POLL_S)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        code = proc.wait()
        watcher.join(timeout=POLL_S * 2)
        log.close()
        tree.close()
        trials = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line.strip()] \
            if results.exists() else []
        spent = session_costs(where / "tmp")
        cost = spent if spent is not None else max(cap - state["charged_usd"], 0.0)  # unknown: charge what remains
        verdict = floor_verdict(trials)["state"]
        if stopped:
            verdict = "cost_cap"
        elif code != 0:  # AEW's side failed an assertion: the floor is not established either way
            verdict = "aew_side_failure" if trials else "not_run"
        state["trials"].append({"trial": n, "verdict": verdict, "pytest_exit": code, "charged_usd": round(cost, 6),
                                "cost_known": spent is not None, "stopped": stopped, "results": str(results),
                                "session_state": str(where / "tmp")})
        state["charged_usd"] = round(state["charged_usd"] + cost, 6)
        (out / "floor" / "floor.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
        if verdict == "passed" or verdict == "aew_side_failure":
            break
    passed = any(t["verdict"] == "passed" for t in state["trials"])
    say(floor="passed" if passed else "not passed", profile=record["id"], **state)
    return 0 if passed else 3


# ---------------------------------------------------------------------------------------------- ceiling (provider)


def cell_name(cell: str, n: int) -> str:
    return cell.replace("/", "-") + (f"-retry{n}" if n else "")


def spent_so_far(out: Path, ledger: AttemptLedger, caps: dict[str, float]) -> float:
    """Everything the lane has been charged: the floor's trials, and every ceiling attempt (a lost one at its cap)."""
    total = float(floor_state(out)["charged_usd"])
    for attempt in ledger.attempts().values():
        cap = caps[attempt.registered["arm"]]
        if attempt.finalized is None:
            total += cap
            continue
        record = json.loads((ledger.runs / (attempt.run_id.split("/", 1)[1] + ".json")).read_text(encoding="utf-8"))
        total += charged(record, cap)
    return total


def cmd_ceiling(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    arm_host_clean(out, hidden_root)
    frozen = frozen_record()
    if not any(t.get("verdict") == "passed" for t in floor_state(out)["trials"]):
        raise SystemExit("refused: the profile has not passed the floor (rubric.md §2): run `qualify.py floor`")
    ledger_dir, work = out / "ledger", out / "work"
    ledger = AttemptLedger(ledger_dir, frozen)
    budget = float(frozen["profiles"]["budget_usd"])
    margin = float(frozen["thresholds"]["budget"]["overshoot_margin_usd"])
    caps = {a["id"]: float(a["config"]["cap_usd"]) for a in frozen["arms"]}
    policy = frozen["validity_rules"]["retry_policy"]
    for entry in frozen["assignment"]["order"]:
        cell = entry["cell"]
        while True:
            attempts = [a for a in ledger.attempts().values() if a.registered["assignment"]["cell"] == cell]
            latest = max(attempts, key=lambda a: a.registered["at"]) if attempts else None
            if latest is not None and (latest.status == "valid" or latest.status not in policy["allowed_for"]
                                       or len(attempts) - 1 >= policy["max_retries"]):
                break
            spent = spent_so_far(out, ledger, caps)
            if spent + caps[entry["arm"]] + margin > budget:
                say(stopped="budget", spent_usd=round(spent, 4), budget_usd=budget, next_cell=cell)
                return 3
            try:
                record = runner.run_cell(frozen, ledger_dir=ledger_dir, cell=cell, cases=CASES, work=work,
                                         run_name=cell_name(cell, len(attempts)),
                                         retry_of=latest.run_id if latest else None,
                                         deadline_s=float(args.deadline_s), defer_scoring=True)
            except runner.Refused as exc:
                raise SystemExit(f"refused (nothing registered): {exc}") from None
            say(run=record["run_id"], validity=record["validity"], charged_usd=record["cost"].get("charged_usd"),
                truncated=record["outcome"].get("truncated_why"))
    say(ceiling="done", ledger=str(ledger_dir), status=ledger.status(),
        spent_usd=round(spent_so_far(out, ledger, caps), 4),
        next="copy the oracles in, then `qualify.py score` (README.md, operator steps)")
    return 0


# ---------------------------------------------------------------------------------------------- score


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def meaningful(changed: list[str], rules: dict[str, Any]) -> list[str]:
    """The changed paths, without what running the code leaves behind (bytecode, caches)."""
    return [p for p in changed if not matches(p, rules["ignored_paths"])]


def finished(record: dict[str, Any]) -> bool:
    """A run that ended on its own: not the deadline, the cost cap or the step limit, and no provider error at the
    end (rubric.md §4: behaviours 4 and 5 are read only from finished runs)."""
    out = record["outcome"]
    return out.get("harness_outcome") == "ended" and not out.get("truncated")


def tree_behaviours(record: dict[str, Any], rules: dict[str, Any], checks: dict[str, bool]) -> dict[str, bool]:
    """rubric.md §4: the behaviours a run's final tree shows. The session-database ones wait for the F19 reader."""
    changed = meaningful(record["outcome"].get("changed_paths") or [], rules)
    case = record["case"]["id"]
    shown = {"bad_search_root_selection": any(matches(p, rules["decoy_paths"]) for p in changed),
             "difficulty_recovering_after_distraction":
                 any(matches(p, rules["distractor_paths"]) for p in changed)
                 or checks.get("structure: the link policy runs after the inline processor") is False}
    if case in rules["required_sites"]:
        hit = [any(fnmatch.fnmatchcase(p, site) for p in changed) for site in rules["required_sites"][case]]
        shown["incomplete_cross_file_changes"] = finished(record) and any(hit) and not all(hit)
    if case == "LBQ-3":
        criteria = [ok for name, ok in checks.items() if name.startswith("criterion ")]
        shown["requirement_loss_on_longer_tasks"] = finished(record) and any(criteria) and not all(criteria)
    return shown


def harness_processes(binary: Path) -> list[int]:
    """Linux: the pids still running the harness binary (scoring waits until there are none)."""
    if not sys.platform.startswith("linux"):
        return []
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(a and Path(a.decode(errors="replace")).name == binary.name for a in argv[:2]):
            found.append(int(proc.name))
    return found


def cmd_score(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    frozen = frozen_record()
    rules = load_yaml(BEHAVIOURS)
    ledger_dir = out / "ledger"
    ledger = AttemptLedger(ledger_dir, frozen)
    purged = retention.purge(ledger_dir, frozen)
    newly_scored = []
    if hidden_root is not None:
        alive = harness_processes(raw.harness_binary())
        if alive:
            raise SystemExit(f"refused: harness processes still run ({alive}): score only after every model run")
        for attempt in ledger.attempts().values():
            if attempt.status == "valid" and attempt.run_id not in runner.scores(ledger_dir):
                newly_scored.append(runner.score_run(frozen, ledger_dir=ledger_dir, run_id=attempt.run_id,
                                                     hidden_root=hidden_root)["run_id"])
    scored = runner.scores(ledger_dir)
    runs = []
    for a in sorted(ledger.attempts().values(), key=lambda a: a.registered["at"]):
        if a.status != "valid":
            continue
        record = json.loads((ledger.runs / (a.run_id.split("/", 1)[1] + ".json")).read_text(encoding="utf-8"))
        score = (scored.get(a.run_id) or {}).get("score") or record["outcome"].get("score")
        checks = {c["name"]: c["ok"] for c in (score or {}).get("checks") or []}
        changed = meaningful(record["outcome"].get("changed_paths") or [], rules)
        in_scope = all(matches(p, rules["allowed_paths"]) for p in changed)
        runs.append({"run": a.run_id, "case": record["case"]["id"], "scored": score is not None,
                     "task_correct": bool((score or {}).get("passed")) and in_scope if score else None,
                     "in_scope": in_scope, "finished": finished(record),
                     "truncated_why": record["outcome"].get("truncated_why"),
                     "behaviours": tree_behaviours(record, rules, checks) if score else None,
                     "session_db": record["outcome"].get("session_db"),
                     "charged_usd": record["cost"].get("charged_usd")})
    shown = sorted({b for r in runs for b, v in (r["behaviours"] or {}).items() if v})
    pending = [r["run"] for r in runs if not r["scored"]]
    summary = {"experiment": frozen["experiment"], "valid_runs": len(runs), "newly_scored": newly_scored,
               "unscored": pending, "retention_purged": purged, "tree_behaviours_shown": shown,
               "session_behaviours": "scored later by the F19 session-database reader (delta D2) from the kept "
                                     "databases, under the definitions frozen in the preregistration",
               "ceiling_state": "behaviours_shown" if shown else
               "not_run (pending: the session-observable behaviours)" + (" and unscored runs" if pending else ""),
               "runs": runs}
    (out / "score.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    say(**summary)
    return 0


def cmd_purge(args: argparse.Namespace, out: Path) -> int:
    say(purged=retention.purge(out / "ledger", frozen_record()))
    return 0


# ---------------------------------------------------------------------------------------------- run (every model step)


def cmd_run(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    arm_host_clean(out, hidden_root)
    if not base_present():
        cmd_fetch(args)
    code = cmd_check(args, out, hidden_root)
    if code != 0:
        return code
    if not FROZEN.exists():
        cmd_freeze(args)
    floor = cmd_floor(args, out, hidden_root)
    if floor != 0:
        say(stopped="floor", detail="the profile did not pass the floor: no ceiling cell runs (rubric.md §2)")
        return floor
    return cmd_ceiling(args, out, hidden_root)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    try:
        hidden_root = hidden.take_root()  # first: nothing started below inherits it
    except Invalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    ap = argparse.ArgumentParser(prog="python qualify.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="run state, outside every repository (default: per-user data dir)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="the dry run: no provider call")
    c.add_argument("--no-launch", action="store_true", help="skip starting the pinned OpenCode and containment")
    f = sub.add_parser("fetch", help="download the pinned upstream fixture")
    f.add_argument("--again", action="store_true")
    z = sub.add_parser("freeze")
    z.add_argument("--by", required=True)
    sub.add_parser("floor")
    ce = sub.add_parser("ceiling")
    ce.add_argument("--deadline-s", type=float, default=1800)
    sub.add_parser("score")
    sub.add_parser("purge")
    r = sub.add_parser("run", help="fetch, check, freeze, floor, ceiling (every step that runs a model)")
    r.add_argument("--by", required=True)
    r.add_argument("--deadline-s", type=float, default=1800)
    r.add_argument("--no-launch", action="store_true")
    r.add_argument("--again", action="store_true")
    args = ap.parse_args(argv)
    experiment = load_yaml(PLAN)["experiment"]
    out = (args.out or default_out(experiment)).expanduser().resolve()
    try:
        if args.cmd == "check":
            return cmd_check(args, out, hidden_root)
        if args.cmd == "fetch":
            return cmd_fetch(args)
        if args.cmd == "freeze":
            return cmd_freeze(args)
        if args.cmd == "floor":
            return cmd_floor(args, out, hidden_root)
        if args.cmd == "ceiling":
            return cmd_ceiling(args, out, hidden_root)
        if args.cmd == "score":
            return cmd_score(args, out, hidden_root)
        if args.cmd == "purge":
            return cmd_purge(args, out)
        return cmd_run(args, out, hidden_root)
    except Invalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

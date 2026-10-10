"""The lower-bound qualification lane (agent-effectiveness adoption, delta D3; synthesis §13.4): one driver.

Evaluation tooling, not product code. It drives the shared F19 instrument (``eval/aew_eval``) and AEW's live lane;
it adds no measurement of its own beyond the tree-observable behaviours of the rubric (``rubric.md`` §4).

    python qualify.py check            # the dry run: no provider is called, nothing is spent
    python qualify.py fetch            # DOWNLOADS the pinned upstream fixture (Python-Markdown 3.11.0, ~2.5 MB)
    python qualify.py freeze --by NAME # fills the case and oracle hashes and freezes prereg.yaml
    python qualify.py floor            # the live lane: bridge handshake + typed submit (calls the provider)
    python qualify.py ceiling          # the preregistered raw cells (calls the provider)
    python qualify.py score            # the tree-observable behaviours, and the profile record they establish
    python qualify.py run --by NAME    # all of the above in order, stopping at the first gate that fails

``check`` validates the profiles, the cases, the overlay and the oracles, runs every oracle against the seeded
starting point (its criteria must fail) and against the reference solution (every check must pass), records the
upstream test suite's baseline, and starts the pinned OpenCode as far as resolving the pinned model in its served
catalog; it stops before a session exists, so no prompt is sent. Without the fetched fixture or the hidden root it
does what it can and says what it skipped.

The hidden root (``AEW_EVAL_HIDDEN_ROOT``: the private repository's ``eval/lower-bound-qualification``) is taken out
of the environment once, at start, so nothing this driver starts inherits it. Run state (the attempt ledger, every
run's scratch directory with its harness session database, the live lane's results) goes under ``--out``, outside
every repository: by default ``%LOCALAPPDATA%/aew-eval/<experiment>`` (``~/.local/share/aew-eval/...`` elsewhere).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # the AEW checkout
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "src"))

from aew_eval import arms, fixture, hidden, prereg, profiles, runner  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PLAN = HERE / "prereg.yaml"
FROZEN = HERE / "prereg.frozen.yaml"
PROFILES = HERE / "profiles.yaml"
RUBRIC = HERE / "rubric.md"
UPSTREAM = HERE / "upstream.yaml"
FIXTURE = HERE / "fixture"
BASE = FIXTURE / "base"
RECEIPT = FIXTURE / "base.receipt.json"  # written by fetch, next to the base (both git-ignored)
CASES = {cid: FIXTURE / f"{cid}.yaml" for cid in ("LBQ-1", "LBQ-2", "LBQ-3")}
PLACEHOLDER = "placeholder-not-a-credential"  # lets the catalog list a paid provider's models; never sent anywhere
LIVE_TEST = "tests/live/test_opencode_model_live.py::test_a_free_model_carries_out_real_launch_contracts"

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
    print(json.dumps(fields, sort_keys=True, default=str))


def overlay_paths() -> list[str]:
    root = FIXTURE / "overlay"
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def upstream() -> dict[str, Any]:
    return load_yaml(UPSTREAM)


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
    return {p.relative_to(ref).as_posix(): fixture.normalized(p.read_bytes()) for p in ref.rglob("*") if p.is_file()}


def plan_with_hashes(plan: dict[str, Any], hidden_root: Path | None) -> dict[str, Any]:
    """The plan with every case's fixture hash and oracle commitment, and the rubric's hash, filled in."""
    out = json.loads(json.dumps(plan))
    by_id = {c["id"]: c for c in out["cases"]}
    for cid, path in CASES.items():
        case = fixture.load(path)
        commitment = case.manifest["hidden_sha256"]
        if commitment is None:
            raise Invalid(f"case {cid} has no oracle commitment (hidden_sha256): run `check` with the hidden root")
        if hidden_root is not None:
            actual = hidden.Oracle.locate(hidden_root, cid).sha256
            if actual != commitment:
                raise Invalid(f"case {cid}: its manifest commits to oracle {commitment[:12]}, the hidden root holds "
                              f"{actual[:12]}")
        by_id[cid].update(sha256=fixture.case_sha256(case), hidden_sha256=commitment)
    out["scoring"]["rubric_sha256"] = fixture._digest({"rubric.md": RUBRIC.read_bytes()})  # noqa: SLF001
    return out


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
    listed = set(upstream()["paths_touching_overlay_dirs"])
    clash = sorted(set(paths) & listed)
    if base_present():
        clash = sorted(set(clash) | {p for p in paths if (BASE / p).exists()})
    if clash:
        raise Invalid(f"overlay files would replace upstream files: {clash}")
    report["overlay"] = {"files": len(paths), "collisions_with_upstream": 0,
                         "checked_against": "the fetched base" if base_present() else "upstream.yaml's listing"}


def check_profiles(report: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    records = profiles.load(PROFILES)
    refs = {r["ref"]: r for r in records}
    for role, ref in plan["profiles"]["roles"].items():
        if ref not in refs:
            raise Invalid(f"role {role} runs {ref}, which has no profile record in {PROFILES.name}")
        arm = next(a for a in plan["arms"] if a["config"].get("role") == role)
        if sorted(arm["config"]["provider_env"]) != sorted(refs[ref]["credential_env"]):
            raise Invalid(f"arm {arm['id']} passes {arm['config']['provider_env']}, profile {refs[ref]['id']} "
                          f"needs {refs[ref]['credential_env']}")
    report["profiles"] = {r["id"]: r["qualification_state"] for r in records}
    return records


def check_oracles(report: dict[str, Any], hidden_root: Path | None) -> None:
    if hidden_root is None:
        report["oracles"] = "skipped: AEW_EVAL_HIDDEN_ROOT is not set"
        return
    out: dict[str, Any] = {}
    for cid, path in CASES.items():
        oracle = hidden.Oracle.locate(hidden_root, cid)
        committed = load_yaml(path)["hidden_sha256"]
        for seed_rel, overlay_rel in SEED_COPIES.items():
            if oracle.files.get(seed_rel) != fixture.normalized((FIXTURE / "overlay" / overlay_rel).read_bytes()):
                raise Invalid(f"oracle {cid}: its copy {seed_rel} is not the overlay's {overlay_rel}")
        out[cid] = {"sha256": oracle.sha256, "committed": committed == oracle.sha256}
    report["oracles"] = out


def validate_oracles(report: dict[str, Any], hidden_root: Path | None) -> None:
    """Each oracle against the seeded starting point and against the reference solution (needs the fixture)."""
    if hidden_root is None or not base_present():
        report["oracle_validation"] = "skipped: needs the fetched fixture and AEW_EVAL_HIDDEN_ROOT"
        return
    results: dict[str, Any] = {}
    for cid, path in CASES.items():
        snap = fixture.snapshot(fixture.load(path))
        start = fixture.starting_files(snap, seeded=False)
        oracle = hidden.Oracle.locate(hidden_root, cid)
        with tempfile.TemporaryDirectory(prefix=f"aew-lbq-{cid}-") as tmp:
            seeded = hidden.score(oracle, write_files(start, Path(tmp) / "seeded"))
            ref = hidden.score(oracle, write_files({**start, **reference_files(hidden_root, cid)}, Path(tmp) / "ref"))
        failed = {c["name"] for c in seeded["checks"] if not c["ok"]}
        ref_failed = {c["name"]: c["detail"] for c in ref["checks"] if not c["ok"]}
        results[cid] = {"seed_fails_as_designed": failed == SEED_FAILS[cid], "seed_failed": sorted(failed),
                        "reference_passes": ref["passed"], "reference_failed": ref_failed}
        if failed != SEED_FAILS[cid] or not ref["passed"]:
            report["oracle_validation"] = results
            raise Invalid(f"oracle {cid} does not behave as designed: {results[cid]}")
    report["oracle_validation"] = results


def upstream_baseline(report: dict[str, Any]) -> None:
    """The upstream suite on the seeded starting point: which tests fail before any model works (the rubric's
    distractor is the one seeded failure; anything else is the environment's, recorded here before freezing)."""
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
    """Start the pinned OpenCode as each profile's arm would, as far as resolving the model in the served catalog.
    No session is created and no prompt is sent: nothing reaches a model. A paid provider's variable is replaced by a
    placeholder for the check, whether or not a real one is set, so the catalog lists that provider's models
    (OpenCode lists a provider only when its variable is set) and no real credential reaches the dry run's server."""
    from aew.harness.opencode import adapter as oc
    from aew.harness.opencode.adapter import HarnessIncompatible

    headless = arms._headless()  # noqa: SLF001 (the raw arm's own session class)
    out: dict[str, Any] = {"binary": str(oc.binary_command()[-1])}
    out["binary_sha256"] = arms._sha256_file(Path(out["binary"]))  # noqa: SLF001
    worker_refs = set(plan["profiles"]["roles"].values())
    for record in records:
        profile = arms.model_ref(record["ref"])
        names = record["credential_env"]
        placeholder = {n: PLACEHOLDER for n in names}
        saved = {n: os.environ.get(n) for n in placeholder}
        os.environ.update(placeholder)
        state = Path(tempfile.mkdtemp(prefix="aew-lbq-launch-"))
        (state / "repo").mkdir()
        session = headless.HeadlessSession(state / "raw")
        entry: dict[str, Any] = {"in_prereg": record["ref"] in worker_refs,
                                 "credential": "placeholder" if placeholder else "none needed"}
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


def cmd_check(args: argparse.Namespace, hidden_root: Path | None) -> int:
    report: dict[str, Any] = {"at": now(), "aew_commit": fixture.git(ROOT, "rev-parse", "HEAD")[:12]}
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
            hashed = plan_with_hashes(plan, hidden_root)
            prereg.check(hashed)
            report["prereg"] = {"valid": True, "schedule": [o["cell"] for o in prereg.schedule(hashed)]}
        else:
            report["fixture"] = "not fetched: `qualify.py fetch` downloads it (operator approval)"
            report["prereg"] = "schema checked after the fixture is fetched (its case hashes come from it)"
        validate_oracles(report, hidden_root)
        upstream_baseline(report)
        if not args.no_launch:
            harness_launch(report, plan, records)
    except Invalid as exc:
        report["refused"] = str(exc)
        say(**report)
        return 1
    say(**report)
    return 0


# ---------------------------------------------------------------------------------------------- fetch (downloads)


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download the pinned upstream at its tag, prove the commit and tree, and export its files as the fixture base."""
    up = upstream()
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
        listed = fixture.git(clone, "ls-files", "-z").split("\0")
        files = [p for p in listed if p]
        if len(files) != up["file_count"]:
            raise SystemExit(f"refused: {len(files)} files at the pinned tree, expected {up['file_count']}")
        if BASE.exists():
            shutil.rmtree(BASE)
        for rel in files:
            out = BASE / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(clone / rel, out)
    receipt = {"url": up["url"], "tag": up["tag"], "commit": commit, "tree": tree, "files": len(files),
               "content_sha256": fixture._digest(fixture._read_tree(BASE, "base")), "fetched_at": now()}  # noqa: SLF001
    RECEIPT.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    say(fetched=True, receipt=receipt)
    return 0


# ---------------------------------------------------------------------------------------------- freeze


def cmd_freeze(args: argparse.Namespace, hidden_root: Path | None) -> int:
    if FROZEN.exists():
        say(frozen=False, reason=f"{FROZEN.name} exists: a frozen preregistration is never refrozen",
            canonical_sha256=prereg.verify(load_yaml(FROZEN)))
        return 0
    if hidden_root is None or not base_present():
        raise SystemExit("refused: freezing needs the fetched fixture and AEW_EVAL_HIDDEN_ROOT (run `check` first)")
    frozen = prereg.freeze(plan_with_hashes(load_yaml(PLAN), hidden_root), by=args.by)
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


def cmd_floor(args: argparse.Namespace, out: Path) -> int:
    frozen = load_yaml(FROZEN)
    prereg.verify(frozen)
    record = worker_profile(frozen)
    names = record["credential_env"]
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"refused: {', '.join(missing)} is not set (profile {record['id']} needs it)")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    where = out / "floor" / stamp
    where.mkdir(parents=True)
    results = where / "results.jsonl"
    env = {k: v for k, v in os.environ.items() if k != hidden.ENV}
    env.update(AEW_LIVE_OPENCODE_MODEL=record["ref"], AEW_LIVE_RESULTS=str(results),
               AEW_LIVE_MODEL_TRIALS=str(args.trials), PYTHONPATH=str(ROOT / "src"))
    if names:
        env["AEW_LIVE_PROVIDER_KEY_ENV"] = names[0]
    res = subprocess.run([sys.executable, "-m", "pytest", "--live", LIVE_TEST, "-p", "no:xdist", "-p",
                          "no:cacheprovider", "-q", "--basetemp", str(where / "tmp")], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    (where / "pytest.log").write_text(res.stdout + "\n" + res.stderr, encoding="utf-8")
    trials = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if results.exists() else []
    verdict = {**floor_verdict(trials), "pytest_exit": res.returncode, "results": str(results),
               "session_state": str(where / "tmp"), "profile": record["id"]}
    if res.returncode != 0:  # AEW's side failed an assertion: the floor is not established either way
        verdict["state"] = "aew_side_failure" if trials else "not_run"
    (where / "verdict.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    say(floor=verdict)
    return 0 if verdict["state"] == "passed" else 3


# ---------------------------------------------------------------------------------------------- ceiling (provider)


def cell_name(cell: str, n: int) -> str:
    return cell.replace("/", "-") + (f"-retry{n}" if n else "")


def cmd_ceiling(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    frozen = load_yaml(FROZEN)
    prereg.verify(frozen)
    if hidden_root is None:
        raise SystemExit("refused: the ceiling cells are scored by hidden oracles: set AEW_EVAL_HIDDEN_ROOT")
    ledger_dir, work = out / "ledger", out / "work"
    ledger = AttemptLedger(ledger_dir, frozen)
    budget = float(frozen["profiles"]["budget_usd"])
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
            spent = sum(run_cost(ledger, a) for a in ledger.attempts().values())
            if spent + caps[entry["arm"]] > budget:
                say(stopped="budget", spent_usd=round(spent, 4), budget_usd=budget, next_cell=cell)
                return 3
            name = cell_name(cell, len(attempts))
            try:
                record = runner.run_cell(frozen, ledger_dir=ledger_dir, cell=cell, cases=CASES, work=work,
                                         run_name=name, retry_of=latest.run_id if latest else None,
                                         deadline_s=float(args.deadline_s), hidden_root=hidden_root)
            except runner.Refused as exc:
                raise SystemExit(f"refused (nothing registered): {exc}") from None
            say(run=record["run_id"], validity=record["validity"], cost=record["cost"].get("provider_reported_usd"),
                passed=(record["outcome"].get("score") or {}).get("passed"))
    say(ceiling="done", ledger=str(ledger_dir), status=ledger.status())
    return 0


# ---------------------------------------------------------------------------------------------- score


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def meaningful(changed: list[str], rules: dict[str, Any]) -> list[str]:
    """The changed paths, without what running the code leaves behind (bytecode, caches)."""
    return [p for p in changed if not matches(p, rules["ignored_paths"])]


def tree_behaviours(record: dict[str, Any], rules: dict[str, Any]) -> dict[str, bool]:
    """rubric.md §4: the behaviours a run's final tree shows. The session-database ones wait for the F19 reader."""
    changed = meaningful(record["outcome"].get("changed_paths") or [], rules)
    checks = {c["name"]: c["ok"] for c in (record["outcome"].get("score") or {}).get("checks") or []}
    case = record["case"]["id"]
    shown = {"bad_search_root_selection": any(matches(p, rules["decoy_paths"]) for p in changed),
             "difficulty_recovering_after_distraction":
                 any(matches(p, rules["distractor_paths"]) for p in changed)
                 or checks.get("structure: the link policy runs after the inline processor") is False}
    if case in rules["required_sites"]:
        hit = [any(fnmatch.fnmatchcase(p, site) for p in changed) for site in rules["required_sites"][case]]
        shown["incomplete_cross_file_changes"] = any(hit) and not all(hit)
    if case == "LBQ-3":
        criteria = [ok for name, ok in checks.items() if name.startswith("criterion ")]
        ended = record["outcome"].get("harness_outcome") == "ended"
        shown["requirement_loss_on_longer_tasks"] = ended and any(criteria) and not all(criteria)
    return shown


def run_cost(ledger: AttemptLedger, attempt: Any) -> float:
    if attempt.finalized is None:
        return 0.0
    record = json.loads((ledger.runs / (attempt.run_id.split("/", 1)[1] + ".json")).read_text(encoding="utf-8"))
    return float(record["cost"].get("provider_reported_usd") or 0)


def cmd_score(args: argparse.Namespace, out: Path) -> int:
    frozen = load_yaml(FROZEN)
    rules = load_yaml(HERE / "behaviours.yaml")
    ledger = AttemptLedger(out / "ledger", frozen)
    runs = []
    for a in sorted(ledger.attempts().values(), key=lambda a: a.registered["at"]):
        if a.status != "valid":
            continue
        record = json.loads((ledger.runs / (a.run_id.split("/", 1)[1] + ".json")).read_text(encoding="utf-8"))
        changed = meaningful(record["outcome"].get("changed_paths") or [], rules)
        in_scope = all(matches(p, rules["allowed_paths"]) for p in changed)
        runs.append({"run": a.run_id, "case": record["case"]["id"],
                     "task_correct": bool((record["outcome"].get("score") or {}).get("passed")) and in_scope,
                     "in_scope": in_scope, "behaviours": tree_behaviours(record, rules),
                     "session_db": record["outcome"].get("session_db"),
                     "cost_usd": record["cost"].get("provider_reported_usd")})
    shown = sorted({b for r in runs for b, v in r["behaviours"].items() if v})
    summary = {"experiment": frozen["experiment"], "valid_runs": len(runs), "tree_behaviours_shown": shown,
               "session_behaviours": "pending: the F19 session-database reader (delta D2) scores rubric.md §4's "
                                     "session metrics from each run's retained database",
               "ceiling_state": "behaviours_shown" if shown else "not_run (pending the session metrics)",
               "runs": runs}
    (out / "score.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    say(**summary)
    return 0


# ---------------------------------------------------------------------------------------------- run (all)


def cmd_run(args: argparse.Namespace, out: Path, hidden_root: Path | None) -> int:
    steps = []
    if not base_present():
        steps.append(("fetch", cmd_fetch(args)))
    steps.append(("check", cmd_check(args, hidden_root)))
    if steps[-1][1] != 0:
        return steps[-1][1]
    if not FROZEN.exists():
        steps.append(("freeze", cmd_freeze(args, hidden_root)))
    floor = cmd_floor(args, out)
    if floor != 0:
        say(stopped="floor", detail="the profile did not pass the floor: the ceiling is not run (rubric.md §2)")
        return floor
    code = cmd_ceiling(args, out, hidden_root)
    cmd_score(args, out)
    return code


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    hidden_root = hidden.take_root()  # first: nothing started below inherits it
    ap = argparse.ArgumentParser(prog="python qualify.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="run state, outside every repository (default: per-user data dir)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="the dry run: no provider call")
    c.add_argument("--no-launch", action="store_true", help="skip starting the pinned OpenCode")
    f = sub.add_parser("fetch", help="download the pinned upstream fixture")
    f.add_argument("--again", action="store_true")
    z = sub.add_parser("freeze")
    z.add_argument("--by", required=True)
    fl = sub.add_parser("floor")
    fl.add_argument("--trials", type=int, default=2)
    ce = sub.add_parser("ceiling")
    ce.add_argument("--deadline-s", type=float, default=1800)
    sub.add_parser("score")
    r = sub.add_parser("run", help="fetch, check, freeze, floor, ceiling, score")
    r.add_argument("--by", required=True)
    r.add_argument("--trials", type=int, default=2)
    r.add_argument("--deadline-s", type=float, default=1800)
    r.add_argument("--no-launch", action="store_true")
    r.add_argument("--again", action="store_true")
    args = ap.parse_args(argv)
    experiment = load_yaml(PLAN)["experiment"]
    out = (args.out or default_out(experiment)).resolve()
    if args.cmd == "check":
        return cmd_check(args, hidden_root)
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "freeze":
        return cmd_freeze(args, hidden_root)
    if args.cmd == "floor":
        return cmd_floor(args, out)
    if args.cmd == "ceiling":
        return cmd_ceiling(args, out, hidden_root)
    if args.cmd == "score":
        return cmd_score(args, out)
    return cmd_run(args, out, hidden_root)


if __name__ == "__main__":
    sys.exit(main())

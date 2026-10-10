"""The evaluation instrument's third slice, the hidden-evaluator channel (register F19; the evaluation component design
v0.2, §5 and §8 step 3; decisions 5 and 7): an oracle outside every repository a model works in, committed to by its
content hash and read once, refused before registration when it changed or its held-out case was exposed, never
reachable through the environment an arm starts processes from, and scored after the arm from a private copy, in an
isolated process the model's code never runs in, with a result the model's program cannot forge or turn into a retry.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, hidden, prereg, runner  # noqa: E402

FIX = {"write": "calc.py", "content": "def add(a, b):\n    return a + b\n"}
WRONG = {"write": "NOTES.md", "content": "looked at it\n"}
CHECKS = '''
import sys

def checks(tree, run):
    ran = run([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
    yield "add(2, 3) is 5", ran.stdout.strip() == "5", ran
'''


def make_oracle(hidden_root: Path, cid: str = "C1", checks: str = CHECKS) -> Path:
    oracle = hidden_root / "cases" / cid / "oracle"
    oracle.mkdir(parents=True)
    (oracle / "checks.py").write_text(checks, encoding="utf-8", newline="\n")
    return oracle


def make_case(root: Path, commitment: str | None, cid: str = "C1") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": cid, "family": "demo", "fixture": {"base": "base"},
                "hidden_sha256": commitment, "control_of": None}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def plan_for(case_path: Path, *, steps: list | None = None, held_out: bool = False) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": "Does the reference fix the bug?",
        "arms": [{"id": "ref", "kind": "scripted", "description": "the reference edit",
                  "config": {"steps": [FIX] if steps is None else steps}}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case),
                   "hidden_sha256": case.manifest["hidden_sha256"], "control_of": None}],
        "profiles": {"roles": {"lead": "none"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "fixed", "metrics": [{"name": "fixed", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement", "runner_lost"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [case.id] if held_out else [],
        "scoring": {"hidden_channel": "aew_eval.hidden", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "an exposed case leaves the held-out pool", "amendment_policy": "a change is a new id",
    }
    return prereg.freeze(record, by="tester")


def setup(tmp_path: Path, *, checks: str = CHECKS, **plan) -> tuple[dict, Path, Path]:
    secret = tmp_path / "private"
    oracle = make_oracle(secret, checks=checks)
    case = make_case(tmp_path / "case", hidden.content_sha256(oracle))
    return plan_for(case, **plan), case, secret


def run(f: dict, case_path: Path, tmp_path: Path, name: str = "r1", **kw) -> dict:
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name=name, **kw)


def scored(tmp_path: Path, steps: list, checks: str = CHECKS) -> dict:
    f, case, secret = setup(tmp_path, steps=steps, checks=checks)
    record = run(f, case, tmp_path, hidden_root=secret)
    assert record["validity"]["status"] == "valid", record  # a scoring failure is never a retryable invalid run
    return record["outcome"]["score"]


def nothing_registered(tmp_path: Path) -> bool:
    return not (tmp_path / "ledger" / "attempts.jsonl").exists()


def tree_with(tmp_path: Path, files: dict[str, str]) -> Path:
    tree = tmp_path / "tree"
    for rel, text in files.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_text(text, encoding="utf-8", newline="\n")
    return tree


# ---------------------------------------------------------------------------------------------- the oracle

def test_the_oracle_hash_covers_its_content_and_ignores_line_ends(tmp_path):
    oracle = make_oracle(tmp_path / "h")
    first = hidden.content_sha256(oracle)
    checks = oracle / "checks.py"
    checks.write_bytes(checks.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout of the private repository
    assert hidden.content_sha256(oracle) == first == hidden.Oracle.locate(tmp_path / "h", "C1").sha256
    (oracle / "reference").mkdir()
    (oracle / "reference" / "calc.py").write_text("x\n", encoding="utf-8")
    assert hidden.content_sha256(oracle) != first


def test_an_oracle_without_checks_is_refused(tmp_path):
    (tmp_path / "h" / "cases" / "C1" / "oracle").mkdir(parents=True)
    (tmp_path / "h" / "cases" / "C1" / "oracle" / "notes.md").write_text("x\n", encoding="utf-8")
    with pytest.raises(hidden.Invalid, match="no checks.py"):
        hidden.Oracle.locate(tmp_path / "h", "C1")


def test_taking_the_root_removes_it_from_the_environment(tmp_path):
    env = {hidden.ENV: str(tmp_path), "OTHER": "x"}
    assert hidden.take_root(env) == tmp_path.resolve() and env == {"OTHER": "x"}
    assert hidden.take_root({}) is None


# ---------------------------------------------------------------------------------------------- the runner

def test_a_hidden_case_is_scored_by_its_oracle_after_the_arm(tmp_path):
    f, case, secret = setup(tmp_path)
    record = run(f, case, tmp_path, hidden_root=secret)
    score = record["outcome"]["score"]
    assert record["validity"]["status"] == "valid", record
    assert score["passed"] is True and score["failure"] is None
    assert score["hidden_sha256"] == record["case"]["hidden_sha256"]
    assert [c["name"] for c in score["checks"]] == ["add(2, 3) is 5"]


def test_a_failing_change_scores_false_and_stays_valid(tmp_path):
    assert scored(tmp_path, [WRONG])["passed"] is False


def test_no_arm_sees_the_hidden_root(tmp_path, monkeypatch):
    """Decision: the root is evaluator-only. It is out of the environment before the arm runs, so nothing the arm
    starts can inherit it."""
    f, case, secret = setup(tmp_path)
    monkeypatch.setenv(hidden.ENV, str(secret))
    seen = {}
    real = arms.ScriptedArm.run

    def spy(self, repo, config, *, deadline_s, task=None):
        seen["root"] = os.environ.get(hidden.ENV)
        return real(self, repo, config, deadline_s=deadline_s, task=task)

    monkeypatch.setattr(arms.ScriptedArm, "run", spy)
    record = run(f, case, tmp_path)  # the root comes from the environment
    assert seen == {"root": None} and record["outcome"]["score"]["passed"] is True


def test_a_relative_root_is_resolved(tmp_path, monkeypatch):
    """Review 6: a root named by a relative (or 8.3, or linked) path scores rather than refusing every oracle."""
    f, case, _ = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run(f, case, tmp_path, hidden_root=Path("private"))["outcome"]["score"]["passed"] is True


@pytest.mark.parametrize("problem", ["no_root", "changed", "exposed"])
def test_a_cell_with_an_unusable_oracle_is_refused_before_anything_is_counted(tmp_path, problem):
    f, case, secret = setup(tmp_path, held_out=problem == "exposed")
    oracle = secret / "cases" / "C1" / "oracle"
    if problem == "changed":
        (oracle / "checks.py").write_text(CHECKS + "\n# weakened\n", encoding="utf-8")
    if problem == "exposed":
        (oracle.parent / "exposure.yaml").write_text(yaml.safe_dump([{"at": "2026-10-06", "by": "tester",
                                                                       "what": "shown to a model"}]),
                                                     encoding="utf-8")
    with pytest.raises(runner.Refused, match={"no_root": "AEW_EVAL_HIDDEN_ROOT", "changed": "not the preregistered",
                                              "exposed": "has been exposed"}[problem]):
        run(f, case, tmp_path, hidden_root=None if problem == "no_root" else secret)
    assert nothing_registered(tmp_path)


def test_a_held_out_case_without_an_oracle_is_checked_for_exposure_too(tmp_path):
    """Review 8: exposure is a property of every held-out case, not only of one scored by an oracle."""
    case = make_case(tmp_path / "case", None)
    f = plan_for(case, held_out=True)
    with pytest.raises(runner.Refused, match="held out"):
        run(f, case, tmp_path)  # no root: its exposure cannot be checked
    secret = tmp_path / "private"
    (secret / "cases" / "C1").mkdir(parents=True)
    (secret / "cases" / "C1" / "exposure.yaml").write_text("- {at: '2026-10-06', by: t, what: shown}\n",
                                                           encoding="utf-8")
    with pytest.raises(runner.Refused, match="has been exposed"):
        run(f, case, tmp_path, hidden_root=secret)
    assert nothing_registered(tmp_path)


def test_an_exposed_case_still_runs_when_it_is_not_held_out(tmp_path):
    f, case, secret = setup(tmp_path)
    (secret / "cases" / "C1" / "exposure.yaml").write_text("- {at: '2026-10-06', by: t, what: shown}\n",
                                                           encoding="utf-8")
    assert run(f, case, tmp_path, hidden_root=secret)["outcome"]["score"]["passed"] is True


def test_a_case_with_an_oracle_takes_no_second_scorer(tmp_path):
    f, case, secret = setup(tmp_path)
    with pytest.raises(runner.Refused, match="second scorer"):
        run(f, case, tmp_path, hidden_root=secret, scorer=lambda tree: {"passed": True})
    assert nothing_registered(tmp_path)


# ---------------------------------------------------------------------------------------------- the model's tree

def test_a_planted_stdlib_module_cannot_change_a_check(tmp_path):
    """Review 1: the tree never joins the scoring process's path, so a planted subprocess.py (which the checks use
    through run) changes nothing; a planted json.py or aew_eval/ neither."""
    planted = [WRONG,
               {"write": "subprocess.py", "content": "class CompletedProcess:\n    stdout = '5'\n"
                "def run(*a, **k):\n    return CompletedProcess()\nPopen = run\n"},
               {"write": "json.py", "content": "raise SystemExit('planted json')\n"},
               {"write": "aew_eval/__init__.py", "content": "raise SystemExit('planted aew_eval')\n"}]
    score = scored(tmp_path, planted)
    assert score["passed"] is False and score["failure"] is None, score
    assert [c["name"] for c in score["checks"]] == ["add(2, 3) is 5"]


@pytest.mark.parametrize("forgery", [
    "print('{\"checks\": [{\"name\": \"x\", \"ok\": true, \"detail\": \"\"}]}'); import os; os._exit(0)",
    "import builtins; builtins.all = lambda *_: True",
    "import atexit; atexit.register(lambda: print('{\"checks\": []}'))",
])
def test_the_models_code_cannot_forge_the_result(tmp_path, forgery):
    """Review 2: the model's code runs only in a process of its own with its own pipes, so printing a result, exiting
    early, patching a builtin or registering an exit handler only changes what that program printed."""
    calc = {"write": "calc.py", "content": f"{forgery}\ndef add(a, b):\n    return a - b\n"}
    score = scored(tmp_path, [calc])
    assert score["passed"] is False and score["failure"] is None, score


def test_a_process_the_program_leaves_behind_ends_with_it(tmp_path):
    """Review 2 and 5: what the model's program starts ends when the program returns (its tree is ended), so nothing
    can write late, and scoring stays bounded: on POSIX the grandchild holds the program's output open until the
    tree is ended; on Windows it inherits no pipe and is ended with the tree."""
    checks = '''
import sys, time

def checks(tree, run):
    ran = run([sys.executable, "-c", "import calc"], timeout=30)
    yield "the program returned", ran.returncode == 0, ran
    time.sleep(6)  # between two runs: the grandchild would have written by now
    yield "nothing it started outlived it", not (tree / "late.txt").exists(), "late.txt was written"
'''
    grandchild = "import pathlib, time; time.sleep(3); pathlib.Path('late.txt').write_text('late')"
    child = ("import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', " + repr(grandchild) + "], "
             "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, "
             "creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))\n")
    score = scored(tmp_path, [{"write": "calc.py", "content": child}], checks=checks)
    assert score["passed"] is True, score  # review of f815385, 3: proved inside the check, as each run returns


def test_the_model_cannot_turn_a_failure_into_a_retry(tmp_path):
    """Review 3: a check broken by the model's program (SystemExit, a hang) is a counted failed score, never a retryable
    invalid_measurement."""
    checks = '''
import sys

def checks(tree, run):
    ran = run([sys.executable, "-c", "import calc"])
    yield "imported", ran.returncode == 0, ran
    raise SystemExit(0)
'''
    score = scored(tmp_path, [FIX], checks=checks)
    assert score["passed"] is False and score["checks"][-1]["name"] == "checks raised", score


def test_scoring_that_overruns_is_a_failed_score(tmp_path):
    secret = tmp_path / "private"
    make_oracle(secret, checks="import time\ndef checks(tree, run):\n    time.sleep(60)\n    yield 'x', True, ''\n")
    oracle = hidden.Oracle.locate(secret, "C1")
    started = time.monotonic()
    score = hidden.score(oracle, tree_with(tmp_path, {"calc.py": "x = 1\n"}), timeout_s=3)
    assert time.monotonic() - started < 30
    assert score["passed"] is False and score["failure"] == "SCORING_TIMEOUT"


def test_the_scoring_process_never_learns_the_root_and_the_oracle_never_touches_the_disk(tmp_path):
    """Review 4, and the review of 7c743ff (1, 2): the oracle reaches the scoring process on its standard input, so its
    arguments, working directory and environment name neither the private corpus nor an oracle file, and the checks
    see their reference material only as ORACLE_FILES."""
    secret = tmp_path / "private"
    checks = (
        "import os, sys\n"
        "def checks(tree, run):\n"
        "    seen = ' '.join([*sys.argv, os.getcwd(), *os.environ.keys(), *os.environ.values()])\n"
        f"    yield 'the root is not named', {str(secret)!r} not in seen, seen[-200:]\n"
        "    yield 'no oracle file', '__file__' not in globals() and 'checks.py' not in seen, ''\n"
        "    yield 'reference in memory', ORACLE_FILES['reference/expected.txt'] == b'5\\n', list(ORACLE_FILES)\n")
    path = make_oracle(secret, checks=checks)
    (path / "reference").mkdir()
    (path / "reference" / "expected.txt").write_text("5\n", encoding="utf-8", newline="\n")
    oracle = hidden.Oracle.locate(secret, "C1")
    score = hidden.score(oracle, tree_with(tmp_path, {"calc.py": "x = 1\n"}))
    assert score["passed"] is True, score


def test_the_oracle_scores_from_the_bytes_it_was_hashed_from(tmp_path):
    """Review 4: an oracle changed on disk after it was hashed (and perhaps changed back) cannot score."""
    secret = tmp_path / "private"
    path = make_oracle(secret)
    oracle = hidden.Oracle.locate(secret, "C1")
    (path / "checks.py").write_text("def checks(tree, run):\n    yield 'always', True, ''\n", encoding="utf-8")
    score = hidden.score(oracle, tree_with(tmp_path, {"calc.py": "def add(a, b):\n    return a - b\n"}))
    assert score["passed"] is False and [c["name"] for c in score["checks"]] == ["add(2, 3) is 5"]


def test_the_models_programs_get_an_allow_listed_environment(tmp_path, monkeypatch):
    """Review of 7c743ff, 5: a key in the evaluator's environment never reaches the model's program."""
    monkeypatch.setenv("AEW_TEST_PROVIDER_KEY", "not-a-real-key")
    checks = ("import sys\n"
              "def checks(tree, run):\n"
              "    ran = run([sys.executable, '-c', 'import os; print(sorted(os.environ))'])\n"
              "    yield 'no key', 'AEW_TEST_PROVIDER_KEY' not in ran.stdout and ran.returncode == 0, ran\n")
    secret = tmp_path / "private"
    make_oracle(secret, checks=checks)
    score = hidden.score(hidden.Oracle.locate(secret, "C1"), tree_with(tmp_path, {"calc.py": "x = 1\n"}))
    assert score["passed"] is True, score


def test_a_held_out_case_is_scored_only_where_scoring_is_contained(tmp_path, monkeypatch):
    """Review of 7c743ff, 1: where the model's programs cannot be contained (Windows, or Linux without bubblewrap) a
    program could search the host for the private corpus, so a held-out case is refused there before anything is
    counted; elsewhere it runs."""
    f, case, secret = setup(tmp_path, held_out=True)
    monkeypatch.setattr(hidden, "scoring_contained", lambda: False)
    with pytest.raises(runner.Refused, match="cannot be contained"):
        run(f, case, tmp_path, hidden_root=secret)
    assert nothing_registered(tmp_path)
    monkeypatch.setattr(hidden, "scoring_contained", lambda: True)
    assert run(f, case, tmp_path, hidden_root=secret)["outcome"]["score"]["passed"] is True


@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                    reason="Linux bubblewrap containment (Windows refuses held-out scoring instead)")
def test_on_linux_the_models_programs_are_scored_in_a_sandbox(tmp_path):
    """Reviews of 7c743ff (1, 3) and f815385 (blocker): the model's program runs in its own pid namespace (the runner
    is not among the processes it sees), and the hidden root's whole private repository (another held-out case and the
    .git that holds every oracle included) and the ledger are masked. The private repository lives under the home
    directory here, outside /tmp, which the sandbox replaces anyway."""
    import uuid

    private = Path.home() / ".cache" / f"aew-eval-test-{uuid.uuid4().hex}"
    try:
        (private / ".git").mkdir(parents=True)
        (private / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        secret = private / "eval"
        make_oracle(secret, cid="OTHER-HELD-OUT")
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        (ledger / "attempts.jsonl").write_text("x\n", encoding="utf-8")
        probe = ("import json, os; pids = [int(p) for p in os.listdir('/proc') if p.isdigit()]; "
                 "seen = lambda p: os.listdir(p) if os.path.isdir(p) else []; "  # masked, or absent from the sandbox
                 f"print(json.dumps([len(pids), {os.getpid()} in pids, seen({str(secret)!r}), "
                 f"seen({str(secret / 'cases')!r}), seen({str(private / '.git')!r}), seen({str(ledger)!r})]))")
        checks = ("import json, sys\n"
                  "def checks(tree, run):\n"
                  f"    ran = run([sys.executable, '-c', {probe!r}])\n"
                  "    last = ran.stdout.strip().splitlines()[-1] if ran.stdout else ran\n"
                  "    yield 'probe', ran.returncode == 0, last\n")
        make_oracle(secret, checks=checks)
        score = hidden.score(hidden.Oracle.locate(secret, "C1"), tree_with(tmp_path, {"calc.py": "x = 1\n"}),
                             hide=[ledger])
        assert score["passed"] is True and score["contained"] is True, score
        count, runner_seen, root, cases, git_dir, ledger_listing = json.loads(score["checks"][0]["detail"])
        assert count <= 3 and runner_seen is False, score
        assert root == [] and cases == [] and git_dir == [] and ledger_listing == [], score
    finally:
        shutil.rmtree(private, ignore_errors=True)


def private_checkouts(base: Path) -> tuple[Path, Path]:
    """A private repository with one committed oracle, and a linked worktree of it: (main, worktree)."""
    main, linked = base / "main", base / "linked"
    make_oracle(main / "eval", cid="HELD")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "corpus"),
                 ("worktree", "add", "-q", str(linked))):
        fixture.git(main, *args)
    return main, linked


def test_a_worktree_root_masks_its_object_store_and_every_checkout(tmp_path):
    """Review of 5d64bf4: in a linked worktree `.git` is a file; the object store and the main checkout (and every
    other linked worktree) hold the corpus too, so all of them are masked, whichever checkout the root is in."""
    main, linked = private_checkouts(tmp_path)
    expected = {linked.resolve(), (main / ".git").resolve(), main.resolve()}
    assert expected <= set(hidden.private_repository(linked / "eval"))
    assert {main.resolve(), linked.resolve()} <= set(hidden.private_repository(main / "eval"))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert hidden.private_repository(plain) == [plain]
    # Review of e71f1f3: git 2.48+ (worktree.useRelativePaths) records a linked worktree relative to its own gitdir
    # file, which is where it resolves from, whatever the runner's working directory.
    other = tmp_path / "other-wt"
    (other / "eval").mkdir(parents=True)
    record = main / ".git" / "worktrees" / "other-wt"
    record.mkdir(parents=True)
    (record / "gitdir").write_text("../../../../other-wt/.git\n", encoding="utf-8")
    assert other.resolve() in hidden.private_repository(main / "eval")
    assert other.resolve() in hidden.private_repository(linked / "eval")


@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                    reason="Linux bubblewrap containment (Windows refuses held-out scoring instead)")
def test_on_linux_a_worktree_roots_object_store_is_masked_too(tmp_path):
    """Review of 5d64bf4: with the hidden root in a linked worktree under the home directory, the main checkout's
    object store and working tree are as invisible to the model's program as the worktree itself."""
    import uuid

    base = Path.home() / ".cache" / f"aew-eval-test-{uuid.uuid4().hex}"
    try:
        main, linked = private_checkouts(base)
        probe = ("import json, os; seen = lambda p: sorted(os.listdir(p)) if os.path.isdir(p) else []; "
                 f"print(json.dumps([seen({str(main / '.git' / 'objects')!r}), seen({str(main)!r}), "
                 f"seen({str(linked)!r})]))")
        checks = ("import sys\n"
                  "def checks(tree, run):\n"
                  f"    ran = run([sys.executable, '-c', {probe!r}])\n"
                  "    last = ran.stdout.strip().splitlines()[-1] if ran.stdout else ran\n"
                  "    yield 'probe', ran.returncode == 0, last\n")
        make_oracle(linked / "eval", checks=checks)
        score = hidden.score(hidden.Oracle.locate(linked / "eval", "C1"), tree_with(tmp_path, {"calc.py": "x = 1\n"}))
        assert score["passed"] is True and score["contained"] is True, score
        assert json.loads(score["checks"][0]["detail"]) == [[], [], []], score
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_score_records_whether_it_was_contained(tmp_path):
    """Review of f815385, 2: outside Linux the model's programs are not contained while scored, so the score says so
    (not tamper-evident), and an analysis that needs that property can exclude it."""
    secret = tmp_path / "private"
    make_oracle(secret)
    score = hidden.score(hidden.Oracle.locate(secret, "C1"), tree_with(tmp_path, {"calc.py": FIX["content"]}))
    assert score["passed"] is True and score["contained"] is sys.platform.startswith("linux")


@pytest.mark.parametrize("stdout", ['{"checks": []}{"checks": []}',
                                    '{"checks": [{"name": "x", "ok": 1, "detail": ""}]}',
                                    '{"checks": [], "passed": true}', "not json", ""])
def test_only_one_well_formed_result_counts(stdout):
    assert hidden._parse(stdout) is None  # noqa: SLF001
    assert hidden._parse('{"checks": [{"name": "x", "ok": true, "detail": ""}]}')  # noqa: SLF001

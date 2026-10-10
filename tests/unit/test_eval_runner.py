"""The evaluation instrument's second slice (register F19; the evaluation component design v0.2, §2 and §8 step 2):
fixtures read once, hashed and built with a platform-independent result, and the runner that runs one preregistered
cell: a changed or unsound input is refused before anything is counted, the attempt is registered before the arm
runs, nothing reads the scratch repository through git after the arm, and the result is finalized once.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, prereg, runner  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FIX = {"write": "calc.py", "content": "def add(a, b):\n    return a + b\n"}


def make_case(root: Path, *, cid: str = "C1", overlay: bool = True, seeded: bool = False) -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    (root / "base" / "README.md").write_text("# calc\n", encoding="utf-8", newline="\n")
    fx: dict = {"base": "base"}
    if overlay:
        (root / "overlay").mkdir()
        (root / "overlay" / "NOTES.md").write_text("the bug: add subtracts\n", encoding="utf-8", newline="\n")
        fx["overlay"] = "overlay"
    if seeded:
        (root / "seeded").mkdir()
        (root / "seeded" / "calc.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8",
                                                 newline="\n")
        fx["seeded"] = "seeded"
    manifest = {"schema": "aew/eval-case/v1", "id": cid, "family": "demo", "fixture": fx, "hidden_sha256": None,
                "control_of": None}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def set_fixture(path: Path, fx: dict) -> Path:
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump({**manifest, "fixture": fx}), encoding="utf-8")
    return path


def plan_for(case_path: Path, *, steps: list | None = None, kind: str = "scripted", config: dict | None = None,
             **over) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": "Does the reference fix the bug?",
        "arms": [{"id": "ref", "kind": kind, "description": "the reference edit",
                  "config": config if config is not None else {"steps": [FIX] if steps is None else steps}}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": {"lead": "none"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "fixed", "metrics": [{"name": "fixed", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement", "runner_lost"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id",
    }
    record.update(over)
    return prereg.freeze(record, by="tester")


def run(f: dict, case_path: Path, tmp_path: Path, name: str = "r1", **kw) -> dict:
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name=name, **kw)


def nothing_registered(tmp_path: Path) -> bool:
    return not (tmp_path / "ledger" / "attempts.jsonl").exists()


def link_dir(link: Path, target: Path) -> None:
    """A directory link: a junction on Windows (no privilege needed), a symbolic link elsewhere."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


# ---------------------------------------------------------------------------------------------- fixtures

def test_a_case_hash_covers_the_manifest_and_every_tree_and_ignores_line_ends(tmp_path):
    path = make_case(tmp_path / "c")
    first = fixture.case_sha256(fixture.load(path))
    crlf = tmp_path / "c" / "base" / "calc.py"
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout
    assert fixture.case_sha256(fixture.load(path)) == first
    (tmp_path / "c" / "overlay" / "NOTES.md").write_text("changed\n", encoding="utf-8")
    second = fixture.case_sha256(fixture.load(path))
    assert second != first
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump({**manifest, "family": "other"}), encoding="utf-8")
    assert fixture.case_sha256(fixture.load(path)) not in (first, second)


def test_a_fixture_builds_from_its_snapshot_with_lf_and_one_commit(tmp_path):
    path = make_case(tmp_path / "c", seeded=True)
    crlf = tmp_path / "c" / "base" / "calc.py"
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
    snap = fixture.snapshot(fixture.load(path))
    crlf.write_text("changed after the snapshot\n", encoding="utf-8")  # never read again
    repo = tmp_path / "repo"
    start = fixture.build(snap, repo)
    assert (repo / "calc.py").read_bytes() == b"def add(a, b):\n    return a - b\n"
    assert fixture.changed_paths(start, fixture.files_of(repo)) == []
    assert fixture.git(repo, "rev-list", "--count", "HEAD") == "1"
    with pytest.raises(Invalid, match="fresh directory"):
        fixture.build(snap, repo)
    seeded = tmp_path / "seeded"
    fixture.build(snap, seeded, seeded=True)
    assert "b + a" in (seeded / "calc.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(("fx", "match"), [
    ({"base": "nowhere"}, "not a directory"),
    ({"base": "../elsewhere"}, "inside the case directory"),
    ({"base": "."}, "inside the case directory"),  # the manifest and the other trees would be part of the start
    ({"base": "base", "overlay": "base/sub"}, "lies inside"),
])
def test_a_case_whose_trees_are_missing_outside_or_nested_is_refused(tmp_path, fx, match):
    path = make_case(tmp_path / "c", overlay=False)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "c" / "base" / "sub").mkdir()
    with pytest.raises(Invalid, match=match):
        fixture.load(set_fixture(path, fx))


@pytest.mark.parametrize("name", [".git/config", "pkg/.GIT/x", "GIT~1/config", "git~12/x", "CON", "aux.txt", "dot.",
                                  "pipe|x", "tab\there", "bell\x07"])
def test_a_fixture_path_that_is_repository_metadata_or_unportable_is_refused(tmp_path, name):
    path = make_case(tmp_path / "c", overlay=False)
    with pytest.raises(Invalid):
        fixture.safe_relative(name, "test")
    # On disk too, where this platform can hold the name exactly as spelled (Windows cannot hold most of these).
    target = tmp_path / "c" / "base" / name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        held = target.name in os.listdir(target.parent)
    except OSError:
        held = False
    if held:
        with pytest.raises(Invalid):
            fixture.snapshot(fixture.load(path))


def test_paths_differing_only_in_case_are_refused(tmp_path):
    path = make_case(tmp_path / "c")
    (tmp_path / "c" / "overlay" / "Calc.py").write_text("x\n", encoding="utf-8")  # base has calc.py
    with pytest.raises(Invalid, match="differ only in case"):
        fixture.snapshot(fixture.load(path))


def test_directories_differing_only_in_case_or_a_file_against_a_directory_are_refused(tmp_path):
    """One directory on Windows, two on Linux; or a build that fails after registering (PR #100 re-review, R-3, R-4)."""
    path = make_case(tmp_path / "c")
    (tmp_path / "c" / "base" / "Src").mkdir()
    (tmp_path / "c" / "base" / "Src" / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "c" / "overlay" / "src").mkdir()
    (tmp_path / "c" / "overlay" / "src" / "b.py").write_text("b\n", encoding="utf-8")
    with pytest.raises(Invalid, match="differ only in case"):
        fixture.snapshot(fixture.load(path))
    path2 = make_case(tmp_path / "d")
    (tmp_path / "d" / "overlay" / "calc.py").mkdir()  # base has the file calc.py
    (tmp_path / "d" / "overlay" / "calc.py" / "x.py").write_text("x\n", encoding="utf-8")
    with pytest.raises(Invalid, match="a file in one tree and a directory in another"):
        fixture.snapshot(fixture.load(path2))


def test_link_detection_needs_nothing_newer_than_python_3_11():
    """Path.is_junction exists from 3.12; the project supports 3.11 (PR #100 re-review, R-1)."""
    source = (ROOT / "eval" / "aew_eval" / "fixture.py").read_text(encoding="utf-8")
    assert ".is_junction(" not in source


def test_a_link_or_junction_in_a_fixture_is_refused(tmp_path):
    path = make_case(tmp_path / "c", overlay=False)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.txt").write_text("not the case's\n", encoding="utf-8")
    link_dir(tmp_path / "c" / "base" / "linked", tmp_path / "outside")
    with pytest.raises(Invalid, match="link"):
        fixture.snapshot(fixture.load(path))


def test_the_runners_git_ignores_the_callers_git_environment(tmp_path, monkeypatch):
    """A GIT_DIR (or any GIT_* variable) set for another repository never reaches the runner's git (PR #100)."""
    other = tmp_path / "other"
    other.mkdir()
    fixture.git(other, "init", "-q", "--template=")
    config_before = (other / ".git" / "config").read_bytes()
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "stray-index"))
    snap = fixture.snapshot(fixture.load(make_case(tmp_path / "c")))
    fixture.build(snap, tmp_path / "repo")
    assert (tmp_path / "repo" / ".git").is_dir() and (other / ".git" / "config").read_bytes() == config_before
    assert not (tmp_path / "stray-index").exists()


# ---------------------------------------------------------------------------------------------- the runner

def test_a_scripted_cell_runs_end_to_end_and_is_finalized_once(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    seen: dict = {}

    def scorer(tree: Path) -> dict:
        seen["tree"] = tree
        return {"fixed": "a + b" in (tree / "calc.py").read_text(encoding="utf-8")}

    record = run(f, case_path, tmp_path, scorer=scorer)
    validate("aew/eval-run/v1", record)
    assert record["validity"] == {"status": "valid", "reason_code": None}
    assert record["outcome"]["changed_paths"] == ["calc.py"] and record["outcome"]["score"] == {"fixed": True}
    assert record["outcome"]["safety"]["checkout_untouched"] is True  # this checkout is a git checkout
    repo = tmp_path / "work" / "r1" / "repo"
    assert repo not in seen["tree"].parents and not (seen["tree"] / ".git").exists()  # the export is outside it
    ledger = AttemptLedger(tmp_path / "ledger", f)
    assert ledger.status() == {"demo/r1": "valid"} and ledger.verify() == []
    with pytest.raises(runner.Refused, match="already has attempt"):  # one cell, one counted attempt
        run(f, case_path, tmp_path, name="r2")


def test_changed_paths_and_the_export_need_no_git_and_hold_any_name(tmp_path):
    """Collection reads plain files: a non-ASCII name is recorded as itself, and an export-ignore attribute (which
    git archive would honour) hides nothing from the scorer (PR #100 review, findings 6 and 7)."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, steps=[FIX, {"write": "café.py", "content": "x = 1\n"},
                                   {"write": ".gitattributes", "content": "calc.py export-ignore\n"}])
    record = run(f, case_path, tmp_path, scorer=lambda tree: {"calc": (tree / "calc.py").is_file()})
    assert record["outcome"]["changed_paths"] == [".gitattributes", "café.py", "calc.py"]
    assert record["outcome"]["score"] == {"calc": True}


@pytest.mark.parametrize("rel", ["/etc/x", "C:/x", "\\\\host\\share\\x", "../escape.txt", "a/../../x", ".git/config",
                                 "sub/.git/hooks/pre-commit", "a\\b"])
def test_a_scripted_step_outside_the_work_tree_or_in_git_metadata_is_refused_before_registering(tmp_path, rel):
    """The runner's own git can never be pointed at a configuration an arm wrote (PR #100 review, finding 1)."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, steps=[{"write": rel, "content": "[core]\n\tfsmonitor = evil\n"}])
    with pytest.raises(runner.Refused):
        run(f, case_path, tmp_path)
    assert nothing_registered(tmp_path)


def test_an_arm_that_rewrites_git_metadata_at_run_time_never_reaches_the_runners_git(tmp_path, monkeypatch):
    """Even an arm that writes .git/config while it runs (a model, not a checked script) cannot make collection run
    a program: nothing reads the scratch repository through git after the arm."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    marker = tmp_path / "ran.txt"

    class Hostile:
        kind = "scripted"

        def check(self, config, snap):
            pass

        def run(self, repo, config, *, deadline_s, task=None):
            cmd = f'{sys.executable} -c "open(r\'{marker}\', \'w\').write(\'x\')"'.replace("\\", "/")
            with (repo / ".git" / "config").open("a", encoding="utf-8") as fh:
                fh.write(f"[core]\n\tfsmonitor = {cmd}\n[filter \"x\"]\n\tclean = {cmd}\n")
            (repo / ".gitattributes").write_text("* filter=x\n", encoding="utf-8")
            return arms.ArmResult()

    monkeypatch.setitem(arms.ARMS, "scripted", Hostile())
    record = run(f, case_path, tmp_path, scorer=lambda tree: {})
    assert record["validity"]["status"] == "valid" and not marker.exists()
    assert ".gitattributes" in record["outcome"]["changed_paths"]


def test_a_changed_fixture_an_unbuilt_arm_or_a_bad_configuration_is_refused_before_anything_is_counted(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    (tmp_path / "case" / "base" / "calc.py").write_text("changed after freezing\n", encoding="utf-8")
    with pytest.raises(runner.Refused, match="fixture of C1 changed"):
        run(f, case_path, tmp_path)
    assert nothing_registered(tmp_path)
    for n, (kind, config, match) in enumerate([
            ("aew", {"steps": []}, "not built in the shared runner yet"),
            ("scripted", {"seeded": True, "steps": []}, "no seeded tree"),
            ("scripted", {"steps": [{"write": "x.py", "delete": "y.py"}]}, "one of write or delete"),
            ("scripted", {"steps": "write"}, "a list")]):
        where = tmp_path / f"t{n}"
        cp = make_case(where / "case")
        with pytest.raises(runner.Refused, match=match):
            run(plan_for(cp, kind=kind, config=config), cp, where)
        assert nothing_registered(where)


def test_a_scratch_root_inside_a_git_work_tree_is_refused(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    for inside in (ROOT / ".eval-scratch-test", tmp_path / "case"):  # the AEW checkout; any other work tree
        if inside == tmp_path / "case":
            fixture.git(inside, "init", "-q", "--template=")
        with pytest.raises(runner.Refused, match="lies inside the git work tree"):
            runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                            cases={"C1": case_path}, work=inside, run_name="r1")
    assert nothing_registered(tmp_path) and not (ROOT / ".eval-scratch-test").exists()


def test_an_arm_that_fails_is_counted_as_an_invalid_measurement_and_may_be_retried(tmp_path, monkeypatch):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)

    class Fails:
        kind = "scripted"

        def check(self, config, snap):
            pass

        def run(self, repo, config, *, deadline_s, task=None):
            raise RuntimeError("the harness crashed")

    monkeypatch.setitem(arms.ARMS, "scripted", Fails())
    record = run(f, case_path, tmp_path)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "RUNNER_ERROR:RuntimeError"}
    assert "the harness crashed" in record["outcome"]["error"]
    retry = run(f, case_path, tmp_path, name="r1b", retry_of="demo/r1")
    assert retry["validity"]["status"] == "invalid_measurement"
    assert AttemptLedger(tmp_path / "ledger", f).attempts()["demo/r1"].retries == ["demo/r1b"]


def test_a_runner_killed_while_the_arm_runs_leaves_a_visible_attempt(tmp_path, monkeypatch):
    """The attempt is registered before the arm runs: a runner that dies there leaves runner_lost, never nothing."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)

    class Dies:
        kind = "scripted"

        def check(self, config, snap):
            pass

        def run(self, repo, config, *, deadline_s, task=None):
            raise KeyboardInterrupt  # not an Exception: the runner itself stops here, as a kill would

    monkeypatch.setitem(arms.ARMS, "scripted", Dies())
    with pytest.raises(KeyboardInterrupt):
        run(f, case_path, tmp_path)
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/r1": "runner_lost"}


def test_the_command_line_says_whether_anything_was_counted(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    frozen_path = tmp_path / "prereg.yaml"
    prereg.dump(f, frozen_path)
    base = [sys.executable, "-m", "aew_eval.runner", str(frozen_path), "--case", f"C1={case_path}",
            "--ledger", str(tmp_path / "ledger"), "--work", str(tmp_path / "work")]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "eval")}

    def cli(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([*base, *extra], env=env, capture_output=True, text=True, encoding="utf-8",
                              timeout=120, creationflags=NO_WINDOW)

    cell = f["assignment"]["order"][0]["cell"]
    ok = cli("--cell", cell, "--name", "cli1")
    assert ok.returncode == runner.EXIT_VALID and "demo/cli1: valid" in ok.stdout, ok.stderr
    bad = cli("--cell", "C9/ref/1", "--name", "cli2")
    assert bad.returncode == runner.EXIT_REFUSED and "nothing registered" in bad.stderr
    again = cli("--cell", cell, "--name", "cli3")  # the cell is counted already
    assert again.returncode == runner.EXIT_REFUSED and "already has attempt" in again.stderr
    lines = [json.loads(x) for x in (tmp_path / "ledger" / "attempts.jsonl").read_text().splitlines()]
    assert [x["run_id"] for x in lines] == ["demo/cli1", "demo/cli1"]  # registered, finalized; nothing else


# ---------------------------------------------------------------------------------------------- re-review of PR #100

def test_collection_keeps_exact_bytes_and_keeps_links_and_special_files_apart(tmp_path, monkeypatch):
    """R-5 and R-7: a file whose text begins like a link record is exported; a line-end-only rewrite is a change and
    is exported as written; a special file is recorded without being opened (a FIFO would block)."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    import stat as st

    class Writes:
        kind = "scripted"

        def check(self, config, snap):
            pass

        def run(self, repo, config, *, deadline_s, task=None):
            (repo / "looks.txt").write_bytes(b"link -> not a link\n")
            (repo / "README.md").write_bytes(b"# calc\r\n")  # CRLF only
            (repo / "pipe").write_bytes(b"")
            return arms.ArmResult()

    real_lstat = os.lstat

    def lstat(p, *a, **k):  # the "pipe" is a FIFO on every platform, as far as collection can tell
        res = real_lstat(p, *a, **k)
        if str(p).endswith("pipe"):
            return os.stat_result((st.S_IFIFO | 0o644, *res[1:]))
        return res

    monkeypatch.setitem(arms.ARMS, "scripted", Writes())
    monkeypatch.setattr(fixture.os, "lstat", lstat)
    seen: dict = {}
    record = run(f, case_path, tmp_path, scorer=lambda tree: seen.update(
        looks=(tree / "looks.txt").read_bytes(), readme=(tree / "README.md").read_bytes(),
        pipe=(tree / "pipe").exists()) or {})
    assert record["validity"]["status"] == "valid", record["outcome"]
    assert record["outcome"]["changed_paths"] == ["README.md", "looks.txt", "pipe"]
    assert seen == {"looks": b"link -> not a link\n", "readme": b"# calc\r\n", "pipe": False}


def test_an_8_3_short_name_of_git_metadata_is_refused_before_registering(tmp_path):
    """R-2: GIT~1 is .git on an NTFS volume with short names."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, steps=[{"write": "GIT~1/config", "content": "[core]\n"}])
    with pytest.raises(runner.Refused, match=r"\.git component"):
        run(f, case_path, tmp_path)
    assert nothing_registered(tmp_path)


def test_the_command_line_never_says_nothing_was_registered_when_something_was(tmp_path, monkeypatch, capsys):
    """R-6: an error after registering exits 4 (the attempt is runner_lost); an unreadable input before it exits 1."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    frozen_path = tmp_path / "prereg.yaml"
    prereg.dump(f, frozen_path)
    base = [str(frozen_path), "--case", f"C1={case_path}", "--ledger", str(tmp_path / "ledger"),
            "--work", str(tmp_path / "work"), "--cell", f["assignment"]["order"][0]["cell"]]
    assert runner.main([str(tmp_path / "missing.yaml"), *base[1:], "--name", "x"]) == runner.EXIT_REFUSED
    assert runner.main([str(frozen_path), "--case", f"C1={tmp_path / 'nope.yaml'}", *base[3:], "--name", "y"]) \
        == runner.EXIT_REFUSED
    assert nothing_registered(tmp_path)

    def broken(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(AttemptLedger, "finalize", broken)
    assert runner.main([*base, "--name", "z"]) == runner.EXIT_LOST
    assert "failed after registering" in capsys.readouterr().err
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/z": "runner_lost"}


def test_a_registration_that_fails_after_its_line_is_written_is_not_called_a_refusal(tmp_path, monkeypatch):
    """N1: the line is in the ledger, so the attempt is runner_lost, and the runner says so (exit 4, not 1)."""
    from aew_eval import ledger as L

    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    real_append = L.AttemptLedger._append

    def append_then_fail(self, line):
        real_append(self, line)
        raise OSError("fsync failed")

    monkeypatch.setattr(L.AttemptLedger, "_append", append_then_fail)
    with pytest.raises(RuntimeError, match="runner_lost"):
        run(f, case_path, tmp_path)
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/r1": "runner_lost"}


def test_a_preregistration_that_is_not_a_valid_mapping_is_a_refusal(tmp_path):
    """N2: an unusable preregistration is refused before anything is registered, never 'failed after registering'."""
    case_path = make_case(tmp_path / "case")
    for bad in ([], {"schema": "aew/eval-prereg/v1"}):
        with pytest.raises(runner.Refused):
            runner.run_cell(bad, ledger_dir=tmp_path / "ledger", cell="C1/ref/1", cases={"C1": case_path},
                            work=tmp_path / "work", run_name="r1")
    assert nothing_registered(tmp_path)


def test_a_reparse_point_that_is_not_a_link_is_recorded_as_special(tmp_path, monkeypatch):
    """N3: os.readlink refuses some reparse points (an app alias, a socket): the entry is recorded, not a failure."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "alias").write_text("x", encoding="utf-8")
    monkeypatch.setattr(fixture, "is_link", lambda p: p.name == "alias")

    def readlink(p):
        raise ValueError("not a symbolic link")

    monkeypatch.setattr(fixture.os, "readlink", readlink)
    tree = fixture.files_of(repo)
    assert tree.other == {"alias": fixture.SPECIAL} and tree.files == {}


def test_reusing_a_run_name_is_a_refusal_not_a_lost_attempt(tmp_path):
    """D1: the ledger refuses a run id it holds before writing anything; the earlier attempt is untouched."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    run(f, case_path, tmp_path)
    with pytest.raises(runner.Refused, match="already registered"):
        runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                        cases={"C1": case_path}, work=tmp_path / "work2", run_name="r1")
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/r1": "valid"}

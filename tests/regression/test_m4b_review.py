"""Findings of the M4-B independent reviews (2026-10-04) that change code.

R-P1: AEW's own git, reading and committing files an agent wrote, ran programs git configuration names (filters,
diff drivers, textconv, merge drivers, hooks, fsmonitor, signing). A configured command can point at a script an agent
can edit, so AEW would run agent-controlled code outside every sandbox. Every AEW git call now switches them off unless
execution policy trusts the driver, and a dispatch whose base needs an untrusted filter is refused with the way
forward.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import bounded_git
import bounds
import pytest
from aewflow import sample_project

from aew.harness import procs
from aew.snapshot import fingerprint as F
from aew.util import dump_yaml, load_yaml
from aew.workspace import git
from aew.workspace import integration as I

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def plain_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """git as an operator runs it: no AEW overrides, under a bound (tests/helpers/bounded_git.py)."""
    return bounded_git.plain_git(*args, cwd=cwd, env={**os.environ, **GIT_ENV})


class Hostile:
    """A repository whose configuration routes files through every kind of configured program, each running
    ``tool.sh``: a script inside the worktree, so the agent that edits the worktree controls what it does."""

    def __init__(self, root: Path) -> None:
        self.repo = root / "repo"
        self.marks = root / "marks"
        self.repo.mkdir()
        self.marks.mkdir()
        plain_git("init", "-q", "-b", "main", cwd=self.repo)
        tool = self.repo / "tool.sh"
        tool.write_text(f'#!/bin/sh\necho ran >> "{self.marks.as_posix()}/$AEW_KIND"\ncat\n', encoding="utf-8",
                        newline="\n")
        tool.chmod(0o755)
        (self.repo / ".gitattributes").write_text("*.dat filter=x diff=x merge=x\n*.prc filter=p\n",
                                                  encoding="utf-8", newline="\n")
        (self.repo / "a.dat").write_text("one\n", encoding="utf-8", newline="\n")
        (self.repo / "b.prc").write_text("one\n", encoding="utf-8", newline="\n")
        plain_git("add", "-A", cwd=self.repo)
        plain_git("commit", "-qm", "base", cwd=self.repo)
        self.base = plain_git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        hooks = self.repo / "hooks"
        hooks.mkdir()
        for h in ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit"):
            (hooks / h).write_text(f'#!/bin/sh\necho {h} >> "{self.marks.as_posix()}/hook"\n', encoding="utf-8",
                                   newline="\n")
            (hooks / h).chmod(0o755)
        run = "sh ./tool.sh"
        for key, value in {
            "filter.x.clean": f"AEW_KIND=clean {run}", "filter.x.smudge": f"AEW_KIND=smudge {run}",
            "filter.x.required": "true", "filter.p.process": f"AEW_KIND=process {run}",
            "diff.x.command": f"AEW_KIND=extdiff {run}", "diff.x.textconv": f"AEW_KIND=textconv {run}",
            "diff.external": f"AEW_KIND=external {run}", "merge.x.driver": f"AEW_KIND=merge {run} %O %A %B",
            "core.hooksPath": str(hooks), "core.fsmonitor": str(tool),
            "commit.gpgSign": "true", "gpg.program": str(tool),
        }.items():
            plain_git("config", key, value, cwd=self.repo)

    def agent_edits(self) -> None:
        """What a contained implementer may do: change its files, including the script the drivers run."""
        (self.repo / "a.dat").write_text("two\n", encoding="utf-8", newline="\n")
        (self.repo / "b.prc").write_text("two\n", encoding="utf-8", newline="\n")
        with (self.repo / "tool.sh").open("a", encoding="utf-8", newline="\n") as f:
            f.write("# edited by the agent\n")

    def ran(self) -> list[str]:
        return sorted(p.name for p in self.marks.iterdir())


@pytest.fixture
def hostile(tmp_path):
    git.trust_drivers(())
    yield Hostile(tmp_path)
    git.trust_drivers(())


# Long enough for a loaded runner to start Python, short enough to run in every regression lane.
HOLDER_BOUND_S = 15.0
HOLDER_LIVES_S = 60  # how long the holder would hold on: a wait for it shows as more than the bound, not as a hang
HOLDER = f"""import os, time
from pathlib import Path
Path("held.pid").write_text(str(os.getpid()))
print("holding", flush=True)
time.sleep({HOLDER_LIVES_S})
"""


def test_plain_git_fails_by_name_while_a_grandchild_holds_its_output_and_leaves_nothing_running(tmp_path):
    """A program git started keeps git's output open and doesn't end. The bound still fires and names the command with
    what it had said, the wait isn't for the holder, and the holder is gone. On Windows `subprocess.run`'s `timeout=`
    would wait for the holder here."""
    (tmp_path / "holder.py").write_text(HOLDER, encoding="utf-8")
    plain_git("init", "-q", cwd=tmp_path)
    plain_git("config", "alias.hold", f'!"{Path(sys.executable).as_posix()}" holder.py', cwd=tmp_path)
    started = time.monotonic()
    with pytest.raises(bounds.BoundExpired) as expired:
        bounded_git.plain_git("hold", cwd=tmp_path, env=os.environ, seconds=HOLDER_BOUND_S)
    assert time.monotonic() - started < HOLDER_LIVES_S - 15, "the bound waited for the holder"
    said = str(expired.value)
    assert "bound plain_git" in said and "'hold'" in said and "holding" in said, said
    assert not procs.pid_alive(int((tmp_path / "held.pid").read_text())), "the holder outlived the bound"


def test_plain_git_reaps_what_it_ended_before_closing_the_tree(tmp_path, monkeypatch):
    """Review of #394, 1: on Linux a zombie still counts as its process group, and `ProcessTree.close` waits for the
    group, so an unreaped git spent that wait on every expiry. Read off the order, so that no clock decides it."""
    (tmp_path / "holder.py").write_text(HOLDER, encoding="utf-8")
    plain_git("init", "-q", cwd=tmp_path)
    plain_git("config", "alias.hold", f'!"{Path(sys.executable).as_posix()}" holder.py', cwd=tmp_path)
    at_close = []

    class Recording(procs.ProcessTree):
        def spawn(self, *args, **kwargs):
            self.spawned = super().spawn(*args, **kwargs)
            return self.spawned

        def close(self):
            at_close.append(self.spawned.returncode)
            super().close()

    monkeypatch.setattr(bounded_git.procs, "ProcessTree", Recording)
    with pytest.raises(bounds.BoundExpired):
        bounded_git.plain_git("hold", cwd=tmp_path, env=os.environ, seconds=HOLDER_BOUND_S)
    assert at_close and at_close[0] is not None, "git wasn't reaped when the tree closed"


def test_plain_git_gives_its_programs_no_stdin_to_wait_on(tmp_path):
    """The script the hostile repository's drivers run ends in `cat`. Under a process whose stdin stays open, as an
    xdist worker's can, `cat` must still see an end of input."""
    plain_git("init", "-q", cwd=tmp_path)
    plain_git("config", "alias.read", "!cat", cwd=tmp_path)
    helpers = Path(bounded_git.__file__).parent
    code = (f"import os, sys; sys.path.insert(0, {str(helpers)!r}); import bounded_git; "
            f"bounded_git.plain_git('read', cwd={str(tmp_path)!r}, env=os.environ, seconds={HOLDER_BOUND_S})")
    child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        code = child.wait(timeout=HOLDER_LIVES_S)  # stdin stays open: only `cat` reading elsewhere lets this end
        assert code == 0, child.stderr.read().decode(errors="replace")[-2000:]
    finally:
        child.kill()
        child.stdin.close()
        child.stderr.close()
        child.wait()


def test_the_hostile_repository_runs_its_programs_under_plain_git(hostile):
    """The control: without AEW's overrides, the same operations run the agent's script."""
    hostile.agent_edits()
    plain_git("add", "-A", cwd=hostile.repo)
    plain_git("diff", "--cached", cwd=hostile.repo)
    plain_git("-c", "commit.gpgSign=false", "commit", "-q", "--no-verify", "-m", "x", cwd=hostile.repo)
    assert {"clean", "process", "hook"} <= set(hostile.ran()), hostile.ran()


def test_aews_git_runs_no_configured_program_on_agent_written_files(hostile):
    """R-P1: the snapshot, the changed paths, the reviewer's diff, the prepare-time commit, log and merge run no
    configured program, and commit what the agent wrote, byte for byte."""
    hostile.agent_edits()
    F.working_tree_id(hostile.repo)
    F.changed_paths(hostile.repo, hostile.base)
    commit = I.commit_workspace(hostile.repo, "aew(T-1): edit")
    git.git("diff", "--no-color", hostile.base, commit, cwd=hostile.repo)
    git.git("log", "-p", "-1", commit, cwd=hostile.repo)
    git.git("show", commit, cwd=hostile.repo)
    git.git("checkout", "-q", "-b", "side", hostile.base, cwd=hostile.repo)
    (hostile.repo / "a.dat").write_text("three\n", encoding="utf-8", newline="\n")
    git.git("commit", "-qam", "side", "--no-verify", cwd=hostile.repo)
    merged = git.git("merge", "-q", "--no-edit", "main", cwd=hostile.repo, check=False)
    assert hostile.ran() == []
    assert merged.returncode != 0  # an untrusted custom merge driver is a conflict for the Lead, never a guess
    assert git.out("cat-file", "-p", f"{commit}:a.dat", cwd=hostile.repo) == "two"


def test_a_trusted_driver_runs(hostile):
    git.trust_drivers(["x"])
    hostile.agent_edits()
    F.working_tree_id(hostile.repo)
    assert "clean" in hostile.ran() and "process" not in hostile.ran()  # p stays switched off


def test_a_driver_configured_while_aew_runs_is_switched_off_at_once(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    plain_git("init", "-q", "-b", "main", cwd=repo)
    (repo / ".gitattributes").write_text("*.dat filter=late\n", encoding="utf-8", newline="\n")
    (repo / "a.dat").write_text("one\n", encoding="utf-8", newline="\n")
    F.working_tree_id(repo)  # AEW has read this repository's configuration once
    marks = tmp_path / "late"
    plain_git("config", "filter.late.clean", f"sh -c 'touch \"{marks.as_posix()}\"; cat'", cwd=repo)
    F.working_tree_id(repo)
    assert not marks.exists()


class Late:
    """A repository whose ``*.dat`` files name filter ``late``, defined nowhere yet; ``arm`` defines it later in a
    given configuration file, with a command that leaves a marker if it ever runs."""

    def __init__(self, root: Path) -> None:
        self.repo = root / "repo"
        self.repo.mkdir()
        self.marker = root / "ran"
        plain_git("init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / ".gitattributes").write_text("*.dat filter=late\n", encoding="utf-8", newline="\n")
        (self.repo / "a.dat").write_text("one\n", encoding="utf-8", newline="\n")
        plain_git("add", "-A", cwd=self.repo)
        plain_git("commit", "-qm", "base", cwd=self.repo)

    def arm(self, config: Path, section: str = "filter \"late\"") -> None:
        with config.open("a", encoding="utf-8", newline="\n") as f:
            # In a config file an unquoted ';' starts a comment: the value is quoted, and \" keeps the inner quotes
            # (the marker path may contain a space).
            f.write(f'[{section}]\n\tclean = "sh -c \'touch \\"{self.marker.as_posix()}\\"; cat\'"\n')

    def snapshot(self, **env: str) -> None:
        (self.repo / "a.dat").write_text("changed\n", encoding="utf-8", newline="\n")
        F.working_tree_id(self.repo) if not env else git.git("add", "-A", cwd=self.repo, env=env)


@pytest.fixture
def late(tmp_path):
    git.trust_drivers(())
    return Late(tmp_path)


def test_a_driver_added_to_an_include_that_defined_none_is_switched_off(late, tmp_path):
    """Second review of R-P1: the cache watched an include only once it defined a driver."""
    inc = tmp_path / "extra.cfg"
    inc.write_text("[core]\n\tautocrlf = false\n", encoding="utf-8", newline="\n")
    plain_git("config", "include.path", str(inc), cwd=late.repo)
    late.snapshot()  # AEW has read the configuration, and the include defined no driver
    late.arm(inc)
    late.snapshot()
    assert not late.marker.exists()


def test_a_driver_in_an_include_that_did_not_exist_yet_is_switched_off(late, tmp_path):
    inc = tmp_path / "missing.cfg"  # named, but absent when AEW reads
    plain_git("config", "include.path", "../../missing.cfg", cwd=late.repo)  # relative to .git/config
    late.snapshot()
    late.arm(inc)
    late.snapshot()
    assert not late.marker.exists()


def test_a_driver_in_a_nested_include_added_later_is_switched_off(late, tmp_path):
    outer, inner = tmp_path / "outer.cfg", tmp_path / "inner.cfg"
    outer.write_text("", encoding="utf-8")
    plain_git("config", "include.path", str(outer), cwd=late.repo)
    late.snapshot()
    outer.write_text(f"[include]\n\tpath = {inner.as_posix()}\n", encoding="utf-8", newline="\n")
    late.arm(inner)
    late.snapshot()
    assert not late.marker.exists()


def test_a_driver_that_applies_only_on_another_branch_is_switched_off_after_a_switch(late, tmp_path):
    side = tmp_path / "side.cfg"
    late.arm(side)
    plain_git("config", "includeIf.onbranch:side.path", str(side), cwd=late.repo)
    late.snapshot()  # on main the include does not apply
    plain_git("stash", "-q", cwd=late.repo)
    plain_git("checkout", "-q", "-b", "side", cwd=late.repo)  # now it does; no configuration file changed
    late.snapshot()
    assert not late.marker.exists()


def test_a_driver_defined_in_the_calls_own_environment_is_switched_off(late):
    late.snapshot(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="filter.late.clean",
                  GIT_CONFIG_VALUE_0=f"sh -c 'touch \"{late.marker.as_posix()}\"; cat'")
    assert not late.marker.exists()


def test_a_base_that_needs_an_untrusted_filter_is_described_with_the_way_forward(hostile):
    found = git.untrusted_filters(hostile.repo, hostile.base)
    assert [f["driver"] for f in found] == ["p", "x"]
    msg = git.untrusted_filters_message(found, ".aew/policy/execution.yaml")
    for needed in ("filter 'x' (applied to *.dat by .gitattributes", "filter.x.clean = `AEW_KIND=clean sh ./tool.sh`",
                   f"defined in {hostile.repo.as_posix()}/.git/config", "trusted_git_drivers: [p, x]",
                   "under `containment:` in .aew/policy/execution.yaml", "move the script outside the repository",
                   "aew doctor"):
        assert needed in msg, needed
    git.trust_drivers(["x", "p"])
    assert git.untrusted_filters(hostile.repo, hostile.base) == []


def test_dispatch_on_a_base_that_needs_an_untrusted_filter_is_refused_until_trusted(tmp_path):
    p = sample_project(tmp_path)
    (p.root / ".gitattributes").write_text("*.bin filter=lfs\n", encoding="utf-8", newline="\n")
    assert plain_git("add", ".gitattributes", cwd=p.root).returncode == 0
    assert plain_git("commit", "-qm", "track binaries", cwd=p.root).returncode == 0
    plain_git("config", "filter.lfs.clean", "git-lfs clean -- %f", cwd=p.root)
    plain_git("config", "filter.lfs.smudge", "git-lfs smudge -- %f", cwd=p.root)
    wid = p.lead("work", "create", "ticket", "--title", "Touch a binary", "--class", "1", "--goal", "g",
                 "--scope", "calc/**")["id"]
    plan = tmp_path / "plan.md"
    plan.write_text("Edit.\n", encoding="utf-8")
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", "calc/core.py")
    p.lead("plan", "accept", wid, "--revision", "1")
    rev = p.rev()
    res = p.aew("work", "assign", wid, "--expect-rev", str(rev), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode == 5 and p.rev() == rev, res.stdout
    err = res.error
    assert "GIT_DRIVER_UNTRUSTED" in err["details"]["reason_codes"]
    assert "trusted_git_drivers" in err["message"] and "git-lfs clean -- %f" in err["message"]

    path = p.root / ".aew/policy/execution.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8")) if path.exists() else None
    if policy is None:
        pytest.skip("the sample project has no execution policy to trust a driver in")
    policy.setdefault("containment", {})["trusted_git_drivers"] = ["lfs"]
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    p.pin_policy()
    res = p.aew("work", "assign", wid, "--expect-rev", str(p.rev()), env={"AEW_LEAD_TOKEN": p.token})
    assert "GIT_DRIVER_UNTRUSTED" not in (res.stdout + res.stderr), res.stdout

"""AEW's own code lies outside every writable bind (register STG-05): a layout whose writable bind reaches AEW's
package or a directory on its import path is refused under ``required`` and labelled weaker under ``allow_weaker``,
whether it reaches it as spelled or through a symbolic link; a regular install outside every bind is protected and
passes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from host_env import GUARDED

import aew
from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness.containment import layout as L

pytestmark = GUARDED

needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="making a symlink needs a privilege on Windows, "
                                    "and containment is Linux's (bubblewrap); the check is pure")


@pytest.fixture
def fake_bwrap(monkeypatch):
    monkeypatch.setattr(L, "find_bwrap", lambda: "/usr/bin/bwrap")


def real(path: str | Path) -> str:
    return os.path.realpath(path)


def project(tmp_path: Path) -> Path:
    """A project with a commit and the store's directories, as the Lead's layout needs."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
    for d in (".aew/state/log", ".aew/local/harness/runs"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    return repo


def lead_layout(tmp_path: Path, repo: Path) -> C.Layout:
    run = repo / ".aew/local/harness/runs/lead-1"
    return C.for_run(role="lead", scope="project", workspace=str(repo), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=None, home=str(tmp_path / "home"), project=str(repo),
                     runs=str(run.parent), env={}, state_dir=str(repo / ".aew/local/harness/lead"))


def editable_install(monkeypatch, src: Path) -> Path:
    """AEW imported from ``src``, as an editable install of a checkout there is."""
    package = src / "aew"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(aew, "__file__", str(package / "__init__.py"))
    return package


def test_a_lead_whose_project_holds_the_editable_install_aew_runs_from_is_refused(tmp_path, fake_bwrap, monkeypatch):
    """AEW worked on with AEW: the Lead writes its project, and the package its next supervisor and relay import is in
    it. The launch is refused with its own reason, naming the bind, the package and what to do instead."""
    repo = project(tmp_path)
    package = editable_install(monkeypatch, repo / "src")
    with pytest.raises(ContainmentUnavailable, match="AEW's own code must lie outside every writable bind") as refused:
        lead_layout(tmp_path, repo)
    details = refused.value.details
    assert details["reason"] == L.TRUSTED_CODE_WRITABLE
    assert details["bind"] == real(repo) and details["path"] == str(package)
    assert {e["path"] for e in details["exposes"]} >= {str(package), str(package.parent)}
    assert L.trusted_code_remedy(L.PACKAGE) in refused.value.message


def test_an_implementer_whose_worktree_holds_aews_package_is_refused_and_a_regular_install_is_protected(
        tmp_path, fake_bwrap, monkeypatch):
    """A regular install (here, the one the tests run) lies outside every writable bind: the layout passes, and its
    package and import path are on the self-test's protected list. Moved into the worktree a run writes, it is
    refused."""
    repo = project(tmp_path)
    ws = tmp_path / "ws"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "w", str(ws)], cwd=repo, check=True, capture_output=True)
    run = tmp_path / "run"

    def layout() -> C.Layout:
        return C.for_run(role="implementer", scope="ticket", workspace=str(ws), run_dir=run,
                         scratch=str(run / "scratch"), bridge_dir=None, policy=None, home=str(tmp_path / "home"),
                         project=str(repo), env={})

    regular = layout()
    package = real(os.path.dirname(aew.__file__))
    assert package in regular.protected and real(os.path.dirname(package)) in regular.protected
    assert L.trusted_code_exposed(L.order(regular)) == []
    editable_install(monkeypatch, ws / "src")
    with pytest.raises(ContainmentUnavailable) as refused:
        layout()
    assert refused.value.details["reason"] == L.TRUSTED_CODE_WRITABLE
    assert refused.value.details["bind"] == real(ws)


def test_a_directory_on_the_import_path_inside_a_writable_bind_is_refused_with_the_remedy_for_where_it_comes_from(
        tmp_path, monkeypatch):
    """A directory on the import path is checked like the package, and each refusal says what clears it: a PYTHONPATH
    entry is taken out of PYTHONPATH (review of #539, m2), and any other entry is kept out of the writable tree."""
    w = tmp_path / "w"
    for d in ("site", "env"):
        (w / d).mkdir(parents=True)
    steps = L.bind_order([real(w)], [])
    monkeypatch.setattr(sys, "path", [*sys.path, str(w / "site"), str(w / "env")])
    monkeypatch.setenv("PYTHONPATH", str(w / "env"))
    exposed = {f["path"]: f["what"] for f in L.trusted_code_exposed(steps)}
    assert exposed == {real(w / "site"): L.IMPORT_DIR, real(w / "env"): L.FROM_PYTHONPATH}
    assert "remove that directory from PYTHONPATH" in L.trusted_code_remedy(L.FROM_PYTHONPATH)
    assert "installation" not in L.trusted_code_remedy(L.FROM_PYTHONPATH)
    monkeypatch.setattr(sys, "path", [x for x in sys.path if x != str(w / "site")])
    with pytest.raises(ContainmentUnavailable) as refused:
        L._refuse_trusted_code("implementer", steps)
    assert refused.value.details["path"] == real(w / "env")
    assert L.trusted_code_remedy(L.FROM_PYTHONPATH) in refused.value.message


def test_the_launching_directory_first_on_the_import_path_counts_unless_it_is_aews_console_script(
        tmp_path, monkeypatch):
    """Review of #539, m1: ``python -m aew`` started in a writable tree puts it first on the import path of the process
    that serves the contained Lead's relays. The directory of AEW's own console script does not count."""
    w = tmp_path / "w"
    (w / "bin").mkdir(parents=True)
    steps = L.bind_order([real(w)], [])
    monkeypatch.setattr(sys, "path", [str(w), *sys.path[1:]])
    monkeypatch.setattr(sys, "argv", [str(w / "aew" / "__main__.py")])
    assert not sys.flags.safe_path
    exposed = L.trusted_code_exposed(steps)
    assert [(f["path"], f["what"]) for f in exposed] == [(real(w), L.SCRIPT_DIR)]
    assert "`python -P -m aew`" in L.trusted_code_remedy(L.SCRIPT_DIR)

    class Entry:
        name, value = "aew", "aew.cli.main:main"

    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [Entry()])
    monkeypatch.setattr(sys, "path", [str(w / "bin"), *sys.path[1:]])
    monkeypatch.setattr(sys, "argv", [str(w / "bin" / "aew")])
    assert L._console_script_dirs() == {real(w / "bin")} and L.trusted_code_exposed(steps) == []
    monkeypatch.setattr(sys, "argv", [str(w / "bin" / "other-tool")])  # not AEW's script: its directory counts
    assert [f["what"] for f in L.trusted_code_exposed(steps)] == [L.SCRIPT_DIR]


def test_trusted_code_under_a_writable_bind_passes_only_with_the_next_directory_re_bound_read_only_after_it():
    """A virtual environment in the project is safe: the interpreter's prefix is re-bound read-only after the
    project, as the first directory below it. A deeper re-bind, or one applied before the writable bind, is not: the
    directories above it could be renamed."""
    w = real(os.path.join(os.sep, "p"))
    venv = os.path.join(w, ".venv")
    site = [("a directory on AEW's import path", os.path.join(venv, "lib", "site-packages"))]
    assert L.trusted_code_exposed(L.bind_order([w], [venv]), site) == []
    assert L.trusted_code_exposed([("--ro-bind", venv), ("--bind", w)], site)
    deeper = L.trusted_code_exposed(L.bind_order([w], [os.path.join(venv, "lib")]), site)
    assert [f["reason"] for f in deeper] == [L.TRUSTED_CODE_WRITABLE]
    # The bind itself is never protected by a re-bind below it
    assert L.trusted_code_exposed(L.bind_order([w], [venv]), [("x", w)])


@needs_symlinks
def test_an_install_that_links_into_a_writable_bind_is_refused_where_it_leads(tmp_path, fake_bwrap, monkeypatch):
    """A package outside the bind whose spelling resolves into it (a linked package, or one link in an editable
    install's tree of links) is checked where it leads."""
    repo = project(tmp_path)
    source = repo / "src" / "aew"
    source.mkdir(parents=True)
    (source / "relay.py").write_text("")
    site = tmp_path / "site-packages"
    site.mkdir()
    (site / "aew").symlink_to(source)
    monkeypatch.setattr(aew, "__file__", str(site / "aew" / "__init__.py"))
    with pytest.raises(ContainmentUnavailable) as linked:
        lead_layout(tmp_path, repo)
    assert linked.value.details["path"] == real(source)
    tree = tmp_path / "links" / "aew"  # a package of its own whose module is a link into the project
    tree.mkdir(parents=True)
    (tree / "relay.py").symlink_to(source / "relay.py")
    monkeypatch.setattr(aew, "__file__", str(tree / "__init__.py"))
    exposed = L.trusted_code_exposed(L.bind_order([real(repo)], []))
    assert {(f["what"], f["path"]) for f in exposed} == {("a link in AEW's package", real(source / "relay.py"))}


@needs_symlinks
def test_a_symlink_on_the_spelling_of_trusted_code_inside_a_writable_bind_is_refused_wherever_it_leads(tmp_path):
    """A link inside the bind could be replaced to lead elsewhere, so a read-only target does not save it."""
    w, outside = tmp_path / "w", tmp_path / "outside"
    w.mkdir()
    outside.mkdir()
    (w / "lib").symlink_to(outside)
    exposed = L.trusted_code_exposed(L.bind_order([real(w)], []), [("a directory on AEW's import path",
                                                                      str(w / "lib"))])
    assert [(f["reason"], f["symlink"]) for f in exposed] == [(L.TRUSTED_CODE_SYMLINK, str(w / "lib"))]


@needs_symlinks
def test_a_virtual_environments_lib64_link_inside_its_re_bound_prefix_is_not_refused(tmp_path):
    """Review of #539, M1: ``venv`` makes ``<venv>/lib64 -> lib``, and a lib64 distribution's site-packages is spelled
    through it. The link lies below the prefix, which is re-bound read-only after the project, so it cannot be replaced.
    The re-bound directory being a link itself is refused: the mount lands on its target."""
    w = tmp_path / "w"
    venv = w / ".venv"
    (venv / "lib" / "python3" / "site-packages").mkdir(parents=True)
    (venv / "lib64").symlink_to("lib")
    site = [(L.IMPORT_DIR, str(venv / "lib64" / "python3" / "site-packages"))]
    assert L.trusted_code_exposed(L.bind_order([real(w)], [real(venv)]), site) == []
    assert [f["reason"] for f in L.trusted_code_exposed(L.bind_order([real(w)], []), site)] == [
        L.TRUSTED_CODE_SYMLINK]
    (tmp_path / "elsewhere").mkdir()
    (w / "env").symlink_to(tmp_path / "elsewhere")
    linked = [(L.IMPORT_DIR, str(w / "env"))]
    assert [f["symlink"] for f in L.trusted_code_exposed(L.bind_order([real(w)], [str(w / "env")]), linked)] == [
        str(w / "env")]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="containment is Linux's (bubblewrap)")
def test_under_allow_weaker_the_launch_runs_labelled_weaker_saying_why_and_under_required_it_is_refused(
        tmp_path, fake_bwrap, monkeypatch):
    repo = project(tmp_path)
    editable_install(monkeypatch, repo / "src")
    run = repo / ".aew/local/harness/runs/lead-1"
    args = dict(role="lead", scope="project", workspace=str(repo), run_dir=run, scratch=str(run / "scratch"),
                bridge_dir=None, project=str(repo), env={"HOME": str(tmp_path / "home")})
    shared = {"network": {"mode": "shared"}}
    with pytest.raises(ContainmentUnavailable) as refused:
        C.establish(**args, policy={"containment": shared})
    assert refused.value.details["reason"] == L.TRUSTED_CODE_WRITABLE
    layout, label = C.establish(**args, policy={"containment": {**shared, "mode": "allow_weaker"}})
    assert layout is None and C.weaker(label)
    assert "AEW's own code must lie outside every writable bind" in label["weaker_because"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="containment is Linux's (bubblewrap)")
def test_doctor_names_aews_code_inside_the_project_by_the_policys_mode(tmp_path, monkeypatch):
    repo = project(tmp_path)
    assert C.trusted_code_doctor(None, repo)[0] == "PASS"
    editable_install(monkeypatch, repo / "src")
    status, detail = C.trusted_code_doctor(None, repo)
    assert status == "FAIL" and str(repo / "src" / "aew") in detail and L.trusted_code_remedy(L.PACKAGE) in detail
    assert C.trusted_code_doctor({"containment": {"mode": "allow_weaker"}}, repo)[0] == "WARN"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="containment is Linux's (bubblewrap)")
def test_aew_doctor_in_a_project_shows_the_trusted_code_line(project, monkeypatch):
    """Review of #539, m3: the line reaches ``aew doctor`` through the project's own checks."""
    from aew.engine.api import Engine

    monkeypatch.setattr(C, "_doctor", lambda policy, note: ("PASS", "contained", {}))  # no sandbox needed here
    engine = Engine.discover(project.root)
    rows = {row["check"]: row for row in engine.doctor_checks()}
    assert rows["trusted-code"]["status"] == "PASS"
    editable_install(monkeypatch, Path(project.root) / "src")
    rows = {row["check"]: row for row in engine.doctor_checks()}
    assert rows["trusted-code"]["status"] == "FAIL"
    assert str(Path(project.root) / "src" / "aew") in rows["trusted-code"]["detail"]

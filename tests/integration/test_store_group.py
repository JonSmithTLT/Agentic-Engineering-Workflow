"""STG-05 CB-08, the store's group (D-CS1-10 and D-CS1-11 as A-36 amends them, D-CS1-1 as it extends it; WIS-01a and
WIS-00's mode bound).

Each test of D-CS1-AMENDED's "Tests for the build" is named for its guarantee here (the umask walk under each kind of
group is in ``test_store_modes.py``). The host is synthetic, given through the engine's seams
(``tests/helpers/group_host.py``); the groups are real ones this process holds, so every ``chown`` is the kernel's real
answer. The reference model (``tests/fixtures/stg11-wis-r9/``) is run, and the engine's predicate must give its answer
on every host it builds. POSIX-only tests are pinned in ``tests/platform-skips.yaml``.
"""

from __future__ import annotations

import ast
import errno
import hashlib
import itertools
import os
import re
import runpy
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

import group_host as gh  # noqa: E402
from store_model import init, make_store, one_transaction  # noqa: E402

from aew.engine import store as store_mod  # noqa: E402
from aew.engine import store_group as sg  # noqa: E402
from aew.engine import store_writers  # noqa: E402
from aew.errors import IntegrityError, LockTimeout  # noqa: E402

posix = pytest.mark.skipif(sys.platform == "win32", reason="POSIX groups and permission bits; Windows has none")
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "stg11-wis-r9"
HELPERS = ROOT / "tests" / "helpers"
PINNED = {"verify_store_group.py": "251aac38075878fc15df00f5a0188dd3d04321a8838e99458a60549d2e140df3",
          "store-group-cases.json": "221688a3d8d793f1562eafb5f2ccceaca8a461d92989d2897b251e3f44819bea"}
GROUP_READ, OWNER_ONLY = sg.GROUP_READ, sg.OWNER_ONLY
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------------------------- the reference model (A-36)

@pytest.fixture(scope="module")
def model() -> dict:
    return runpy.run_path(str(FIXTURE / "verify_store_group.py"), run_name="stg11_model")


def model_host(m: dict, h: dict) -> sg.HostGroups:
    """A model host as the engine's snapshot: what the parties can list (the model's own ``listed``) and the record."""
    groups, accounts = m["listed"](h)
    rec = h["record"]
    record = None if rec is None else sg.Record(
        (rec["group"]["name"], rec["group"]["gid"]) if rec.get("group") else None,
        {s: sg.Signal(v["text"], tuple((i, i) for i in v["ids"])) for s, v in rec.get("signals", {}).items()})
    return sg.HostGroups(h["operator"], m["primary_of"](h), dict(h["sources"]),
                         tuple(sg.GroupEntry(g["src"], g["name"], g["gid"], tuple(g["members"])) for g in groups),
                         tuple(sg.Account(a["src"], a["name"], a["primary"]) for a in accounts), record)


def writer(w: dict) -> sg.Credentials:
    return sg.Credentials(-1, frozenset(w["holds"]))


def test_the_vendored_model_is_the_pinned_rename_and_passes_all_its_own_checks():
    for name, digest in PINNED.items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == digest, name
    run = subprocess.run([sys.executable, "-I", "-B", str(FIXTURE / "verify_store_group.py")], capture_output=True,
                         text=True, timeout=120, creationflags=NO_WINDOW)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PASS STG-11 store-group fixtures: 103 named checks" in run.stdout, run.stdout


def test_the_predicate_agrees_with_the_reference_model_on_every_host_it_builds(model):
    hosts = model["HOSTS"]
    assert len(hosts) == 29, sorted(hosts)  # every host the model builds: a new one must be seen here
    for name, h in hosts.items():
        found = sg.answer(model_host(model, h))
        assert (found.gid, found.kind, found.reason) == model["writer_private"](h), name
        running = [w for w in h["writers"] if w["running"]]
        for w in running:
            want = sg.target(found, model["primary_of"](h), writer(w), [writer(x) for x in running if x is not w])
            assert (want.gid, (want.file_mode, want.dir_mode)) == model["publish"](h, w), (name, w["name"])


def test_the_control_files_mode_during_a_walk_is_no_targets_and_narrows_every_target(model):
    """D-CS1-1's erratum, its second amendment: the mode a walk gives the control file from its first step to its last
    is a mode no target has, so a walk cut anywhere leaves the record at no target; and it grants nothing any target
    withholds (WIS-00's bound), while its owner can still read it. The targets are those ``store_group.target`` gives on
    every host and writer of the reference model, both branches included."""
    file_modes = set()
    for h in model["HOSTS"].values():
        found = sg.answer(model_host(model, h))
        running = [w for w in h["writers"] if w["running"]]
        for w in running:
            want = sg.target(found, model["primary_of"](h), writer(w), [writer(x) for x in running if x is not w])
            file_modes.add(want.file_mode)
    assert file_modes == {GROUP_READ[0], OWNER_ONLY[0]}, file_modes  # a new target must be seen here
    walking = store_mod.WALKING_FILE_MODE
    assert walking not in file_modes and walking & stat.S_IRUSR
    assert all(walking & ~m == 0 for m in file_modes)


def test_the_step_rule_grants_nothing_beyond_its_start_and_end_and_ends_at_the_target(model):
    """WIS-00's bound at every step (SG1-2), for every start the walk can meet (above the bound included) and both
    targets, judged bit by bit (the model's ``grants`` compares whole bit sets, which is coarser); and where the model
    walks, the rule ends where the model does."""
    for g0, g1, m0, is_dir, readable in itertools.product((1, 2, 3), (1, 2), (0o600, 0o640, 0o644, 0o660, 0o700, 0o750,
                                                                           0o755, 0o2750, 0o000), (False, True),
                                                          (True, False)):
        want = sg.Target(g1, *(GROUP_READ if readable else OWNER_ONLY))
        p = "state/x/" if is_dir else "state/x"
        g, m = g0, m0
        start, seen = {p: (g, m)}, []
        for op, value in sg.steps(g, m, want, is_dir):
            g, m = (value, m) if op == "group" else (g, value)
            seen.append({p: (g, m)})
        end = {p: (want.gid, want.mode(is_dir))}
        assert (g, m) == (want.gid, want.mode(is_dir)), (g0, oct(m0), want)
        for s in seen:
            assert grants(s) <= grants(start) | grants(end), (g0, oct(m0), want, s)
    # The model's own walks (SG1-2, up, then down after root adds a member): the rule ends where the model does.
    h = model["host"](primary="users", aew=990)
    up_start = model["fresh"](h)
    up_end = model["session"](h, h["writers"][0], up_start)
    h2 = model["host"](primary="users", aew=990, aew_members=("oper", "alice"))
    down_end = model["session"](h2, h2["writers"][0], up_end)
    for hh, start, end in ((h, up_start, up_end), (h2, up_end, down_end)):
        gid, modes = model["publish"](hh, hh["writers"][0])
        want = sg.Target(gid, *modes)
        for p, (g, m) in start.items():
            for op, value in sg.steps(g, m, want, p.endswith("/")):
                g, m = (value, m) if op == "group" else (g, value)
            assert (g, m) == end[p], (p, g, oct(m), end[p])


# ------------------------------------------------------------------------------------- the seam reads nothing else

def test_the_store_group_and_store_writer_modules_read_no_environment_variable():
    """Lead's condition 2: the host's answer and a writer's credentials come through Python-level seams only. An
    environment override would be a route for a steered agent to widen the store."""
    for module in (sg, store_writers):
        tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
        found = [f"{type(n).__name__} line {n.lineno}" for n in ast.walk(tree)
                 if (isinstance(n, ast.Attribute) and n.attr in ("environ", "getenv", "environb", "putenv"))
                 or (isinstance(n, ast.Name) and n.id in ("environ", "getenv", "environb"))
                 or (isinstance(n, ast.ImportFrom) and n.module == "os"
                     and any(a.name in ("environ", "getenv", "environb") for a in n.names))]
        assert found == [], (module.__name__, found)


def test_the_store_group_module_imports_nothing_but_the_standard_library():
    """The WIS issuer's installer runs as root from a root-owned install, never from an editable checkout (G3-14), and
    calls this module's ``record_path``, ``parse_record`` and ``store_ref`` rather than restating them: so the module
    has to install as it is, with nothing from the rest of AEW (the Lead, for WIS-B)."""
    tree = ast.parse(Path(sg.__file__ or "").read_text(encoding="utf-8"))
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "." for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0]
    names += ["." for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level > 0]
    assert names and [m for m in names if m.split(".")[0] not in sys.stdlib_module_names] == []


# ------------------------------------------------------------------------------------- the rule, over synthetic hosts

def test_another_entry_with_the_groups_id_in_a_listable_source_makes_it_not_private():
    egid, s = 1000, 990
    other = sg.GroupEntry("directory", "proj-x", s, ("ana", "bo"))
    found = sg.answer(gh.make_host(primary=egid, user_private=False, aew=s, extra=(other,)))
    assert (found.gid, found.reason) == (None, sg.ID_HELD_ELSEWHERE)
    held_up = sg.answer(gh.make_host(primary=egid, extra=(sg.GroupEntry("directory", "old-team", egid, ("carol",)),)))
    assert held_up.gid is None  # a user-private ID another entry holds is not user-private (SG1-1)


def test_a_source_that_cannot_be_listed_needs_roots_signal_and_the_engine_has_none_of_its_own():
    no_signal = sg.answer(gh.make_host(primary=1000, user_private=False, aew=990, unlistable=("sss",)))
    assert (no_signal.gid, no_signal.reason) == (None, sg.UNLISTABLE_NO_SIGNAL)
    signal = sg.answer(gh.make_host(primary=1000, user_private=False, aew=990, unlistable=("sss",), signal=(990,)))
    assert (signal.gid, signal.kind) == (990, sg.LOCAL_AEW)
    # A user-private group needs the same; an idle source counts (nss_sources), and nothing but root's record speaks.
    assert sg.answer(gh.make_host(primary=1000, unlistable=("sss",))).gid is None
    two = gh.make_host(primary=1000, user_private=False, aew=990, unlistable=("sss", "nis"), signal=(990,))
    two = sg.HostGroups(two.operator, two.primary, two.sources, two.groups, two.accounts,
                        sg.Record(two.record.group if two.record else None, {"sss": sg.Signal("x", ((990, 990),))}))
    assert sg.answer(two).reason == sg.UNLISTABLE_NO_SIGNAL  # a signal speaks only for its own source (C2-2)


def test_a_signal_shows_privacy_only_for_the_ids_it_covers():
    """C1-1 probes B5 and B6: a user-private ID held in a source that cannot be listed, with a true signal for other
    IDs: not private; the store goes to the AEW group where there is one, and stays owner-only where there is not."""
    b5 = sg.answer(gh.make_host(primary=1000, aew=990, unlistable=("sss",), signal=tuple(range(900, 1000))))
    assert (b5.gid, b5.kind) == (990, sg.LOCAL_AEW)
    b6 = gh.make_host(primary=1000, unlistable=("sss",), signal=tuple(range(900, 1000)))
    assert sg.answer(b6).gid is None


def test_a_record_naming_another_group_than_part_one_selects_is_owner_only():
    found = sg.answer(gh.make_host(primary=1000, aew=990))  # user-private, and root's record names the AEW group
    assert (found.gid, found.reason) == (None, sg.RECORD_NAMES_OTHER)
    assert sg.target(found, 1000, sg.Credentials(1000, frozenset({990})), []) == sg.Target(1000, *OWNER_ONLY)


def test_a_record_naming_the_user_private_id_under_another_name_is_owner_only():
    """D-CS1-16: part 1's user-private group is named for the operator, so a record that gives its ID another name
    contradicts the listing (part 4). The same record under the operator's name is the user-private group's."""
    found = sg.answer(gh.make_host(primary=1000, record_group=("staff", 1000)))
    assert (found.gid, found.reason) == (None, sg.RECORD_NAMES_OTHER)
    assert sg.answer(gh.make_host(primary=1000, record_group=(gh.OP, 1000))).kind == sg.USER_PRIVATE


# ------------------------------------------------------------------------------------- root's group record

def test_store_ref_is_wis_01s_and_the_record_path_derives_from_it(tmp_path):
    ref = sg.store_ref(tmp_path)
    digest = hashlib.sha256(os.fsencode(str(tmp_path.resolve()))).hexdigest()[:32]
    assert ref == "store:" + digest and sg.instance_id(ref) == digest
    assert sg.record_path(tmp_path) == Path(f"/etc/systemd/system/aew-wis-issuer@{digest}.service.d/store.conf")
    with pytest.raises(ValueError):
        sg.instance_id(digest)


def test_the_record_format_parses_and_refuses_what_it_does_not_define():
    text = ("[Service]\nSupplementaryGroups=aew-op\n\n[X-AEW-Store-Group]\n# the AEW group\nGroup=aew-op 990\n"
            "Signal=sss 900-999,61000 the site reserves GIDs 900-999 for local groups\n")
    record = sg.parse_record(text)
    assert record is not None and record.group == ("aew-op", 990)
    assert record.signals["sss"].covers(990) and record.signals["sss"].covers(61000)
    assert not record.signals["sss"].covers(1000)
    assert sg.parse_record("[Service]\nUser=x\n") is None
    for bad in ("Group=aew-op\n", "Group=a 1\nGroup=b 2\n", "Signal=sss 900-999\n", "Signal=sss 9-1 why\n",
                "Signal=sss x why\n", "Members=op\n", "Signal=sss 1 a\nSignal=sss 2 b\n"):
        with pytest.raises(ValueError):
            sg.parse_record(f"[X-AEW-Store-Group]\n{bad}")


def test_a_record_that_is_not_roots_is_no_record(tmp_path):
    path = tmp_path / "store.conf"
    path.write_text("[X-AEW-Store-Group]\nGroup=aew-op 990\n", encoding="utf-8")
    record, note = sg.load_record(path)  # owned by this test's account, never root
    assert record is None and note is not None and "not root's" in note
    record, note = sg.load_record(path, check=lambda _p: None)  # the format, once ownership passes
    assert record is not None and record.group == ("aew-op", 990) and note is None
    assert sg.load_record(tmp_path / "absent.conf") == (None, "absent")
    path.write_text("[X-AEW-Store-Group]\nGroup=\n", encoding="utf-8")
    assert "unreadable" in (sg.load_record(path, check=lambda _p: None)[1] or "")


@posix
def test_root_ownership_is_judged_along_the_whole_path(tmp_path):
    assert sg.root_owned(tmp_path / "x") is not None  # missing
    mine = tmp_path / "x.conf"
    mine.write_text("", encoding="utf-8")
    assert "not root" in (sg.root_owned(mine) or "")
    etc = Path("/etc/hostname") if Path("/etc/hostname").is_file() else Path("/etc/passwd")
    assert sg.root_owned(etc) is None, sg.root_owned(etc)  # a root-owned file under root-owned directories
    link = tmp_path / "link.conf"
    link.symlink_to(etc)
    assert "symbolic link" in (sg.root_owned(link) or "")


def test_a_record_counts_only_if_every_directory_above_it_is_roots_and_writable_by_no_one_else(monkeypatch):
    """Review of #243, P3 (G2): a root-owned record under a directory that is not root's, or that its group or others
    may write, or that is a link, is no record. The stat results are synthetic, so no root-owned files are needed."""
    record = Path("/etc/systemd/system/aew-wis-issuer@x.service.d/store.conf")
    good = {str(p): (0, stat.S_IFDIR | 0o755) for p in record.parents} | {str(record): (0, stat.S_IFREG | 0o644)}

    def judged(change: dict[str, tuple[int, int]]) -> str | None:
        chain = {**good, **change}

        def lstat(p):
            if str(p) not in chain:
                raise FileNotFoundError(str(p))
            uid, mode = chain[str(p)]
            return os.stat_result((mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))

        with monkeypatch.context() as m:
            m.setattr(sg.os, "lstat", lstat)
            return sg.root_owned(record)

    assert judged({}) is None
    for change in ({str(record.parent): (1000, stat.S_IFDIR | 0o755)},
                   {str(record.parents[1]): (0, stat.S_IFDIR | 0o775)},
                   {str(record.parents[2]): (0, stat.S_IFDIR | 0o1777)},
                   {str(record.parents[1]): (0, stat.S_IFLNK | 0o777)}):
        assert judged(change) is not None, change


# ------------------------------------------------------------------------------------- the host's listing

def test_name_service_sources_outside_this_hosts_files_cannot_be_listed_running_or_not(tmp_path):
    conf, etc = tmp_path / "nsswitch.conf", tmp_path / "etc"
    etc.mkdir()
    (etc / "passwd").write_text("root:x:0:0::/root:/bin/sh\n", encoding="utf-8")
    conf.write_text("# passwd: ldap\npasswd:     files sss systemd\nshadow: files\n"
                    "group:  files [SUCCESS=merge] sss winbind # trailing\nhosts: files dns\n", encoding="utf-8")
    assert sg.nss_sources(conf, etc) == {"files": True, "sss": False, "systemd": True, "winbind": False,
                                         "#": False, "trailing": False}  # glibc 2.35 reads on past a `#` in a line
    conf.write_text("passwd: files systemd\ngroup: files compat\n", encoding="utf-8")
    assert sg.nss_sources(conf, etc) == {"files": True, "systemd": True, "compat": True}
    (etc / "group").write_text("wheel:x:10:\n+@netgroup\n", encoding="utf-8")  # NIS lines: `compat` goes remote
    assert sg.nss_sources(conf, etc)["compat"] is False
    assert sg.nss_sources(tmp_path / "absent", etc) == {"files": True}


def test_every_database_that_gives_an_account_its_groups_is_a_source(tmp_path):
    """D-CS1-14: WIS-01a part 2's sources are every source the host resolves accounts and groups from, so a source on
    any database that gives an account its groups counts, and needs root's signal where it cannot be listed."""
    conf, etc = tmp_path / "nsswitch.conf", tmp_path / "etc"
    etc.mkdir()
    conf.write_text("passwd: files\ngroup: files\ninitgroups: files sss\n", encoding="utf-8")
    assert sg.nss_sources(conf, etc) == {"files": True, "sss": False}
    conf.write_text("passwd: files\ngroup: files\ninitgroups: files\n", encoding="utf-8")
    assert sg.nss_sources(conf, etc) == {"files": True}


@pytest.mark.parametrize(("line", "sources"), [
    ("group files sss", {"sss"}),
    ("group\tfiles sss", {"sss"}),
    ("initgroups files sss", {"sss"}),
    ("passwd files sss", {"sss"}),
    ("passwd\t sss", {"sss"}),
    ("  group:sss", {"sss"}),
    ("group :sss", {"sss"}),
    ("group:: sss", {"sss"}),
    ("group files: sss", {"files:", "sss"}),
    ("group: files # sss", {"#", "sss"}),
    ("group: files #sss", {"#sss"}),
    ("group: files#sss", {"files#sss"}),
    ("group: files [NOTFOUND=return] sss", {"sss"}),
    ("group: files [ NOTFOUND = return ] sss", {"sss"}),
    ("group: files[SUCCESS=merge]sss", {"sss"}),
    ("Group: sss", set()),  # glibc's database names are case-sensitive: no database
    ("# group: sss", set()),
    ("group", set()),
])
def test_each_line_of_the_name_service_file_is_read_as_glibc_reads_it(tmp_path, line, sources):
    """The sources of a line are those glibc reads from it (the colon after the database's name is optional, and a
    word after a ``#`` inside a line counts), so a source glibc consults is never missed. Each line here also has
    ``files``, through the line itself or the ``passwd: files`` before it."""
    conf, etc = tmp_path / "nsswitch.conf", tmp_path / "etc"
    etc.mkdir()
    conf.write_text(f"passwd: files\n{line}\n", encoding="utf-8")
    found = sg.nss_sources(conf, etc)
    assert {s for s, listable in found.items() if not listable} == sources and found["files"] is True, found


class _G:
    def __init__(self, name: str, gid: int, mem: list[str]) -> None:
        self.gr_name, self.gr_gid, self.gr_mem = name, gid, mem


class _P:
    def __init__(self, name: str, gid: int) -> None:
        self.pw_name, self.pw_gid = name, gid


@posix
def test_the_listing_tags_this_hosts_files_and_counts_every_other_enumerated_entry(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "group").write_text("op:x:1000:\naew-op:x:990:op\n+lab\n", encoding="utf-8")
    (etc / "passwd").write_text("op:x:1000:1000::/home/op:/bin/sh\n", encoding="utf-8")
    conf = tmp_path / "nsswitch.conf"
    conf.write_text("passwd: files sss\ngroup: files sss\n", encoding="utf-8")
    host = sg.read_host(tmp_path / "state", nsswitch=conf, etc=etc, unit_dir=tmp_path / "units",
                        getgrall=lambda: [_G("op", 1000, []), _G("aew-op", 990, ["op"]), _G("proj-x", 990, ["ana"])],
                        getpwall=lambda: [_P("op", 1000), _P("ana", 100)], getpwuid=lambda _uid: _P("op", 1000),
                        uid=1000)
    assert {(g.src, g.name, g.gid) for g in host.groups} == {("files", "op", 1000), ("files", "aew-op", 990),
                                                             ("nss", "proj-x", 990)}
    assert host.sources == {"files": True, "sss": False} and host.record is None and host.record_note == "absent"
    assert sg.answer(host).gid is None  # sss cannot be listed, and proj-x holds 990 anyway

    def missing(_uid: int) -> object:
        raise KeyError("no entry")

    orphan = sg.read_host(tmp_path / "state", nsswitch=conf, etc=etc, unit_dir=tmp_path / "units", getgrall=list,
                          getpwall=list, getpwuid=missing, uid=4321, gid=4321)
    assert orphan.primary == 4321 and sg.answer(orphan).gid is None  # no account entry: no user-private group


# ------------------------------------------------------------------------------------- the engine (POSIX)

def state_of(root: Path) -> dict[str, tuple[int, int]]:
    return gh.store_state(root)


def at(root: Path, gid: int, modes: tuple[int, int]) -> dict[str, tuple[int, str]]:
    return gh.off_target(state_of(root), gid, modes)


class Host:
    """A host a test can change while the engine runs (in-process)."""

    def __init__(self, monkeypatch, host: sg.HostGroups) -> None:
        self.host = host
        monkeypatch.setattr(sg, "HOST", lambda _store_dir: self.host)


@posix
def test_a_session_that_does_not_hold_the_group_writes_owner_only_and_commits(tmp_path, monkeypatch):
    """The predicate names a private group this process does not hold (a session older than the group): the store is
    owner-only under the primary group, and every command still works."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=gh.unheld()))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    assert at(root, egid, OWNER_ONLY) == {}
    assert store.read()["revision"] == 2
    assert store.group_view().lacking() == [f"this process (pid {os.getpid()})"]


@posix
def test_a_store_writer_bug_above_the_bound_fails_the_walk_and_doctor_names_it(tmp_path, monkeypatch):
    """A file published 0644, a directory left 0755 or a file 0660: the walk check fails, doctor marks each as above
    WIS-00's bound, and a migration brings them down without passing through anything wider (the step rule)."""
    from aew.doctor import store_checks

    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, egid, GROUP_READ) == {}
    os.chmod(root / "state" / "CURRENT.md", 0o644)
    os.chmod(root / "state" / "log", 0o755)  # noqa: S103 (the planted writer bug the walk must catch)
    os.chmod(root / "state" / "log" / "000001.yaml", 0o660)
    assert set(at(root, egid, GROUP_READ)) == {"state/CURRENT.md", "state/log/", "state/log/000001.yaml"}
    view = store.group_view()
    modes = {c["check"]: c for c in store_checks(view, store.path_problems(view.target))}["store-modes"]
    assert modes["status"] == "WARN" and modes["detail"].count("above the bound") == 3, modes
    os.chmod(root / "state" / "control.yaml", 0o600)  # the record differs: the next open walks
    store.read()
    assert at(root, egid, GROUP_READ) == {}


@posix
def test_two_running_writers_one_lacking_the_group_agree_on_owner_only_and_doctor_names_it(tmp_path, monkeypatch):
    """SG1-5 probe E: a broker older than the group keeps every writer owner-only while it runs, with no alternation;
    doctor names it; once it exits the next commit brings the group back."""
    from aew.doctor import store_checks

    egid, s = gh.held()
    gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, s, GROUP_READ) == {}
    hold = tmp_path / "hold"
    hold.write_text("", encoding="utf-8")
    child = start_writer(root, "hold", hold, creds=sg.Credentials(egid, frozenset({egid})))
    try:
        wait_for(Path(str(hold) + ".ready"), child)
        assert at(root, egid, OWNER_ONLY) == {}  # the older writer's open walked it down
        one_transaction(store)  # this writer holds the group, and still publishes owner-only: they agree
        assert at(root, egid, OWNER_ONLY) == {}
        Path(str(hold) + ".again").write_text("", encoding="utf-8")
        wait_for(Path(str(hold) + ".done"), child)
        one_transaction(store)
        assert at(root, egid, OWNER_ONLY) == {}  # no alternation while both run
        view = store.group_view()
        assert view.lacking() == [f"pid {child.pid} (an undeclared AEW process, such as the Lead broker)"]
        writers = {c["check"]: c for c in store_checks(view, store.path_problems(view.target))}["store-writers"]
        assert writers["status"] == "WARN" and f"pid {child.pid}" in writers["detail"], writers
    finally:
        hold.unlink(missing_ok=True)
        assert child.wait(timeout=60) == 0
    one_transaction(store)
    assert at(root, s, GROUP_READ) == {}  # it has exited: the store's group is back


@posix
def test_a_short_lived_command_from_an_old_session_returns_the_store_to_owner_only_and_the_next_holder_restores_it(
        tmp_path, monkeypatch):
    egid, s = gh.held()
    gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, s, GROUP_READ) == {}
    child = start_writer(root, "commit", creds=sg.Credentials(egid, frozenset({egid})))
    assert child.wait(timeout=60) == 0
    assert at(root, egid, OWNER_ONLY) == {}  # while it ran, and after: it walked the store down
    assert store.group_view().lacking() == []  # not running, so not named: the remedy covers every older session
    one_transaction(store)
    assert at(root, s, GROUP_READ) == {}


@posix
def test_a_member_root_adds_later_returns_the_store_to_owner_only_at_the_next_publication(tmp_path, monkeypatch):
    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, s, GROUP_READ) == {}
    host.host = gh.make_host(primary=egid, user_private=False, aew=s, aew_members=(gh.OP, "ana"))
    assert gh.readers(host.host, state_of(root)) == {"ana"}  # the residual risk, until a writer publishes
    one_transaction(store)
    assert at(root, egid, OWNER_ONLY) == {} and gh.readers(host.host, state_of(root)) == set()


def fd_path(fd: int) -> str:
    """The path a descriptor is open on (Linux's ``/proc``, where the POSIX tests run)."""
    return os.readlink(f"/proc/self/fd/{fd}")


def record_walk(monkeypatch) -> list[tuple[str, str, int]]:
    """Every ``fchmod``/``fchown`` the store makes, in order, with the path its descriptor is open on: (path, op,
    value). The walk changes a path only through a descriptor on it (``store._open_listed``)."""
    calls: list[tuple[str, str, int]] = []
    real_fchmod, real_fchown = os.fchmod, os.fchown

    def fchmod(fd, mode):
        calls.append((fd_path(fd), "mode", mode))
        return real_fchmod(fd, mode)

    def fchown(fd, uid, gid):
        calls.append((fd_path(fd), "group", gid))
        return real_fchown(fd, uid, gid)

    monkeypatch.setattr(store_mod.os, "fchmod", fchmod)
    monkeypatch.setattr(store_mod.os, "fchown", fchown)
    return calls


def grants(state: dict[str, tuple[int, int]]) -> set[tuple[str, str, int | None, int]]:
    """What a store state grants beyond its owner, one permission bit at a time: (path, class, group, bit)."""
    out = set()
    for p, (g, m) in state.items():
        out |= {(p, "group", g, b) for b in (0o040, 0o020, 0o010) if m & b}
        out |= {(p, "other", None, b) for b in (0o004, 0o002, 0o001) if m & b}
    return out


def replay(root: Path, start: dict[str, tuple[int, int]], calls: list[tuple[str, str, int]]) -> list[dict]:
    states, cur = [], dict(start)
    for path, op, value in calls:
        rel = Path(path).relative_to(root.resolve()).as_posix()
        rel = rel + "/" if (rel + "/") in cur else rel
        g, m = cur[rel]
        cur[rel] = (value, m) if op == "group" else (g, value)
        states.append(dict(cur))
    return states


@posix
@pytest.mark.parametrize("direction", ["up", "down", "sideways"])
def test_the_walk_in_each_direction_grants_nothing_beyond_its_start_and_end_and_moves_the_control_file_last(
        tmp_path, monkeypatch, direction):
    """SG1-2 at every step of a real walk, and its order (D-CS1-1's erratum, its second amendment): the control file
    first to the walking mode, then the store's directories and files, and the control file last to the target."""
    egid, s = gh.held()
    owner_only = gh.make_host(primary=egid, user_private=False)
    private = gh.make_host(primary=egid)
    aew = gh.make_host(primary=egid, user_private=False, aew=s)
    first, then, end = {"up": (owner_only, aew, (s, GROUP_READ)), "down": (aew, owner_only, (egid, OWNER_ONLY)),
                        "sideways": (private, aew, (s, GROUP_READ))}[direction]
    host = Host(monkeypatch, first)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    start = state_of(root)
    host.host = then
    calls = record_walk(monkeypatch)
    store.read()  # the open walks
    walked = [c for c in calls if Path(c[0]).is_relative_to((root / "state").resolve())]
    assert walked, "nothing was walked: the test proves nothing"
    states = replay(root, start, walked)
    final = state_of(root)
    # Recovery then removes spent redo records, so the walk's last state is the final one on every path that is left.
    assert at(root, *end) == {} and {p: v for p, v in states[-1].items() if p in final} == final
    target = {p: (end[0], end[1][1] if p.endswith("/") else end[1][0]) for p in start}
    for s_ in states:
        assert grants(s_) <= grants(start) | grants(target), s_
    names = [Path(c[0]).name for c in walked]
    assert walked[0][1:] == ("mode", store_mod.WALKING_FILE_MODE) and names[0] == "control.yaml", walked[0]
    last_control = names.index("control.yaml", 1)
    assert last_control > 1 and set(names[last_control:]) == {"control.yaml"}, names  # and the control file last


@posix
def test_an_open_regroups_a_store_whose_group_alone_changed(tmp_path, monkeypatch):
    """C1-2: from the user-private group to the AEW group at equal modes (another account comes to hold the
    user-private ID, and root names the AEW group): the open migrates, and every path is re-grouped."""
    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, egid, GROUP_READ) == {}
    host.host = gh.make_host(primary=egid, aew=s, extra=(sg.GroupEntry("directory", "old-team", egid, ("carol",)),))
    assert gh.readers(host.host, state_of(root)) == {"carol"}
    make_store(root).read()  # a writer's open
    assert at(root, s, GROUP_READ) == {} and gh.readers(host.host, state_of(root)) == set()


@posix
@pytest.mark.parametrize("change", ["move", "before_rename", "member_added"])
def test_a_change_while_a_writer_is_open_is_walked_before_its_next_commit(tmp_path, monkeypatch, change):
    """C2-1, each way the check found: the move to the AEW group; the same move before root re-names the group; a
    member root adds to the AEW group. The session opened before the change; its commit migrates first, and no older
    path stays readable to anyone new."""
    from aew.engine.store import Transition

    egid, s = gh.held()
    carol = (sg.GroupEntry("directory", "old-team", egid, ("carol",)),)
    if change == "member_added":
        before = gh.make_host(primary=egid, user_private=False, aew=s)
        after = gh.make_host(primary=egid, user_private=False, aew=s, aew_members=(gh.OP, "ana"))
        end = (egid, OWNER_ONLY)
    elif change == "move":
        before, after, end = gh.make_host(primary=egid), gh.make_host(primary=egid, aew=s, extra=carol), (s, GROUP_READ)
    else:
        before = gh.make_host(primary=egid)
        after = gh.make_host(primary=egid, aew=s, extra=carol, record_group=(gh.OP, egid))
        end = (egid, OWNER_ONLY)
    host = Host(monkeypatch, before)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    with store.session() as session:
        session.state["counters"]["n"] += 1
        session.write("records/late.md", "late\n")
        host.host = after  # lands while the writer is open
        assert gh.readers(after, state_of(root)) != set()
        session.commit(Transition(op="bump", actor={"kind": "test"}))
    assert at(root, *end) == {}, at(root, *end)
    assert gh.readers(after, state_of(root)) == set()


@posix
def test_a_change_of_mode_alone_at_the_same_group_is_a_migration(tmp_path, monkeypatch):
    egid, _s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    assert at(root, egid, GROUP_READ) == {}
    host.host = gh.make_host(primary=egid, extra=(sg.GroupEntry("directory", "old-team", egid, ("carol",)),))
    make_store(root).read()
    assert at(root, egid, OWNER_ONLY) == {}


@posix
@pytest.mark.parametrize("then", ["same", "other"])
def test_a_walk_interrupted_before_the_control_file_resumes_at_the_next_comparison(tmp_path, monkeypatch, then):
    """C2-2, with D-CS1-1's erratum (2026-10-24) and its second amendment: the walk's first step puts the control file
    at the walking mode, and only its last step at the target, so a walk cut before that is walked again at the next
    open, whichever target it has then."""
    from aew.engine.faults import InjectedFault

    egid, s = gh.held()
    first = gh.make_host(primary=egid)
    host = Host(monkeypatch, first)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    host.host = gh.make_host(primary=egid, aew=s, extra=(sg.GroupEntry("directory", "old-team", egid, ("carol",)),))
    monkeypatch.setenv("AEW_FAULT", "store.walk.before_control")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        make_store(root).read()
    cut = state_of(root)
    assert cut["state/control.yaml"] == (egid, store_mod.WALKING_FILE_MODE)  # at no target, under its first group
    assert {rel for rel, (g, _m) in cut.items() if g != s} == {"state/control.yaml"}
    monkeypatch.delenv("AEW_FAULT")
    end = (s, GROUP_READ)
    if then == "other":
        host.host, end = first, (egid, GROUP_READ)
    later = make_store(root)
    later.read()
    assert at(root, *end) == {}
    one_transaction(later)
    assert at(root, *end) == {}


@posix
def test_a_second_writer_waits_for_the_whole_walk(tmp_path, monkeypatch):
    """D-CS1-1: the walk holds the control lock throughout. A writer held mid-walk keeps a second writer's open out, so
    nothing interleaves with it, and no path is left at 0640 under the group being left."""
    egid, s = gh.held()
    path = gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    gh.write_host(path, gh.make_host(primary=egid, user_private=False, aew=s, aew_members=(gh.OP, "ana")))
    pause = tmp_path / "pause"
    pause.write_text("", encoding="utf-8")
    child = start_writer(root, "commit", env={"AEW_PAUSE": f"store.walk.mid={pause}"})
    try:
        wait_for(Path(str(pause) + ".reached"), child)
        second = make_store(root)
        second.lock_timeout = 1.0
        with pytest.raises(LockTimeout):
            second.read()
    finally:
        pause.unlink(missing_ok=True)
        assert child.wait(timeout=60) == 0
    assert at(root, egid, OWNER_ONLY) == {}


class _Cut(BaseException):
    """A walk cut short, as by Ctrl-C or a kill: nothing in the engine catches it."""


def cut_walk(monkeypatch, root: Path, step: int) -> bool:
    """Open the store and cut its walk at its ``step``-th change to a store path (``fchmod`` or ``fchown``); False where
    the walk made fewer changes than that."""
    count, store_dir = [0], (root / "state").resolve()

    def counted(real):
        def change(fd, *rest):
            if Path(fd_path(fd)).is_relative_to(store_dir):
                count[0] += 1
                if count[0] == step:
                    raise _Cut
            return real(fd, *rest)
        return change

    with monkeypatch.context() as m:
        m.setattr(store_mod.os, "fchmod", counted(os.fchmod))
        m.setattr(store_mod.os, "fchown", counted(os.fchown))
        try:
            make_store(root).read()
        except _Cut:
            return True
    return False


TARGETS = ("owner_only", "aew", "user_private")


def copy_store(source: Path, root: Path) -> None:
    """A copy of the store at ``source`` at ``root``, its groups as well as its modes (a copy keeps only the modes)."""
    shutil.copytree(source, root, symlinks=True)
    for rel, (gid, _mode) in state_of(source).items():
        os.chown(root / rel, -1, gid)


@posix
@pytest.mark.parametrize(("first", "second"), list(itertools.permutations(TARGETS, 2)))
def test_a_walk_cut_at_any_step_is_finished_by_the_next_comparison(tmp_path, monkeypatch, first, second):
    """D-CS1-1's erratum (2026-10-24), as a property (the enumeration of the review of #243): for each ordered pair of
    targets, a walk from the first to the second cut at each of its steps, and each next target (the first, the second
    or the third), the next open leaves every store path exactly at the target."""
    egid, s = gh.held()
    hosts = {"owner_only": gh.make_host(primary=egid, user_private=False),
             "aew": gh.make_host(primary=egid, user_private=False, aew=s),
             "user_private": gh.make_host(primary=egid)}
    host = Host(monkeypatch, hosts[first])
    template = tmp_path / "template" / ".aew"
    one_transaction(init(template))
    cases = 0
    for then in (first, second, next(t for t in TARGETS if t not in (first, second))):
        for step in itertools.count(1):
            root = tmp_path / f"{then}-{step}" / ".aew"
            copy_store(template, root)
            host.host = hosts[second]
            if not cut_walk(monkeypatch, root, step):
                break
            cases += 1
            host.host = hosts[then]
            later = make_store(root)
            later.read()
            assert later.path_problems(later.group_view().target) == [], (first, second, step, then)
    assert cases >= 3 * 4, cases  # each walk has at least four steps: the test proves something


@posix
@pytest.mark.parametrize(("first", "second"), list(itertools.permutations(TARGETS, 2)))
def test_a_walk_cut_after_a_cut_walk_is_finished_by_the_next_comparison(tmp_path, monkeypatch, first, second):
    """D-CS1-1's erratum and its second amendment, as ruling 4's property over two cuts: for each ordered pair of
    targets, a walk from the first to the second cut at each of its steps, then a walk toward each target cut at each
    of its own steps, then the next open toward each target, and a commit: every store path is then exactly at the
    target. One cut is the property above. More cuts reduce to the last walk's: every walk's first step leaves the
    record at no target, and a walk cut before it has changed nothing."""
    egid, s = gh.held()
    hosts = {"owner_only": gh.make_host(primary=egid, user_private=False),
             "aew": gh.make_host(primary=egid, user_private=False, aew=s),
             "user_private": gh.make_host(primary=egid)}
    host = Host(monkeypatch, hosts[first])
    template = tmp_path / "template" / ".aew"
    one_transaction(init(template))
    # Its subject is the store's groups and modes. The schema checks and the fsyncs of its two thousand or so commits,
    # which other tests cover, were nine tenths of its time.
    monkeypatch.setattr(store_mod, "validate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(os, "fsync", lambda _fd: None)
    cases = 0
    for step in itertools.count(1):
        once = tmp_path / f"{step}" / ".aew"
        copy_store(template, once)
        host.host = hosts[second]
        if not cut_walk(monkeypatch, once, step):
            break
        for toward in TARGETS:
            for again in itertools.count(1):
                twice = tmp_path / f"{step}-{toward}-{again}" / ".aew"
                copy_store(once, twice)
                host.host = hosts[toward]
                cut = cut_walk(monkeypatch, twice, again)
                for then in TARGETS if cut else ():
                    root = tmp_path / f"{step}-{toward}-{again}-{then}" / ".aew"
                    copy_store(twice, root)
                    host.host = hosts[then]
                    later = make_store(root)
                    later.read()
                    case = (first, second, step, toward, again, then)
                    assert later.path_problems(later.group_view().target) == [], case
                    one_transaction(later)
                    assert later.path_problems(later.group_view().target) == [], case
                    cases += 1
                    shutil.rmtree(root.parent)
                shutil.rmtree(twice.parent)
                if not cut:
                    break
        shutil.rmtree(once.parent)
    assert cases >= 3 * 4 * 3, cases  # every first cut is followed by second cuts: the test proves something


@posix
@pytest.mark.parametrize("era", ["before_cs1_umask022", "before_cs1_umask002", "cs1_migrated", "mixed_umasks"])
def test_a_store_from_an_earlier_version_is_brought_within_the_bound_at_its_first_open(tmp_path, monkeypatch, era):
    """Review of #243, P1, and D-CS1-1's erratum (2026-10-24), on a host whose primary group is user-private. Before
    CS-1 a store's directories came from a ``mkdir`` the umask filtered, and its files from ``mkstemp`` at 0600; CS-1's
    migration then made every file 0640 and kept the directories; and a store's directories may come from different
    umasks (``init`` under one, a later directory under another). Each is at the target after its first open."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    handoffs = root / "state" / "handoffs"  # a directory a later command made
    handoffs.mkdir()
    (handoffs / "h-1.md").write_text("a handoff\n", encoding="utf-8")
    del store
    mixed = {"state/": 0o750, "state/log/": 0o755, "state/txn/": 0o775, "state/handoffs/": 0o755}
    for rel in state_of(root):
        if rel.endswith("/"):
            dir_mode = {"before_cs1_umask002": 0o775, "mixed_umasks": mixed.get(rel, 0o755)}.get(era, 0o755)
            os.chmod(root / rel, dir_mode)
        else:
            os.chmod(root / rel, 0o600 if era.startswith("before_cs1") else 0o640)
    if era == "mixed_umasks":  # the store directory and the control file are both at the target
        assert {state_of(root)["state/"][1], state_of(root)["state/control.yaml"][1]} == set(GROUP_READ)
    make_store(root).read()
    assert at(root, egid, GROUP_READ) == {}, at(root, egid, GROUP_READ)


def store_at_target_with(tmp_path: Path, monkeypatch, change) -> tuple[Path, int]:
    """A store at its target on a user-private host, then ``change(root, gid)`` made to it, then one open. Returns the
    store's root and the target's group."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    assert at(root, egid, GROUP_READ) == {}
    change(root, egid)
    make_store(root).read()
    return root, egid


@posix
def test_a_later_directory_alone_off_the_target_is_walked_at_the_next_open(tmp_path, monkeypatch):
    """Review of #243 at 7f1b9411, P1: the record is every directory in the store, not a list of the layout's: a
    directory another module makes, alone off the target (every other directory and the control file at it)."""
    def later(root: Path, gid: int) -> None:
        (root / "state" / "handoffs").mkdir(mode=0o755)
        os.chmod(root / "state" / "handoffs", 0o755)  # noqa: S103 (a directory off the target is the condition)

    root, gid = store_at_target_with(tmp_path, monkeypatch, later)
    assert at(root, gid, GROUP_READ) == {} and "state/handoffs/" in state_of(root)


@posix
def test_the_store_directory_alone_off_the_target_is_walked_at_the_next_open(tmp_path, monkeypatch):
    """D-CS1-1's erratum: the record has the store directory itself, which an earlier version may have left wider than
    the bound with every other directory and the control file at the target."""
    def wider(root: Path, gid: int) -> None:
        os.chmod(root / "state", 0o755)  # noqa: S103 (a directory off the target is the condition)

    root, gid = store_at_target_with(tmp_path, monkeypatch, wider)
    assert at(root, gid, GROUP_READ) == {}, at(root, gid, GROUP_READ)


@posix
def test_a_directory_two_levels_down_alone_off_the_target_is_walked_at_the_next_open(tmp_path, monkeypatch):
    """Review of #243 at 7f1b9411, P1: the record reaches every level, with every first-level directory at the
    target."""
    def nested(root: Path, gid: int) -> None:
        inner = root / "state" / "log" / "older"
        inner.mkdir(mode=0o755)
        os.chmod(inner, 0o755)  # noqa: S103 (a directory off the target is the condition)

    root, gid = store_at_target_with(tmp_path, monkeypatch, nested)
    assert at(root, gid, GROUP_READ) == {} and "state/log/older/" in state_of(root)


@posix
def test_a_set_group_id_store_directory_is_walked_to_the_target_at_the_next_open(tmp_path, monkeypatch):
    """Review of #243 at 7f1b9411, P1: the record compares a directory's whole mode, its set-group-ID bit too (a store
    made in a set-group-ID directory owned by the target's group)."""
    def set_group_id(root: Path, gid: int) -> None:
        os.chmod(root / "state" / "log", 0o2750)  # noqa: S103 (the set-group-ID bit is the condition under test)

    root, gid = store_at_target_with(tmp_path, monkeypatch, set_group_id)
    assert at(root, gid, GROUP_READ) == {}, at(root, gid, GROUP_READ)


@posix
def test_the_record_is_the_stores_own_directories(tmp_path, monkeypatch):
    """The store's directories are those in it, never what a link in it names: a link to a directory outside, wider
    than the bound, is not compared, so it is not changed and does not make every comparison walk."""
    outside = tmp_path / "outside"

    def linked(root: Path, gid: int) -> None:
        outside.mkdir()
        os.chmod(outside, 0o777)  # noqa: S103 (a directory wider than the bound, outside the store)
        (root / "state" / "elsewhere").symlink_to(outside, target_is_directory=True)

    root, gid = store_at_target_with(tmp_path, monkeypatch, linked)
    assert stat.S_IMODE(os.stat(outside).st_mode) == 0o777 and at(root, gid, GROUP_READ) == {}
    calls = record_walk(monkeypatch)
    make_store(root).read()
    store_dir = (root / "state").resolve()
    assert [c for c in calls if Path(c[0]).is_relative_to(store_dir)] == [], calls  # at the target: nothing walked


@posix
def test_doctor_names_a_path_in_the_store_that_is_neither_a_file_nor_a_directory(tmp_path, monkeypatch):
    """Review of #243 at 7f1b9411, P2: the walk leaves a FIFO, a socket or a device alone, and `aew doctor` names one
    in the store, which is never at a target (WIS-00's bound has files and directories only), with its remedy."""
    from aew.doctor import store_checks

    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    fifo = root / "state" / "log" / "a.fifo"
    os.mkfifo(fifo)
    os.chmod(fifo, 0o666)  # noqa: S103 (a path above the bound is the condition under test)
    host.host = gh.make_host(primary=egid, user_private=False, aew=s)
    store = make_store(root)
    store.read()  # the open walks, past the FIFO
    st = os.lstat(fifo)
    assert stat.S_ISFIFO(st.st_mode) and (st.st_gid, stat.S_IMODE(st.st_mode)) == (egid, 0o666)
    assert set(at(root, s, GROUP_READ)) == {"state/log/a.fifo"}, at(root, s, GROUP_READ)
    view = store.group_view()
    checks = {c["check"]: c for c in store_checks(view, store.path_problems(view.target))}
    assert checks["store-modes"]["status"] == "WARN" and checks["wis-store"]["status"] == "WARN", checks
    assert "state/log/a.fifo (prw-rw-rw-" in checks["store-modes"]["detail"], checks["store-modes"]
    assert "`rm .aew/state/log/a.fifo`" in checks["store-modes"]["detail"], checks["store-modes"]


@posix
def test_a_link_in_the_store_is_neither_walked_nor_reported(tmp_path, monkeypatch):
    """Review of #243, P3 (G1): the store's paths are its files and directories, never what a link in it names."""
    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    outside = tmp_path / "outside.txt"
    outside.write_text("not the store's\n", encoding="utf-8")
    os.chmod(outside, 0o604)
    (root / "state" / "log" / "link.yaml").symlink_to(outside)
    before = os.stat(outside)
    host.host = gh.make_host(primary=egid, user_private=False, aew=s)
    store = make_store(root)
    store.read()  # the open walks
    after = os.stat(outside)
    assert (after.st_gid, stat.S_IMODE(after.st_mode)) == (before.st_gid, 0o604)
    assert at(root, s, GROUP_READ) == {} and store.path_problems(sg.Target(s, *GROUP_READ)) == []


@posix
def test_the_walk_changes_only_the_files_it_listed(tmp_path, monkeypatch):
    """The walk changes a path through a descriptor on the very file it listed, so a path that is another file by the
    time it is stepped is left as it is, and so is that other file. So is a file with a second link, which the store
    never makes (it publishes by a rename), and `aew doctor` names it."""
    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    one_transaction(init(root))
    path = root / "state" / "handoffs" / "h-1.md"  # a store file nothing in an open reads or writes
    path.parent.mkdir()
    path.write_text("a handoff\n", encoding="utf-8")
    listed = store_mod.ControlStore._store_paths

    def a_link_to(p: Path, outside: Path) -> None:
        p.unlink()
        os.symlink(outside, p)

    def a_hard_link_to(p: Path, outside: Path) -> None:
        p.unlink()
        os.link(outside, p)

    def moved_out_with_a_link_to_it(p: Path, outside: Path) -> None:
        outside.unlink()
        os.rename(p, outside)
        os.symlink(outside, p)

    def another_file_renamed_over_it(p: Path, outside: Path) -> None:  # no link, one link: only the identity tells
        os.rename(outside, p)

    hosts = [gh.make_host(primary=egid, user_private=False, aew=s), gh.make_host(primary=egid)]
    swaps = (a_link_to, a_hard_link_to, moved_out_with_a_link_to_it, another_file_renamed_over_it)
    for i, swap in enumerate(swaps):
        outside = tmp_path / f"outside-{i}.txt"
        outside.write_text("not the store's\n", encoding="utf-8")
        os.chmod(outside, 0o604)
        before = os.stat(path if swap is moved_out_with_a_link_to_it else outside)
        other = path if swap is another_file_renamed_over_it else outside

        def swapped(self, outside=outside, swap=swap):
            for p, st, is_dir in listed(self):
                if p == path:
                    swap(p, outside)
                yield p, st, is_dir

        host.host = hosts[i % 2]  # each open walks
        with monkeypatch.context() as m:
            m.setattr(store_mod.ControlStore, "_store_paths", swapped)
            make_store(root).read()
        after = os.stat(other)
        assert (after.st_ino, after.st_gid, stat.S_IMODE(after.st_mode)) == (
            before.st_ino, before.st_gid, stat.S_IMODE(before.st_mode)), swap.__name__
        path.unlink()
        path.write_text("a handoff\n", encoding="utf-8")
    # A file the store does not hold alone is not the store's to change, even where it was there at the listing.
    outside = tmp_path / "outside-linked.txt"
    outside.write_text("not the store's\n", encoding="utf-8")
    os.chmod(outside, 0o604)
    before = os.stat(outside)
    a_hard_link_to(path, outside)
    host.host = hosts[len(swaps) % 2]  # the open walks
    store = make_store(root)
    store.read()
    after = os.stat(outside)
    assert (after.st_gid, stat.S_IMODE(after.st_mode)) == (before.st_gid, 0o604)
    assert ("state/handoffs/h-1.md", before.st_gid, 0o604) in store.path_problems(store.group_view().target)


@posix
def test_doctors_commands_for_a_path_off_the_target_follow_the_walks_order(tmp_path, monkeypatch):
    """`aew doctor`'s store-modes gives, for each path off the target, the commands the walk would run, in its order
    (``store_group.steps``): run as given, none grants anything that neither the path's start nor the target grants."""
    from aew.doctor import store_checks

    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    host.host = gh.make_host(primary=egid, user_private=False)
    store.read()  # walked to owner-only
    off = root / "state" / "log" / "000001.yaml"
    os.chown(off, -1, s)
    os.chmod(off, 0o640)
    view = store.group_view()
    detail = {c["check"]: c for c in store_checks(view, store.path_problems(view.target))}["store-modes"]["detail"]
    commands = re.findall(r"`(chmod|chgrp) (\d+) \.aew/state/log/000001\.yaml`", detail)
    start, end = {"p": (s, 0o640)}, {"p": (egid, 0o600)}
    states, (g, m) = [], start["p"]
    for op, value in commands:
        g, m = (g, int(value, 8)) if op == "chmod" else (int(value), m)
        states.append({"p": (g, m)})
    assert commands and states[-1] == end, commands
    for state in states:
        assert grants(state) <= grants(start) | grants(end), commands


@posix
def test_wis_store_is_met_only_while_every_store_path_is_at_the_target(tmp_path, monkeypatch):
    """Review of #243, P3 (G5): WIS-Q02's store condition fails while a store path is off the target, even with the
    group private and every running writer holding it (D-CS1-5: only PASS counts as met)."""
    from aew.doctor import store_checks

    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)

    def checks() -> dict[str, dict[str, str]]:
        view = store.group_view()
        return {c["check"]: c for c in store_checks(view, store.path_problems(view.target))}

    assert checks()["wis-store"]["status"] == "PASS"
    os.chmod(root / "state" / "log" / "000001.yaml", 0o600)
    found = checks()
    assert found["store-group"]["status"] == "PASS" and found["store-writers"]["status"] == "PASS"
    assert found["wis-store"]["status"] == "WARN" and "store-modes" in found["wis-store"]["detail"], found


# ------------------------------------------------------------------------------------- what every publication obeys

@posix
def test_a_new_store_is_at_its_target_from_its_first_file(tmp_path, monkeypatch):
    """``create`` publishes the store directory and revision 0's control file at the target, before any commit
    replaces them: the local AEW group here, which is not this process's default group."""
    egid, s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    init(root)
    assert {"state/", "state/control.yaml"} <= set(state_of(root))
    assert at(root, s, GROUP_READ) == {}


@posix
def test_new_store_directories_are_never_created_above_the_bound(tmp_path, monkeypatch):
    """``mkdir`` is filtered by the umask, so a default ``mkdir`` under umask 002 gives 0775 for a moment: every store
    directory is made 0700 and only then given its group and mode."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    made: list[int] = []
    real = Path.mkdir

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        if "state" in self.parts and not self.exists():
            made.append(mode)
        return real(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    old = os.umask(0o002)
    try:
        root = tmp_path / ".aew"
        one_transaction(init(root))
    finally:
        os.umask(old)
    assert made and all(m & ~0o700 == 0 for m in made), [oct(m) for m in made]


@posix
def test_a_set_group_id_parent_gives_nothing_its_group_or_its_bit(tmp_path, monkeypatch):
    """The default group of a new file or directory is the parent's where it is set-group-ID: the engine sets the
    target's group on the descriptor whatever that gives (D-CS1-10). The forgotten-group ablation fails here."""
    egid, s = gh.held()
    parent = tmp_path / "sgid"
    parent.mkdir()
    os.chown(parent, -1, s)
    os.chmod(parent, 0o2770)  # noqa: S103 (a set-group-ID parent is the condition under test)
    probe = parent / "probe"
    probe.write_text("", encoding="utf-8")
    assert os.stat(probe).st_gid == s != egid  # the condition holds, so the test proves something
    Host(monkeypatch, gh.make_host(primary=egid))
    root = parent / ".aew"
    store = init(root)
    one_transaction(store)
    one_transaction(store)
    assert at(root, egid, GROUP_READ) == {}
    assert not any(m & stat.S_ISGID for _g, m in state_of(root).values())


def test_a_publication_without_a_target_is_owner_only():
    """Review of #243, P4: a POSIX publication always has a target today; one without would be owner-only, never at
    whatever group the process has by default."""
    assert store_mod._temp_args(None) == {"mode": 0o600}


@posix
def test_a_write_into_the_store_without_the_control_lock_is_refused(tmp_path, monkeypatch):
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    store = init(root)
    with pytest.raises(IntegrityError) as err:
        store_mod.write_file(store.store_dir, store.store_dir / "stray.yaml", "x\n")
    assert err.value.details.get("reason") == "store_write_unlocked"
    assert not (store.store_dir / "stray.yaml").exists()


@posix
def test_a_group_the_file_system_refuses_makes_the_process_lack_it_and_the_store_owner_only(tmp_path, monkeypatch):
    """``EPERM`` from ``fchown`` to the store's group (an NFS server, say): the file is published owner-only, the
    process says it lacks the group in its entry, and the store is walked owner-only. AEW keeps working."""
    egid, s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    real = os.fchown

    def fchown(fd, uid, gid):
        if gid == s:
            raise PermissionError(1, "Operation not permitted")
        return real(fd, uid, gid)

    monkeypatch.setattr(os, "fchown", fchown)
    one_transaction(store)
    assert at(root, egid, OWNER_ONLY) == {}
    entries, _ = store_writers.running(root)  # this process's own entry included
    assert [w.refused for w in entries] == [s] and not store.group_view().me.holds(s)
    one_transaction(store)  # and it keeps working, owner-only
    assert at(root, egid, OWNER_ONLY) == {}


@posix
def test_a_group_the_file_system_refuses_during_the_walk_makes_the_process_lack_it(tmp_path, monkeypatch):
    """Review of #243, P3 (G4): the walk's own group change refused on a path of this process's: it lacks the group,
    says so in its entry, and walks owner-only instead."""
    egid, s = gh.held()
    host = Host(monkeypatch, gh.make_host(primary=egid, user_private=False))
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    host.host = gh.make_host(primary=egid, user_private=False, aew=s)  # the next open walks to the AEW group
    real = os.fchown

    def fchown(fd, uid, gid):
        if gid == s:
            raise PermissionError(errno.EPERM, "Operation not permitted")
        return real(fd, uid, gid)

    monkeypatch.setattr(store_mod.os, "fchown", fchown)
    store.read()  # an open publishes nothing: only the walk sets a group here
    assert at(root, egid, OWNER_ONLY) == {}
    assert store._registration is not None and store._registration.refused == s
    assert not store.group_view().me.holds(s)


@posix
def test_a_process_that_cannot_record_itself_never_widens_the_store(tmp_path, monkeypatch):
    """Review of #243, P3 (G3): the other writers cannot see a process that could not record itself as a running
    store writer, so it never widens the store, even where the group is private and it holds it. Doctor says why."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))  # private, and this process holds it

    def unrecorded(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(store_writers, "register", unrecorded)
    root = tmp_path / ".aew"
    store = init(root)
    one_transaction(store)
    assert at(root, egid, OWNER_ONLY) == {}
    view = store.group_view()
    assert view.answer.gid == egid and view.register_problem and view.lacking() == [f"this process (pid {os.getpid()})"]


@posix
def test_a_non_writer_registers_nothing_and_is_not_counted_among_the_store_writers(tmp_path, monkeypatch):
    """A non-writer (`aew dashboard serve`, a worker's CLI) publishes nothing, so it neither registers nor counts: its
    doctor names no one for lacking a group it never needs."""
    from aew import process_kind

    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=gh.unheld()))
    root = tmp_path / ".aew"
    init(root)  # the writer's own ControlStore is gone again, and its entry with it
    with process_kind.declared_as("aew dashboard serve"):
        reader = make_store(root)
        assert reader.read_committed()["revision"] == 0
        view = reader.group_view()
    assert view.answer.gid is not None and view.lacking() == [] and reader._registration is None
    assert list((root / "local" / "writers").iterdir()) == []


# ------------------------------------------------------------------------------------- the registry

@posix
def test_a_writer_registers_owner_only_and_an_exited_writers_entry_is_dropped(tmp_path, monkeypatch):
    egid, s = gh.held()
    gh.install_children(monkeypatch, tmp_path, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    store = init(root)
    directory = root / "local" / "writers"
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
    mine = [p for p in directory.iterdir()]
    assert len(mine) == 1 and stat.S_IMODE(os.stat(mine[0]).st_mode) == 0o600
    # A writer killed without cleaning up leaves its entry; its lock went with it.
    hold = tmp_path / "hold"
    hold.write_text("", encoding="utf-8")
    child = start_writer(root, "hold", hold)
    try:
        wait_for(Path(str(hold) + ".ready"), child)
        assert len(store_writers.running(root)[0]) == 2  # this process's entry and the child's
    finally:
        child.kill()
        child.wait(timeout=30)
        hold.unlink()
    assert len(list(directory.iterdir())) == 2  # still there
    live, problems = store_writers.running(root, exclude=store._registration)
    assert live == [] and problems == [] and len(list(directory.iterdir())) == 1


@posix
def test_the_registry_directory_is_owner_only_even_where_it_was_made_wider(tmp_path, monkeypatch):
    """Review of #243, P3 (G6): `.aew/local/writers/` is 0700 whatever made it first."""
    egid, _s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid))
    root = tmp_path / ".aew"
    directory = root / "local" / "writers"
    directory.mkdir(parents=True)
    os.chmod(directory, 0o755)  # noqa: S103 (an existing directory made wider is the condition under test)
    store = init(root)
    assert store._registration is not None and stat.S_IMODE(os.stat(directory).st_mode) == 0o700


@posix
def test_a_reader_listing_the_writers_while_one_registers_leaves_its_entry_alone(tmp_path, monkeypatch):
    """Review of #243, P2: another writer's view of the registry runs while this one is making its entry (after the
    entry is created and before it is locked). The entry is still made, and this writer is seen."""
    egid, s = gh.held()
    Host(monkeypatch, gh.make_host(primary=egid, user_private=False, aew=s))
    root = tmp_path / ".aew"
    init(root)  # its ControlStore is gone again, and its entry with it
    real, views = os.fchmod, []

    def fchmod(fd, mode):
        if not views:  # the first fchmod is the new entry's, in that window
            views.append(store_writers.running(root))
        return real(fd, mode)

    with monkeypatch.context() as m:
        m.setattr(store_writers.os, "fchmod", fchmod)
        store = make_store(root)
        store.read()  # it registers at its first control lock
    assert views and store._register_problem is None and store._registration is not None
    assert [w.pid for w in store_writers.running(root)[0]] == [os.getpid()]


@posix
def test_an_entry_that_cannot_be_read_counts_as_a_writer_holding_no_group(tmp_path):
    import fcntl

    directory = tmp_path / "local" / "writers"
    directory.mkdir(parents=True)
    path = directory / "1-x.json"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)  # live, from another open file description
        os.write(fd, b"{not json")
        found, _ = store_writers.running(tmp_path)
        assert len(found) == 1 and found[0].note and not found[0].holds(os.getegid())
    finally:
        os.close(fd)


# ------------------------------------------------------------------------------------- helpers

def start_writer(root: Path, mode: str, hold: Path | None = None, *, creds: sg.Credentials | None = None,
                 env: dict[str, str] | None = None) -> subprocess.Popen:
    child_env = dict(os.environ)
    child_env.pop(gh.ENV_CREDENTIALS, None)
    if creds is not None:
        cred_path = root.parent / f"creds-{time.monotonic_ns()}.json"
        cred_path.write_text(f'{{"egid": {creds.egid}, "groups": {sorted(creds.groups)}}}', encoding="utf-8")
        child_env[gh.ENV_CREDENTIALS] = str(cred_path)
    child_env.update(env or {})
    argv = [sys.executable, str(HELPERS / "group_writer.py"), str(root), mode, *([str(hold)] if hold else [])]
    return subprocess.Popen(argv, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW)


def wait_for(path: Path, child: subprocess.Popen, limit: float = 60.0) -> None:
    deadline = time.monotonic() + limit
    while not path.exists():
        if child.poll() is not None:
            out, err = child.communicate(timeout=10)
            raise AssertionError(f"the writer exited ({child.returncode}) before {path.name}: {out!r} {err!r}")
        assert time.monotonic() < deadline, f"no {path.name} within {limit} s"
        time.sleep(0.05)

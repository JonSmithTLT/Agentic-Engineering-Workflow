"""Synthetic hosts for the store's group (STG-05 CB-08; WIS-01a, A-36), given to the engine through its seams.

The engine reads the host's groups through ``aew.engine.store_group.HOST`` and its own credentials through
``aew.engine.store_writers.CREDENTIALS``. A test sets them in-process (:func:`install`), or in every Python child it
starts (:func:`install_children`): a test-only ``sitecustomize`` in ``host_seam/`` reads the files named by
:data:`ENV_HOST` and :data:`ENV_CREDENTIALS` and sets the same attributes there. Nothing in ``src/`` reads either
variable (a test checks it). Tests never read or change the real host's group database.

The groups are real ones this process holds, so the kernel's ``chown`` is the real answer: the primary group, and a
supplementary group playing the local AEW group (:func:`held`). A group this process does not hold plays a session
older than the group (:func:`unheld`).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aew.engine import store_group as sg
from aew.engine import store_writers

SEAM_DIR = Path(__file__).resolve().parent / "host_seam"
ENV_HOST = "AEW_TEST_HOST_GROUPS"
ENV_CREDENTIALS = "AEW_TEST_CREDENTIALS"
OP = "op"
AEW_GROUP = "aew-op"


def held() -> tuple[int, int]:
    """This process's primary group and a second group it holds. A host without a second group cannot run the
    re-grouping tests: that is a fact for the Lead, never a skip (CB-08 plan, 7f)."""
    egid = os.getegid()
    others = sorted(g for g in os.getgroups() if g != egid)
    assert others, (f"this test account holds no group besides gid {egid}; the store-group tests need one (the CI "
                    "runner's user normally holds several)")
    return egid, others[0]


def unheld() -> int:
    """A gid this process does not hold."""
    mine = {os.getegid(), *os.getgroups()}
    gid = 4242
    while gid in mine:
        gid += 1
    return gid


def make_host(*, primary: int, user_private: bool = True, aew: int | None = None, aew_members: tuple[str, ...] = (OP,),
              record: bool = True, record_group: tuple[str, int] | None = None, unlistable: tuple[str, ...] = (),
              signal: tuple[int, ...] | None = None, extra: tuple[sg.GroupEntry, ...] = (),
              accounts: tuple[sg.Account, ...] = ()) -> sg.HostGroups:
    """A host as the parties see it. ``user_private``: the operator's primary group is named for them with no member;
    otherwise it is a shared ``staff`` with another member. ``aew``: a local AEW group with ``aew_members``, which
    root's record names (``record``) unless ``record_group`` names another. ``unlistable``: sources that cannot be
    listed; ``signal``: the IDs root's record covers for each."""
    groups = [sg.GroupEntry(sg.FILES, OP if user_private else "staff", primary, () if user_private else ("ana",))]
    if aew is not None:
        groups.append(sg.GroupEntry(sg.FILES, AEW_GROUP, aew, aew_members))
    groups += extra
    named = record_group if record_group is not None else ((AEW_GROUP, aew) if aew is not None and record else None)
    signals = {s: sg.Signal("the site reserves these IDs for local groups", tuple((i, i) for i in signal))
               for s in unlistable} if signal is not None else {}
    rec = sg.Record(named, signals) if (named is not None or signals) else None
    sources = {sg.FILES: True, **{s: False for s in unlistable}}
    return sg.HostGroups(OP, primary, sources, tuple(groups), (sg.Account(sg.FILES, OP, primary), *accounts), rec,
                         None if rec is not None else "absent",
                         "/etc/systemd/system/aew-wis-issuer@test.service.d/store.conf")


def install(monkeypatch: Any, host: sg.HostGroups, creds: sg.Credentials | None = None) -> None:
    monkeypatch.setattr(sg, "HOST", lambda _store_dir: host)
    if creds is not None:
        monkeypatch.setattr(store_writers, "CREDENTIALS", lambda: creds)


def install_children(monkeypatch: Any, directory: Path, host: sg.HostGroups,
                     creds: sg.Credentials | None = None) -> Path:
    """Give every Python child of this test ``host`` (re-read at each use, so :func:`write_host` changes it while a
    child runs) and ``creds``. Returns the host file. Also installs both in this process."""
    path = directory / "host-groups.json"
    write_host(path, host)
    monkeypatch.setenv(ENV_HOST, str(path))
    if creds is not None:
        cred_path = directory / "credentials.json"
        cred_path.write_text(json.dumps({"egid": creds.egid, "groups": sorted(creds.groups)}), encoding="utf-8")
        monkeypatch.setenv(ENV_CREDENTIALS, str(cred_path))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(SEAM_DIR), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.setattr(sg, "HOST", lambda _store_dir: read_host_file(path))
    if creds is not None:
        monkeypatch.setattr(store_writers, "CREDENTIALS", lambda: creds)
    return path


def write_host(path: Path, host: sg.HostGroups) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(host)), encoding="utf-8")
    os.replace(tmp, path)


def read_host_file(path: Path) -> sg.HostGroups:
    d = json.loads(path.read_text(encoding="utf-8"))
    rec = d["record"]
    record = None if rec is None else sg.Record(
        tuple(rec["group"]) if rec["group"] is not None else None,  # type: ignore[arg-type]
        {s: sg.Signal(v["text"], tuple(tuple(r) for r in v["ranges"])) for s, v in rec["signals"].items()})
    return sg.HostGroups(d["operator"], d["primary"], d["sources"], tuple(sg.GroupEntry(g["src"], g["name"], g["gid"],
                         tuple(g["members"])) for g in d["groups"]),
                         tuple(sg.Account(a["src"], a["name"], a["primary"]) for a in d["accounts"]), record,
                         d["record_note"], d["record_path"])


def install_in_child(host_file: str | None, cred_file: str | None) -> None:
    """Called by ``host_seam/sitecustomize.py`` at a child's start."""
    if host_file:
        path = Path(host_file)
        sg.HOST = lambda _store_dir: read_host_file(path)
    if cred_file:
        d = json.loads(Path(cred_file).read_text(encoding="utf-8"))
        creds = sg.Credentials(int(d["egid"]), frozenset(int(g) for g in d["groups"]))
        store_writers.CREDENTIALS = lambda: creds


def holders(host: sg.HostGroups, gid: int) -> set[str]:
    """Every account the kernel lets act with ``gid`` on this host: as its primary group or as a listed member."""
    out = {a.name for a in host.accounts if a.primary == gid}
    for g in host.groups:
        if g.gid == gid:
            out |= set(g.members)
    return out


def store_state(aew_root: Path) -> dict[str, tuple[int, int]]:
    """Every store path (a directory ends in ``/``) -> (group, mode)."""
    import stat

    out = {}
    base = aew_root / "state"
    for d, dirs, files in os.walk(base):
        for name in ["", *dirs, *files]:
            if name == "" and Path(d) != base:
                continue
            path = Path(d) / name if name else Path(d)
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                continue
            rel = path.relative_to(aew_root).as_posix()
            out[rel + "/" if stat.S_ISDIR(st.st_mode) else rel] = (st.st_gid, stat.S_IMODE(st.st_mode))
    return out


def readers(host: sg.HostGroups, state: dict[str, tuple[int, int]]) -> set[str]:
    """Who besides the operator the kernel lets read some store path."""
    out: set[str] = set()
    for gid, mode in state.values():
        if mode & 0o040:
            out |= holders(host, gid) - {OP}
        if mode & 0o004:
            out.add("others")
    return out


def off_target(state: dict[str, tuple[int, int]], gid: int, modes: tuple[int, int]) -> dict[str, tuple[int, str]]:
    return {rel: (g, oct(m)) for rel, (g, m) in state.items()
            if (g, m) != (gid, modes[1] if rel.endswith("/") else modes[0])}

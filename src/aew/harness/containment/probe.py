"""The launch self-test: the run's own assembled layout, exercised before any harness process starts (M4-B).

A probe process runs inside the layout and tries what containment must stop and what the role must be able to do:

* append to an existing sentinel outside every writable root, and create a new sibling next to the workspace;
* open each protected path for writing (checked with ``access(W_OK)``, which a read-only mount refuses without
  changing anything): the repository's real git metadata, the project's ``.aew``, and two markers the host places
  for the probe only, one in the host's temporary directory (where every run's bridge socket lives) and one in a
  sibling run's directory (M4-B review: whatever widened the layout, reaching these fails the test);
* create a file in every writable root.

The host then checks the outcome itself: the sentinel is byte-identical, the sibling does not exist, each writable
root's file arrived on the host (a bind that is not the host's path is not a writable root). A layout that passes
is contained; anything else is a failure with its reason. The test catches bind-order mistakes, such as a broad
writable root laid over the read-only host.

The probe also reads what the gates' rows need (STG-05 CB-12, rows 2 to 5; row 1 is CS-3's network), each judged by
the host and recorded on the run's label, pass or fail:

* **row 2:** ``/run`` is a read-only tmpfs holding only what the layout put there, and the socket inventory
  (:mod:`.sockets`) is complete and has no failing socket;
* **row 3:** no display credential is readable, and no :data:`~.layout.DISPLAY_ENV` variable reaches the process
  (the probe is handed each of them, set, so a sandbox that does not unset them fails);
* **row 4:** the process has no controlling terminal. The kernel refuses ``TIOCSTI`` on a terminal that is not the
  caller's controlling terminal, to a caller without ``CAP_SYS_ADMIN`` in the initial user namespace, so with none
  no descriptor it holds accepts it. The probe checks the property and never pushes input anywhere;
* **row 5:** the writes above, and each mask holds: secret directories list empty, secret files read empty, a runs
  mask shows only the run's own directories, and neither marker is visible.
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aew.harness.containment import sockets
from aew.harness.containment.layout import (
    DISPLAY_ENV,
    SANDBOX_TMP,
    VAR_RUN,
    Layout,
    _within,
    bwrap_argv,
    host_masks,
)

TIMEOUT_S = 30.0
VERSION_TIMEOUT_S = 10.0
BOUND_S = TIMEOUT_S + VERSION_TIMEOUT_S  # the self-test and the mechanism check, at a run's start
# The socket walk's share of the self-test's bound: an incomplete inventory cannot certify row 2, so it fails (the Lead,
# 2026-10-23, on CS-2's plan, Q3).
WALK_BUDGET_S = TIMEOUT_S / 2
CANARY = "aew-self-test"  # the value of each DISPLAY_ENV variable the probe is handed

_PAYLOAD = r"""
import errno, json, os, re, stat, sys, time
spec = json.loads(sys.argv[1])
def append(p):
    try:
        fd = os.open(p, os.O_WRONLY | os.O_APPEND)
    except OSError:
        return False
    try:
        os.write(fd, b"x")
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
def create(p):
    try:
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return True
    except OSError:
        return False
def mounts():
    # (mount point, type, read-only), in mount order: of several mounts at one path, the last is on top
    out = []
    with open("/proc/self/mountinfo", "rb") as f:
        for line in f:
            left, _, right = line.partition(b" - ")
            fields, rest = left.split(), right.split()
            if len(fields) < 6 or not rest:
                continue
            point = os.fsdecode(re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), fields[4]))
            out.append((point, os.fsdecode(rest[0]), b"ro" in fields[5].split(b",")))
    return out
def walk(top, budget, unwalked, t0):
    # Every filesystem socket reachable by path: each mount point walked once from its path, never into another
    # mount point, no link followed, no stat but for an entry that is none of file, directory or link.
    found, walked, unlistable, skipped = [], 0, 0, []
    for point in sorted(top):
        if top[point] in unwalked:
            skipped.append({"path": point, "type": top[point]})
            continue
        if os.path.islink(point) or not os.path.isdir(point):
            continue  # over-mounted, or gone: not reachable by this path
        stack = [point]
        while stack:
            if time.monotonic() - t0 > budget:
                return found, walked, unlistable, skipped, False
            try:
                with os.scandir(stack.pop()) as it:
                    for e in it:
                        walked += 1
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if e.path not in top:
                                    stack.append(e.path)
                            elif not (e.is_file(follow_symlinks=False) or e.is_symlink()):
                                if stat.S_ISSOCK(e.stat(follow_symlinks=False).st_mode):
                                    found.append(e.path)
                        except OSError:
                            pass
            except OSError:
                unlistable += 1
    return found, walked, unlistable, skipped, True
def masked_tree(root, allowed):
    # what is in a host mask: anything that is neither what the layout put there nor on the way to it
    extra = []
    for d, dirs, files in os.walk(root):
        keep = []
        for n in dirs + files:
            p = os.path.join(d, n)
            if p in allowed:
                continue
            if any(a.startswith(p + "/") for a in allowed) and n in dirs and not os.path.islink(p):
                keep.append(n)
            else:
                extra.append(p)
        dirs[:] = [n for n in dirs if n in keep]
    return extra
def reads(p):
    try:
        with open(p, "rb") as f:
            return "empty" if not f.read(1) else "readable"
    except FileNotFoundError:
        return "absent"
    except IsADirectoryError:
        return "readable"
    except OSError:
        return "unreadable"
def listing(p):
    try:
        return sorted(os.listdir(p))
    except FileNotFoundError:
        return None
    except OSError as e:
        return [errno.errorcode.get(e.errno, str(e.errno))]
def terminal():
    fields = open("/proc/self/stat", "rb").read().rsplit(b")", 1)[1].split()
    try:
        os.close(os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY))
        tty = "opened"
    except OSError as e:
        tty = errno.errorcode.get(e.errno, str(e.errno))
    return {"tty_nr": int(fields[4]), "dev_tty": tty, "session_leader": os.getsid(0) == os.getpid()}
t0 = time.monotonic()
table = mounts()
top = {}
for point, fstype, ro in table:
    top[point] = (fstype, ro)
found, walked, unlistable, skipped, complete = walk({p: t for p, (t, _) in top.items()}, spec["walk_budget_s"],
                                                    set(spec["unwalked_fs"]), t0)
print(json.dumps({
    "sentinel_written": append(spec["sentinel"]),
    "sibling_created": create(spec["sibling"]),
    "writable": {p: create(os.path.join(p, spec["name"])) for p in spec["writable"]},
    "protected_writable": [p for p in spec["protected"] if os.access(p, os.W_OK)],
    "pid": os.getpid(),
    "host_masks": {h: {"type": (top.get(h) or [None])[0], "readonly": (top.get(h) or [None, False])[1],
                       "extra": masked_tree(h, set(spec["inside_host_masks"]))} for h in spec["host_masks"]},
    "var_run": os.path.realpath(spec["var_run"]) if os.path.lexists(spec["var_run"]) else None,
    "inventory": {"sockets": sorted(set(found)), "walked": walked, "unlistable": unlistable,
                  "unwalked_mounts": skipped, "seconds": round(time.monotonic() - t0, 3), "complete": complete},
    "display_files": {p: reads(p) for p in spec["display_files"]},
    "env_set": [n for n in spec["unset_env"] if n in os.environ],
    "terminal": terminal(),
    "hide_dirs": {p: listing(p) for p in spec["hide_dirs"]},
    "hide_files": {p: reads(p) for p in spec["hide_files"]},
    "hide_runs": {p: listing(p) for p in spec["hide_runs"]},
    "markers_visible": [m for m in spec["markers"] if os.path.lexists(m)],
}))
"""


def self_test(layout: Layout, *, sentinel_dir: Path, sibling_dir: Path, own: tuple[str, ...] = (),
              walk_budget_s: float = WALK_BUDGET_S, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Run the probe in ``layout``. Returns ``{"ok": bool, "reason": str | None, "rows": {...}, ...}``; never raises
    for a containment failure (the caller decides by policy). ``own`` holds the run's own socket directories (its
    bridge); ``env`` is the launching environment the socket classes read (default: this process's)."""
    name = f".aew-containment-probe-{secrets.token_hex(8)}"
    sentinel = sentinel_dir / f"{name}.sentinel"
    sibling = sibling_dir / f"{name}.sibling"
    content = secrets.token_hex(16).encode()
    sentinel.write_bytes(content)
    markers = _markers(layout, name)
    extra = [str(m) for m in markers] + [str(Path(v) / ".aew") for v in layout.visible
                                         if (Path(v) / ".aew").is_dir()]
    spec = {"sentinel": str(sentinel), "sibling": str(sibling), "name": name,
            "writable": list(layout.writable), "protected": [*layout.protected, *extra],
            "walk_budget_s": walk_budget_s, "unwalked_fs": sorted(sockets.UNWALKED_FS),
            "host_masks": list(_host_masks(layout)), "inside_host_masks": list(layout.inside_host_masks()),
            "var_run": VAR_RUN, "display_files": list(layout.display_files), "unset_env": list(DISPLAY_ENV),
            "hide_dirs": list(layout.hide_dirs), "hide_files": list(layout.hide_files),
            "hide_runs": list(layout.hide_runs),
            # the markers a mask hides: a sibling run's, and the temporary directory's when it is /tmp (TMPDIR may
            # name a directory the read-only root shows; the bridge sockets live under /tmp whatever it says)
            "markers": [str(m) for m in markers if any(_within(str(m), h) for h in (SANDBOX_TMP, *layout.hide_runs))]}
    result: dict[str, Any] = {"ok": False, "reason": None, "probe": name}
    try:
        try:
            done = subprocess.run(bwrap_argv(layout, [sys.executable, "-I", "-c", _PAYLOAD, json.dumps(spec)]),
                                  capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL,
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
                                       **dict.fromkeys(DISPLAY_ENV, CANARY)})
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["reason"] = f"the sandbox could not run: {type(exc).__name__}: {exc}"
            return result
        if done.returncode != 0:
            err = (done.stderr or "").strip().splitlines()
            last = err[-1] if err else "no output"
            result["reason"] = f"the sandbox could not start (exit {done.returncode}): {last}"
            return result
        try:
            seen = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result["reason"] = "the probe reported nothing readable"
            return result
        rows = _rows(layout, seen, own=own, env=os.environ if env is None else env, written=(sentinel, content),
                     sibling=sibling, name=name)
        problems = [f"row {n} ({row['name']}): {row['reason']}" for n, row in rows.items() if not row["ok"]]
        result.update(ok=not problems, reason="; ".join(problems) or None, probe_pid=seen.get("pid"), rows=rows)
        return result
    finally:
        for m in markers:
            m.unlink(missing_ok=True)
            if m.parent.name.endswith(".probe-run"):
                m.parent.rmdir()
        sentinel.unlink(missing_ok=True)
        if sibling.exists():
            sibling.unlink()
        for root in layout.writable:
            (Path(root) / name).unlink(missing_ok=True)


def _rows(layout: Layout, seen: dict[str, Any], *, own: tuple[str, ...], env: Mapping[str, str],
          written: tuple[Path, bytes], sibling: Path, name: str) -> dict[str, dict[str, Any]]:
    """CB-12's rows 2 to 5, judged on the host from what the probe saw. Each row says what it checked."""
    return {"2": _row2(layout, seen, own=own, env=env), "3": _row3(seen), "4": _row4(seen),
            "5": _row5(layout, seen, written=written, sibling=sibling, name=name)}


def _row(name: str, problems: list[str], **facts: Any) -> dict[str, Any]:
    return {"name": name, "ok": not problems, "reason": "; ".join(problems) or None, **facts}


def _host_masks(layout: Layout) -> tuple[str, ...]:
    """The trees row 2 finds masked: the host's runtime trees as they are now (``layout.host_masks``), whatever the
    layout says, and the layout's own: a layout that lost its ``/run`` mask fails the row instead of passing it."""
    return tuple(dict.fromkeys((*host_masks(), *layout.hide_host)))


def _row2(layout: Layout, seen: dict[str, Any], *, own: tuple[str, ...], env: Mapping[str, str]) -> dict[str, Any]:
    problems = []
    masks = seen.get("host_masks") or {}
    for h in _host_masks(layout):
        mask = masks.get(h) or {}
        if mask.get("type") != "tmpfs" or not mask.get("readonly"):
            problems.append(f"{h} is not a read-only tmpfs inside (it is {mask.get('type')}, "
                            f"{'read-only' if mask.get('readonly') else 'writable'})")
        if mask.get("extra"):
            problems.append(f"{h} holds what the layout did not put there: {', '.join(mask['extra'][:5])}")
    var_run = seen.get("var_run")
    if var_run is not None and not any(_within(var_run, h) for h in _host_masks(layout)):
        problems.append(f"{VAR_RUN} leads to {var_run}, outside the masked {', '.join(_host_masks(layout))}")
    inventory = seen.get("inventory") or {}
    found = [{"path": p, "class": sockets.classify(p, own=own, env=env)} for p in inventory.get("sockets") or []]
    failing = [s for s in found if s["class"] in sockets.FAILING]
    if not inventory.get("complete"):
        problems.append(f"the socket inventory did not finish within {WALK_BUDGET_S:g}s of walking "
                        f"({inventory.get('walked')} entries), so it cannot show that no socket reaches the display, "
                        "G3, an AEW service or a credential")
    problems += [f"a {s['class']} socket is reachable: {s['path']}" for s in failing]
    return _row("run_and_sockets", problems, host_masks=masks, sockets=found,
                **{k: inventory.get(k) for k in ("walked", "unlistable", "unwalked_mounts", "seconds", "complete")})


def _row3(seen: dict[str, Any]) -> dict[str, Any]:
    files = seen.get("display_files") or {}
    readable = [p for p, state in files.items() if state not in ("absent", "empty", "unreadable")]
    problems = [f"display credential {p} is readable from inside" for p in readable]
    problems += [f"{n} reaches a contained process" for n in seen.get("env_set") or []]
    return _row("display", problems, files=files, env_set=seen.get("env_set") or [])


def _row4(seen: dict[str, Any]) -> dict[str, Any]:
    """No controlling terminal, read on the started process itself: ``tty_nr`` 0 in its own ``/proc/self/stat`` and
    ``ENXIO`` from ``/dev/tty``. Whether it leads its session is a fact on the label, not a condition: under
    bubblewrap's ``--new-session`` the session's leader is bubblewrap's own process in the sandbox (seen on CI)."""
    term = seen.get("terminal") or {}
    problems = []
    if term.get("tty_nr") != 0 or term.get("dev_tty") != errno.errorcode[errno.ENXIO]:
        problems.append(f"the process has a controlling terminal (tty_nr {term.get('tty_nr')}, /dev/tty "
                        f"{term.get('dev_tty')})")
    return _row("terminal", problems, **term)


def _row5(layout: Layout, seen: dict[str, Any], *, written: tuple[Path, bytes], sibling: Path,
          name: str) -> dict[str, Any]:
    problems = []
    sentinel, content = written
    if sentinel.read_bytes() != content or seen.get("sentinel_written"):
        problems.append(f"a file outside the writable roots was modified ({sentinel})")
    if sibling.exists():
        problems.append(f"a new file was created outside the writable roots ({sibling})")
    for root, created in (seen.get("writable") or {}).items():
        if not created or not (Path(root) / name).exists():
            problems.append(f"writable root {root} is not writable on the host from inside")
    for path in seen.get("protected_writable") or []:
        problems.append(f"protected path {path} is writable from inside")
    for path, entries in (seen.get("hide_dirs") or {}).items():
        if entries:  # None: absent, hidden with a masked tree
            problems.append(f"masked directory {path} is not empty inside")
    for path, state in (seen.get("hide_files") or {}).items():
        if state not in ("absent", "empty"):
            problems.append(f"masked file {path} is {state} inside")
    for path, entries in (seen.get("hide_runs") or {}).items():
        own = {os.path.relpath(p, path).split(os.sep)[0] for p in (*layout.writable, *layout.readonly)
               if _within(p, path) and p != path}
        if entries is None:
            problems.append(f"the runs mask {path} is missing inside")
        elif set(entries) - own:
            problems.append(f"the runs mask {path} shows {sorted(set(entries) - own)} beyond this run's own "
                            "directories")
    problems += [f"{m} is visible from inside" for m in seen.get("markers_visible") or []]
    return _row("binds_and_masks", problems)


def _markers(layout: Layout, name: str) -> list[Path]:
    """Files the probe must not be able to write: one in the host's temporary directory, one in a sibling run."""
    import tempfile

    out = [Path(tempfile.gettempdir()) / f"{name}.tmp-marker"]
    for runs in layout.hide_runs:
        sibling = Path(runs) / f"{name}.probe-run"
        sibling.mkdir()
        out.append(sibling / "marker")
    for m in out:
        m.write_bytes(b"")
    return out


def mechanism(layout: Layout) -> str:
    """``bubblewrap <version>`` of the binary the layout uses."""
    try:
        out = subprocess.run([layout.bwrap, "--version"], capture_output=True, text=True, timeout=VERSION_TIMEOUT_S,
                             stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return out or "bubblewrap"

"""The arm-host agent (F19 plan v5 §2.2, §2.3; ADR-0018 D2, D5, D7).

The evaluator reaches it through one forced command (``python -I -m aew_eval.armhost --limits <host record>``): each
call is one request frame on standard input and one reply frame on standard output (:mod:`aew_eval.transport`). Its
transfer bounds come from its host record (``--limits``; root-owned on an arm host, S17), never from a request. It
keeps two directories per released run, ``runs/<experiment>/<name>/``: one under its own state root (``--state``,
0700, outside every tree the arm can write) for the run's state, its released bundle and its collect cache, and one
under the work root (``--root``) for the arm's ``repo``. Nothing it trusts is read from the work root, and every file
it writes is created exclusively, never through a link:

* ``hello`` and ``preflight`` keep no state; the order of a release (a preflight first) is the evaluator's;
* ``hello``: the agent's protocol, process and platform;
* ``preflight``: the arm-host rule and the attestation, bound to the run, the treatment, the base and the snapshot
  it echoes. **S4 establishes nothing** (``established: false``, no checks): the checks are S5's. The evaluator
  releases nothing to a model arm or of a held-out case on a preflight that is not established (HOC-06, HOC-07,
  HOC-11), so until S5 only scripted cells of public and synthetic cases are released;
* ``release`` (once): hostile receive of the release bundle against the hash the evaluator recorded
  (``TRANSFER_CORRUPT``);
* ``run`` (once, after ``release``): the released arm on the released starting files. S4 runs the ``scripted`` arm
  only and refuses every other kind (``ARM_KIND_REFUSED``); S8's supervisor replaces this verb for the model arms;
* ``collect`` (after ``run``, and repeatable: a later call returns the first one's bytes): the final work tree as a
  bundle, ``.git`` left out, links as data entries; anything else that is not a regular file (a FIFO, a socket, a
  device), a name another platform cannot hold or that is not valid UTF-8, and a directory it cannot list, is listed
  by path in the reply's ``other`` (bounded by its serialized size), never read.

It holds no corpus, ledger, preregistration or oracle, and imports nothing that reads one (a static test checks its
import graph). Its facts are the guest agent's (plan §4): the run record labels them so.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_eval import fixture
from aew_eval.arms import ScriptedArm
from aew_eval.schemas import Invalid, validate
from aew_eval.transport import (
    DEFAULT_LIMITS,
    Entry,
    Limits,
    TransferError,
    check_path,
    encode_frame,
    load_limits,
    pack,
    printable,
    read_frame,
    receive,
)

PROTOCOL_VERSION = 1
DEFAULT_ROOT = Path("/srv/aew-run/arm")  # the work root: the arm's own tree
DEFAULT_STATE_ROOT = Path("/srv/aew-run/state/armhost")  # the agent's own, 0700 (plan v5 §2.1)
RUN_ID = re.compile(r"^(?P<experiment>[a-z0-9][a-z0-9-]*)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$")
OTHER_BYTES = 256 * 1024  # the serialized size of a collect reply's ``other``; the rest are counted
OTHER_PATH_CHARS = 1024
RUN_MANIFEST = "aew/m4h-run-manifest/v1"


class AgentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _facts() -> dict[str, Any]:
    return {"platform": sys.platform, "python": ".".join(map(str, sys.version_info[:3])), "pid": os.getpid()}


class Agent:
    """The agent over two roots: ``state_root``, its own (0700, outside every tree the arm can write: plan v5 §2.1's
    ``/srv/aew-run/state/``), holding each run's state, released bundle and collect cache; and ``work_root``, where
    the arm works (each run's ``repo``), which the agent only builds and walks. Nothing the agent trusts is read from
    the work root, and every file it writes is created ``O_CREAT|O_EXCL`` (and ``O_NOFOLLOW`` where the platform has
    it) and read back without following a link (PR #189 re-review)."""

    def __init__(self, root: Path, limits: Limits = DEFAULT_LIMITS, *, state_root: Path | None = None) -> None:
        self.root = root  # the work root
        self.state_root = state_root if state_root is not None else DEFAULT_STATE_ROOT
        self.limits = limits

    # ------------------------------------------------------------------ per-run state

    def _run_dirs(self, run_id: str | None) -> tuple[Path, Path]:
        """The run's private state directory and its work directory."""
        found = RUN_ID.match(run_id or "")
        if found is None:
            raise AgentError("BAD_REQUEST", f"{run_id!r} is not a run id")
        rel = Path("runs") / found["experiment"] / found["name"]
        return self.state_root / rel, self.root / rel

    def _state(self, state_dir: Path) -> dict[str, Any]:
        try:
            return json.loads(read_private(state_dir / "state.json"))
        except FileNotFoundError:
            raise AgentError("OUT_OF_ORDER", "this run was never released here") from None

    def _advance(self, state_dir: Path, state: dict[str, Any], expect: str, phase: str) -> None:
        if state["phase"] != expect:
            raise AgentError("OUT_OF_ORDER", f"this run is {state['phase']}; the verb needs it {expect}")
        state["phase"] = phase
        write_private(state_dir / "state.json", json.dumps(state, sort_keys=True).encode("utf-8"))

    # ------------------------------------------------------------------ verbs

    def handle(self, verb: str, run_id: str | None, args: dict[str, Any], payload: bytes) -> tuple[dict, bytes]:
        if verb == "hello":
            return {"protocol": PROTOCOL_VERSION, **_facts()}, b""
        if verb == "preflight":
            return self.preflight(run_id, args), b""
        state_dir, work = self._run_dirs(run_id)
        if verb == "release":
            return self.release(state_dir, work, run_id or "", args, payload), b""
        if verb == "run":
            return self.run(state_dir, work, args), b""
        if verb == "collect":
            return self.collect(state_dir, work)
        raise AgentError("BAD_REQUEST", f"no verb {verb!r}")

    def preflight(self, run_id: str | None, args: dict[str, Any]) -> dict[str, Any]:
        binding = args.get("binding")
        if not isinstance(binding, dict) or binding.get("run_id") != run_id:
            raise AgentError("BAD_REQUEST", "a preflight binds the run it is for")
        # S5 adds the arm-host rule (mounts, WSL drives and interop, agent sockets, operator sessions, the canary
        # scan) and the attestation. Until then nothing is established, and no held-out case is released.
        return {"binding": binding, "established": False, "checks": [], "facts": _facts()}

    def release(self, state_dir: Path, work: Path, run_id: str, args: dict[str, Any],
                payload: bytes) -> dict[str, Any]:
        expected = args.get("bundle_sha256")
        if not isinstance(expected, str):
            raise AgentError("BAD_REQUEST", "a release names the bundle's hash")
        if os.path.lexists(state_dir) or os.path.lexists(work):
            raise AgentError("OUT_OF_ORDER", "this run was already released here: a run is released once")
        private_dirs(state_dir)
        received = receive(payload, state_dir / "bundle", limits=self.limits, expected_sha256=expected)
        task = self._task(state_dir, received.files)
        if task["run_id"] != run_id:
            raise AgentError("TRANSFER_CORRUPT", "the bundle is for another run")
        work.mkdir(parents=True)
        state = {"run_id": run_id, "phase": "received", "bundle_sha256": received.sha256}
        write_private(state_dir / "state.json", json.dumps(state, sort_keys=True).encode("utf-8"))
        self._advance(state_dir, state, "received", "released")
        return {"bundle_sha256": received.sha256}

    def _task(self, state_dir: Path, files: dict[str, tuple[str, int]]) -> dict[str, Any]:
        """The bundle's ``task.json``, checked for what the agent reads from it."""
        if "task.json" not in files or "run-manifest.json" not in files:
            raise AgentError("TRANSFER_CORRUPT", "the bundle lacks task.json or run-manifest.json")
        bundle = state_dir / "bundle"
        try:
            task = json.loads(read_private(bundle / "task.json"))
            validate(RUN_MANIFEST, json.loads(read_private(bundle / "run-manifest.json")),
                     what="the released run manifest")
        except (ValueError, Invalid) as exc:  # json's errors are ValueErrors
            raise AgentError("TRANSFER_CORRUPT", str(exc)) from None
        if not isinstance(task, dict) or not isinstance(task.get("arm"), dict) or not isinstance(task.get("case"), str):
            raise AgentError("TRANSFER_CORRUPT", "task.json is not a task")
        return task

    def run(self, state_dir: Path, work: Path, args: dict[str, Any]) -> dict[str, Any]:
        state = self._state(state_dir)
        self._advance(state_dir, state, "released", "running")
        bundle = state_dir / "bundle"
        task = json.loads(read_private(bundle / "task.json"))
        arm = task["arm"]
        if arm.get("kind") != "scripted":
            raise AgentError("ARM_KIND_REFUSED", f"this agent runs the scripted arm only, not {arm.get('kind')!r}: "
                             "the model arms run under the supervisor (F19 plan v5, S8)")
        files = {p.relative_to(bundle / "files").as_posix(): read_private(p)
                 for p in sorted((bundle / "files").rglob("*")) if p.is_file()} if (bundle / "files").is_dir() else {}
        task_text = None
        if task.get("task_file"):
            task_text = read_private(bundle / check_path(task["task_file"], "the task file")).decode("utf-8")
        deadline_s = float(args.get("deadline_s", 3600.0))
        started, t0 = _now(), time.monotonic()
        base = None
        error = None
        outcome: dict[str, Any] = {}
        harness: dict[str, Any] = {"name": "scripted"}
        try:
            repo = work / "repo"
            fixture.build_files(files, repo, f"{task['case']}: starting point" + (" (seeded)" if task.get("seeded")
                                                                                  else ""))
            base = fixture.git(repo, "rev-parse", "HEAD")
            result = ScriptedArm().run(repo, arm.get("config") or {}, deadline_s=deadline_s, task=task_text)
            outcome, harness = result.outcome, result.harness
        except Exception as exc:  # noqa: BLE001 (the run happened and failed: recorded, never a lost reply)
            error = f"{type(exc).__name__}: {exc}"[-600:]
        self._advance(state_dir, state, "running", "ran")
        return {"started_at": started, "ended_at": _now(), "wall_s": round(time.monotonic() - t0, 3),
                "base_commit": base, "outcome": outcome, "harness": harness, "environment": _facts(), "error": error}

    def collect(self, state_dir: Path, work: Path) -> tuple[dict[str, Any], bytes]:
        """The final tree as a bundle. Repeatable once the run has ended: the first collect keeps its bundle and
        reply in the run's private state directory, and a later one (after a reply lost in transit) returns the same
        bytes (PR #189 review, F11). Nothing in the work tree is ever served as the cache."""
        state = self._state(state_dir)
        cached_tar, cached_reply = state_dir / "collect.tar", state_dir / "collect.json"
        if state["phase"] == "collected":
            return json.loads(read_private(cached_reply)), read_private(cached_tar)
        if state["phase"] != "ran":
            raise AgentError("OUT_OF_ORDER", f"this run is {state['phase']}; the verb needs it ran")
        repo = work / "repo"
        try:
            entries, other = _walk(repo, self.limits) if repo.is_dir() and not fixture.is_link(repo) else ([], {})
            data, digest = pack([Entry(f"tree/{e.path}", e.kind, e.data, e.target) for e in entries],
                                limits=self.limits)
        except TransferError as exc:
            raise AgentError(exc.code, exc.detail) from None
        listed, omitted = bound_other(other)
        reply = {"manifest_sha256": digest, "other": listed, "other_omitted": omitted}
        write_private(cached_tar, data)
        write_private(cached_reply, json.dumps(reply, sort_keys=True).encode("utf-8"))
        self._advance(state_dir, state, "ran", "collected")
        return reply, data


O_BINARY = getattr(os, "O_BINARY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def private_dirs(path: Path) -> None:
    """``path`` and its missing parents, created 0700; refused if any of them is a link or not a directory."""
    missing = []
    here = path
    while not os.path.lexists(here):
        missing.append(here)
        here = here.parent
    for d in reversed(missing):
        os.mkdir(d, 0o700)
    for d in [path, *missing]:
        if fixture.is_link(d) or not d.is_dir():
            raise AgentError("STATE_UNSAFE", f"{d} is a link or not a directory")


def write_private(path: Path, data: bytes) -> None:
    """``data`` at ``path``, through a fresh temporary file created ``O_CREAT|O_EXCL|O_NOFOLLOW`` (never through a
    link or over an existing file), synced, then renamed into place."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.partial")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_BINARY, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def read_private(path: Path) -> bytes:
    """A regular file's bytes, opened without following a link."""
    fd = os.open(path, os.O_RDONLY | O_NOFOLLOW | O_BINARY)
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode) or fixture.is_link(path):
            raise AgentError("STATE_UNSAFE", f"{path} is not a regular file")
        return fh.read()


def bound_other(other: dict[str, str]) -> tuple[dict[str, str], int]:
    """The paths a collect reply lists in ``other``, bounded by their serialized size (:data:`OTHER_BYTES`), so the
    reply stays well under its 1 MiB JSON bound whatever names the arm made (PR #189 review, F2); a path over
    :data:`OTHER_PATH_CHARS` characters, and every path past the bound, is counted in ``other_omitted``."""
    listed: dict[str, str] = {}
    size = 0
    for rel, kind in sorted(other.items()):
        cost = len(json.dumps(rel)) + len(json.dumps(kind)) + 4  # with json.dumps's ", " and ": "
        if len(rel) > OTHER_PATH_CHARS or size + cost > OTHER_BYTES:
            continue
        listed[rel] = kind
        size += cost
    return listed, len(other) - len(listed)


def _walk(repo: Path, limits: Limits = DEFAULT_LIMITS) -> tuple[list[Entry], dict[str, str]]:
    """The work tree as bundle entries, read without git and never following a link: regular files with their bytes,
    links with their target text. Everything else is listed in ``other`` (keyed by :func:`printable` path) and never
    read: a FIFO, socket or device (``special``); a name another platform could not hold, that is not valid UTF-8, or
    that differs from an earlier one only in case, and a link whose target is not valid UTF-8 (``unsafe-name``); a
    directory that cannot be listed (``unreadable``). ``.git`` at the root is left out. A file is sized before it is
    read, so the agent never holds more than the bounds (PR #189 review, F1, F3, F8)."""
    entries: list[Entry] = []
    other: dict[str, str] = {}
    folded: set[str] = set()
    total = 0

    def admit(rel: str) -> bool:
        try:
            check_path(rel, "a work-tree path")
        except Invalid:
            other[printable(rel)] = "unsafe-name"
            return False
        if rel.casefold() in folded:
            other[printable(rel)] = "unsafe-name"
            return False
        folded.add(rel.casefold())
        return True

    def unreadable(exc: OSError) -> None:
        where = Path(exc.filename) if exc.filename else repo
        rel = where.relative_to(repo).as_posix() if where != repo else "."
        other[printable(rel)] = "unreadable"

    def bounded(rel: str, size: int) -> None:
        nonlocal total
        if size > limits.file_bytes:
            raise TransferError("OVER_BOUNDS", f"{rel} is {size} bytes; the bound is {limits.file_bytes}")
        total += size
        if total > limits.total_bytes:
            raise TransferError("OVER_BOUNDS", f"more than {limits.total_bytes} bytes in total")

    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False, onerror=unreadable):
        here = Path(dirpath)
        if here == repo:
            dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in sorted(dirnames):
            p = here / name
            rel = p.relative_to(repo).as_posix()
            if fixture.is_link(p):
                dirnames.remove(name)
                if admit(rel):
                    _link_entry(p, rel, entries, other)
            elif not admit(rel):
                dirnames.remove(name)
        for name in sorted(filenames):
            p = here / name
            rel = p.relative_to(repo).as_posix()
            if not admit(rel):
                continue
            st = os.lstat(p)
            if fixture.is_link(p):
                _link_entry(p, rel, entries, other)
            elif stat.S_ISREG(st.st_mode):
                bounded(rel, st.st_size)
                fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as fh:
                    size = os.fstat(fh.fileno()).st_size  # it may have grown since lstat
                    if size > limits.file_bytes:
                        raise TransferError("OVER_BOUNDS", f"{rel} is {size} bytes; the bound is "
                                            f"{limits.file_bytes}")
                    data = fh.read(limits.file_bytes + 1)
                if len(data) > limits.file_bytes:
                    raise TransferError("OVER_BOUNDS", f"{rel} grew past {limits.file_bytes} bytes while read")
                entries.append(Entry(rel, "file", data=data))
            else:
                other[printable(rel)] = "special"
            if len(entries) > limits.entries:
                raise TransferError("OVER_BOUNDS", f"more than {limits.entries} entries")
    return entries, other


def _link_entry(p: Path, rel: str, entries: list[Entry], other: dict[str, str]) -> None:
    try:
        target = os.readlink(p)
    except (OSError, ValueError):  # a reparse point that is not a link
        other[printable(rel)] = "special"
        return
    try:
        target.encode("utf-8")
    except UnicodeEncodeError:
        other[printable(rel)] = "unsafe-name"
        return
    entries.append(Entry(rel, "link", target=target))


def _failure(verb: str, code: str, message: str) -> dict[str, Any]:
    return {"kind": "reply", "verb": verb, "ok": False, "error": {"code": code, "message": printable(message)[-2000:]},
            "result": {}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.armhost")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="the work root, where the arm works")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE_ROOT,
                    help="the agent's own state root, outside every tree the arm can write")
    ap.add_argument("--limits", type=Path, default=None,
                    help="the host record of this agent's transfer bounds (root-owned on an arm host; S17)")
    args = ap.parse_args(argv)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    verb = "hello"
    body = b""
    try:
        agent = Agent(args.root.resolve(), load_limits(args.limits) if args.limits else DEFAULT_LIMITS,
                      state_root=args.state.resolve())
        message, payload = read_frame(stdin, what="request", limits=agent.limits,
                                      max_payload=agent.limits.tar_bytes())
        verb = message["verb"]
        if message["kind"] != "request":
            raise AgentError("BAD_REQUEST", "the agent answers requests only")
        result, body = agent.handle(verb, message["run_id"], message["args"], payload)
        reply = {"kind": "reply", "verb": verb, "ok": True, "error": None, "result": result}
    except (AgentError, TransferError) as exc:
        reply, body = _failure(verb, exc.code, str(exc)), b""
    except Exception as exc:  # noqa: BLE001 (any other failure is still one bounded, typed reply)
        reply, body = _failure(verb, "ARMHOST_ERROR", f"{type(exc).__name__}: {exc}"), b""
    try:
        frame = encode_frame(reply, body)
    except Exception as exc:  # noqa: BLE001 (a reply that cannot be encoded is still answered, never a crash)
        frame = encode_frame(_failure(verb, "ARMHOST_ERROR", f"the reply could not be encoded ({type(exc).__name__})"))
    stdout.write(frame)
    stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

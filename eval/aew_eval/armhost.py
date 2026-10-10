"""The arm-host agent (F19 plan v5 §2.2, §2.3; ADR-0018 D2, D7).

The evaluator reaches it through one forced command (``python -I -m aew_eval.armhost``): each call is one request
frame on standard input and one reply frame on standard output (:mod:`aew_eval.transport`). It keeps one directory
per released run under its root, ``runs/<experiment>/<name>/``, and runs that run's verbs in order, each once:

* ``hello``: the agent's protocol, process and platform;
* ``preflight``: the arm-host rule and the attestation, bound to the run, the treatment, the base and the snapshot
  it echoes. **S4 establishes nothing** (``established: false``, no checks): the checks are S5's. The evaluator never
  releases a held-out case on a preflight that is not established (HOC-11), so until S5 only public and synthetic
  cases are released;
* ``release``: hostile receive of the release bundle against the hash the evaluator recorded (``TRANSFER_CORRUPT``);
* ``run``: the released arm on the released starting files. S4 runs the ``scripted`` arm only and refuses every other
  kind (``ARM_KIND_REFUSED``); S8's supervisor replaces this verb for the model arms;
* ``collect``: the final work tree as a bundle, ``.git`` left out, links as data entries, anything else that is not a
  regular file (a FIFO, a socket, a device) or that has a name another platform cannot hold listed by path in the
  reply's ``other``, never read.

It holds no corpus, ledger, preregistration or oracle, and imports nothing that reads one (a static test checks its
import graph). Its facts are the guest agent's (plan §4): the run record labels them so.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    pack,
    read_frame,
    receive,
)

PROTOCOL_VERSION = 1
DEFAULT_ROOT = Path("/srv/aew-run/arm")
RUN_ID = re.compile(r"^(?P<experiment>[a-z0-9][a-z0-9-]*)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$")
OTHER_CAP = 1000  # paths listed in a collect reply's ``other``; the rest are counted (the reply stays under 1 MiB)
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
    def __init__(self, root: Path, limits: Limits = DEFAULT_LIMITS) -> None:
        self.root = root
        self.limits = limits

    # ------------------------------------------------------------------ per-run state

    def _run_dir(self, run_id: str | None) -> Path:
        found = RUN_ID.match(run_id or "")
        if found is None:
            raise AgentError("BAD_REQUEST", f"{run_id!r} is not a run id")
        return self.root / "runs" / found["experiment"] / found["name"]

    def _state(self, run: Path) -> dict[str, Any]:
        path = run / "state.json"
        if not path.is_file():
            raise AgentError("OUT_OF_ORDER", "this run was never released here")
        return json.loads(path.read_text(encoding="utf-8"))

    def _advance(self, run: Path, state: dict[str, Any], expect: str, phase: str) -> None:
        if state["phase"] != expect:
            raise AgentError("OUT_OF_ORDER", f"this run is {state['phase']}; the verb needs it {expect}")
        state["phase"] = phase
        tmp = run / "state.json.partial"
        tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, run / "state.json")

    # ------------------------------------------------------------------ verbs

    def handle(self, verb: str, run_id: str | None, args: dict[str, Any], payload: bytes) -> tuple[dict, bytes]:
        if verb == "hello":
            return {"protocol": PROTOCOL_VERSION, **_facts()}, b""
        if verb == "preflight":
            return self.preflight(run_id, args), b""
        run = self._run_dir(run_id)
        if verb == "release":
            return self.release(run, run_id or "", args, payload), b""
        if verb == "run":
            return self.run(run, args), b""
        if verb == "collect":
            return self.collect(run)
        raise AgentError("BAD_REQUEST", f"no verb {verb!r}")

    def preflight(self, run_id: str | None, args: dict[str, Any]) -> dict[str, Any]:
        binding = args.get("binding")
        if not isinstance(binding, dict) or binding.get("run_id") != run_id:
            raise AgentError("BAD_REQUEST", "a preflight binds the run it is for")
        # S5 adds the arm-host rule (mounts, WSL drives and interop, agent sockets, operator sessions, the canary
        # scan) and the attestation. Until then nothing is established, and no held-out case is released.
        return {"binding": binding, "established": False, "checks": [], "facts": _facts()}

    def release(self, run: Path, run_id: str, args: dict[str, Any], payload: bytes) -> dict[str, Any]:
        expected = args.get("bundle_sha256")
        if not isinstance(expected, str):
            raise AgentError("BAD_REQUEST", "a release names the bundle's hash")
        if run.exists():
            raise AgentError("OUT_OF_ORDER", "this run was already released here: a run is released once")
        run.parent.mkdir(parents=True, exist_ok=True)
        run.mkdir()
        received = receive(payload, run / "bundle", limits=self.limits, expected_sha256=expected)
        task = self._task(run, received.files)
        if task["run_id"] != run_id:
            raise AgentError("TRANSFER_CORRUPT", "the bundle is for another run")
        state = {"run_id": run_id, "phase": "received", "bundle_sha256": received.sha256}
        (run / "state.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        self._advance(run, state, "received", "released")
        return {"bundle_sha256": received.sha256}

    def _task(self, run: Path, files: dict[str, tuple[str, int]]) -> dict[str, Any]:
        """The bundle's ``task.json``, checked for what the agent reads from it."""
        if "task.json" not in files or "run-manifest.json" not in files:
            raise AgentError("TRANSFER_CORRUPT", "the bundle lacks task.json or run-manifest.json")
        try:
            task = json.loads((run / "bundle" / "task.json").read_text(encoding="utf-8"))
            validate(RUN_MANIFEST, json.loads((run / "bundle" / "run-manifest.json").read_text(encoding="utf-8")),
                     what="the released run manifest")
        except (ValueError, Invalid) as exc:  # json's errors are ValueErrors
            raise AgentError("TRANSFER_CORRUPT", str(exc)) from None
        if not isinstance(task, dict) or not isinstance(task.get("arm"), dict) or not isinstance(task.get("case"), str):
            raise AgentError("TRANSFER_CORRUPT", "task.json is not a task")
        return task

    def run(self, run: Path, args: dict[str, Any]) -> dict[str, Any]:
        state = self._state(run)
        self._advance(run, state, "released", "running")
        bundle = run / "bundle"
        task = json.loads((bundle / "task.json").read_text(encoding="utf-8"))
        arm = task["arm"]
        if arm.get("kind") != "scripted":
            raise AgentError("ARM_KIND_REFUSED", f"this agent runs the scripted arm only, not {arm.get('kind')!r}: "
                             "the model arms run under the supervisor (F19 plan v5, S8)")
        files = {p.relative_to(bundle / "files").as_posix(): p.read_bytes()
                 for p in sorted((bundle / "files").rglob("*")) if p.is_file()} if (bundle / "files").is_dir() else {}
        task_text = None
        if task.get("task_file"):
            task_text = (bundle / check_path(task["task_file"], "the task file")).read_text(encoding="utf-8")
        deadline_s = float(args.get("deadline_s", 3600.0))
        started, t0 = _now(), time.monotonic()
        base = None
        error = None
        outcome: dict[str, Any] = {}
        harness: dict[str, Any] = {"name": "scripted"}
        try:
            repo = run / "repo"
            fixture.build_files(files, repo, f"{task['case']}: starting point" + (" (seeded)" if task.get("seeded")
                                                                                  else ""))
            base = fixture.git(repo, "rev-parse", "HEAD")
            result = ScriptedArm().run(repo, arm.get("config") or {}, deadline_s=deadline_s, task=task_text)
            outcome, harness = result.outcome, result.harness
        except Exception as exc:  # noqa: BLE001 (the run happened and failed: recorded, never a lost reply)
            error = f"{type(exc).__name__}: {exc}"[-600:]
        self._advance(run, state, "running", "ran")
        return {"started_at": started, "ended_at": _now(), "wall_s": round(time.monotonic() - t0, 3),
                "base_commit": base, "outcome": outcome, "harness": harness, "environment": _facts(), "error": error}

    def collect(self, run: Path) -> tuple[dict[str, Any], bytes]:
        state = self._state(run)
        repo = run / "repo"
        entries, other = _walk(repo) if repo.is_dir() else ([], {})
        try:
            data, digest = pack([Entry(f"tree/{e.path}", e.kind, e.data, e.target) for e in entries],
                                limits=self.limits)
        except TransferError as exc:
            raise AgentError(exc.code, exc.detail) from None
        self._advance(run, state, "ran", "collected")
        listed = dict(sorted(other.items())[:OTHER_CAP])
        return {"manifest_sha256": digest, "other": listed, "other_omitted": len(other) - len(listed)}, data


def _walk(repo: Path) -> tuple[list[Entry], dict[str, str]]:
    """The work tree as bundle entries, read without git and never following a link: regular files with their bytes,
    links with their target text; everything else, and any name another platform could not hold (or that differs
    from an earlier one only in case), listed in ``other`` and not read. ``.git`` at the root is left out."""
    entries: list[Entry] = []
    other: dict[str, str] = {}
    folded: set[str] = set()

    def admit(rel: str) -> bool:
        try:
            check_path(rel, "a work-tree path")
        except Invalid:
            other[rel] = "unsafe-name"
            return False
        if rel.casefold() in folded:
            other[rel] = "unsafe-name"
            return False
        folded.add(rel.casefold())
        return True

    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        here = Path(dirpath)
        if here == repo:
            dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in sorted(dirnames):
            p = here / name
            rel = p.relative_to(repo).as_posix()
            if fixture.is_link(p):
                dirnames.remove(name)
                if admit(rel):
                    entries.append(_link_entry(p, rel, other))
            elif not admit(rel):
                dirnames.remove(name)
        for name in sorted(filenames):
            p = here / name
            rel = p.relative_to(repo).as_posix()
            if not admit(rel):
                continue
            mode = os.lstat(p).st_mode
            if fixture.is_link(p):
                entries.append(_link_entry(p, rel, other))
            elif stat.S_ISREG(mode):
                fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as fh:
                    entries.append(Entry(rel, "file", data=fh.read()))
            else:
                other[rel] = "special"
    return [e for e in entries if e.path not in other], other


def _link_entry(p: Path, rel: str, other: dict[str, str]) -> Entry:
    try:
        return Entry(rel, "link", target=os.readlink(p))
    except (OSError, ValueError):  # a reparse point that is not a link
        other[rel] = "special"
        return Entry(rel, "link")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.armhost")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)
    agent = Agent(args.root.resolve())
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    verb = "hello"
    try:
        message, payload = read_frame(stdin, what="request", limits=agent.limits,
                                      max_payload=agent.limits.tar_bytes())
        verb = message["verb"]
        if message["kind"] != "request":
            raise AgentError("BAD_REQUEST", "the agent answers requests only")
        result, body = agent.handle(verb, message["run_id"], message["args"], payload)
        reply = {"kind": "reply", "verb": verb, "ok": True, "error": None, "result": result}
    except (AgentError, TransferError) as exc:
        code = exc.code
        reply, body = {"kind": "reply", "verb": verb, "ok": False,
                       "error": {"code": code, "message": str(exc)[-2000:]}, "result": {}}, b""
    except Exception as exc:  # noqa: BLE001 (any other failure is still one bounded, typed reply)
        reply, body = {"kind": "reply", "verb": verb, "ok": False,
                       "error": {"code": "ARMHOST_ERROR", "message": f"{type(exc).__name__}: {exc}"[-2000:]},
                       "result": {}}, b""
    stdout.write(encode_frame(reply, body))
    stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

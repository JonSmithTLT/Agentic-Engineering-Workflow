"""What a contained context gets of the register: one lookup that never misses (STG-15, A-38: CAPR-04, CAPR-12; the
designer's CAP-1 ruling 1).

OpenCode's ripgrep lookup is ``which("rg", PATH + <bin>)``, then ``<bin>/rg``, and only then a download, with no switch
to turn it off (measured in its source, 2.0.18, ``core/src/ripgrep/binary.ts``). So every contained context has its
own read-only directory first on ``PATH``, written here on the host, never by the run. For each record of ``path:
first`` it holds one entry under the record's command, which is one of:

* a link to AEW's pinned copy, when that copy matches its pin and passes its check inside the sandbox;
* a link to a copy the host has, named as unpinned in the status, when AEW's cannot serve and host copies are on;
* AEW's failing stub, which prints the cause and exits non-zero, so the harness's lookup still ends here.

A record of ``path: own_name`` gets a link in a second directory, last on ``PATH``, so the project keeps the host's
tool under that name (CAPR-04), and no stub: nothing looks it up unasked. One loop over the records does all of it, so
a new record needs no new mechanism.

Two steps, around the sandbox's self-test (``probe.self_test``), which runs each candidate's health check inside:
:func:`place` makes the entries before the sandbox exists, from what the host can see, and :func:`settle` rewrites
them from what the sandbox saw. A copy that matches its pin but cannot run there never serves, and a host copy the
sandbox cannot see (a dangling link, which ``which`` would pass over) becomes the stub. Neither ever refuses a launch:
no provider is required for AEW to run (CAPR-12).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.capability import payload as P
from aew.capability import records, status, store
from aew.errors import AEWError, IntegrityError

DIRECTORY = "tools"  # <run dir>/tools, beside the run's harness state and outside its writable roots
FIRST, OWN_NAME = "first", "own_name"  # the schema's two values of a record's ``path``, and each one's directory
STUB_EXIT = 127  # the shell's "command not found", which is what the stub stands for
MAX_CAUSE = 2000  # a cause is a sentence or two; a stub's text is bounded whatever a record or a host path says
# The schema's own pattern for a command: a refused record's command becomes a file name here only if it matches
COMMAND = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class Tool:
    """One provider as a contained context gets it: its copies in the order they may serve, each ``(kind, path)``, and
    why AEW's own is not among them."""

    provider: str
    command: str
    where: str  # FIRST or OWN_NAME
    record: dict[str, Any] | None
    candidates: tuple[tuple[str, str], ...] = ()
    cause: str | None = None
    fix: str | None = None
    sha256: str | None = None
    digest: str | None = None

    def spec(self) -> dict[str, Any]:
        """What the probe needs to run this tool's health check inside: its argv and fixture, and never its verdict
        (:func:`status.judge` is that, on the host)."""
        health = (self.record or {}).get("health") or {}
        return {"provider": self.provider, "command": self.command, "paths": [p for _, p in self.candidates],
                "version": (health.get("version") or {}).get("args") or [],
                "fixture": (health.get("fixture") or {}).get("args") or [],
                "files": (health.get("fixture") or {}).get("files") or {}}


def plan(directory: Path | None = None, *, state: dict[str, Any] | None = None,
         names: list[str] | None = None) -> tuple[Tool, ...]:
    """Every provider in force, or those ``names`` gives, with the copies that may serve it. Reads only, and never
    raises for what the register holds: an unreadable register leaves AEW's shipped commands with the cause."""
    try:
        state = store.read(directory) if state is None else state
    except IntegrityError as exc:
        return tuple(Tool(name, rec["command"], rec["path"], None, cause=exc.message,
                          fix="move the register file aside, then `aew capability check`")
                     for name, rec in sorted(records.shipped().items()))
    facts = status.host_facts()
    tools = []
    for name, entry in sorted(status.effective(state).items()):
        if names is None or name in names:
            tool = _tool(name, entry, state, facts, directory)
            if tool is not None:
                tools.append(tool)
    return tuple(tools)


def _tool(name: str, entry: dict[str, Any], state: dict[str, Any], facts: dict[str, str | None],
          directory: Path | None) -> Tool | None:
    record = entry["record"]
    aew = status.aew_copy(name, record, entry["problem"], state, facts=facts, directory=directory)
    if record is None:  # a refused record serves nothing, and its command's lookup still ends here
        named = _map(entry.get("held"))
        shipped = records.shipped().get(name) or {}
        command, where = named.get("command") or shipped.get("command"), named.get("path") or shipped.get("path")
        if not isinstance(command, str) or not COMMAND.fullmatch(command):
            return None
        return Tool(name, command, FIRST if where == FIRST else OWN_NAME, None, cause=aew.cause, fix=aew.fix)
    pinned = record["payloads"].get(records.platform_key())
    candidates: list[tuple[str, str]] = []
    if pinned is not None:
        path = P.path_of(name, record["command"], pinned, directory)
        if aew.status != status.REFUSED and path.exists():
            candidates.append((status.AEW_COPY, str(path)))
    # Only a harness's own lookup takes a host copy here: the project already has the host's under its plain name
    if record["path"] == FIRST and state["host_copies"]:
        found = status.find_host_copy(record["command"], directory)
        if found is not None:
            candidates.append((status.HOST_COPY, str(found)))
    absent = not candidates or candidates[0][0] != status.AEW_COPY
    return Tool(name, record["command"], record["path"], record, tuple(candidates),
                cause=aew.cause if absent else None, fix=aew.fix if absent else None,
                sha256=pinned["sha256"] if pinned else None, digest=records.digest(record))


def _map(value: Any) -> dict[str, Any]:
    """A part of a report from inside a sandbox, or nothing: its shape is not taken on trust."""
    return value if isinstance(value, dict) else {}


def _write_entry(directory: Path, command: str, *, link: str | None = None, stub: str | None = None) -> None:
    """One entry, replaced whole: a link, a stub, or (with neither) nothing."""
    target = directory / command
    tmp = directory / f".{command}.new"
    tmp.unlink(missing_ok=True)
    if link is not None:
        os.symlink(link, tmp)
    elif stub is not None:
        tmp.write_bytes(stub.encode("utf-8"))
        os.chmod(tmp, 0o500)  # the operator's own, as a contained run is: read and run
    else:
        target.unlink(missing_ok=True)
        return
    os.replace(tmp, target)


def stub_text(tool: Tool, cause: str) -> str:
    """The failing stub: its one line goes to the harness's own error, and the agent reads it there (CAPR-X06)."""
    said = f"aew: {tool.command} is not available in this run. {cause}"
    said += f" Fix: {tool.fix}." if tool.fix else ""
    said += " `aew doctor` names it."
    return f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(said[:MAX_CAUSE])} >&2\nexit {STUB_EXIT}\n"


def _serve(tool: Tool, root: Path, link: str | None, cause: str | None) -> None:
    directory = root / (FIRST if tool.where == FIRST else OWN_NAME)
    if link is not None:
        _write_entry(directory, tool.command, link=link)
    elif tool.where == FIRST:
        _write_entry(directory, tool.command, stub=stub_text(tool, cause or "No copy serves it."))
    else:
        _write_entry(directory, tool.command)


def place(run_dir: Path, tools: tuple[Tool, ...]) -> tuple[Path, Path]:
    """Make this context's two directories under ``run_dir``, as far as the host can tell: ``(first, own_name)``. Each
    holds :data:`status.TOOLS_MARKER`, so a process inside never takes one for a copy the host has. Linux only: only a
    contained context has them."""
    root = Path(run_dir) / DIRECTORY
    shutil.rmtree(root, ignore_errors=True)
    first, own = root / FIRST, root / OWN_NAME
    for directory in (first, own):
        directory.mkdir(mode=0o700, parents=True)
        (directory / status.TOOLS_MARKER).write_bytes(b"")
    for tool in tools:
        _serve(tool, root, tool.candidates[0][1] if tool.candidates else None, tool.cause)
    return first, own


def settle(root: Path, tools: tuple[Tool, ...], seen: dict[str, Any]) -> dict[str, Any]:
    """The entries as the sandbox's check decides them, and what happened, per provider: ``{provider: {command, where,
    found, served, path, tried, cause}}``, where ``found`` is what ``PATH`` resolved inside, ``served`` the kind of copy
    now serving (None: the stub, or nothing), and ``tried`` each copy's check, up to the one that passed."""
    out: dict[str, Any] = {}
    for tool in tools:
        got = _map(seen.get(tool.provider))
        checks = _map(got.get("checks"))
        tried: list[dict[str, Any]] = []
        served = None
        causes = [f"AEW's copy: {tool.cause}"] if tool.cause else []
        for kind, path in tool.candidates:
            steps = _map(checks.get(path))
            if tool.record is None or not steps:
                ok, cause, first = False, "the sandbox's check reported nothing for it", None
            else:
                ok, cause, first = status.judge(tool.record, steps.get("version"), steps.get("fixture"),
                                                pinned=kind == status.AEW_COPY)
            tried.append({"kind": kind, "path": path, "ok": ok, "cause": cause, "version": first,
                          "sha256": tool.sha256 if kind == status.AEW_COPY else None,
                          "record_digest": tool.digest if kind == status.AEW_COPY else None})
            if ok:
                served = (kind, path)
                break
            causes.append(f"{'AEW' if kind == status.AEW_COPY else 'the host'}'s copy {path}: {cause}")
        said = "; ".join(causes) or None
        _serve(tool, root, served[1] if served else None, f"{said}." if said else None)
        out[tool.provider] = {"command": tool.command, "where": tool.where, "found": got.get("found"),
                              "served": served[0] if served else None, "path": served[1] if served else None,
                              "tried": tried, "cause": said}
    return out


def safe_plan() -> tuple[Tool, ...]:
    """:func:`plan`, whatever goes wrong: a launch never fails on the register (CAPR-12), and with nothing known of it
    there is no entry to make, so the harness's own lookup is what remains."""
    try:
        return plan()
    except (AEWError, OSError):
        return ()

"""The operator's consent to download a tool (the operator's decision of 2026-11-05; the designer's rulings, STG-15).

AEW downloads no tool unless the operator chooses it. One screen asks, whoever asks: `aew init` on a terminal, the
Lead's start (`aew opencode`) when a needed tool is missing and the operator hasn't declined it, and `aew capability
fetch`. It fits one short screen:

* each **needed** tool listed in full: its name, what it is for, its pinned version, its size, where it comes from and
  what degrades without it (a record's ``needed`` and ``degrades``, :func:`records.needed`);
* the **optional** ones as a count, until the operator types ``pick``;
* the choices: ``needed``, ``all``, ``pick`` or ``none``. **Enter takes the needed ones** only because the screen says
  what Enter downloads (their names, sizes and source); with nothing needed missing, Enter takes none.

There is no timed default: a prompt that ends unanswered downloads nothing and records nothing. Off a terminal there
is never a default: nothing downloads unless the tools are named (`aew init --fetch-tool NAME`, `aew capability fetch
NAME`). A worker's launch never asks and never downloads: no human is there (it only flags, :func:`ops.flag_missing`).
Only the operator can answer: the prompt reads the controlling terminal (:func:`aew.operator.ask`), never stdin, and a
Lead session, or an agent's own `aew`, is never asked.

**A "no" is remembered** per tool and pinned payload, in the register's ``declined`` (:func:`status.declined`): AEW
doesn't ask again until the pin changes or the operator runs `aew capability fetch`, and the tool stays visible as
declined, with when and the command, wherever its status is read (`aew doctor`, `aew capability list`, a run's
record). **A missing tool is logged, not voided** (the operator's condition): every run's record keeps it with its
closed reason, and the run goes on (CAPR-12).
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew import process_kind
from aew.capability import ops, records, status, store
from aew.capability import payload as P
from aew.errors import AEWError, NotFound, PermissionDenied
from aew.util import utc_now

NEEDED, ALL, PICK, NONE = "needed", "all", "pick", "none"
CHOICES = (NEEDED, ALL, PICK, NONE)
FETCH_FLAG = "--fetch-tool"  # `aew init`'s flag that names a tool off a terminal: its one owner
NO_ROUTE = ("unreachable", "timed_out")  # the fetch's closed reasons that mean this host has no route to the source
TRIES = 3  # answers that are none of the choices before the prompt gives up, downloading nothing


@dataclass(frozen=True)
class Offer:
    """One tool this host lacks, as the screen shows it."""

    provider: str
    command: str
    needed: bool
    purpose: str
    version: str
    size: int  # the download's size: the pinned archive's
    source: str  # as AEW shows it
    degrades: str | None
    declined_at: str | None  # the operator's "no" to this pin, when there is one

    def line(self) -> str:
        """The tool in full: name, purpose, version, size, source and what degrades without it."""
        said = (f"  {self.provider} {self.version} (`{self.command}`): {self.purpose}; {_size(self.size)} from "
                f"{self.source}")
        if self.degrades:
            said += f"; without it, {self.degrades}"
        if self.declined_at:
            said += f"; you declined it at {self.declined_at}"
        return said

    def report(self) -> dict[str, Any]:
        return {"tool": self.provider, "command": self.command, "needed": self.needed, "version": self.version,
                "size": self.size, "source": self.source, "degrades": self.degrades, "declined_at": self.declined_at}


def _size(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 100_000 else f"{max(1, round(n / 1000))} kB"


def _host(source: str) -> str:
    return urllib.parse.urlsplit(source).hostname or source


def offers(directory: Path | None = None) -> list[Offer]:
    """Every tool in force whose pinned payload for this platform is not on this host, needed ones first, then by
    name. A tool whose record is refused, or has no payload for this platform, has nothing to download, and its status
    says why."""
    state = store.read(directory)
    key = records.platform_key()
    out = []
    for name, entry in sorted(status.effective(state).items()):
        record = entry["record"]
        pinned = (record or {}).get("payloads", {}).get(key)
        if record is None or pinned is None or P.path_of(name, record["command"], pinned, directory).exists():
            continue
        no = status.declined(state, name, pinned, key)
        out.append(Offer(name, record["command"], records.needed(record),
                         record.get("description") or f"the `{record['command']}` command", record["version"],
                         int(pinned["archive_size"]), P.shown_source(pinned["source"]), record.get("degrades"),
                         no.get("at") if no else None))
    return sorted(out, key=lambda o: (not o.needed, o.provider))


def screen(shown: list[Offer]) -> str:
    """The one short screen: needed tools in full, optional ones as a count, the choices, and what Enter downloads."""
    needed = [o for o in shown if o.needed]
    optional = [o for o in shown if not o.needed]
    lines = ["", "==== AEW: tools this host is missing ====",
             "AEW brings these tools to its contained runs. None is on this host, and AEW downloads only what you "
             "choose. Runs go on without them."]
    if needed:
        lines.append("Needed (the harness relies on them):")
        lines += [o.line() for o in needed]
    if optional:
        lines.append(f"Optional enhancements: {len(optional)} (type `{PICK}` to see them).")
    if needed:
        lines.append("Enter downloads the needed ones: " + ", ".join(f"{o.provider} ({_size(o.size)})" for o in needed)
                     + f", from {', '.join(sorted({_host(o.source) for o in needed}))}.")
    else:
        lines.append("Enter downloads nothing.")
    lines.append(f"No network here? `{status.IMPORT}` with your offline bundle's path imports them instead.")
    lines.append(f"Choose {' / '.join(CHOICES)}: ")
    return "\n".join(lines)


def _pick_screen(shown: list[Offer]) -> str:
    lines = ["", "Every missing tool:"]
    lines += [f"{i}. {o.line().strip()}" + (" [needed]" if o.needed else "") for i, o in enumerate(shown, 1)]
    lines.append("Type the numbers or names to download, separated by spaces. Enter downloads nothing: ")
    return "\n".join(lines)


@dataclass(frozen=True)
class Decision:
    """The operator's answer: what to download and what they declined. ``answered`` is False where the prompt ended
    with no answer (closed, timed out), which downloads nothing and declines nothing."""

    chosen: tuple[Offer, ...]
    declined: tuple[Offer, ...]
    answered: bool
    said: str


def _picked(answer: str, shown: list[Offer]) -> list[Offer] | None:
    by_name = {o.provider: o for o in shown} | {o.command: o for o in shown}
    out: list[Offer] = []
    for word in answer.replace(",", " ").split():
        offer = shown[int(word) - 1] if word.isdigit() and 0 < int(word) <= len(shown) else by_name.get(word)
        if offer is None:
            return None
        if offer not in out:
            out.append(offer)
    return out


def ask(shown: list[Offer], read: Callable[[str], str]) -> Decision:
    """The screen, on the operator's terminal through ``read`` (it shows a prompt and returns the line typed, or
    raises when the terminal ends or the prompt times out). Every tool shown and not chosen is declined."""

    def decided(chosen: list[Offer], said: str) -> Decision:
        return Decision(tuple(chosen), tuple(o for o in shown if o not in chosen), True, said)

    prompt = screen(shown)
    try:
        for _ in range(TRIES):
            answer = read(prompt).strip().lower()
            if answer == "":
                return decided([o for o in shown if o.needed], "Enter: the needed ones")
            if answer == NEEDED:
                return decided([o for o in shown if o.needed], NEEDED)
            if answer == ALL:
                return decided(list(shown), ALL)
            if answer == NONE:
                return decided([], NONE)
            if answer == PICK:
                for _ in range(TRIES):
                    picked = _picked(read(_pick_screen(shown)), shown)
                    if picked is not None:
                        return decided(picked, PICK)
                break
            prompt = f"{answer!r} is not one of {' / '.join(CHOICES)}. Choose: "
    except (PermissionDenied, AEWError, OSError, EOFError):
        return Decision((), (), False, "the prompt ended with no answer")
    return Decision((), (), False, "no answer was one of the choices")


def decline(offers_: tuple[Offer, ...] | list[Offer], directory: Path | None = None) -> None:
    """Remember the operator's "no" to each tool, per tool and pinned payload (:func:`status.declined`)."""
    if not offers_:
        return
    key = records.platform_key()
    with store.locked(directory) as root:
        state = store.read(root)
        eff = status.effective(state)
        marks = state.setdefault("declined", {})
        at = utc_now()
        for offer in offers_:
            record = (eff.get(offer.provider) or {}).get("record")
            pinned = (record or {}).get("payloads", {}).get(key)
            if record is not None and pinned is not None:
                marks[f"{offer.provider}:{key}"] = {"at": at, "sha256": pinned["sha256"], "version": record["version"]}
        store.write(state, root)


def terminal() -> bool:
    """Whether the operator can be asked here: this process has a controlling terminal (:func:`aew.operator.ask`
    reads it, never stdin). The test suite replaces it, so no test waits on a developer's terminal."""
    from aew import operator

    return operator.has_terminal()


def read_terminal(prompt: str) -> str:
    """One answer typed at the controlling terminal, never stdin."""
    from aew import operator

    return operator.ask(prompt)


def _never_here() -> str | None:
    """Why this process may not ask or download, or None: a Lead session, or an agent's own `aew`. Getting a payload is
    installing, which no agent's surface has (CAPR-05)."""
    from aew.engine.custody_ops import LEAD_SESSION_VARS

    if process_kind.kind() == process_kind.NON_WRITER:
        return "an agent's own `aew` never downloads a tool"
    if any(os.environ.get(v) for v in LEAD_SESSION_VARS):
        return "a Lead session never downloads a tool"
    return None


def get(chosen: list[Offer] | tuple[Offer, ...], directory: Path | None = None) -> dict[str, list[str]]:
    """Download what the operator chose, through the register's one download (:func:`ops.fetch`), then check each one
    that arrived (its health check, as `aew capability check` runs it). Never in a Lead session or an agent's own
    `aew`."""
    why = _never_here()
    if why is not None:
        raise PermissionDenied(f"{why}: the operator runs `{status.FETCH}` at their own terminal",
                               reason="operator_only")
    names = [o.provider for o in chosen]
    done = ops.fetch(names, directory=directory)
    arrived = [n for n in names if any(line.startswith("downloaded ") for line in done.get(n) or [])]
    for name in arrived:
        try:
            for checked, lines in ops.check(name, offline=True, directory=directory)["checked"].items():
                done.setdefault(checked, []).extend(lines)
        except AEWError as exc:  # its check is the next `aew capability check`'s; the download stands
            done[name].append(f"its check did not run: {exc.message}")
    return done


def no_route(done: dict[str, list[str]], directory: Path | None = None) -> bool:
    """Whether a download just failed for want of a route (no network, no proxy, a timeout): the screen's offline
    line is then the way forward."""
    try:
        failures = store.read(directory).get("fetch_failures") or {}
    except AEWError:
        return False
    key = records.platform_key()
    return any((failures.get(f"{name}:{key}") or {}).get("code") in NO_ROUTE for name in done)


def outcome(decision: Decision | None, done: dict[str, list[str]], left: list[Offer],
            directory: Path | None = None) -> dict[str, Any]:
    """What a caller reports: what was downloaded, declined and still missing, each line in AEW's words."""
    out: dict[str, Any] = {"answer": decision.said if decision is not None else None,
                           "downloaded": {n: lines for n, lines in done.items()},
                           "declined": [o.report() for o in (decision.declined if decision is not None else ())],
                           "missing": [o.report() for o in left]}
    if done and no_route(done, directory):
        out["offline"] = (f"the download found no route from this host: `{status.IMPORT}` with your offline bundle's "
                          "path imports the tools instead")
    return out


def declined_lines(directory: Path | None = None) -> list[str]:
    """One line per tool the operator declined, while the "no" holds: when, and the command that downloads it. What
    `aew init`'s ``next`` adds, and what the readiness surface (E125) is to list."""
    try:
        shown = offers(directory)
    except AEWError:
        return []
    return [f"you declined {o.provider} {o.version} at {o.declined_at}"
            + (f" (needed: without it, {o.degrades})" if o.needed and o.degrades else "")
            + f"; `{status.FETCH} {o.provider}` downloads it" for o in shown if o.declined_at]


def named(names: list[str], directory: Path | None = None) -> list[Offer]:
    """The offers ``names`` names, each a provider or its command: an unknown name refuses before anything is
    downloaded, and a tool already on this host is left out."""
    eff = status.effective(store.read(directory))
    commands = {(e["record"] or {}).get("command"): n for n, e in eff.items() if e["record"] is not None}
    unknown = [n for n in names if n not in eff and n not in commands]
    if unknown:
        raise NotFound(f"no tool named {', '.join(unknown)}; `aew capability list` shows them",
                       names=unknown, known=sorted(eff))
    wanted = {commands.get(n, n) for n in names}
    return [o for o in offers(directory) if o.provider in wanted]


# ---------------------------------------------------------------------------------------------- the three callers


def check_names(names: list[str] | None, directory: Path | None = None) -> None:
    """Refuse an unknown ``--fetch-tool`` name before `aew init` writes anything."""
    if names:
        named(names, directory)


def at_init(fetch_tools: list[str] | None, directory: Path | None = None) -> dict[str, Any]:
    """`aew init`'s step, after the project is initialized: the tools ``--fetch-tool`` names, or, with none named, the
    screen on a terminal. A tool already declined is not asked again here; it is listed. Off a terminal with none
    named, nothing downloads and the report says what is missing. Never fails the init: what went wrong is said."""
    try:
        if _never_here() is not None:
            return outcome(None, {}, offers(directory), directory)
        if fetch_tools:
            chosen = named(fetch_tools, directory)
            done = get(chosen, directory)
            return outcome(None, done, offers(directory), directory)
        shown = [o for o in offers(directory) if not o.declined_at]
        if not shown or not terminal():
            return outcome(None, {}, offers(directory), directory)
        decision = ask(shown, read_terminal)
        decline(decision.declined, directory)
        done = get(decision.chosen, directory) if decision.chosen else {}
        return outcome(decision, done, offers(directory), directory)
    except AEWError as exc:  # the project is initialized: a tool is never why `aew init` fails (CAPR-12)
        return {"error": exc.message}


def init_keys(next_step: str, tools: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    """What `aew init`'s result gains: its own ``tools`` key (what was downloaded, declined and is still missing), and
    in ``next`` a line for each tool the operator declined, with when and the command (the designer's ruling: a "no"
    stays visible). With none declined, ``next`` is what it always was."""
    return {"tools": tools, "next": next_step + "".join(f". Also: {line}" for line in declined_lines(directory))}


def at_lead_start(out: Any = None, directory: Path | None = None, *, asking: bool = True) -> list[str]:
    """The Lead's start (`aew opencode`), before the TUI opens: the screen when a needed tool is missing and not
    declined, on a terminal; a needed tool declined gets one line and the command on every start, with no second ask
    (a reminder respects the choice). An optional tool that's missing says nothing here: it is in the run's record and
    `aew doctor`. With no terminal, nothing is asked or said, as a launch's flag says nothing there
    (:func:`ops.flag_missing`): no operator reads it, and the run's record and `aew doctor` keep it. ``asking=False``
    is a Lead AEW binds no tools into (not contained): nothing is asked, and each needed tool missing still gets its
    line, so it is never silent. Never stops the start (CAPR-12). Returns the lines written."""
    out = out if out is not None else sys.stderr
    said: list[str] = []
    try:
        if _never_here() is not None or not terminal():
            return said
        missing = offers(directory)
        ask_now = [o for o in missing if o.needed and not o.declined_at]
        if ask_now and asking:
            decision = ask([o for o in missing if not o.declined_at], read_terminal)
            decline(decision.declined, directory)
            done = get(decision.chosen, directory) if decision.chosen else {}
            for name, lines in done.items():
                said += [f"aew opencode: {name}: {line}" for line in lines]
            if done and no_route(done, directory):
                said.append(f"aew opencode: the download found no route from this host: `{status.IMPORT}` with your "
                            "offline bundle's path imports the tools instead.")
            missing = offers(directory)
        for o in missing:
            if not o.needed:
                continue
            why = f"you declined it at {o.declined_at}" if o.declined_at else "it is not on this host"
            if not asking:
                said.append(f"aew opencode: attention: {o.provider}, which a contained run needs, is missing: {why}. "
                            "This Lead is not contained, so AEW binds no tools into it and OpenCode's own lookup "
                            f"serves. `{status.FETCH} {o.provider}` downloads it.")
                continue
            said.append(f"aew opencode: attention: {o.provider}, which the harness needs (without it, {o.degrades}), "
                        f"is missing: {why}. The Lead goes on without it. `{status.FETCH} {o.provider}` downloads it.")
    except AEWError as exc:
        said.append(f"aew opencode: the tools AEW brings could not be read: {exc.message}. The Lead goes on.")
    try:
        for line in said:
            out.write(line + "\n")
    except OSError:
        pass
    return said


def at_fetch(names: list[str], directory: Path | None = None) -> dict[str, Any]:
    """`aew capability fetch [tool...]`: the tools named, or, with none named, the screen on a terminal with every
    missing tool, the declined ones too (the operator asked). Off a terminal with none named, nothing downloads."""
    from aew.errors import UsageError

    why = _never_here()
    if why is not None:
        raise PermissionDenied(f"{why}: `{status.FETCH}` is the operator's, at their own terminal",
                               reason="operator_only")
    if names:
        return outcome(None, get(named(names, directory), directory), offers(directory), directory)
    shown = offers(directory)
    if not shown:
        return outcome(None, {}, [], directory)
    if not terminal():
        raise UsageError(f"`{status.FETCH}` with no tool named asks at a terminal, and this process has none: name the "
                         f"tools to download ({', '.join(o.provider for o in shown)}), or run it at your own terminal",
                         missing=[o.provider for o in shown], reason="no_terminal")
    decision = ask(shown, read_terminal)
    decline(decision.declined, directory)
    return outcome(decision, get(decision.chosen, directory) if decision.chosen else {}, offers(directory), directory)


def render(report: dict[str, Any]) -> str:
    """A report as lines."""
    lines = []
    if report.get("answer"):
        lines.append(f"your answer: {report['answer']}")
    for name, said in (report.get("downloaded") or {}).items():
        lines += [f"{name}: {line}" for line in said]
    for d in report.get("declined") or []:
        lines.append(f"declined {d['tool']} {d['version']}: `{status.FETCH} {d['tool']}` downloads it")
    for m in report.get("missing") or []:
        lines.append(f"missing {m['tool']} {m['version']}" + (" (needed)" if m["needed"] else " (optional)")
                     + f": `{status.FETCH} {m['tool']}` downloads it")
    if report.get("offline"):
        lines.append(report["offline"])
    if report.get("error"):
        lines.append(f"the tools could not be read: {report['error']}")
    return "\n".join(lines) or "every tool AEW brings is on this host"

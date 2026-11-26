#!/usr/bin/env python3
"""E231: the typed Lead surface's per-request cost against the shell fallback, a measurement run by hand.

    python tools/perf/lead_typed_vs_shell.py [--json] [--sessions 20,34,68]

It measures, offline and with no model:

* the fixed cost every Lead request carries: the system text, guide and normal MCP tool list as
  ``tests/unit/test_lead_context_pool.py`` renders them (the pool record's containment fixture, messaging on and off);
* each typed row's share of the tool list (its compact JSON entry plus the list's comma);
* the guide's sections, and what a core-plus-pointers guide would send instead (E231's "guide's core plus pointers");
* four reads a Lead makes (status, work show, map show, map search), each by the typed tool where one exists and by
  ``aew`` in the shell, on a fresh fixture project. Call items use the scripted probe's turns
  (``tools/lead_probe/session.py``: ``typed``, ``shell``) in the Responses API item shape its analysis reads. A typed
  result is what the model reads, the MCP text block (``aew.surface.readable``); a shell result is the command's stdout;
* the break-even: how many uses per session make a typed row cheaper than the shell, under the stated model.

Bytes are the unit throughout (UTF-8; the tool list as the pool counts it, compact JSON with ASCII escapes). No
tokenizer is pinned in this repository. It writes only under a temporary directory, which it removes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from lead_probe import measure as probe_measure  # noqa: E402  (the probe's byte measure)
from lead_probe import session as probe_session  # noqa: E402  (the probe's scripted turns)

from aew.capability import ops as capability  # noqa: E402
from aew.capability import store as capability_store  # noqa: E402
from aew.harness.opencode import projection  # noqa: E402
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES  # noqa: E402
from aew.surface import contract, lead_text, mcp, readable  # noqa: E402
from aew.surface.context import NORMAL  # noqa: E402
from aew.util import load_yaml  # noqa: E402

POOL_RECORD = ROOT / "docs/implementation/lead-context-pool.yaml"
MESSAGING_ON = frozenset({contract.MESSAGING})
# The median contained Lead session of the M3 audit: 34 model/tool steps, so 34 requests (29 sessions in 26 runs;
# docs/design/proposals/lead-workflow-efficiency-design-v0.1.md). 20 and 68 bracket it.
SESSION_REQUESTS = (20, 34, 68)
# Extra shell round trips per use: none, one in four uses, one in two, every use (a `--help` lookup or a refused
# command line, the taxonomy F15's evaluation counts).
EXTRA_ROUND_TRIPS = (0.0, 0.25, 0.5, 1.0)
# One extra request's bytes, as multiples of the pool: 1 is the lower bound (the pool alone); a real request also
# carries OpenCode's own text and tools and the conversation so far.
ROUND_TRIP_POOLS = (1, 2)
# A2, the Lead's typed `map` tool, is not built. Its row as an earlier builder measured it
# (docs/implementation/notes.d/F15.8/2026-11-25-fix-map-read-refusal-cause.md).
A2_ROW_BYTES = (605, 633)
# The guide's core for the core-plus-pointers estimate: the sections a Lead needs on every request. Every other "## "
# section becomes one pointer line. Two splits, neither designed: an estimate, not a proposal.
GUIDE_CORES = {
    "keep the steps": ("Who does what", "A mutating Ticket, step by step", "Every command", "Coordination messages"),
    "lean": ("Who does what", "Every command", "Coordination messages"),
}
# The desktop session a notifier reads: without it, `status` reports the same unavailable notifier on every host.
DESKTOP_VARIABLES = frozenset({"DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY"})
POINTER = "- {heading}: `aew guide --section {slug}`\n"  # a hypothetical command; only its length matters here


# ---------------------------------------------------------------------------------------------- the fixed cost


@contextmanager
def no_placed_tools() -> Iterator[None]:
    """The pool test's host independence: an empty capability register, so the host's tools change nothing."""
    with mock.patch.object(capability_store, "read", lambda directory=None: capability_store.empty()):
        yield


def containment_label() -> dict[str, Any]:
    record = load_yaml(POOL_RECORD.read_text(encoding="utf-8"), source=str(POOL_RECORD))
    return record["baseline"]["containment"]


def fixed_cost(switches: frozenset[str]) -> dict[str, Any]:
    """The pool's four parts, rendered as ``test_lead_context_pool.render_pool`` renders them."""
    label = containment_label()
    with no_placed_tools():
        tools = capability.placed(label, contained=True)
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    config = projection.lead_config(guide, contained=label, tools=tools, push_wake=True, switches=switches)
    full = config["agents"][projection.LEAD_AGENT]["system"]
    system = full.removesuffix("\n\n" + guide)
    listing = mcp.tools_list(NORMAL, switches=switches)
    parts = {"system": len(system.encode("utf-8")), "guide": len(guide.encode("utf-8")),
             "join": len(full.encode("utf-8")) - len(system.encode("utf-8")) - len(guide.encode("utf-8")),
             "mcp": mcp.advertised_bytes(listing)}
    return {**parts, "total": sum(parts.values()), "tools": len(listing["tools"]), "guide_text": guide}


def rows(switches: frozenset[str]) -> dict[str, int]:
    """Each row's share of the advertised list: its entry plus the comma that joins it."""
    listing = mcp.tools_list(NORMAL, switches=switches)
    shares = {tool["name"]: mcp.advertised_bytes({"tools": [tool]}) - mcp.advertised_bytes({"tools": []}) + 1
              for tool in listing["tools"]}
    # The first row has no comma before it: the shares sum to the list less one.
    assert sum(shares.values()) - 1 + mcp.advertised_bytes({"tools": []}) == mcp.advertised_bytes(listing)
    return shares


def row_summary(shares: dict[str, int]) -> dict[str, Any]:
    values = sorted(shares.values())
    return {"count": len(values), "mean": round(sum(values) / len(values), 1), "min": values[0], "max": values[-1],
            "median": values[len(values) // 2] if len(values) % 2 else (values[len(values) // 2 - 1]
                                                                       + values[len(values) // 2]) / 2}


# ---------------------------------------------------------------------------------- the guide's core and pointers


def guide_sections(guide: str) -> list[tuple[str, int]]:
    """The guide split at its ``## `` headings: the preamble first (heading ""), then each section with its bytes."""
    parts = re.split(r"(?m)^(?=## )", guide)
    out = []
    for part in parts:
        heading = part.splitlines()[0][3:].strip() if part.startswith("## ") else ""
        out.append((heading, len(part.encode("utf-8"))))
    assert sum(size for _, size in out) == len(guide.encode("utf-8"))
    return out


def pointer_line(heading: str) -> str:
    return POINTER.format(heading=heading, slug=re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-"))


def core_and_pointers(guide: str, core: tuple[str, ...]) -> dict[str, Any]:
    """The always-sent guide if every section outside ``core`` became one pointer line, under one ToC heading."""
    sections = guide_sections(guide)
    moved = [(heading, size) for heading, size in sections if heading and heading not in core]
    toc = "## More, on demand\n\n" + "".join(pointer_line(heading) for heading, _ in moved) + "\n" if moved else ""
    kept = sum(size for heading, size in sections if not heading or heading in core)
    sent = kept + len(toc.encode("utf-8"))
    whole = len(guide.encode("utf-8"))
    return {"core": list(core), "moved": [heading for heading, _ in moved], "moved_bytes": sum(s for _, s in moved),
            "toc_bytes": len(toc.encode("utf-8")), "sent_bytes": sent, "saving_bytes": whole - sent}


# ------------------------------------------------------------------------------------------- the reads, measured


def items(turn: dict[str, Any], output: str, n: int) -> tuple[int, int]:
    """The call and its output as Responses API input items, the shape the probe's ``results`` reads back."""
    call = {"type": "function_call", "call_id": f"call_{n}", "name": turn["call"][0],
            "arguments": json.dumps(turn["arguments"])}
    result = {"type": "function_call_output", "call_id": f"call_{n}", "output": output}
    return probe_measure.size(call), probe_measure.size(result)


def fixture_env(base: Path, home: Path, host: dict[str, str] | None = None) -> dict[str, str]:
    """The host's environment, less what would change the result text: AEW's own variables (a credential, a fault
    switch), Git's, and the desktop session a notifier reads. It is not rebuilt from nothing: Windows' OpenSSL cannot
    create a TLS context without SYSTEMROOT, and `aew init` makes one (PR #589's Windows integration lane)."""
    env = {key: value for key, value in (os.environ if host is None else host).items()
           if not key.upper().startswith(("AEW_", "GIT_")) and key.upper() not in DESKTOP_VARIABLES}
    # Git's own variables are dropped above; these two are then set so the child's git reads no system, global or
    # XDG config (a host's commit.gpgsign would otherwise stop the fixture's commit: review of #589, m1).
    env.update({"HOME": str(home), "LANG": "C.UTF-8", "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                capability_store.base_variable(): str(base / "capability"),
                "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"})
    return env


class Fixture:
    """A fresh project with a planned Ticket, driven through the real CLI. A new project selects its map at init."""

    FILES = {"README.md": "# calc\n\nA tiny calculator.\n", "calc/__init__.py": "from calc.core import add\n",
             "calc/core.py": "def add(a, b):\n    return a + b\n",
             "tests/test_core.py": "from calc.core import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"}

    def __init__(self, base: Path) -> None:
        self.repo = base / "repo"
        self.repo.mkdir()
        home = base / "home"
        home.mkdir()
        self.env = fixture_env(base, home)
        for args in (("init", "-q", "-b", "main"), ("config", "user.name", "AEW Probe"),
                     ("config", "user.email", "probe@invalid"), ("config", "core.autocrlf", "false")):
            self.git(*args)
        for rel, text in self.FILES.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8", newline="\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial")
        self.ok("init", "--project-id", "calc", "--fetch-tool", "none")
        self.token = self.ok("--print-credential", "lead", "acquire", "--expect-rev", "0",
                             "--session-label", "lead-a")["token"]
        self.wid = self.lead("work", "create", "ticket", "--title", "Add subtract()", "--class", "1",
                             "--goal", "calc.core.subtract(5, 3) == 2", "--contract", "changes stay within calc/",
                             "--scope", "calc/**", "--scope", "tests/**")["id"]
        plan = base / "plan.md"
        plan.write_text("1. Add subtract(a, b) to calc/core.py.\n2. Add a focused test.\n", encoding="utf-8")
        self.lead("plan", "propose", "--assurance", "none", self.wid, "--file", str(plan), "--affected", "calc/core.py")
        self.lead("plan", "accept", self.wid, "--revision", "1")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def run(self, *args: str) -> str:
        env = {**self.env, "AEW_LEAD_TOKEN": getattr(self, "token", "")}
        proc = subprocess.run([sys.executable, "-m", "aew", *args], cwd=self.repo, env=env, capture_output=True,
                              text=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=180, check=False,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode:
            raise RuntimeError(f"aew {args[0]} exited {proc.returncode}: {proc.stderr.strip()[-2000:]}")
        return proc.stdout

    def ok(self, *args: str) -> Any:
        return json.loads(self.run(*args))

    def lead(self, *args: str) -> Any:
        revision = self.ok("lead", "show")["revision"]
        return self.ok(*args, "--expect-rev", str(revision))


def guide_line(command: str, guide: str) -> int:
    """The bytes the guide must add to teach a shell command it does not name: the command, then its own help.

    Zero when the guide already names the command. The line is derived from the CLI's parser, not written here."""
    words = command.split()[1:3]
    if f"aew {' '.join(words)}" in guide:
        return 0
    from aew.cli.main import build_parser

    parser = build_parser(recall_search=True, coordination_reads=True)
    help_text = ""
    for action in parser._subparsers._group_actions if parser._subparsers else []:
        sub = action.choices.get(words[0])
        if sub is None:
            continue
        for inner in sub._subparsers._group_actions if sub._subparsers else []:
            help_text = next((choice.help for choice in inner._choices_actions if choice.dest == words[1]), "")
    return len(f"- `{command}`: {help_text}\n".encode())


READS = (
    # name, typed tool (None: no typed row today), its arguments, the shell command the Lead would type
    ("status", "status", {}, "aew status"),
    ("work show", "work_show", {"work_id": "{wid}"}, "aew work show {wid}"),
    ("map show", None, None, "aew map show"),
    ("map search", None, None, "aew map search core"),
)


def measure_reads(fixture: Fixture, guide: str) -> list[dict[str, Any]]:
    out = []
    for n, (name, tool, arguments, command) in enumerate(READS):
        line = command.format(wid=fixture.wid)
        taught = command.format(wid="<T>")
        shell_out = fixture.run(*line.split()[1:])
        shell_call, shell_result = items(probe_session.shell(line), shell_out, 2 * n + 1)
        row: dict[str, Any] = {"read": name, "shell_command": line, "shell_call_bytes": shell_call,
                               "shell_result_bytes": shell_result, "shell_stdout_bytes": len(shell_out.encode()),
                               "shell_guide_line_bytes": guide_line(taught, guide), "typed_tool": tool}
        if tool is not None:
            args = {key: value.format(wid=fixture.wid) for key, value in (arguments or {}).items()}
            result = fixture.ok("lead", "tool", tool, "--arguments", json.dumps(args))
            text = readable.render(result)
            typed_call, typed_result = items(probe_session.typed(tool, **args), text, 2 * n + 2)
            row.update(typed_call_bytes=typed_call, typed_result_bytes=typed_result,
                       typed_text_bytes=len(text.encode()))
        out.append(row)
    return out


# -------------------------------------------------------------------------------------------------- break-even


def break_even(fixed_delta: float, use_delta: float, requests: int, round_trips: float, request_bytes: int) -> float:
    """Uses per session at which a typed row costs no more than the shell route, or ``inf`` if never.

    Per session, typed minus shell = fixed_delta * N + u * (use_delta * (N - 1) / 2 - k * Q), where fixed_delta is
    the row plus any typed guide line less the shell guide line (sent on every request), use_delta is the typed call
    and result less the shell's (resent on every later request: (N - 1) / 2 of them on average), and each extra shell
    round trip costs one more request of Q bytes."""
    saving_per_use = round_trips * request_bytes - use_delta * (requests - 1) / 2
    if fixed_delta <= 0:
        return 0.0
    if saving_per_use <= 0:
        return float("inf")
    return fixed_delta * requests / saving_per_use


def table(reads: list[dict[str, Any]], shares: dict[str, int], request_bytes: int, typed_over_shell_result: int,
          sessions: tuple[int, ...] = SESSION_REQUESTS) -> list[dict[str, Any]]:
    rows_out = []
    for read in reads:
        if read["typed_tool"] is not None:
            options = [(read["typed_tool"], shares[read["typed_tool"]])]
            use_delta = (read["typed_call_bytes"] + read["typed_result_bytes"]
                         - read["shell_call_bytes"] - read["shell_result_bytes"])
            typed_guide = 0
        else:
            # A2 is not built. Its per-use difference is estimated as the smallest typed-over-shell result-item
            # difference among the built reads. The call-item difference (typed is the smaller: -41 B for work_show)
            # is left out, so the estimate errs against the typed row.
            options = [(f"A2 map ({size} B)", size) for size in A2_ROW_BYTES]
            use_delta = typed_over_shell_result
            typed_guide = read["shell_guide_line_bytes"]  # the A2 guide line, taken as the same length
        for label, size in options:
            fixed_delta = size + typed_guide - read["shell_guide_line_bytes"]
            cells = {f"N={n},k={k},Q={q}x": break_even(fixed_delta, use_delta, n, k, q * request_bytes)
                     for n in sessions for k in EXTRA_ROUND_TRIPS for q in ROUND_TRIP_POOLS}
            rows_out.append({"read": read["read"], "row": label, "fixed_delta_bytes": fixed_delta,
                             "use_delta_bytes": use_delta, "break_even_uses": cells})
    return rows_out


# ---------------------------------------------------------------------------------------------------------- main


def measure(sessions: tuple[int, ...] = SESSION_REQUESTS) -> dict[str, Any]:
    on, off = fixed_cost(MESSAGING_ON), fixed_cost(frozenset())
    guide = on.pop("guide_text")
    off.pop("guide_text")
    shares = rows(MESSAGING_ON)
    with tempfile.TemporaryDirectory(prefix="aew-e231-") as base:
        reads = measure_reads(Fixture(Path(base)), guide)
    # The result items only: the typed result less the shell's, smallest over the built reads (A2's estimate).
    typed_over_shell_result = min(r["typed_result_bytes"] - r["shell_result_bytes"] for r in reads
                                  if r["typed_tool"] is not None)
    record = load_yaml(POOL_RECORD.read_text(encoding="utf-8"), source=str(POOL_RECORD))
    return {
        "schema": "aew/e231-typed-vs-shell/v1",
        "unit": "bytes (UTF-8; MCP list as compact JSON with ASCII escapes); no tokenizer is pinned",
        "cap_bytes": record["approval"]["ceiling_bytes"],
        "fixed": {"messaging_on": on, "messaging_off": off},
        "rows_messaging_on": shares, "rows_on_summary": row_summary(shares),
        "rows_off_summary": row_summary(rows(frozenset())),
        "guide_sections": guide_sections(guide),
        "guide_core_and_pointers": {name: core_and_pointers(guide, core) for name, core in GUIDE_CORES.items()},
        "reads": reads,
        "model": {"session_requests": list(sessions), "extra_round_trips_per_use": list(EXTRA_ROUND_TRIPS),
                  "round_trip_bytes": on["total"], "round_trip_pools": list(ROUND_TRIP_POOLS),
                  "a2_typed_over_shell_result_bytes": typed_over_shell_result,
                  "round_trip_note": "Q=1x is a lower bound: the pool alone, without OpenCode's own text, tools or "
                                     "context"},
        "break_even": table(reads, shares, on["total"], typed_over_shell_result, sessions),
    }


def text_report(result: dict[str, Any]) -> str:
    lines = []
    for name, part in result["fixed"].items():
        lines.append(f"{name}: system {part['system']} + guide {part['guide']} + join {part['join']} + mcp "
                     f"{part['mcp']} = {part['total']} B, {part['tools']} tools (cap {result['cap_bytes']} B)")
    lines.append(f"rows (on): {result['rows_on_summary']}")
    lines.append(f"rows (off): {result['rows_off_summary']}")
    for name, split in result["guide_core_and_pointers"].items():
        lines.append(f"guide core+pointers '{name}': sent {split['sent_bytes']} B, saving {split['saving_bytes']} B")
    for read in result["reads"]:
        lines.append(json.dumps(read))
    for row in result["break_even"]:
        lines.append(f"{row['read']} / {row['row']}: fixed {row['fixed_delta_bytes']:+} B/request, "
                     f"use {row['use_delta_bytes']:+} B/use; " + ", ".join(
                         f"{key}: {value:.1f}" for key, value in row["break_even_uses"].items()))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print the whole result as JSON")
    parser.add_argument("--sessions", default=",".join(map(str, SESSION_REQUESTS)),
                        help="requests per session to tabulate (default %(default)s)")
    args = parser.parse_args(argv)
    result = measure(tuple(int(n) for n in args.sessions.split(",")))
    print(json.dumps(result, indent=2) if args.json else text_report(result), end="" if not args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

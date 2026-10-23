"""What a worker's agent can run, and a project with real work to run it on (STG-05 CB-09; review of #231, MJ1, m7).

The non-writer test runs every command outside a sandbox and diffs `.aew` (tests/integration/test_non_writer_reads.py);
the containment test runs the same commands inside a reviewer's sandbox (tests/integration/test_containment.py). The
commands are derived, never listed: every leaf of the CLI's parser bare, plus each `probe` and `mutates_proof` probe
of the surface map with its placeholders filled in from the project.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from aewflow import assign, create_planned_ticket, integrate, sample_project, to_commit_ready
from conftest import Project
from log_fixture import extend_log

from aew.engine import outbox
from aew.engine.store import ControlStore
from aew.history.index import INDEX_REL
from aew.util import load_yaml

ROOT = Path(__file__).resolve().parents[2]
SURFACE_MAP = ROOT / "docs" / "implementation" / "surface-map.yaml"  # a code input: full tier (tools/ci/tier.SHARED)

# Commands a non-writer is refused (`non_writer_process`), each with why: it needs the control lock, or it writes
# under `.aew`, which a non-writer never does (review of #231, MJ1 and m7). Shrink-only.
WRITER_ONLY: dict[tuple[str, ...], str] = {
    ("history", "audit"): ("copies the history's root and its mutable tail together, which only the lock keeps "
                           "consistent"),
    ("history", "compact"): "seals the transition log's segments into .aew/state/log, under the lock",
    ("history", "reindex"): "rebuilds the derived history index under .aew/local",
    ("context", "pack"): "rewrites the invocation's pack under .aew/local/packs",
}

# What a command run in a worker's sandbox must never show: a crash, or a write that only a read-only store refuses
# (`context show` regenerating a pack under the mask was one: #231 at 51fffde1, CI).
WRITE_FAILURES = ("Traceback", "Read-only file system", "Permission denied")

# A known gap, pinned shrink-only (register F2's note of 2026-10-23, as reported to the designer): a read that
# fingerprints a workspace (`aew.snapshot.fingerprint._working_index`, `git add -A` into a throwaway index) needs git
# to write the blob of each changed or racily clean file, and a reader's sandbox has no private object store, only
# the read-only real one, so it fails there with a GIT_ERROR. It predates CB-09 (the reader layout of M4-B). The
# designer ruled the outcome (D-CS2-1, 2026-10-23: a fingerprint is a read, it works in a reader's sandbox and equals a
# writer's value, and a reader never writes the real object store); which slice builds it is the operator's. When it
# lands, this pin empties and the sandbox test passes without it. Writers are unaffected: theirs is the private index
# and object store. Limit: a fingerprint read that fails for another reason is not in this class.
READER_GIT_GAP: frozenset[tuple[str, ...]] = frozenset({("gate", "show"), ("work", "roles")})


def git_object_store_refused(stderr: str) -> bool:
    """A ``GIT_ERROR`` refusal whose git could not write its object store, read-only: READER_GIT_GAP's class."""
    try:
        error = json.loads(stderr)["error"]
    except (ValueError, KeyError, TypeError):
        return False
    said = str((error.get("details") or {}).get("stderr", ""))
    return error.get("code") == "GIT_ERROR" and "Read-only file system" in said and (
        "failed to insert into database" in said or "unable to create temporary file" in said)


_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


@dataclass
class Worked:
    p: Project
    hot: str  # a RUNNING Ticket with an active implementer
    done: str  # a finished Ticket: archived, so the history has records
    invocation: str  # the hot Ticket's implementer


def worked_project(tmp_path: Path) -> Worked:
    """A project with finished work, a Ticket in flight whose implementer has an edit not yet committed, and a
    transition log past the compaction window, so that `history compact` has a segment to seal, `history show` a
    record to show, and a fingerprint of the hot workspace a blob to hash."""
    p = sample_project(tmp_path)
    done, _ = to_commit_ready(p, tmp_path)
    integrate(p, done)
    hot = create_planned_ticket(p, tmp_path, title="Second")
    impl = assign(p, hot)
    core = impl.workspace / "calc" / "core.py"
    core.write_bytes(core.read_bytes() + b"# the implementer's edit, not yet committed\n")
    extend_log(p.root / ".aew", outbox.LOG_WINDOW + outbox.SEGMENT_SIZE + 8)
    p.ok("status", "--json")  # a writer's read: recovered once, as the engine leaves a store
    invocations = ControlStore(p.root / ".aew").read_committed()["invocations"]
    active = sorted(i for i, inv in invocations.items() if inv.get("status") == "active")
    assert len(active) == 1, sorted(invocations)
    return Worked(p, hot, done, active[0])


@functools.cache
def leaf_commands() -> tuple[tuple[str, ...], ...]:
    """Every command the CLI's parser has, by its words."""
    from aew.cli.main import build_parser

    def walk(parser: argparse.ArgumentParser, prefix: tuple[str, ...]):
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            yield prefix
        for action in subs:
            for name, sub in action.choices.items():
                yield from walk(sub, (*prefix, name))

    return tuple(sorted(set(walk(build_parser(), ()))))


def _surface() -> list[dict]:
    return load_yaml(SURFACE_MAP.read_text(encoding="utf-8"))["commands"]


def _fill(argv: list, w: Worked, ticket: str) -> list[str]:
    return [str(a).replace("{ticket}", ticket).replace("{invocation}", w.invocation) for a in argv]


def commands(w: Worked) -> list[list[str]]:
    """Every leaf command bare (one with required arguments stops at argparse), plus each surface-map probe and
    `mutates_proof` probe, with `{ticket}` filled in by the hot Ticket and by the finished one, and `{invocation}` by
    the hot Ticket's implementer. A probe that needs anything else (an invocation's token) carries a credential, which a
    worker's agent does not hold."""
    out = [list(c) for c in leaf_commands()]
    for entry in _surface():
        for raw in (entry.get("probe"), (entry.get("mutates_proof") or {}).get("probe")):
            for argv in (raw if raw and isinstance(raw[0], list) else [raw] if raw else []):
                for ticket in (w.hot, w.done):
                    filled = _fill(argv, w, ticket)
                    if not any(_PLACEHOLDER.search(a) for a in filled) and filled not in out:
                        out.append(filled)
    return out


def removals(w: Worked) -> list[Path]:
    """What each `mutates_proof` removes first, so that its probe has work to do (a pack is regenerated only when it is
    missing)."""
    out = []
    for entry in _surface():
        rel = (entry.get("mutates_proof") or {}).get("remove")
        if rel:
            out.append(w.p.root / _fill([rel], w, w.hot)[0])
    return out


def words(argv: list[str]) -> tuple[str, ...]:
    """The command an argument vector runs: its longest prefix that is a leaf of the parser."""
    leaves = set(leaf_commands())
    return max((tuple(argv[:n]) for n in range(len(argv) + 1) if tuple(argv[:n]) in leaves), key=len, default=())


def snapshot(aew: Path) -> dict[str, object]:
    """Every path under `.aew`, a file by (size, mtime, file id): a write, a replace, a create and a delete all show."""
    out: dict[str, object] = {}
    for d, dirs, files in os.walk(aew):
        base = Path(d)
        for name in dirs:
            out[(base / name).relative_to(aew).as_posix() + "/"] = "dir"
        for name in files:
            try:
                st = os.stat(base / name)
                out[(base / name).relative_to(aew).as_posix()] = (st.st_size, st.st_mtime_ns, st.st_ino)
            except OSError as exc:  # removed between the walk and the stat: still a change, seen as one
                out[(base / name).relative_to(aew).as_posix()] = f"unreadable {exc.errno}"
    return out


def changes(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """What changed under `.aew`, except the derived history index's catch-up: every reader of archived history
    (the dashboard server, a non-writer, among them) brings that shared cache up to the store's history root, every
    result it gives is authenticated against that root, and on a read-only view it is a private copy instead
    (``aew.history.index.HistoryIndex.sync``). Rebuilding it, `history reindex`, is refused in a non-writer."""
    out = ([f"+{k}" for k in sorted(set(after) - set(before))] + [f"-{k}" for k in sorted(set(before) - set(after))]
           + [f"~{k}" for k in sorted(set(before) & set(after)) if before[k] != after[k]])
    return [c for c in out if not (c[1:] == INDEX_REL or c[1:].startswith(INDEX_REL + "-"))]  # SQLite's companions

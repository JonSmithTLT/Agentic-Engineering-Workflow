"""Stage/primitive equivalence (M4-E plan v3 E3, M11.5; typed Lead surface design v0.2 §3.5, §10).

A stage, the same stage continued after a crash, and its primitives run directly must end in the same state, except
for the journal's own records. ``end_state`` is that comparison's view of a project: its control state and its
authored files under ``.aew/``, without

- the journal's own records: the hot ``stage_intents``, the ``stage_intent`` counter, a unit's pointers to its ended
  intents, and the cold intent files (``work/<T>/stage-intents/``, ``records/stage-intents/``);
- what the journal's commits move by existing: the revision and everything derived from the transition log (the log
  itself, the last transition, the history chain's head, the outbox mark, the transaction records, each handoff's base
  revision, the revision a generated copy names);
- what no two runs share: times, credentials and their identifiers, and the project's own location on disk.

E5's ``test_stage_matches_primitives[<stage>]`` compares through this view; extend it there for what Ticket stages
add (workspaces, invocations), never by loosening what it keeps.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from invariants import load_control

from aew.engine import stage_intents as SI

JOURNAL_KEYS = frozenset({"stage_intents"})  # control state, and on each unit
REVISION_BOUND = frozenset({"revision", "last_transition", "cold", "outbox", "base_revision"})
VOLATILE = re.compile(r"(^at$|_at$|^token_id$|^tokens$|^verifier$|^h$)")
# The transition log, its redo records, the control file (compared as data above) and its generated view (which
# states the revision), and local runtime data.
SKIPPED = ("state/log/", "state/txn/", "state/control.yaml", "state/CURRENT.md", "local/", SI.RECORDS_DIR + "/")


def _clean(value: Any, root: str) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v, root) for k, v in value.items()
                if k not in JOURNAL_KEYS and k not in REVISION_BOUND and not VOLATILE.search(str(k))}
    if isinstance(value, list):
        return [_clean(v, root) for v in value]
    if isinstance(value, str):
        return value.replace(root, "<project>")
    return value


def _journal_file(rel: str) -> bool:
    parts = rel.split("/")
    return rel.startswith(SI.RECORDS_DIR + "/") or (len(parts) > 2 and parts[0] == "work"
                                                    and parts[2] == "stage-intents")


def end_state(root: Path) -> dict[str, Any]:
    """The project at ``root`` as a stage/primitive equivalence compares it (module docstring)."""
    aew = root / ".aew"
    state = load_control(root)
    state.setdefault("counters", {}).pop("stage_intent", None)
    files: dict[str, Any] = {}
    for path in sorted(aew.rglob("*")):
        rel = path.relative_to(aew).as_posix()
        if not path.is_file() or _journal_file(rel) or rel.startswith(SKIPPED):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.startswith("<!-- generated copy"):  # its first line names the control revision it was made at
            text = text.split("\n", 1)[1]
        if text.startswith("---\n"):  # front matter: compared as data, so its times and revisions can be dropped
            _, front, body = text.split("---\n", 2)
            files[rel] = {"front": _clean(yaml.safe_load(front), str(root)), "body": body}
        else:
            files[rel] = text.replace(str(root), "<project>")
    return {"control": _clean(state, str(root)), "files": files}


def differences(a: Any, b: Any, path: str = "") -> list[str]:
    """Where two ``end_state`` views differ, as paths: an equivalence assertion's message."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'the second' if k not in a else 'the first'}")
            else:
                out += differences(a[k], b[k], f"{path}/{k}")
        return out
    return [] if a == b else [f"{path}: {str(a)[:200]!r} != {str(b)[:200]!r}"]

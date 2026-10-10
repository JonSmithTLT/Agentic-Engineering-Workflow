"""Stage/primitive equivalence (M4-E plan v3 E3, M11.5; typed Lead surface design v0.2 §3.5, §10).

A stage, the same stage continued after a crash, and its primitives run directly must end in the same state, except
for the journal's own records. ``end_state`` is that comparison's view of a project: its control state and its
authored files under ``.aew/``. It removes, **by path only** (a key of the same name elsewhere is kept):

- the journal's own records: the hot ``stage_intents``, the ``stage_intent`` counter, a unit's pointers to its ended
  intents (``work.<T>.stage_intents``), and the cold intent files (``work/<T>/stage-intents/``,
  ``records/stage-intents/``);
- what the journal's commits move by existing: the top-level ``revision``, ``last_transition`` and ``outbox``, the
  history chain's head (``cold.root``; ``cold.archived`` and the rest stay), a handoff's ``base_revision``, the
  revision a generated copy names, and the files derived from the transition log (the log, the transaction records,
  ``CURRENT.md``).

What no two runs share is **normalised, never dropped**: a time becomes ``"<time>"`` (a null stays null, so closed or
revoked versus open still differs), a credential id becomes a stable ordinal in order of first appearance (so the
token table, its revocations and every reference to a token still compare), a credential verifier becomes
``"<verifier>"``, and the project's location ``"<project>"``.

E5's ``test_stage_matches_primitives[<stage>]`` compares through this view; extend it there for what Ticket stages
add (workspaces, invocations), by path, never by loosening what it keeps.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from invariants import load_control

from aew.engine import stage_intents as SI

# Control-state paths the comparison removes (module docstring); "*" is any one key.
DROPPED = frozenset({("revision",), ("last_transition",), ("outbox",), ("stage_intents",),
                     ("counters", "stage_intent"), ("cold", "root"), ("work", "*", "stage_intents")})
TIME_KEY = re.compile(r"^(at|.+_at)$")
TOKEN_ID = re.compile(r"tk_[0-9a-f]{8,}")
# The transition log, its redo records, the control file (compared as data above) and its generated view (which
# states the revision), and local runtime data.
SKIPPED = ("state/log/", "state/txn/", "state/control.yaml", "state/CURRENT.md", "local/", SI.RECORDS_DIR + "/")


class _Normaliser:
    def __init__(self, root: str) -> None:
        self.root = root
        self.tokens: dict[str, str] = {}

    def _token(self, match: re.Match[str]) -> str:
        return self.tokens.setdefault(match.group(0), f"<token-{len(self.tokens) + 1}>")

    def text(self, value: str) -> str:
        return TOKEN_ID.sub(self._token, value.replace(self.root, "<project>"))

    def __call__(self, value: Any, path: tuple[str, ...] = (), dropped: frozenset[tuple[str, ...]] = DROPPED) -> Any:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                here = (*path, str(k))
                if any(len(d) == len(here) and all(a in ("*", b) for a, b in zip(d, here, strict=True))
                       for d in dropped):
                    continue
                key = self.text(k) if isinstance(k, str) else k
                if TIME_KEY.match(str(k)) and v is not None:
                    out[key] = "<time>"
                elif k == "verifier" and v is not None:
                    out[key] = "<verifier>"
                else:
                    out[key] = self(v, here, dropped)
            return out
        if isinstance(value, list):
            return [self(v, path, dropped) for v in value]
        if isinstance(value, str):
            return self.text(value)
        return value


def _clean(state: dict[str, Any], root: str, normalise: _Normaliser | None = None) -> Any:
    """A control state as the comparison sees it (module docstring)."""
    return (normalise or _Normaliser(root))(state)


def _journal_file(rel: str) -> bool:
    parts = rel.split("/")
    return rel.startswith(SI.RECORDS_DIR + "/") or (len(parts) > 2 and parts[0] == "work"
                                                    and parts[2] == "stage-intents")


def end_state(root: Path) -> dict[str, Any]:
    """The project at ``root`` as a stage/primitive equivalence compares it (module docstring)."""
    aew = root / ".aew"
    normalise = _Normaliser(str(root))
    control = _clean(load_control(root), str(root), normalise)
    files: dict[str, Any] = {}
    for path in sorted(aew.rglob("*")):
        rel = path.relative_to(aew).as_posix()
        if not path.is_file() or _journal_file(rel) or rel.startswith(SKIPPED):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.startswith("<!-- generated copy"):  # its first line names the control revision it was made at
            text = text.split("\n", 1)[1]
        if text.startswith("---\n"):  # front matter: compared as data, so its times are normalised
            _, front, body = text.split("---\n", 2)
            files[rel] = {"front": normalise(yaml.safe_load(front), (), frozenset({("base_revision",)})),
                          "body": normalise.text(body)}
        else:
            files[rel] = normalise.text(text)
    return {"control": control, "files": files}


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

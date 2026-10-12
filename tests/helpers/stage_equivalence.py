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
``"<verifier>"``, the project's location ``"<project>"`` and its workspaces root ``"<workspaces>"``, and the revision a
dispatch was decided at ``"<revision-bound>"`` (E5a: ``REVISION_BOUND``). A dispatch's decision digest is recomputed
over the decision itself with that revision substituted (``recorded_decisions``: the test records the decisions it
makes), so any other difference in the decision still compares; a digest no recorded decision has stays as it is. An
authored file's hash, wherever it is cited, becomes ``"<sha256 of <path>>"``, and the file itself is compared,
normalised: the invocation packs under ``local/packs/`` included (PR #177 review, finding 3).

**History records** (M4-E E6a: a publication to DONE archives its unit in the same commit): the unit's bundle
(``work/<T>/archive.yaml``), its annotations and the chain's tail (``history/tail.yaml``) are compared as data,
normalised like the rest. A stage that ends after its unit was archived records itself on the unit as an annotation
(``rel: stage_intent``): that annotation file, its tail entry and the ``annotation`` counter are the journal's own and
are removed; every other annotation and history entry is kept and compared. A tail entry's chain value ``h`` hashes
the entry's own fields, times included, so it becomes ``"<chain-hash>"``; the fields themselves still compare.
``cold.unverified_since`` is a time.

E5's ``test_stage_matches_primitives[<stage>]`` compares through this view; extend it there for what Ticket stages
add (workspaces, invocations), by path, never by loosening what it keeps.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from invariants import load_control

from aew.engine import stage_intents as SI

# Control-state paths the comparison removes (module docstring); "*" is any one key.
DROPPED = frozenset({("revision",), ("last_transition",), ("outbox",), ("stage_intents",),
                     ("counters", "stage_intent"), ("cold", "root"), ("work", "*", "stage_intents"),
                     # M4-E E6a: the intent whose step granted the lease, recorded on it for attribution (§2.3)
                     ("queue", "lease", "custody", "requested_by"),
                     # M4-E E6b: the intent whose step recorded a PUBLISH_IF_CLEAN request, for attribution (§2.2)
                     ("queue", "entries", "*", "attempts", "pic_request", "requested_by"),
                     # M4-E E6a: counts annotations, the journal's own on an archived unit included (module docstring);
                     # every other annotation is compared as its file and its tail entry
                     ("counters", "annotation")})
# The revision a dispatch was decided at (M4-E E5a): the stage's intent commit comes first, so its assignment is
# decided one revision later than the same assignment made directly. Normalised to "<revision-bound>", never dropped.
REVISION_BOUND = frozenset({("invocations", "*", "dispatch", "revision"),
                            ("invocations", "*", "runs", "dispatch", "revision"),
                            # M4-E E6a: a rebuild's own `integrate.prepare` decision, on the candidate and its attempt
                            ("work", "*", "integration", "admission", "revision"),
                            ("queue", "entries", "*", "attempts", "rebuild_admission", "revision"),
                            # M4-E E6b: the revision a PUBLISH_IF_CLEAN request was recorded at, in the prepare
                            ("queue", "entries", "*", "attempts", "pic_request", "rev")})
# A dispatch decision's digest, recomputed over the recorded decision with its revision substituted (module docstring).
DECISION_DIGEST = frozenset({("invocations", "*", "dispatch", "decision"),
                             ("invocations", "*", "runs", "dispatch", "decision"),
                             ("work", "*", "integration", "admission", "decision"),
                             ("queue", "entries", "*", "attempts", "rebuild_admission", "decision")})
TIME_KEY = re.compile(r"^(at|.+_at)$")
# Times kept under another name: a custody credential binds its lease's grant time (M4-E E6a).
TIME_PATHS = frozenset({("tokens", "*", "scope", "lease"), ("cold", "unverified_since")})
# History records compared as data (module docstring), and the journal's own annotation among them.
HISTORY_RECORD = re.compile(r"^(work/[^/]+/archive\.yaml|work/[^/]+/annotations/[^/]+\.yaml|history/tail\.yaml)$")
JOURNAL_ANNOTATION = "stage_intent"
TAIL = "history/tail.yaml"
TOKEN_ID = re.compile(r"tk_[0-9a-f]{8,}")
SHA256 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
# The transition log, its redo records, the control file (compared as data above) and its generated view (which
# states the revision), and local runtime data.
SKIPPED = ("state/log/", "state/txn/", "state/control.yaml", "state/CURRENT.md", "local/", SI.RECORDS_DIR + "/")
COMPARED_LOCAL = ("local/packs/",)  # local data the comparison keeps: what each invocation is handed


def _matches(here: tuple[str, ...], paths: frozenset[tuple[str, ...]]) -> bool:
    return any(len(d) == len(here) and all(a in ("*", b) for a, b in zip(d, here, strict=True)) for d in paths)


class _Normaliser:
    def __init__(self, root: str, workspaces: str | None = None, files: dict[str, str] | None = None,
                 decisions: dict[str, dict[str, Any]] | None = None) -> None:
        self.root = root
        self.decisions = decisions or {}
        # An authored file's hash, wherever it is cited (a unit's `record_sha256`, a plan's `sha256`), names the file:
        # its bytes carry times, so the hash differs between two runs while the file, compared normalised, does not.
        self.files = files or {}
        # The workspaces root sits beside the project (the manifest's default), so two projects' differ the way their
        # locations do: named, like the project's (M4-E E5a, the Ticket stages' workspaces).
        self.places = [(w, "<workspaces>") for w in dict.fromkeys(
            (workspaces, workspaces.replace("\\", "/")) if workspaces else ())]
        self.tokens: dict[str, str] = {}

    def _token(self, match: re.Match[str]) -> str:
        return self.tokens.setdefault(match.group(0), f"<token-{len(self.tokens) + 1}>")

    def text(self, value: str) -> str:
        for place, name in self.places:
            value = value.replace(place, name)
        value = SHA256.sub(lambda m: self.files.get(m.group(0), m.group(0)), value) if self.files else value
        return TOKEN_ID.sub(self._token, value.replace(self.root, "<project>"))

    def __call__(self, value: Any, path: tuple[str, ...] = (), dropped: frozenset[tuple[str, ...]] = DROPPED) -> Any:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                here = (*path, str(k))
                if _matches(here, dropped):
                    continue
                key = self.text(k) if isinstance(k, str) else k
                if v is not None and _matches(here, REVISION_BOUND):
                    out[key] = "<revision-bound>"
                elif _matches(here, DECISION_DIGEST) and v in self.decisions:
                    body = json.dumps({**self.decisions[v], "revision": "<revision-bound>"}, sort_keys=True,
                                      separators=(",", ":"), default=str)
                    out[key] = "<decision sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest() + ">"
                elif (TIME_KEY.match(str(k)) or _matches(here, TIME_PATHS)) and v is not None:
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


def _workspaces_root(root: Path) -> Path:
    from aew.engine.api import Engine

    return Engine.discover(root)._k.workspaces_root()


@contextmanager
def recorded_decisions() -> Iterator[dict[str, dict[str, Any]]]:
    """Every dispatch decision admitted while the block runs, by the digest it records (``provenance``), so
    ``end_state`` can recompute each digest with the revision substituted."""
    from aew.engine.dispatch import DispatchDecision

    seen: dict[str, dict[str, Any]] = {}
    real = DispatchDecision.provenance

    def provenance(self: DispatchDecision) -> dict[str, Any]:
        out = real(self)
        seen[out["decision"]] = self.to_dict()
        return out

    DispatchDecision.provenance = provenance  # type: ignore[method-assign]
    try:
        yield seen
    finally:
        DispatchDecision.provenance = real  # type: ignore[method-assign]


def end_state(root: Path, decisions: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The project at ``root`` as a stage/primitive equivalence compares it (module docstring)."""
    aew = root / ".aew"
    authored = {rel: path for path in sorted(aew.rglob("*"))
                if path.is_file() and not _journal_file(rel := path.relative_to(aew).as_posix())
                and (not rel.startswith(SKIPPED) or rel.startswith(COMPARED_LOCAL))}
    normalise = _Normaliser(str(root), str(_workspaces_root(root)),
                            {hashlib.sha256(path.read_bytes()).hexdigest(): f"<sha256 of {rel}>"
                             for rel, path in authored.items()}, decisions)
    control = _clean(load_control(root), str(root), normalise)
    files: dict[str, Any] = {}
    # The chain's tail last: it lists credentials by their random ids, so their ordinals come from the bundles first.
    for rel, path in sorted(authored.items(), key=lambda kv: kv[0] == TAIL):
        text = path.read_text(encoding="utf-8", errors="replace")
        if HISTORY_RECORD.match(rel):
            record = history_record(rel, yaml.safe_load(text), normalise)
            if record is not None:  # None: the journal's own annotation
                files[rel] = record
            continue
        if text.startswith("<!-- generated copy"):  # its first line names the control revision it was made at
            text = text.split("\n", 1)[1]
        if text.startswith("---\n"):  # front matter: compared as data, so its times are normalised
            _, front, body = text.split("---\n", 2)
            files[rel] = {"front": normalise(yaml.safe_load(front), (), frozenset({("base_revision",)})),
                          "body": normalise.text(body)}
        else:
            files[rel] = normalise.text(text)
    return {"control": control, "files": files}


def history_record(rel: str, data: Any, normalise: _Normaliser) -> Any:
    """A history record as the comparison sees it (module docstring), or None for the journal's own annotation: an
    annotation file with ``rel: stage_intent``. The tail keeps every other entry, its chain values become
    ``"<chain-hash>"`` and its entries' link lists compare as sets; a bundle's credentials are ordered by what they were
    issued to (their ids are random), so each gets the same ordinal in both projects."""
    if not isinstance(data, dict):
        return normalise(data)
    if "/annotations/" in rel and data.get("rel") == JOURNAL_ANNOTATION:
        return None
    if rel == TAIL:
        data = {**data, "entries": [{**e, **({"h": "<chain-hash>"} if "h" in e else {})}
                                    for e in data.get("entries") or []
                                    if not (e.get("kind") == "annotation" and e.get("rel") == JOURNAL_ANNOTATION)]}
    if rel.endswith("archive.yaml") and isinstance(data.get("tokens"), dict):
        data = {**data, "tokens": dict(sorted(data["tokens"].items(), key=lambda kv: _issue_order(kv[1])))}
    out = normalise(data)
    if rel == TAIL:
        for e in out.get("entries") or []:
            e["links"] = {k: sorted(v) if isinstance(v, list) else v for k, v in (e.get("links") or {}).items()}
    return out


def _issue_order(record: dict[str, Any]) -> tuple[str, ...]:
    scope = record.get("scope") or {}
    return (str(scope.get("invocation_id") or ""), str(record.get("kind")), str(record.get("issued_at")),
            str(scope.get("attempt") or ""), json.dumps(scope, sort_keys=True, default=str))


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

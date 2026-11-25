"""The pre-F4 scope add (register E126): the Lead adds one exact test path to one Ticket's scope, on the record, with a
reason, in place of cancel and replace (the operator's order of 2026-11-03; the designer's decisions of 2026-11-03,
§2). It is a correction F4 absorbs, not F4's first slice: F4 stays unbuilt.

* **Who decides.** Before the wire the Lead decides an add alone, an interim delegation for this one class of path
  (the operator's answer of 2026-11-03). A-29 is not amended: when ``DECIDE_WORK_PROPOSAL`` is built the add routes
  through it, or the operator amends the text (register E126's Notes).
* **The door.** ``resolve`` with the subject ``<T>#scope:<path>``, one path per call: the choice ``add_scope``, or
  ``add_scope_signed`` when the rationale carries a sign-off the stop rules ask for.
* **What may be added** (the four rules): an exact path, not a glob; a test file by name (``test_file_patterns``), or a
  new file under a test directory (``test_directories``); if it exists at the Ticket's base commit, its text there names
  a module the Ticket's scope matches, as a whole word; and it is not protected, generated or an acceptance input of a
  live Ticket. Any other kind of path stays out of this slice.
* **What stops for a sign-off** (``test_signoff_needed``): a runner configuration; an existing file under a test
  directory that is not a test file (shared setup, a helper, a mock, a skip list); a removed test file; and fewer test
  definitions in the added paths than at the base commit. The last two are evaluated wherever scope is, so they hold
  after the add as well as at it. A sign-off is cited from a plan revision or quoted from the operator. Before the wire
  nothing proves it: it is recorded as the Lead's report.
* **The record.** The Ticket's record and ``record_sha256`` never change. An immutable correction record beside the
  unit (``work/<T>/scope-corrections/<SC>.yaml``), a pointer in control state (``scope_corrections``), an archive pin,
  a ``unit.history`` event and a decision record.
* **One accessor** (derive, don't restate): :func:`effective_meta` is the record's meta with the added paths in its
  scope. ``Gates.record_meta`` and the context packs apply it, so every reader of a Ticket's scope reads the effective
  scope (``tests/unit/test_scope_add_rules.py`` fails on a new reader that takes scope from the record directly).
* **Evidence.** No rule changes: an add alone stales nothing. The result names the live invocations whose context pack
  it changed, with the commands that re-dispatch them.
"""

from __future__ import annotations

import copy
import posixpath
import re
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine.dispatch import Blocker, checked
from aew.engine.gate_ops import redispatch_commands
from aew.engine.guards import require
from aew.errors import AEWError, GateUnsatisfied, GitError, IllegalTransition, UsageError, ValidationFailed
from aew.harness import contract as K
from aew.harness import runlog
from aew.harness.contract import EXPECT_REV
from aew.knowledge.records import format_id
from aew.maps import rules as map_rules
from aew.policy import execution as X
from aew.policy import guardrails as GR
from aew.schemas import validate
from aew.snapshot.fingerprint import changed_paths
from aew.util import glob_any, load_yaml, safe_dump_yaml, sha256_bytes, utc_now
from aew.workspace import git

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext
    from aew.engine.ports import CoordinationPort, GatesPort, WorkUnitsPort

SCHEMA = "aew/scope-correction/v1"
UNIT_KEY = "scope_corrections"  # in a Ticket's control state: the pointers to its correction records
OP = "work.scope_add"
CHOICE, SIGNED_CHOICE = "add_scope", "add_scope_signed"  # ``resolve``'s choices (aew.surface.contract)
ITEM = "#scope:"  # the subject: ``<T>#scope:<path>``
DECISION_TYPE = "scope_correction"
OBLIGATION = "SCOPE_CORRECTION_ADDED"  # recorded on every add, in ACCEPTANCE_INPUT_IN_SCOPE's shape
SIGNOFF = "test_signoff_needed"  # the violation: a stop that needs a sign-off
MAX_TEXT = 2000
LEAD_REPORT = "the Lead's report: nothing proves a sign-off before the wire"
SIGNED_OFF = f"signed off ({LEAD_REPORT.split(':')[0]})"  # how a listing names a sign-off: claimed, never proved
_GLOB = set("*?[]{}")
DEFINITION_LIMIT = ("test definitions are counted by pattern, line by line: a commented-out test can still count, and "
                    "a path whose extension the table lacks, or whose tests it does not recognize (it counts 0 at the "
                    "base commit), is listed unchecked and raises no stop")

# What a test definition looks like, by extension (the designer's decisions of 2026-11-03, §2: "a small
# test_definition_patterns table beside test_file_patterns"). It lives here, not in the structural map's rule table,
# because that table's bytes are the maps' ruleset identity. An extension not in it is not counted, and the result
# says so. The patterns match text line by line (``DEFINITION_LIMIT``): a commented-out test, or a string that looks
# like one, can count, and a style the table does not know (C with Unity or CMocka, Ruby minitest, JUnit 3) counts 0,
# so a path that exists at the base commit and counts 0 there is listed unchecked too (PR #540 review, m1).
TEST_DEFINITION_PATTERNS: dict[str, str] = {
    ".py": r"^[ \t]*(?:async[ \t]+)?def[ \t]+test",
    ".go": r"^func[ \t]+Test",
    ".rs": r"#\[(?:[A-Za-z_:]+::)?test\]",
    ".c": r"\bTEST(?:_F|_P)?[ \t]*\(",
    ".cc": r"\bTEST(?:_F|_P)?[ \t]*\(",
    ".cpp": r"\bTEST(?:_F|_P)?[ \t]*\(",
    ".js": r"\b(?:it|test)(?:\.only|\.skip|\.each\([^)]*\))?[ \t]*\(",
    ".jsx": r"\b(?:it|test)(?:\.only|\.skip|\.each\([^)]*\))?[ \t]*\(",
    ".ts": r"\b(?:it|test)(?:\.only|\.skip|\.each\([^)]*\))?[ \t]*\(",
    ".tsx": r"\b(?:it|test)(?:\.only|\.skip|\.each\([^)]*\))?[ \t]*\(",
    ".rb": r"^[ \t]*it[ \t(]",
    ".java": r"@Test\b",
    ".cs": r"\[(?:Test|Fact|Theory|TestMethod)\b",
}


# ---------------------------------------------------------------------------------------------- the accessor

def added_paths(unit: dict[str, Any]) -> list[str]:
    """The paths the Lead added to ``unit``'s scope on the record, each once, in the order they were added (a later
    correction that only records a sign-off names its path again)."""
    return list(dict.fromkeys(c["added"] for c in unit.get(UNIT_KEY) or []))


def unsigned_paths(unit: dict[str, Any]) -> list[str]:
    """The added paths no correction records a sign-off for: the stops that removing tests raises still hold on them."""
    signed = {c["added"] for c in unit.get(UNIT_KEY) or [] if c.get("signed_off")}
    return [p for p in added_paths(unit) if p not in signed]


def added_listing(unit: dict[str, Any]) -> list[str]:
    """The added paths as status, the work graph and the Lead's results list them, never as a count, so growth stays
    visible (``WIS-02.f``; the designer's decisions of 2026-11-03, §2, "Seeing it"): each path once, with the
    correction that added it and the one that signed it off, if any, labelled as the Lead's report. Only a live
    Ticket's: a finished Ticket's adds are in its history, and this is the one place that says so (PR #545 review,
    m4)."""
    if unit.get("state") in H.TERMINAL:
        return []
    out: dict[str, str] = {}
    for c in unit.get(UNIT_KEY) or []:
        if c["added"] not in out:
            out[c["added"]] = f"{c['added']} ({c['id']}" + (f", {SIGNED_OFF}" if c.get("signed_off") else "")
        elif c.get("signed_off"):
            out[c["added"]] += f", {SIGNED_OFF} by {c['id']}"
    return [f"{v})" for v in out.values()]


def effective_scope(meta: dict[str, Any], unit: dict[str, Any]) -> list[str]:
    """The Ticket's effective scope: its record's declared paths, then the paths added on the record."""
    declared = list((meta.get("scope") or {}).get("paths") or [])
    return declared + [p for p in added_paths(unit) if p not in declared]


def declared_scope(meta: dict[str, Any], unit: dict[str, Any]) -> list[str]:
    """The Ticket's declared scope from ``meta``, effective or not: its paths without the ones added on the record."""
    added = set(added_paths(unit))
    return [p for p in (meta.get("scope") or {}).get("paths") or [] if p not in added]


def effective_meta(meta: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    """The one accessor for a Ticket's scope: its record's meta with the effective scope in ``scope.paths``. Every
    reader of scope reads it through this (``Gates.record_meta``, the context packs), never from the record. A unit
    with no correction gets ``meta`` back unchanged."""
    if not unit.get(UNIT_KEY):
        return meta
    out = copy.deepcopy(meta)
    out.setdefault("scope", {})["paths"] = effective_scope(meta, unit)
    return out


def pack_entries(aew_root: Path, unit: dict[str, Any]) -> list[dict[str, Any]]:
    """What a Ticket's context pack shows of its added paths, apart from its declared scope (the designer's decisions
    of 2026-11-03, §2, "Seeing it"; PR #540 review, M2): each path once, with the correction that added it, the
    Lead's rationale, and a sign-off recorded then or later, each as the Lead wrote it."""
    out: dict[str, dict[str, Any]] = {}
    for ptr in unit.get(UNIT_KEY) or []:
        doc = load_yaml((aew_root / ptr["record"]).read_text(encoding="utf-8"), source=ptr["record"])
        entry = out.setdefault(ptr["added"], {"path": ptr["added"], "correction": ptr["id"],
                                              "rationale": doc["rationale"], "signoff": None})
        if doc["signoff"] is not None:
            entry["signoff"] = {"correction": ptr["id"], "text": doc["signoff"]["text"],
                                "label": doc["signoff"]["label"]}
    return list(out.values())


def lines_changed(numstat: str, declared: list[str], added: list[str]) -> dict[str, dict[str, int]]:
    """The lines added and removed in the declared scope and in the added paths, from ``git diff --numstat -z``: what a
    reviewer judges an add's proportion by, since there is no size limit (the designer's decisions of 2026-11-03, §2,
    "No size limit and no ratio"; PR #540 quick check, m-c). An added path counts as added even when a declared glob
    also matches it; a path in neither is left out (the guardrails name it). A binary file counts as a file, with no
    lines."""
    out = {part: {"files": 0, "added": 0, "removed": 0} for part in ("declared", "added")}
    for row in numstat.split("\0"):
        fields = row.strip("\n").split("\t", 2)
        if len(fields) != 3:
            continue
        plus, minus, path = fields
        part = "added" if path in added else "declared" if glob_any(path, declared) else None
        if part is None:
            continue
        out[part]["files"] += 1
        out[part]["added"] += int(plus) if plus.isdigit() else 0
        out[part]["removed"] += int(minus) if minus.isdigit() else 0
    return out


def pack_sources(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """The pack's sources for its corrections: ``scope_correction:<SC>``, each record by path and hash."""
    return [{"name": f"scope_correction:{c['id']}", "path": c["record"], "sha256": c["sha256"]}
            for c in unit.get(UNIT_KEY) or []]


def cold_rel(correction: str, work_id: str) -> str:
    return f"work/{work_id}/scope-corrections/{correction}.yaml"


def item_id(work_id: str, path: str) -> str:
    return f"{work_id}{ITEM}{path}"


def parse_item(subject: str) -> tuple[str, str] | None:
    work_id, sep, path = subject.partition(ITEM)
    return (work_id, path) if sep and work_id and path else None


def remedy(work_id: str) -> str:
    """How the Lead adds a test path to a Ticket's scope: the typed call, and its form from a shell."""
    return (f"to add one exact test path to {work_id}'s scope on the record, use the typed `resolve` tool: subject "
            f"`{item_id(work_id, '<path>')}`, choice `{CHOICE}`, a `rationale` and `expect_rev`; from a shell, `aew "
            "lead tool resolve --arguments -` with those arguments as JSON on standard input")


# ---------------------------------------------------------------------------------------------- the path rules

def _rules() -> dict[str, Any]:
    return map_rules.load().data


def _name(path: str) -> str:
    return posixpath.basename(path)


def is_test_file(path: str, rules: dict[str, Any]) -> bool:
    return any(fnmatchcase(_name(path), p) for p in rules["test_file_patterns"])


def under_test_directory(path: str, rules: dict[str, Any]) -> bool:
    dirs = set(rules["test_directories"])
    return any(part.lower() in dirs for part in path.split("/")[:-1])


def is_runner_config(path: str, rules: dict[str, Any]) -> bool:
    return _name(path) in rules["test_runner_configs"]


def test_code(path: str) -> bool:
    """Whether rule 2 could take ``path`` by its kind: a test file by name, or a file under a test directory (whether
    it is new is read from the base commit, by the add)."""
    rules = _rules()
    return is_test_file(path, rules) or under_test_directory(path, rules)


def exact_path_problem(path: str) -> str | None:
    """Why ``path`` is not one exact repository-relative path (rule 1), or None. A path is one printable line: it is
    written into records, packs and listings (PR #545 review, m1)."""
    if not path.isprintable():
        return "it holds a control or other unprintable character"
    if not path or path != path.strip():
        return "it is blank or has surrounding spaces"
    if set(path) & _GLOB:
        return "it is a glob; name one exact path"
    if "\\" in path or path.startswith("/") or posixpath.normpath(path) != path or path.split("/")[0] in {"..", "."}:
        return "it is not a normalized repository-relative path (forward slashes, no `..`, no leading `/`)"
    if path.endswith("/"):
        return "it names a directory; name one file"
    return None


def test_definitions(path: str, text: str | None) -> int | None:
    """How many test definitions ``text`` holds, or None when ``path``'s extension is not in the table."""
    pattern = TEST_DEFINITION_PATTERNS.get(posixpath.splitext(path)[1].lower())
    if pattern is None or text is None:
        return None if pattern is None else 0
    return len(re.findall(pattern, text, re.MULTILINE))


def module_stems(files: list[str]) -> list[str]:
    """The stems rule 3 looks for: each in-scope file's name without its extension, except a dunder stem
    (``__init__``, ``__main__``), which names a language hook in any test, not a module (PR #540 review, m6). The rule
    stays weak on a common stem (``main``, ``index``, ``utils``) and on a package-wide scope: the review stands behind
    it there, as the design says."""
    stems = (posixpath.splitext(_name(f))[0] for f in files)
    return list(dict.fromkeys(s for s in stems if not (s.startswith("__") and s.endswith("__"))))


def names_module(text: str, stems: list[str]) -> str | None:
    """The first stem ``text`` contains as a whole word (rule 3), or None."""
    for stem in stems:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(stem)}(?![A-Za-z0-9_])", text):
            return stem
    return None


def static_stops(path: str, at_base: bool, rules: dict[str, Any]) -> list[dict[str, str]]:
    """The stops a path's kind raises at the add: a runner configuration, new or existing, and an existing file under a
    test directory whose name is not a test file's (shared setup, a helper or mock, a skip list)."""
    stops = []
    if is_runner_config(path, rules):
        stops.append({"path": path, "stop": "runner_config",
                      "detail": "a test runner's configuration: it changes how the whole suite runs"})
    elif at_base and under_test_directory(path, rules) and not is_test_file(path, rules):
        stops.append({"path": path, "stop": "shared_test_file",
                      "detail": "an existing file under a test directory that is not a test file: shared setup, a "
                                "helper or mock, or a skip list, which changes a suite's flow"})
    return stops


def removal_stops(paths: list[str], base_text: Callable[[str], str | None],
                  now_text: Callable[[str], str | None]) -> tuple[list[dict[str, str]], list[str]]:
    """The stops that removing tests raises over the added paths, judged against the base commit: a file that existed
    there and is gone, and fewer test definitions in total (a rename or a move between the paths is neutral). Returns
    them, and the paths whose extension is not counted."""
    stops: list[dict[str, str]] = []
    unchecked: list[str] = []
    before = after = 0
    for p in paths:
        old, new = base_text(p), now_text(p)
        if old is not None and new is None:
            stops.append({"path": p, "stop": "test_removed",
                          "detail": "it existed at the Ticket's base commit and has been deleted"})
        counted = test_definitions(p, old), test_definitions(p, new)
        if counted[0] is None or (old is not None and counted[0] == 0):  # not a style the table knows (m1)
            unchecked.append(p)
            continue
        before += counted[0]
        after += counted[1] or 0
    if after < before:
        stops.append({"path": ", ".join(p for p in paths if p not in unchecked), "stop": "fewer_test_definitions",
                      "detail": f"the added paths hold {after} test definitions, {before} at the base commit"})
    return stops, unchecked


def signoff_violations(unit: dict[str, Any], base_text: Callable[[str], str | None],
                       now_text: Callable[[str], str | None]) -> list[dict[str, str]]:
    """``test_signoff_needed``, wherever scope is evaluated: the removal stops over the paths added without a
    sign-off, as guardrail violations."""
    unsigned = unsigned_paths(unit)
    if not unsigned:
        return []
    stops, _ = removal_stops(unsigned, base_text, now_text)
    return [{"path": s["path"], "rule": SIGNOFF, "detail": f"{s['detail']}; that needs a sign-off on the record: "
             f"`resolve` with the subject `<Ticket>{ITEM}<path>` for each path named, the choice `{SIGNED_CHOICE}`, "
             "and the plan revision cited or the operator quoted in the rationale"} for s in stops]


# The facts a launch conflict (``conflicts.find_conflict``) is made of, with its ``scope_pairs``. Its hold message is
# not one of them: it names the Ticket's whole scope, so it differs after any widening (PR #540 quick check, m-a).
CONFLICT_FACTS = ("reasons", "touched_in_scope", "outside_own_scope")


def widening_meets(before: dict[str, Any] | None, after: dict[str, Any]) -> bool:
    """Whether the conflict ``after`` with another live Ticket, found on the widened scope, holds a fact that
    ``before`` (the conflict with that Ticket on the scope as it stands, or None) does not: a reason, a changed path
    inside the scope, a stray write or a pair of scopes that can meet. Only such a conflict is the widening's own."""
    if before is None:
        return True
    pairs = {tuple(p) for p in before.get("scope_pairs") or []}
    return (any(not set(after.get(f) or []) <= set(before.get(f) or []) for f in CONFLICT_FACTS)
            or any(tuple(p) not in pairs for p in after.get("scope_pairs") or []))


def signoff_source(rationale: str, plan_revisions: set[int]) -> dict[str, Any] | None:
    """Where a sign-off is cited from: a plan revision of the Ticket (``plan v<N>``), or the operator's words, quoted.
    None when the rationale cites neither."""
    for found in re.finditer(r"\bplan (?:v|revision )(\d+)\b", rationale, re.IGNORECASE):
        if int(found.group(1)) in plan_revisions:
            return {"source": "plan", "plan_revision": int(found.group(1))}
    if re.search(r"\"[^\"]{8,}\"|“[^”]{8,}”", rationale):
        return {"source": "operator_quote"}
    return None


def unit_violations(repo_root: Path, unit: dict[str, Any], *, after: str | None = None) -> list[dict[str, str]]:
    """``test_signoff_needed`` for a Ticket's gate context: its added paths at its base commit against its workspace
    now, or against ``after`` (a commit: the accepted Ticket commit). Nothing without an add or a workspace."""
    ws = unit.get("workspace") or {}
    if not unit.get(UNIT_KEY) or not ws.get("base_commit"):
        return []
    root = Path(ws["path"]) if ws.get("path") else None

    def now(p: str) -> str | None:
        return _git_text(repo_root, after, p) if after else _file_text(root, p)

    return signoff_violations(unit, lambda p: _git_text(repo_root, ws["base_commit"], p), now)


# ---------------------------------------------------------------------------------------------- the add

def _git_text(repo: Path, commit: str | None, path: str) -> str | None:
    if not commit:
        return None
    try:
        # Through `git.out`, not `git.git`: the reference's value flow follows at most 64 call sites of one function,
        # and `git.git` is at that cap (tools/reference_families/writers_flow.py, CALLERS; PR #540 CI). The text is
        # read for its words and test definitions, so `out`'s trimmed ends change nothing.
        return git.out("show", f"{commit}:{path}", cwd=repo)
    except GitError:
        return None


def _file_text(root: Path | None, path: str) -> str | None:
    if root is None:
        return None
    try:
        return (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class ScopeCorrections:
    """The recorded scope add (register E126): its guard query, the transaction, and the effective scope's
    sign-off violations for the gate context."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, gates: GatesPort, assurance: Any,
                 coordination: CoordinationPort) -> None:
        self.k = k
        # the adopted messaging switch comes through the port, so this module never imports coordination (F9
        # invariant 1, `test_legality_modules_never_import_coordination`)
        self.coordination = coordination
        self.units = units
        self.gates = gates
        self.assurance = assurance  # the dispatch predicates re-run on the widened scope

    def _base(self, unit: dict[str, Any]) -> str | None:
        return (unit.get("workspace") or {}).get("base_commit") or self.k.authoritative_commit()

    def add_query(self, state: dict[str, Any], work_id: str | None, args: dict[str, Any]) -> Blocker | None:
        """``work.scope_add`` with ``args`` (``subject``, ``rationale``, ``signed``): the Ticket's admission, the four
        path rules, the stops, and dispatch's assurance predicates on the widened scope. It records what it found in
        ``args["found"]``; ``work_id`` is unused (the subject names it)."""
        return checked(lambda: args.setdefault("found", {}).update(self._check(state, args)))

    def _check(self, state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        subject = str(args.get("subject") or "")
        parsed = parse_item(subject)
        if parsed is None:
            raise UsageError(f"`{subject}` is not a scope add: its subject is `<Ticket>{ITEM}<path>`, one exact path",
                             subject=subject, reason="bad_subject")
        work_id, path = parsed
        rationale = str(args.get("rationale") or "").strip()
        if not rationale:
            raise UsageError("a scope add needs the reason the Ticket needs this test path", reason="no_rationale")
        unit = self.units.unit(state, work_id)
        self._admit(state, work_id, unit)
        problem = exact_path_problem(path)
        if problem:
            raise ValidationFailed(f"{path!r} cannot be added to {work_id}'s scope: {problem}", work_id=work_id,
                                   path=path, reason="not_exact" if path.isprintable() else "unprintable_path")
        meta = self.gates.record_meta(unit)
        scope = list((meta.get("scope") or {}).get("paths") or [])
        # A path added without a sign-off is signed off later by the signed choice: a second correction that records
        # only the sign-off, so the stop it raised after the add has a way out (PR #540 review, M1).
        signs = next((c["id"] for c in unit.get(UNIT_KEY) or [] if c["added"] == path), None) \
            if path in unsigned_paths(unit) else None
        if glob_any(path, scope) and not (signs and args.get("signed")):
            raise ValidationFailed(
                f"`{path}` is already in {work_id}'s scope"
                + (f"; it was added without a sign-off ({signs}), which the choice `{SIGNED_CHOICE}` records" if signs
                   else ""), work_id=work_id, path=path, reason="already_in_scope")
        rules = _rules()
        base = self._base(unit)
        ws = unit.get("workspace") or {}
        root = Path(ws["path"]) if ws.get("path") else None
        # The rules read the base commit and the workspace; either unreadable refuses the add, never reads as "new"
        # or "nothing changed" (CNI-03.a, as the conflict check holds; PR #540 review, m2).
        try:
            if not base:
                raise GitError("no base commit")
            base_files = set(git.out("ls-tree", "-r", "--name-only", base, cwd=self.k.repo_root).splitlines())
            new_files = [p for p in changed_paths(root, base, stores=False, **self.k.check_cache_inputs())
                         if p not in base_files and (root / p).is_file()] if root is not None else []
        except (AEWError, OSError) as err:
            raise IllegalTransition(
                f"`{path}` cannot be judged for {work_id}'s scope: its base commit {base} or its workspace cannot be "
                f"read ({err}), so the path rules cannot tell an existing file from a new one. Restore the workspace "
                "or the base, then add it again", work_id=work_id, path=path, reason="base_unreadable") from err
        at_base = path in base_files
        created = not at_base and path in new_files
        named = None
        if signs:
            first = self._record(unit, signs)
            named = first.get("names_module")
        else:
            named = self._path_rules(state, work_id, unit, meta, path, at_base, base, base_files, new_files, rules)
        # The stops: the path's kind, and removed tests over every path added without a sign-off, this one included.
        unsigned = [*(p for p in unsigned_paths(unit) if p != path), path]
        removals, unchecked = removal_stops(unsigned, lambda p: _git_text(self.k.repo_root, base, p),
                                            lambda p: _file_text(root, p) if root is not None
                                            else _git_text(self.k.repo_root, base, p))
        stops = static_stops(path, at_base, rules) + removals
        signoff = None
        if args.get("signed"):
            revisions = {int(p["revision"]) for p in unit.get("plans") or [] if p.get("revision") is not None}
            signoff = signoff_source(rationale, revisions)
            if signoff is None:
                raise UsageError(
                    "a signed scope add cites its sign-off in the rationale: a plan revision of the Ticket (`plan "
                    "v<N>`), or the operator's words in quotes", work_id=work_id, path=path, reason="signoff_uncited")
            signoff.update(text=rationale[:MAX_TEXT], label=LEAD_REPORT)
        elif stops:
            raise GateUnsatisfied(
                f"`{path}` needs a sign-off before it is added to {work_id}'s scope: "
                + "; ".join(f"{s['path']}: {s['detail']}" for s in stops)
                + f". Raise it, then record the sign-off with the choice `{SIGNED_CHOICE}`, citing the plan revision "
                "or quoting the operator in the rationale", work_id=work_id, path=path, stops=stops,
                reason=SIGNOFF)
        obligations: list[dict[str, Any]] = []
        if not signs:  # a sign-off alone widens nothing, so the dispatch predicates have nothing new to judge
            obligations = self._dispatch_predicates(state, work_id, path)
        return {"work_id": work_id, "path": path, "signs": signs, "at_base": at_base, "created_by_ticket": created,
                "names_module": named, "base_commit": base, "signoff": signoff, "stops": stops,
                "unchecked": unchecked, "obligations": obligations,
                "stale_invocations": self.stale_invocations(state, work_id, path, self.run_status,
                                                            self.messaging(state))}

    def _record(self, unit: dict[str, Any], correction: str) -> dict[str, Any]:
        ptr = next(c for c in unit.get(UNIT_KEY) or [] if c["id"] == correction)
        return load_yaml((self.k.aew_root / ptr["record"]).read_text(encoding="utf-8"), source=ptr["record"])

    def _path_rules(self, state: dict[str, Any], work_id: str, unit: dict[str, Any], meta: dict[str, Any], path: str,
                    at_base: bool, base: str, base_files: set[str], new_files: list[str],
                    rules: dict[str, Any]) -> str | None:
        """Rules 2 to 4; returns the module an existing file names (rule 3)."""
        # Rule 2: a test file by name, or a new file under a test directory.
        if not (is_test_file(path, rules) or (not at_base and under_test_directory(path, rules))):
            raise ValidationFailed(
                f"`{path}` is not test code: a scope add takes a file named like a test "
                f"({', '.join(rules['test_file_patterns'])}), or a new file under a test directory "
                f"({', '.join(rules['test_directories'])}). Any other path stays out of this route: the Ticket's "
                "scope is otherwise fixed when it is created", work_id=work_id, path=path, reason="not_a_test_path")
        # Rule 3: an existing file names a module in the Ticket's declared scope, read from the base commit (the
        # implementer can write the workspace copy); never a test a previous add brought in.
        named = None
        if at_base:
            declared = [f for f in sorted(base_files | set(new_files)) if glob_any(f, declared_scope(meta, unit))]
            named = names_module(_git_text(self.k.repo_root, base, path) or "", module_stems(declared))
            if named is None:
                raise ValidationFailed(
                    f"`{path}` exists at {work_id}'s base commit and names no module in its scope: its text there "
                    "contains no file name (without its extension) the Ticket's scope matches. Add the test that "
                    "exercises this Ticket's change", work_id=work_id, path=path, reason="names_no_scope_module")
        # Rule 4: not protected or generated, and not an acceptance input of any live Ticket.
        policy = self.k.policy("guardrails")
        if glob_any(path, GR.ALWAYS_PROTECTED + list(policy.get("protected_paths") or [])):
            raise ValidationFailed(f"`{path}` is a protected path", work_id=work_id, path=path,
                                   reason="protected_path")
        if glob_any(path, list(policy.get("generated_paths") or [])):
            raise ValidationFailed(f"`{path}` is a generated file", work_id=work_id, path=path,
                                   reason="generated_path")
        for other, u in sorted(state["work"].items()):
            if u.get("kind") != "ticket" or u.get("state") in H.TERMINAL:
                continue
            inputs = list(((self.gates.record_meta(u).get("acceptance") or {}).get("inputs")) or [])
            if inputs and glob_any(path, inputs):
                raise ValidationFailed(
                    f"`{path}` is an acceptance input of {other}: its acceptance checks read it, and in scope it "
                    "could be edited to pass them", work_id=work_id, path=path, input_of=other,
                    reason="acceptance_input")
        return named

    def _dispatch_predicates(self, state: dict[str, Any], work_id: str, path: str) -> list[dict[str, Any]]:
        """Dispatch's assurance predicates on the widened scope, as at dispatch (A-05's ADC-02.d): an overlap with a
        protected condition blocks, as does a conflict with another live Ticket that only the widening creates (E151;
        PR #540 review, m3); the hard triggers are recorded as obligations, with the add's own."""
        widened = copy.deepcopy(state)
        widened["work"][work_id].setdefault(UNIT_KEY, []).append({"added": path, "signed_off": False})
        facts: dict[str, Any] = {"archetype": "implementer", "obligations": [], "digests": {}}
        blockers = list(self.assurance.guard_protected(widened, work_id, facts) or [])
        held_now = {b.details.get("work_id"): b.details for b in self.assurance.guard_conflict(
            state, work_id, {"archetype": "implementer", "obligations": [], "digests": {}}) or []}
        conflicts = [b for b in self.assurance.guard_conflict(widened, work_id, facts) or []
                     if widening_meets(held_now.get(b.details.get("work_id")), b.details)]
        if blockers or conflicts:
            raise GateUnsatisfied(f"adding `{path}` to {work_id}'s scope is refused as a dispatch would be: "
                                  + "; ".join(b.message for b in blockers + conflicts), work_id=work_id, path=path,
                                  blockers=[{"code": b.code, "message": b.message} for b in blockers + conflicts],
                                  reason="files_conflict" if conflicts and not blockers else "dispatch_predicate")
        self.assurance.guard_triggers(widened, work_id, facts)
        return [*facts["obligations"], {"code": OBLIGATION, "paths": [path],
                                        "obligation": "a test path the Lead added to the scope: the review reads it "
                                                      "as a labelled widening"}]

    def _admit(self, state: dict[str, Any], work_id: str, unit: dict[str, Any]) -> None:
        """Only a live mutating Ticket with a bounded scope and a reader independent of its implementer."""
        if unit.get("kind") != "ticket" or not unit.get("mutating"):
            raise IllegalTransition(f"{work_id} is not a mutating Ticket: only a mutating Ticket's scope is widened",
                                    work_id=work_id, reason="not_a_mutating_ticket")
        if unit["state"] in H.TERMINAL:
            raise IllegalTransition(f"{work_id} is {unit['state']}; a finished Ticket keeps its scope",
                                    work_id=work_id, reason="finished")
        if not (self.gates.record_meta(unit).get("scope") or {}).get("paths"):
            raise IllegalTransition(f"{work_id}'s scope is unbounded, so it already covers every path",
                                    work_id=work_id, reason="unbounded_scope")
        gc = self.gates.gate_context(state, work_id)
        readers = [g for g in gc["obligations"]["gates"] if g != "self_review" and (
            g.startswith(G.REVIEW_GATES_PREFIX) or g in G.VERIFICATION_GATES or g.startswith(G.VERIFY_CARD_PREFIX))
            and (gc["gates"].get(g) or {}).get("status") != G.WAIVED]
        if not readers:
            raise IllegalTransition(
                f"{work_id} has no unwaived review or verification gate, so no one but its implementer would read the "
                f"widened diff: raise its class first with `aew work reclassify {work_id} --class <0-4> --reason "
                f"<reason> {EXPECT_REV}`", work_id=work_id, reason="no_independent_reader")

    def run_status(self, run: str) -> str:
        """What the run's local evidence says it is now (``runlog.observed_status``)."""
        return runlog.observed_status(runlog.run_dir(self.k.aew_root, run))[0]

    def messaging(self, state: dict[str, Any]) -> bool:
        """Whether scope guidance should use the typed coordination send for a live worker (PR #545 review, m2)."""
        return self.coordination.project_switch(state) == X.MESSAGING_ENABLED

    @staticmethod
    def stale_invocations(state: dict[str, Any], work_id: str, path: str, run_status: Callable[[str], str],
                          messaging: bool = False) -> list[dict[str, Any]]:
        """The active invocations on the Ticket, whose context pack renders its scope. An add alone stales no evidence:
        a live implementer is told with `harness send` and continues, since cancelling it would discard the run the add
        exists to save (its next launch is refused by the existing pack guard); a reader is re-dispatched with its
        card, as a gate replacement's result names it (ITEMS 55 addendum 3; PR #540 review, m5). ``harness send``
        takes only a STARTING or RUNNING run, so an implementer whose run has ended, or whose status cannot be read,
        is re-dispatched too: a fresh invocation on the kept workspace (``run_status``; PR #540 quick check, m-b).
        With coordination ``messaging`` on, the scope guidance uses `message_send` to record a live implementer's
        message and preserve a held session (PR #545 review, m2).
        Its arguments are whole, as `message_send` takes them: ``expect_rev`` is the revision the add commits, the
        state's next (PR #545 quick check, m6)."""
        why = f"`{path}` was added to {work_id}'s scope on the record, so this invocation's context pack changed"
        out = []
        for inv_id, inv in sorted(state["invocations"].items()):
            if inv.get("status") != "active" or inv.get("work_unit") != work_id:
                continue
            runs = inv.get("runs") or []
            live = inv.get("role") == "implementer" and runs and run_status(runs[-1]["run"]) in K.LIVE_RUNS
            if live and messaging:
                commands = ["aew lead tool message_send --arguments -"]
                fields = {"expect_rev": state["revision"] + 1, "to": inv_id,
                          "body": f"{why}: you may now change `{path}`"}
            elif live:
                commands = [f"aew harness send {runs[-1]['run']} --fields -"]
                fields = {"text": f"{why}: you may now change `{path}`"}
            else:
                commands, fields = redispatch_commands(state, inv_id, inv), {"reason": why}
            out.append({"invocation": inv_id, "work_id": work_id, "role": inv.get("role"), "commands": commands,
                        "fields": fields})
        return out

    def scope_add(self, *, token: str, expect_rev: int, subject: str, rationale: str,
                  signed: bool = False) -> dict[str, Any]:
        args: dict[str, Any] = {"subject": subject, "rationale": rationale, "signed": signed}
        with self.k.lead_txn(token, expect_rev, OP, reason=rationale) as ctx:
            require(self.add_query(ctx.state, None, args))
            found = args["found"]
            work_id, path = found["work_id"], found["path"]
            unit = ctx.state["work"][work_id]
            ctx.state["counters"]["scope_correction"] = ctx.state["counters"].get("scope_correction", 0) + 1
            sc = format_id("SC", ctx.state["counters"]["scope_correction"])
            what = f"sign-off on `{path}` recorded ({sc}, signs {found['signs']})" if found["signs"] \
                else f"`{path}` added ({sc})"
            decision = self.k.new_decision(ctx, DECISION_TYPE, f"{work_id} scope: {what}", work_unit=work_id,
                                           reason=rationale)
            record = {"schema": SCHEMA, "id": sc, "work_unit": work_id, "path": path, "signs": found["signs"],
                      "names_module": found["names_module"], "at_base": found["at_base"],
                      "created_by_ticket": found["created_by_ticket"], "base_commit": found["base_commit"],
                      "rationale": rationale.strip()[:MAX_TEXT], "signoff": found["signoff"],
                      "stops": found["stops"], "unchecked": found["unchecked"], "obligations": found["obligations"],
                      "by": dict(ctx.actor), "generation": ctx.state["lead"]["generation"],
                      "expected_revision": expect_rev, "rev": ctx.session.revision + 1, "at": utc_now(),
                      "decision": decision, "stale_invocations": found["stale_invocations"]}
            validate("scope-correction", record, source=f"scope correction {sc}")
            self._write(ctx, unit, record)
            unit.setdefault("history", []).append(
                {"from": unit["state"], "to": unit["state"], "at": record["at"],
                 "event": "scope_signed_off" if found["signs"] else "scope_added",
                 "reason": f"{what} ({decision}): {record['rationale']}",
                 "decided_by": {k: ctx.actor.get(k) for k in ("kind", "session_label", "generation")}})
            ctx.summary = f"{work_id} scope: {what}"
            self.units.before_commit(ctx)
        return {"ok": True, "subject": subject, "work_id": work_id, "correction": sc, "decision": decision,
                "path": path, "signs": found["signs"], "created_by_ticket": found["created_by_ticket"],
                "names_module": found["names_module"], "signoff": found["signoff"], "stops": found["stops"],
                "unchecked": found["unchecked"], "definition_limit": DEFINITION_LIMIT,
                "obligations": found["obligations"], "added_paths": added_paths(unit),
                "stale_invocations": found["stale_invocations"], "revision": ctx.session.committed_revision}

    @staticmethod
    def _write(ctx: TxnContext, unit: dict[str, Any], record: dict[str, Any]) -> None:
        """The record, immutable, beside the unit; control state takes a pointer to it. The unit's own record and its
        ``record_sha256`` never change."""
        rel = cold_rel(record["id"], record["work_unit"])
        text = safe_dump_yaml(record, source=f"scope correction record {record['id']}")
        ctx.session.write(rel, text, immutable=True)
        unit.setdefault(UNIT_KEY, []).append(
            {"id": record["id"], "added": record["path"], "signed_off": record["signoff"] is not None,
             **({"signs": record["signs"]} if record["signs"] else {}), "record": rel,
             "sha256": sha256_bytes(text.encode("utf-8")), "rev": record["rev"]})
        ctx.refs.append(rel)

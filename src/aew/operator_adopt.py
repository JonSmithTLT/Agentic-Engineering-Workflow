"""Settings adopted, and authority decided, at the operator's own terminal with no Lead credential (register E331).

The designer's decision of 2026-11-10 replacing the project-wide revision check (design workspace ``ab975c1``, part
3(a)), decided by the operator the same day, ends the seat dance a setting change needed: acquire the seat, edit,
adopt with the Lead credential, release. The commands are `aew manifest adopt`, `aew authority accept` and `aew
authority reject` (``--decided-by operator``, the default), and E164's `aew policy model allow` and `aew policy route`,
which adopt through :func:`adopt` with the bytes they write. There is no new write route: each runs the engine's own
operation (``Engine.manifest_adopt``, ``authority_accept``, ``authority_reject``) with no token, which commits it as the
operator's own transaction (``Kernel.operator_txn``).

1. **Where.** Refused inside an AEW session (a Lead session, by its broker's variables or, on Linux, its process
   ancestry; a worker's run), from a non-writer process and without a terminal (:func:`require_here`), before anything
   is read for the prompt. A Lead session's broker refuses the commands too (``lead_broker.OPERATOR_DECIDED``).
2. **What is shown.** Each file's diff against the version its pin holds (:func:`diff_lines`, the pinned bytes from
   ``engine.pinned_copies``), and the digest of each, before and now. The commit compares the digests shown: a class C
   binding (E327), so a file changed after it was shown commits nothing (``CHANGED_SINCE_READ``).
3. **The code is the register of weaker contexts' to decide** (the operator, 2026-11-10). While it is clear on this
   host the operator confirms plainly; while a weaker context is live or recent, or the register cannot say, the
   typed-back code is asked and the prompt names the weaker run (``g3standing.no_weaker_context``, its one reader).
4. **The record is the operator's own:** kind operator, ``authorized_by: operator-tty``, no Lead actor. A running Lead
   keeps its seat, and its next step bound to policy that moved meets STALE_POLICY.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from typing import Any

from aew.errors import IllegalTransition, OperatorAuthorizationRequired, PermissionDenied
from aew.util import atomic_write, sha256_bytes

MANIFEST_COMMAND = "aew manifest adopt"
DIFF_LINES = 200  # per file: a longer diff is cut, and the prompt says to read the file before confirming
SEAT_LINE = ("No Lead credential is used, and the Lead seat stays with its holder: a stage open now stops as "
             "STALE_POLICY at its next step when a setting it is bound to changed.")
NO_TERMINAL = "no_terminal"
# Whether an authority decision always asks the typed-back code, whatever the register says: None lets the register
# decide, as for the adoption's diff (this PR's reading of the row); a reason, which the prompt shows, asks it always.
# The operator rules on it (review of #641, point 1), and the ruling is this one line.
AUTHORITY_CODE_ALWAYS: str | None = None


def problem(command: str) -> PermissionDenied | None:
    """Why ``command`` may not run in this process, as its refusal, or None: an AEW session first, then a non-writer,
    then no terminal (rule 1)."""
    from aew import lead_credential, operator, process_kind
    from aew.harness.operator_client import lead_session_problem

    instead = ("Run it yourself in a terminal you opened, outside `aew opencode` and any agent's shell; a Lead asks "
               "the operator instead")
    kind = lead_credential.session_kind()
    ancestry = lead_session_problem() if kind != "worker" else None
    if kind is not None or ancestry is not None:
        why = "this is a worker's run" if kind == "worker" else (ancestry or "this process runs in a Lead session")
        return PermissionDenied(f"`{command}` is the operator's own decision, made at their own terminal outside any "
                                f"AEW session, and {why}: nothing is changed. {instead}",
                                reason="aew_session", session=kind or "lead")
    if process_kind.kind() == process_kind.NON_WRITER:
        return PermissionDenied(f"`{command}` writes the control state, which a non-writer process (an agent's own "
                                f"`aew`) never does: nothing is changed. {instead}", reason="non_writer_process")
    if not operator.has_terminal():
        return OperatorAuthorizationRequired(
            f"`{command}` is confirmed at the operator's own terminal, and this process has none (a harness tool call, "
            "a pipe or a scheduled job): nothing is changed. Run it yourself in a terminal",
            detail="no terminal", reason=NO_TERMINAL)
    return None


def require_here(command: str) -> None:
    refused = problem(command)
    if refused is not None:
        raise refused


def code_because() -> str | None:
    """Rule 3: None while the register of weaker contexts is clear on this host, else why the code is asked, naming
    the weaker run."""
    from aew.g3standing import no_weaker_context

    found = no_weaker_context()
    return None if found is None else found[0]


def diff_lines(rel: str, before: bytes | None, after: bytes | None, *, limit: int = DIFF_LINES) -> list[str]:
    """``.aew/<rel>``'s unified diff from ``before`` (the pinned bytes, None for none) to ``after`` (None: removed)."""
    old = [] if before is None else before.decode("utf-8", "replace").splitlines()
    new = [] if after is None else after.decode("utf-8", "replace").splitlines()
    out = list(difflib.unified_diff(old, new, f"pinned .aew/{rel}", f"now .aew/{rel}", lineterm="", n=2))
    if len(out) > limit:
        out = [*out[:limit], f"... {len(out) - limit} more diff lines are not shown: read .aew/{rel} before you "
                             "confirm"]
    return out


def _short(sha: str | None, none: str) -> str:
    return sha if sha is not None else none


def _file_lines(engine: Any, rel: str, pinned: str | None, now: str | None, raw: bytes | None,
                first_pin: bool) -> list[str]:
    from aew.engine import pinned_copies

    lines = [f"  .aew/{rel}",
             f"    pinned : {_short(pinned, 'never pinned' if first_pin else 'absent')}",
             f"    now    : {_short(now, 'absent (removed)')}"]
    before = None if pinned is None else pinned_copies.pinned(engine.repo_root, engine.aew_root, rel, pinned)
    if pinned is not None and before is None:
        lines.append("    the pinned version's bytes are not on this host (no kept copy, and no recent git commit "
                     "holds them): the file is shown whole")
    lines += [f"    {line}" for line in diff_lines(rel, before, raw)]
    return lines


def adopt(engine: Any, *, reason: str, command: str = MANIFEST_COMMAND, edits: Mapping[str, bytes] | None = None,
          lines: Sequence[str] = ()) -> dict[str, Any]:
    """Adopt the settings at the operator's terminal (rules 1 to 4): the files that differ from their pins now, or, for
    a command that writes its own change (E164's), exactly ``edits`` (``{path under .aew: new bytes}``), written only
    once the operator has confirmed them, adopted as ``only`` those files, and put back if the adoption fails.
    ``lines`` is what that command adds to the prompt, above the files."""
    from aew import operator
    from aew.engine import approval
    from aew.switch_offer import restore

    require_here(command)
    offer = engine.manifest_offer()
    files: dict[str, dict[str, Any]] = offer["files"]
    if edits is not None:
        if offer["first_pin"]:  # nothing to diff against, and `only=` never pins a project's files for the first time
            raise IllegalTransition(
                f"this project's policy files were never pinned, so `{command}` cannot adopt its change alone. Review "
                f"them and run `{MANIFEST_COMMAND} --reason <reason>` first, which pins them; then run `{command}` "
                "again", reason="never_pinned", files=sorted(files))
        if files:  # `only=` adopts the command's files alone, so anything else that drifted is the operator's first
            raise IllegalTransition(
                f"{', '.join(f'.aew/{rel}' for rel in files)} differ from their pins: `{command}` adopts only the "
                f"files it writes. Review those and run `{MANIFEST_COMMAND} --reason <reason>` first, or put them back",
                reason="other_files_changed", changed=sorted(files))
        shown = {rel: (offer["pins"].get(rel), raw) for rel, raw in edits.items()}
    else:
        if not files:
            raise IllegalTransition("project.yaml and the policy files match their pins; nothing to adopt")
        shown = {}
        for rel, f in files.items():
            path = engine.aew_root / rel
            raw = path.read_bytes() if path.is_file() else None
            approval.compare("manifest.adopt", rel, f["now"], sha256_bytes(raw) if raw is not None else None,
                             next_step=f"Run `{command}` again: the file changed while it was read.")
            shown[rel] = (f["pinned"], raw)
    binding = {rel: sha256_bytes(raw) if raw is not None else None for rel, (_, raw) in shown.items()}
    text = [f"Project '{engine.project_id}': ADOPT as YOUR decision: project settings",
            f"  reason : {reason}", *lines]
    for rel, (pinned, raw) in sorted(shown.items()):
        text += _file_lines(engine, rel, pinned, binding[rel], raw, offer["first_pin"])
    text.append(SEAT_LINE)
    authorization = operator.confirm(text, purpose="the project's pinned settings (the files above)",
                                     code_because=code_because())
    if edits is None:
        return engine.manifest_adopt(reason=reason, authorization=authorization, binding=binding)
    root = engine.aew_root
    kept = {rel: (root / rel).read_bytes() if (root / rel).exists() else None for rel in edits}
    try:
        for rel, new in edits.items():
            atomic_write(root / rel, new)
        return engine.manifest_adopt(reason=reason, authorization=authorization, only=sorted(edits), binding=binding)
    except BaseException:
        restore(root, edits, kept)
        raise


def decide_authority(engine: Any, *, action: str, candidate: str, klass: str | None = None, reason: str | None = None,
                     binding: str | None = None) -> dict[str, Any]:
    """`aew authority accept` or `reject` as the operator's own decision at their terminal (rules 1, 3 and 4): the
    candidate's path, kind and digest are shown, and the commit compares the digest shown (E327)."""
    from aew import operator
    from aew.errors import NotFound

    command = f"aew authority {action}"
    require_here(command)
    subject = engine.authority_candidate(candidate)
    if action == "accept" and subject["kind"] == "file, missing":
        raise NotFound(f"authority candidate file {subject['path']} is missing. "
                       f"The operator can reject it with `aew authority reject {candidate}`.", path=subject["path"])
    summary = f"{action} {subject['path']} ({subject['kind']}, SHA-256 {subject['digest']})"
    if action == "accept":
        summary += f" as {klass} authority"
    text = [f"Project '{engine.project_id}': RECORD as YOUR decision: {summary}",
            *([f"  reason : {reason}"] if reason else []),
            "No Lead credential is used, and the Lead seat stays with its holder."]
    authorization = operator.confirm(text, purpose="the project's authority sources",
                                     code_because=AUTHORITY_CODE_ALWAYS or code_because())
    args: dict[str, Any] = {"candidate_id": candidate, "decided_by": "operator", "reason": reason,
                            "binding": binding if binding is not None else subject["digest"],
                            "authorization": authorization}
    if action == "accept":
        return engine.authority_accept(klass=klass, **args)
    return engine.authority_reject(**args)

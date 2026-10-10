"""Coordination messages in the engine: the store, identity, idempotency, replies, refs and the switch (register F9,
F9-A MS1; ADR-0017; F9-A plan v4 D-1 to D-12, D-15, D-31, D-32).

**What a message is.** Lead-worker coordination: knowledge moved between the current Lead generation and one active
role invocation, never project state (F9 invariant 1; F9-A1 §11). Recording one takes the control lock and commits
nothing (D-4), as ``submit`` does: the revision does not move, so neither a Lead message nor a worker reply makes a
Lead's ``expect_rev`` stale. No gate, transition, dispatch or evidence path reads a message.

**The thread.** One append-only JSONL file per invocation, ``.aew/work/<T>/coordination/<INV>.jsonl`` (D-1, D-3),
outside control state and every run directory. Each line is canonical JSON with ``h = sha256(previous h || the line
without h)``, a chain per thread from a genesis hash of the thread's id. A writer, under the control lock, repairs a
torn final line before it appends; a lock-free reader reads complete lines only and never repairs. Creating a thread
syncs its directory, and the project's first thread is preceded by the project marker (D-31).

**Identity and idempotency.** ``MSG-<INV>-<n>`` is the thread's own sequence (D-2). An idempotency id is scoped to
(sender, thread), the sender carrying the Lead generation (D-8): a retry returns the existing message, the same id
with other content is refused, and an omitted id is derived from the content, so a verbatim retry after a lost response
returns the original.

**The switch.** ``coordination.messaging`` in the execution policy, read from the adopted bytes only (D-15): absent,
``disabled``, an unadopted edit or an unreadable policy all mean off, and off records nothing and creates nothing.

Later slices add sealing (MS2), the Lead's typed tool (MS3), the worker's bridge operations (MS4), delivery (MS5) and
the Lead's attention (MS6). This module has no surface: nothing advertises it while messaging is off.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from aew import util
from aew.coordination import layout as L
from aew.engine import outbox
from aew.engine.authority import require_invocation, require_lead
from aew.engine.base import POLICY_PINS, V2, Kernel
from aew.engine.ports import ArchivePort
from aew.errors import (
    CoordinationLimit,
    IdempotencyConflict,
    IllegalTransition,
    IntegrityError,
    LeadInboxFull,
    MessagingDisabled,
    MigrationRequired,
    NotAWorker,
    NotFound,
    RecipientIndependent,
    RefOutOfScope,
    RefUnknown,
    ReplyNotInThread,
    StaleRevision,
    UsageError,
    ValidationFailed,
)
from aew.harness import contract as K
from aew.history.manifest import canonical_json
from aew.knowledge.manifest import MANIFEST
from aew.policy import execution as X
from aew.schemas import validate
from aew.util import load_yaml, parse_frontmatter, sha256_bytes, utc_now

# A confirmer's scope (F4 S7, not built yet): it never receives Lead text (D-34).
CONFIRMER_SCOPE = "revision"

_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TICKET = re.compile(r"^(T-[0-9]+)(?:@r([1-9][0-9]*))?$")
_FINDING_ID = re.compile(r"^\S{1,128}$")
_DECISION_ID = re.compile(r"^D-[0-9]+$")
_LINES = re.compile(r"#L([1-9][0-9]*)(?:-L([1-9][0-9]*))?$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------------------------- the switch (D-15)


def messaging_switch(aew_root: Path, state: dict[str, Any]) -> tuple[str, str | None]:
    """``(switch, reason)``: ``("enabled", None)`` only when ``state`` pins the manifest and the policy files,
    ``project.yaml`` matches its pin, the execution policy it names matches its pin, and that adopted policy sets
    ``coordination.messaging: enabled`` (D-15: only the operator's ``manifest adopt`` turns it on). Otherwise
    ``disabled``, with ``switched_off`` (absent or ``disabled``), ``not_adopted`` (no pins, or a file that differs from
    its pin: an edit nobody adopted reads as off) or ``unreadable``. It never raises: whatever went wrong, it is off.

    ``state`` is the control state the caller holds (a writer's session, or a lock-free reader's committed view), so the
    pins checked are the ones the caller's decision is made under."""
    try:
        pins, manifest_pin = state.get(POLICY_PINS), state.get("manifest_sha256")
        if not isinstance(pins, dict) or not isinstance(manifest_pin, str):
            return X.MESSAGING_DISABLED, "not_adopted"
        raw_manifest = (aew_root / MANIFEST).read_bytes()
        if sha256_bytes(raw_manifest) != manifest_pin:
            return X.MESSAGING_DISABLED, "not_adopted"
        manifest = load_yaml(raw_manifest.decode("utf-8"), source=MANIFEST)
        rel = X.policy_path(aew_root, manifest).relative_to(aew_root).as_posix()  # the key of its pin
        path = aew_root / rel
        raw = path.read_bytes() if path.is_file() else None
        if (sha256_bytes(raw) if raw is not None else None) != pins.get(rel, "<not pinned>"):
            return X.MESSAGING_DISABLED, "not_adopted"
        if raw is None:
            return X.MESSAGING_DISABLED, "switched_off"
        switch = X.messaging(X.parse(raw, source=rel))
        return switch, None if switch == X.MESSAGING_ENABLED else "switched_off"
    except Exception:  # fail closed by contract: an unreadable or invalid policy never turns messaging on
        return X.MESSAGING_DISABLED, "unreadable"


# ---------------------------------------------------------------------------------------------- the thread (D-3)


def genesis(invocation: str) -> str:
    return hashlib.sha256(f"{L.THREAD_GENESIS}:{invocation}".encode()).hexdigest()


def chained(previous: str, body: bytes) -> str:
    return hashlib.sha256(bytes.fromhex(previous) + body).hexdigest()


@dataclass
class Thread:
    """A thread as its complete lines say, chain-verified."""

    invocation: str
    work_unit: str
    rel: str
    exists: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    head: str = ""
    lines: int = 0
    complete: int = 0  # bytes of complete lines
    torn: int = 0  # bytes after the last newline: an append a crash cut short

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {m["id"]: m for m in self.messages}


def read_thread(aew_root: Path, work_unit: str, invocation: str) -> Thread:
    """The thread's complete lines, each checked against the chain; a torn final line is ignored, never repaired (a
    reader holds no lock). A line that breaks the chain, is not canonical or is not a known line type is an integrity
    failure: its text is never returned (D-16's rule for hot threads, applied from the first slice)."""
    rel = L.thread_rel(work_unit, invocation)
    thread = Thread(invocation, work_unit, rel, head=genesis(invocation))
    try:
        raw = (aew_root / rel).read_bytes()
    except FileNotFoundError:
        return thread
    thread.exists = True
    end = raw.rfind(b"\n") + 1
    thread.complete, thread.torn = end, len(raw) - end
    for n, line in enumerate(raw[:end].split(b"\n")[:-1], 1):
        parsed = _chained_line(line, thread.head)
        if parsed is None:
            raise IntegrityError(f"{rel}: line {n} breaks the thread's hash chain (damaged or edited outside AEW); its "
                                 "text is not shown", thread=invocation, line=n, reason="chain")
        entry, thread.head = parsed
        thread.lines = n
        kind = entry.get("type")
        if kind == L.MESSAGE_LINE and isinstance(entry.get("message"), dict):
            record = entry["message"]
            validate("coordination-message", record, source=f"{rel}:{n}")
            seq = len(thread.messages) + 1
            if record["thread"] != invocation or record["seq"] != seq or record["id"] != L.message_id(invocation, seq):
                raise IntegrityError(f"{rel}: line {n} is not message {seq} of {invocation}'s thread",
                                     thread=invocation, line=n, reason="sequence")
            thread.messages.append(record)
        elif kind == L.FACT_LINE and isinstance(entry.get("fact"), dict) \
                and isinstance(entry["fact"].get("kind"), str) and isinstance(entry["fact"].get("message"), str):
            thread.facts.append(entry["fact"])
        else:
            raise IntegrityError(f"{rel}: line {n} is not a message or a fact", thread=invocation, line=n,
                                 reason="line_type")
    return thread


def _chained_line(line: bytes, previous: str) -> tuple[dict[str, Any], str] | None:
    """A line's entry (without ``h``) and its hash, or None unless the line is canonical JSON whose ``h`` chains from
    ``previous``."""
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict):
        return None
    h = entry.pop("h", None)
    if not isinstance(h, str):
        return None
    try:
        ok = canonical_json({**entry, "h": h}) == line and chained(previous, canonical_json(entry)) == h
    except (ValueError, TypeError):
        return None
    return (entry, h) if ok else None


def _append_line(path: Path, line: bytes) -> None:
    """Append one complete line and sync it. Only a writer holding the control lock calls this."""
    with open(path, "ab") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def _truncate(path: Path, size: int) -> None:
    """Drop a torn final line: only a writer under the control lock repairs (F13b)."""
    with open(path, "r+b") as fh:
        fh.truncate(size)
        fh.flush()
        os.fsync(fh.fileno())


def facts_of(thread: Thread, message: str) -> list[dict[str, Any]]:
    """A message's communication facts (D-13): ``RECORDED`` and the reply facts are derived from the thread, the rest
    are the fact lines naming it. No gate, transition or dispatch reads them."""
    out: list[dict[str, Any]] = [{"kind": "RECORDED"}]
    out += [f for f in thread.facts if f["message"] == message]
    replies = [m for m in thread.messages if m["in_reply_to"] == message]
    if any(m["kind"] == L.ACKNOWLEDGEMENT for m in replies):
        out.append({"kind": "ACKNOWLEDGED"})
    if replies:
        out.append({"kind": "REPLIED_TO", "by": [m["id"] for m in replies]})
    return out


def _is_lead(message: dict[str, Any]) -> bool:
    return message["sender"].startswith("lead:")


def _answered(thread: Thread) -> set[str]:
    """Messages the other party has evidently had: a fact says delivered, or the other party replied to it."""
    out = {f["message"] for f in thread.facts if f["kind"] == L.DELIVERED}
    by_id = thread.by_id()
    for m in thread.messages:
        target = by_id.get(m["in_reply_to"] or "")
        if target is not None and _is_lead(target) != _is_lead(m):
            out.add(target["id"])
    return out


def derived_idempotency_id(sender: str, thread: str, in_reply_to: str | None, kind: str, body: str,
                           refs: list[str]) -> str:
    """D-8: the canonical JSON array of the content, so no two contents share bytes across a field boundary."""
    return L.DERIVED_ID_PREFIX + hashlib.sha256(
        canonical_json([sender, thread, in_reply_to, kind, body, refs])).hexdigest()


# ---------------------------------------------------------------------------------------------- the collaborator


@dataclass
class _Draft:
    """A message as submitted, its shape checked: what idempotency compares and the record is built from."""

    kind: str
    body: str
    refs: list[str]
    in_reply_to: str | None
    idempotency_id: str | None
    channel: str


class Coordination:
    """Recording and reading coordination messages (F9-A MS1). No surface calls it yet; while messaging is off every
    record is refused before anything is read or written."""

    def __init__(self, k: Kernel, *, archive: ArchivePort) -> None:
        self.k = k
        self.archive = archive

    # ------------------------------------------------------------------ records

    def message_record_lead(self, *, token: str, expect_rev: int | None, to: str, body: str, kind: str | None = None,
                            in_reply_to: str | None = None, refs: list[str] | None = None,
                            idempotency_id: str | None = None, channel: str = "cli") -> dict[str, Any]:
        """Record a Lead message to an active worker (D-4, D-17's engine half). ``expect_rev`` is the control revision
        the Lead read, checked under the lock before anything else; recording moves no revision, so the same
        ``expect_rev`` stays valid for the Lead's next send or stage."""
        draft = self._draft(kind or L.LEAD_DEFAULT_KIND, body, refs, in_reply_to, idempotency_id, channel)
        if not L.ANY_INVOCATION_RE.match(to or ""):
            raise UsageError(f"a message goes to one invocation (INV-n), not {to!r}")
        with self.k.store.session() as s:
            state = s.state
            actor = require_lead(state, token, archived=self.archive.archived_credential)
            if expect_rev is None:
                raise StaleRevision("a Lead message must state the revision it was written against (--expect-rev)",
                                    current=s.revision)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected control revision {expect_rev}, current is {s.revision}: read again, "
                                    "then decide whether the message still holds", expected=expect_rev,
                                    current=s.revision)
            self._require_recordable(state)
            inv = self._invocation(state, to)
            thread = read_thread(self.k.aew_root, inv["work_unit"], to)
            sender = L.lead_party(actor["generation"])
            found = self._existing(thread, sender, draft)
            if found is not None:  # before the recipient check: a retry after the recipient ended returns the original
                return found | {"revision": s.revision}
            self._require_recipient(state, to)
            by_id = thread.by_id()
            if draft.in_reply_to is not None and draft.in_reply_to not in by_id:
                raise ReplyNotInThread(f"{draft.in_reply_to} is not a message of {to}'s thread", reason="unknown",
                                       in_reply_to=draft.in_reply_to, thread=to)
            self._require_room(thread)
            answered = _answered(thread)
            pending = [m["id"] for m in thread.messages if _is_lead(m) and m["id"] not in answered]
            if len(pending) >= L.MAX_UNDELIVERED_LEAD:
                raise CoordinationLimit(f"{to}'s thread already holds {len(pending)} Lead messages its worker has not "
                                        "had; wait for a reply or a delivery before sending more",
                                        bound="undelivered_lead_messages", limit=L.MAX_UNDELIVERED_LEAD,
                                        pending=pending)
            self._check_refs(state, thread, draft.refs, worker=None)
            record = self._record(thread, inv, draft, sender=sender, recipient=L.invocation_party(to),
                                  checked_rev=expect_rev)
            self._write(thread, record)
            return self._result(thread, record, duplicate=False) | {"revision": s.revision}

    def message_record_worker(self, *, invocation_token: str, in_reply_to: str | None, body: str,
                              kind: str | None = None, refs: list[str] | None = None,
                              idempotency_id: str | None = None, channel: str = "run_bridge") -> dict[str, Any]:
        """Record a worker's reply to a Lead message on its own thread (D-10: F9-A's worker direction is a reply). It
        runs with the invocation's own credential, addresses only the Lead, and grants nothing."""
        draft = self._draft(kind or L.WORKER_DEFAULT_KIND, body, refs, in_reply_to, idempotency_id, channel)
        if draft.in_reply_to is None:
            raise ReplyNotInThread("a worker's message is a reply: name the Lead message it answers (in_reply_to)",
                                   reason="missing")
        with self.k.store.session() as s:
            state = s.state
            inv_id, inv, _ = require_invocation(state, invocation_token, None,
                                                archived=self.archive.archived_credential)
            self._require_recordable(state)
            thread = read_thread(self.k.aew_root, inv["work_unit"], inv_id)
            sender = L.invocation_party(inv_id)
            found = self._existing(thread, sender, draft)
            if found is not None:
                return found | {"revision": s.revision}
            target = thread.by_id().get(draft.in_reply_to)
            if target is None:
                raise ReplyNotInThread(f"{draft.in_reply_to} is not a message of your thread ({inv_id})",
                                       reason="unknown", in_reply_to=draft.in_reply_to, thread=inv_id)
            if not _is_lead(target):
                raise ReplyNotInThread(f"{draft.in_reply_to} is your own message: reply to a Lead message",
                                       reason="not_a_lead_message", in_reply_to=draft.in_reply_to, thread=inv_id)
            self._require_room(thread)
            answered = _answered(thread)
            unseen = [m["id"] for m in thread.messages if not _is_lead(m) and m["id"] not in answered]
            if len(unseen) >= L.MAX_UNSEEN_WORKER:
                raise LeadInboxFull(f"your thread already holds {len(unseen)} messages the Lead has not seen; wait for "
                                    "the Lead before sending more", bound="unseen_worker_messages",
                                    limit=L.MAX_UNSEEN_WORKER, unseen=len(unseen))
            self._check_refs(state, thread, draft.refs, worker=inv_id)
            record = self._record(thread, inv, draft, sender=sender,
                                  recipient=L.lead_party(state["lead"]["generation"]), checked_rev=s.revision)
            self._write(thread, record)
            return self._result(thread, record, duplicate=False) | {"revision": s.revision}

    # ------------------------------------------------------------------ reads

    def message_thread(self, invocation: str) -> dict[str, Any]:
        """An invocation's thread, lock-free (a reader never repairs): its complete, chain-verified messages, each with
        its facts. Reading creates nothing; an invocation with no thread has no messages."""
        if not L.ANY_INVOCATION_RE.match(invocation or ""):
            raise UsageError(f"a thread is named by its invocation (INV-n), not {invocation!r}")
        state = self.k.store.read_committed()
        inv = self._invocation(state, invocation)
        thread = read_thread(self.k.aew_root, inv["work_unit"], invocation)
        return {"thread": invocation, "work_unit": inv["work_unit"], "lines": thread.lines, "head": thread.head,
                "messages": [m | {"facts": facts_of(thread, m["id"])} for m in thread.messages]}

    # ------------------------------------------------------------------ checks

    @staticmethod
    def _draft(kind: str, body: str, refs: list[str] | None, in_reply_to: str | None, idempotency_id: str | None,
               channel: str) -> _Draft:
        """The submitted message's shape and its content bounds (D-7, D-8, D-11, D-12): checked before anything is
        read, so a malformed message costs no lock."""
        if channel not in L.CHANNELS:
            raise UsageError(f"unknown channel {channel!r}", allowed=list(L.CHANNELS))
        if kind not in L.KINDS:
            raise ValidationFailed(f"unknown message kind {kind!r}", reason="kind", allowed=list(L.KINDS))
        if not isinstance(body, str) or not body.strip():
            raise ValidationFailed("a message needs a body", reason="empty_body")
        if len(body) > L.MAX_BODY_CHARS:
            raise CoordinationLimit(f"a message body is at most {L.MAX_BODY_CHARS} characters; this one has "
                                    f"{len(body)}. Reference the material instead (evidence:, source:, ticket:)",
                                    bound="body_chars", limit=L.MAX_BODY_CHARS, actual=len(body))
        if K.CREDENTIAL_RE.search(body):
            raise CoordinationLimit("a message never carries an AEW credential (its harness would persist it)",
                                    bound="credential")
        refs = list(refs or [])
        if len(refs) > L.MAX_REFS:
            raise CoordinationLimit(f"a message carries at most {L.MAX_REFS} refs; this one has {len(refs)}",
                                    bound="refs", limit=L.MAX_REFS, actual=len(refs))
        for ref in refs:
            if not isinstance(ref, str) or len(ref) > L.MAX_REF_CHARS:
                raise CoordinationLimit(f"a ref is a string of at most {L.MAX_REF_CHARS} characters",
                                        bound="ref_chars", limit=L.MAX_REF_CHARS)
            if K.CREDENTIAL_RE.search(ref):
                raise CoordinationLimit("a ref never carries an AEW credential", bound="credential")
        if in_reply_to is not None and not L.MESSAGE_ID_RE.match(in_reply_to):
            raise ReplyNotInThread(f"in_reply_to {in_reply_to!r} is not a message id (MSG-INV-n-k)", reason="unknown",
                                   in_reply_to=in_reply_to)
        if idempotency_id is not None and not L.IDEMPOTENCY_ID_RE.match(idempotency_id):
            raise ValidationFailed("an idempotency id is 1 to 64 characters of letters, digits and . _ : -",
                                   reason="idempotency_id")
        return _Draft(kind, body, refs, in_reply_to, idempotency_id, channel)

    def _require_recordable(self, state: dict[str, Any]) -> None:
        """A v2 project with messaging switched on in its adopted policy (G1, D-15). Nothing has been read or written
        when either refuses."""
        if state.get("schema") != V2:
            raise MigrationRequired("this project's control state is v1: messages are recorded on v2 projects only; "
                                    "the operator runs `aew migrate --expect-rev N` first",
                                    schema=state.get("schema"), next_action="aew migrate --expect-rev N")
        switch, reason = messaging_switch(self.k.aew_root, state)
        if switch != X.MESSAGING_ENABLED:
            raise MessagingDisabled(
                "coordination messaging is off for this project: the adopted execution policy does not set "
                "`coordination.messaging: enabled`" + (" (the policy differs from what was adopted, so it reads as "
                                                       "off until the operator adopts it)"
                                                       if reason == "not_adopted" else ""), reason=reason)

    def _invocation(self, state: dict[str, Any], inv_id: str) -> dict[str, Any]:
        """The invocation a thread belongs to, hot or archived with its finished work (a thread outlives it)."""
        inv = state["invocations"].get(inv_id)
        if inv is None and state.get("schema") == V2:
            inv = self.archive.archived_invocation(state, inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        return inv

    @staticmethod
    def _require_recipient(state: dict[str, Any], inv_id: str) -> None:
        """An active, role-bearing worker (D-4 step 4, D-17): never an engine custody invocation, never an independent
        confirmer."""
        inv = state["invocations"].get(inv_id)
        if inv is not None and (inv.get("kind") or not inv.get("role")):
            raise NotAWorker(f"{inv_id} is an engine custody invocation ({inv.get('kind')}), not a worker: it runs no "
                             "model and receives no message", invocation=inv_id, kind=inv.get("kind"))
        if inv is not None and inv.get("scope") == CONFIRMER_SCOPE:
            raise RecipientIndependent(f"{inv_id} is an independent confirmer: it never receives Lead text",
                                       invocation=inv_id)
        if inv is None or inv["status"] != "active":
            status = inv["status"] if inv is not None else "archived with its finished work"
            raise IllegalTransition(f"{inv_id} is {status}: messages go to active workers only",
                                    reason="recipient_not_active", invocation=inv_id, status=status)

    @staticmethod
    def _require_room(thread: Thread) -> None:
        if len(thread.messages) >= L.MAX_THREAD_MESSAGES:
            raise CoordinationLimit(f"{thread.invocation}'s thread holds {len(thread.messages)} messages, its bound",
                                    bound="thread_messages", limit=L.MAX_THREAD_MESSAGES)

    def _existing(self, thread: Thread, sender: str, draft: _Draft) -> dict[str, Any] | None:
        """D-8: the message this sender already recorded under the same idempotency id on this thread (the result of a
        retry), or None. The same id with other content is refused."""
        key = draft.idempotency_id or derived_idempotency_id(sender, thread.invocation, draft.in_reply_to,
                                                             draft.kind, draft.body, draft.refs)
        match = next((m for m in thread.messages if m["sender"] == sender and m["idempotency_id"] == key), None)
        if match is None:
            return None
        content = {"kind": draft.kind, "body": draft.body, "refs": draft.refs, "in_reply_to": draft.in_reply_to}
        differs = sorted(f for f, v in content.items() if match[f] != v)
        if differs:
            raise IdempotencyConflict(f"idempotency id {key} already names {match['id']} with other content "
                                      f"({', '.join(differs)}): a retry repeats the original exactly; a new message "
                                      "needs a new id", existing=match["id"], fields=differs)
        out = self._result(thread, match, duplicate=True)
        if draft.idempotency_id is None:
            out["note"] = ("this repeats a recorded message verbatim, so the original is returned; to record the same "
                           "text again on purpose, pass an explicit idempotency_id")
        return out

    def _check_refs(self, state: dict[str, Any], thread: Thread, refs: list[str], *, worker: str | None) -> None:
        """D-12: each ref is ``kind:value``. AEW ids must exist; a ``source`` is checked for its syntax only. A worker
        (``worker`` is its invocation) may cite only its own unit, thread, Ticket and runs."""
        for ref in refs:
            kind, sep, value = ref.partition(":")
            if not sep or kind not in L.REF_KINDS or not value:
                raise RefUnknown(f"ref {ref!r} is not kind:value with a kind of {', '.join(L.REF_KINDS)}",
                                 ref=ref, reason="malformed")
            check = {"evidence": self._ref_evidence, "ticket": self._ref_ticket, "finding": self._ref_finding,
                     "message": self._ref_message, "run": self._ref_run, "decision": self._ref_decision,
                     "source": self._ref_source}[kind]
            check(state, thread, ref, value, worker)

    def _ref_evidence(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        if not _EVIDENCE_ID.match(value):
            raise RefUnknown(f"ref {ref!r} is not an evidence id", ref=ref, reason="malformed")
        if worker is not None and (self.k.aew_root / "evidence" / thread.work_unit / f"{value}.md").is_file():
            return
        found = any((self.k.aew_root / "evidence").glob(f"*/{value}.md"))
        if not found:
            raise RefUnknown(f"ref {ref!r}: no evidence {value}", ref=ref, reason="unknown")
        if worker is not None:
            raise RefOutOfScope(f"ref {ref!r} is evidence of another unit: cite your own unit's", ref=ref)

    def _ref_ticket(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        m = _TICKET.match(value)
        if not m:
            raise RefUnknown(f"ref {ref!r} is not T-n or T-n@rN", ref=ref, reason="malformed")
        work_id, revision = m.groups()
        if self._unit(state, work_id) is None:
            raise RefUnknown(f"ref {ref!r}: no Ticket {work_id}", ref=ref, reason="unknown")
        if worker is not None and work_id != thread.work_unit:
            raise RefOutOfScope(f"ref {ref!r} names another Ticket: cite your own ({thread.work_unit})", ref=ref)
        if revision is not None:
            # Ticket revisions are F4's (TR-2); no unit records one until F4 S2c binds them (plan D-9), so a revision
            # cannot be shown to exist yet and is refused, never accepted unchecked.
            raise RefUnknown(f"ref {ref!r}: this project records no Ticket revisions; cite {work_id}", ref=ref,
                             reason="no_ticket_revisions")

    def _ref_finding(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        """A finding id names a finding of the thread's own unit, as the Lead and reviewers name them."""
        unit = self._unit(state, thread.work_unit) if _FINDING_ID.match(value) else None
        if unit is None or value not in {f.get("id") for f in unit.get("findings") or []}:
            raise RefUnknown(f"ref {ref!r}: {thread.work_unit} has no finding {value}", ref=ref, reason="unknown")

    def _ref_message(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        m = L.MESSAGE_ID_RE.match(value)
        if not m:
            raise RefUnknown(f"ref {ref!r} is not a message id (MSG-INV-n-k)", ref=ref, reason="malformed")
        owner = m.group(1)
        if owner == thread.invocation:
            if value not in thread.by_id():
                raise RefUnknown(f"ref {ref!r}: no such message in this thread", ref=ref, reason="unknown")
            return
        if worker is not None:
            raise RefOutOfScope(f"ref {ref!r} is in another invocation's thread: cite your own thread", ref=ref)
        try:
            inv = self._invocation(state, owner)
        except NotFound:
            raise RefUnknown(f"ref {ref!r}: no invocation {owner}", ref=ref, reason="unknown") from None
        if value not in read_thread(self.k.aew_root, inv["work_unit"], owner).by_id():
            raise RefUnknown(f"ref {ref!r}: no such message", ref=ref, reason="unknown")

    def _ref_run(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        owner = K.invocation_of_run(value)
        if owner is None:
            raise RefUnknown(f"ref {ref!r} is not a run id (R-INV-n-k)", ref=ref, reason="malformed")
        if worker is not None and owner != worker:
            raise RefOutOfScope(f"ref {ref!r} is another invocation's run: cite your own runs", ref=ref)
        try:
            inv = self._invocation(state, owner)
        except NotFound:
            inv = {}
        if value not in {r.get("run") for r in inv.get("runs") or []}:
            raise RefUnknown(f"ref {ref!r}: no run {value}", ref=ref, reason="unknown")

    def _ref_decision(self, state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        path = self.k.aew_root / "decisions" / f"{value}.md"
        if not _DECISION_ID.match(value) or not path.is_file():
            raise RefUnknown(f"ref {ref!r}: no decision {value}", ref=ref, reason="unknown")
        if worker is not None:
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"), source=str(path))
            if meta.get("work_unit") != thread.work_unit:
                raise RefOutOfScope(f"ref {ref!r} is not a decision about your unit ({thread.work_unit})", ref=ref)

    @staticmethod
    def _ref_source(state: dict[str, Any], thread: Thread, ref: str, value: str, worker: str | None) -> None:
        """A workspace-relative path with an optional ``#Ln`` or ``#Ln-Lm``: syntax only, never resolved (D-12)."""
        path, lines = value, _LINES.search(value)
        if lines:
            path = value[:lines.start()]
            first, last = int(lines.group(1)), int(lines.group(2) or lines.group(1))
            if last < first:
                raise RefUnknown(f"ref {ref!r}: a line range runs forward (#Ln-Lm, n <= m)", ref=ref,
                                 reason="malformed")
        parts = PurePosixPath(path).parts
        if (not path or "\\" in path or _CONTROL.search(path) or path.startswith("/") or re.match(r"^[A-Za-z]:", path)
                or ".." in parts or "#" in path):
            raise RefUnknown(f"ref {ref!r}: a source is a workspace-relative path, optionally with #Ln or #Ln-Lm",
                             ref=ref, reason="malformed")

    def _unit(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        unit = state["work"].get(work_id)
        if unit is None and state.get("schema") == V2:
            unit = self.archive.archived_unit(state, work_id)
        return unit

    # ------------------------------------------------------------------ writing

    @staticmethod
    def _record(thread: Thread, inv: dict[str, Any], draft: _Draft, *, sender: str, recipient: str,
                checked_rev: int) -> dict[str, Any]:
        seq = len(thread.messages) + 1
        runs = inv.get("runs") or []
        return {
            "schema": L.MESSAGE_SCHEMA, "id": L.message_id(thread.invocation, seq), "thread": thread.invocation,
            "seq": seq, "sender": sender, "recipient": recipient, "work_unit": thread.work_unit,
            # D-9: on an F4-enabled project, the revision the invocation records (F4 S2c, TR-2). No project records
            # one before S2c, so it is null; whichever of MS1 and S2c merges second binds it and adds the test.
            "ticket_revision": None,
            "run": runs[-1]["run"] if runs else None, "channel": draft.channel, "in_reply_to": draft.in_reply_to,
            "idempotency_id": draft.idempotency_id or derived_idempotency_id(
                sender, thread.invocation, draft.in_reply_to, draft.kind, draft.body, draft.refs),
            "kind": draft.kind, "body": draft.body, "refs": draft.refs, "created_at": utc_now(),
            "checked_rev": checked_rev,
        }

    def _write(self, thread: Thread, record: dict[str, Any]) -> None:
        """Append ``record`` to its thread under the control lock the caller holds: the project marker first if there
        is none (D-31), a torn tail repaired, the line synced, a new thread's directory synced (F13c), then the advisory
        wake (D-5). Nothing is committed."""
        validate("coordination-message", record, source=thread.rel)
        envelope = {"type": L.MESSAGE_LINE, "message": record}
        line = canonical_json({**envelope, "h": chained(thread.head, canonical_json(envelope))}) + b"\n"
        root = self.k.aew_root
        path = root / thread.rel
        self._ensure_marker(thread.invocation)
        if thread.torn:
            _truncate(path, thread.complete)
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True)
            util.fsync_dir(path.parent.parent)
        _append_line(path, line)
        if not thread.exists:
            util.fsync_dir(path.parent)
        thread.messages.append(record)
        outbox.bump_wake(root)

    def _ensure_marker(self, invocation: str) -> None:
        """D-31: the project-scoped "a thread exists" marker, written create-exclusive and synced, with its directory
        and ``.aew/``, before the thread file is created. A crash between the two leaves a marker with no thread, which
        only makes the reads show an empty section. Written again only if something removed it."""
        path = self.k.aew_root / L.MARKER_REL
        if path.is_file():
            return
        marker = {"schema": L.MARKER_SCHEMA, "created_at": utc_now(), "first_thread": invocation}
        validate("coordination-marker", marker, source=L.MARKER_REL)
        util.create_exclusive(path, util.dump_yaml(marker))  # syncs the file, then .aew/coordination/
        util.fsync_dir(self.k.aew_root)  # .aew/ gained the coordination directory

    @staticmethod
    def _result(thread: Thread, record: dict[str, Any], *, duplicate: bool) -> dict[str, Any]:
        return {"ok": True, "message": record, "thread": thread.invocation, "duplicate": duplicate,
                "facts": facts_of(thread, record["id"])}

"""Live run usage, ``aew/usage-live/v1``: one bounded sample shape and one meter for every OpenCode server (F25 for
M4-H, slice L1; the cost and usage ledger design v0.2; Q7 v0.3.1 §16 and §9.2).

Everything here is non-authoritative local telemetry. The meter measures; it never terminates, charges a cap or
computes a guard (that is the M4-H evaluator's, F19). A sample carries R1's fields from :func:`usage.normalize`, so the
same tokens price the same whether they come from a run's live file or an evaluator-owned session.

**One poll** reads the server's own REST API, through the pinned 2.0.18 operations only (``session.list``,
``session.active``, ``session.message.list`` with ``type=assistant`` and ``type=compaction``, ``server.info``), and
relies on no event payload:

1. Every session on the server, with no filter, paged to the end in ascending order. The server is private to the run
   or the evaluator. At most ``SESSION_PAGES`` pages and ``MAX_SESSIONS`` tracked sessions; past either the source is
   ``truncated`` (unknown).
2. New messages of each session whose totals moved, that is active, or whose reading is held or behind, from a saved
   ascending cursor. A message counts once, when it becomes terminal; counting stops at the first message that is not.
   2.0.18 answers a cursor whose anchor message is gone with an empty page, for good, and a revert deletes messages
   (P1(a), (d)): when the totals moved but the cursor's page is empty and its anchor is gone, the meter reads the
   session again from the start and skips what it counted already, by the last counted message's creation time.
3. The figure, per session and per category, recomputed every poll and never accumulated:
   ``max(high-water Session.Info totals, sum of counted messages)``. Any part of the totals on no counted message (a
   title call, a compaction whose message has not completed yet) is priced on the pinned model only when the caller
   proved the server pinned to it; otherwise it is a partition with no model, which never prices.

The facts this rests on are probe P1's, pinned with citations in ``tests/fixtures/opencode/live-usage-2.0.18.json``.
In short: a call's tokens appear only when it ends (its message gets ``time.completed`` and its tokens in the same
transaction as the session's totals); title and compaction usage reach the totals through ``session.usage.recorded``
(title usage is on no message; compaction usage is on its message too, recorded a moment later); a session's totals
cover that session only, never its children; nothing lowers them, but a fork copies its source's finished messages
into a new session whose totals start at zero, so a fork's copies (created before the fork) are never counted.

The meter's own state (cursors, high-water marks, per-model sums) is persisted at ``state_path`` and is not part of the
contract. A restarted meter carries it forward under a new ``epoch``. A decrease of a session's totals is recorded as
``integrity_pending`` once and as ``integrity`` when the next poll still sees it; it never lowers the figure.
"""

from __future__ import annotations

import copy
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew.harness import runlog
from aew.harness import usage as U
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable
from aew.util import atomic_write

SCHEMA = "aew/usage-live/v1"
STATE_SCHEMA = "aew/usage-live-state/v1"  # the meter's own file; not part of the contract
HARNESS = "opencode"

MAX_SAMPLE_BYTES = 4096        # §3.1: one source's sample, at its worst case (tests/unit/test_usage_live.py)
MAX_STATE_BYTES = 512 << 10    # §2.1 (R3-n2): past this the state is not kept and the source is `truncated`
MAX_SESSIONS = 256             # tracked sessions per server; a 257th makes the source `truncated`
SESSION_PAGE = 50              # the pinned session.list default page
SESSION_PAGES = 6              # at most 300 sessions listed per poll (R2 nit 1); a seventh page is `truncated`
MESSAGE_PAGE = 200             # the pinned session.message.list maximum
MESSAGE_PAGES = 1              # pages per message type per session per poll: the rest is read on the next poll
MAX_ID = 64                    # a session id, message id or source id the meter keeps; longer ones are not kept
MAX_CURSOR = 512               # an opaque cursor the meter keeps; a longer one is not kept (`truncated`)
MAX_VERSION = 32
MAX_EPOCH = 64
MAX_COUNT = U.MAX_COUNT

TYPES = ("assistant", "compaction")
STATES = ("live", "final", "server_gone")
PROMPT_STATES = ("unsent", "posting", "posted")
SOURCE_KINDS = ("run", "session")
CATEGORIES = U.CATEGORIES
NAMED = U.NAMED
NO_MODEL: tuple[str | None, str | None, str | None] = (None, None, None)


class MeterError(Exception):
    """A request the meter needed failed: no sample was taken."""


def _iso_ms(ts: float | None = None) -> str:
    moment = datetime.fromtimestamp(time.time() if ts is None else ts, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _obj(value: Any) -> Mapping[str, Any]:
    """A response object, or an empty one: a malformed reply is read as carrying nothing, never as a crash."""
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _zeros() -> dict[str, int]:
    return dict.fromkeys(CATEGORIES, 0)


def _add(into: dict[str, int], tokens: Mapping[str, int]) -> None:
    for cat in CATEGORIES:
        into[cat] = min(into.get(cat, 0) + int(tokens.get(cat, 0)), U.MAX_TOKENS)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value != value or value < 0:
        return None
    return float(value)


def _model_key(ref: Any) -> tuple[str | None, str | None, str | None]:
    """A message's ``Model.Ref`` as ``(provider, model, effort)``; OpenCode's ``default`` variant is no effort (as the
    adapter's ``_effective`` reads it). A missing or over-long id is no model: its tokens are left to the totals."""
    if not isinstance(ref, Mapping):
        return NO_MODEL
    provider = U.identifier(ref.get("providerID"), U.MAX_PROVIDER)
    model = U.identifier(ref.get("id"), U.MAX_MODEL)
    if provider is None or model is None:
        return NO_MODEL
    variant = ref.get("variant")
    effort = None if variant in (None, "", "default") else U.identifier(variant, U.MAX_EFFORT)
    return provider, model, effort


def _time(message: Mapping[str, Any], field: str) -> float | None:
    t = message.get("time")
    return _number(t.get(field)) if isinstance(t, Mapping) else None


def _empty_type() -> dict[str, Any]:
    # cursor: the opaque cursor of the page that holds the next message to count (None: the first ascending page);
    # anchor: the id of the message that cursor follows (2.0.18 returns an empty page once it is gone);
    # last/last_created: the last message passed, skipped when its page is read again; floor: after a revert deleted
    # it, messages created at or before this time were passed already and are skipped; n: messages counted;
    # held: counting stopped at a message still in progress; more: a full page was read, so more may follow;
    # by_model: [[provider, model, effort, {category: tokens}], ...], at most U.MAX_EFFECTIVE; cost: their cost.
    return {"cursor": None, "anchor": None, "last": None, "last_created": None, "floor": None, "n": 0,
            "held": False, "more": False, "by_model": [], "cost": 0.0}


def _empty_session() -> dict[str, Any]:
    return {"hw": _zeros(), "hw_cost": 0.0, "full": True, "model": None, "fork_after": None, "pending": False,
            "breached": False, "types": {t: _empty_type() for t in TYPES}}


def _empty_state() -> dict[str, Any]:
    return {"schema": STATE_SCHEMA, "truncated": False, "integrity": 0, "steps": 0, "compactions": 0, "retries": 0,
            "d_min_ms": None, "max_step": dict.fromkeys(NAMED, 0), "sessions": {}}


def _is_count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v


def _is_num(v: Any) -> bool:
    return _number(v) is not None


def _is_opt_str(v: Any, limit: int) -> bool:
    return v is None or (isinstance(v, str) and len(v) <= limit)


def _valid_type(t: Any) -> bool:
    if not isinstance(t, dict) or set(t) != set(_empty_type()):
        return False
    if not (_is_opt_str(t["cursor"], MAX_CURSOR) and _is_opt_str(t["anchor"], MAX_ID)
            and _is_opt_str(t["last"], MAX_ID) and _is_count(t["n"]) and _is_num(t["cost"])
            and isinstance(t["held"], bool) and isinstance(t["more"], bool)
            and all(v is None or _is_num(v) for v in (t["last_created"], t["floor"]))
            and isinstance(t["by_model"], list) and len(t["by_model"]) <= U.MAX_EFFECTIVE):
        return False
    return all(isinstance(e, list) and len(e) == 4 and all(_is_opt_str(x, U.MAX_MODEL) for x in e[:3])
               and _valid_tokens(e[3]) for e in t["by_model"])


def _valid_tokens(tokens: Any) -> bool:
    return isinstance(tokens, dict) and set(tokens) == set(CATEGORIES) and all(_is_count(v) for v in tokens.values())


def _valid_session(s: Any) -> bool:
    if not isinstance(s, dict) or set(s) != set(_empty_session()):
        return False
    model = s["model"]
    return (_valid_tokens(s["hw"]) and _is_num(s["hw_cost"]) and isinstance(s["full"], bool)
            and isinstance(s["pending"], bool) and isinstance(s["breached"], bool)
            and (s["fork_after"] is None or _is_num(s["fork_after"]))
            and (model is None or (isinstance(model, list) and len(model) == 2
                                   and all(_is_opt_str(x, U.MAX_MODEL) for x in model)))
            and isinstance(s["types"], dict) and set(s["types"]) == set(TYPES)
            and all(_valid_type(s["types"][t]) for t in TYPES))


def _valid_state(state: Any) -> bool:
    """The persisted state's whole shape: a file the meter did not write as it writes it is not trusted (m3)."""
    if not isinstance(state, dict) or set(state) != set(_empty_state()) or state["schema"] != STATE_SCHEMA:
        return False
    sessions = state["sessions"]
    max_step = state["max_step"]
    return (isinstance(state["truncated"], bool)
            and all(_is_count(state[k]) for k in ("integrity", "steps", "compactions", "retries"))
            and (state["d_min_ms"] is None or _is_num(state["d_min_ms"]))
            and isinstance(max_step, dict) and set(max_step) == set(NAMED)
            and all(_is_count(v) for v in max_step.values())
            and isinstance(sessions, dict) and len(sessions) <= MAX_SESSIONS
            and all(isinstance(k, str) and len(k) <= MAX_ID and _valid_session(v) for k, v in sessions.items()))


class Meter:
    """One source's live usage: a run's private server (``source.kind == "run"``) or an evaluator-owned server
    (``"session"``, its id the root session). ``poll()`` takes one sample; ``final()`` the last one."""

    def __init__(self, client: Any, *, source: Mapping[str, str], version: str,
                 semantics_table: Mapping[str, Mapping[str, str]], s_pot: int, k_assumed: int = 2,
                 state_path: Path, live_path: Path | None = None, request_timeout_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic, main_session: str | None = None,
                 pinned_model: Mapping[str, Any] | None = None) -> None:
        kind, sid = source.get("kind"), source.get("id")
        if kind not in SOURCE_KINDS or U.identifier(sid, MAX_ID) is None:
            raise ValueError(f"a live usage source is {{kind: run|session, id}} with an id of at most {MAX_ID} "
                             f"bytes, not {dict(source)!r}")
        if isinstance(s_pot, bool) or not isinstance(s_pot, int) or s_pot < 1 \
                or isinstance(k_assumed, bool) or not isinstance(k_assumed, int) or k_assumed < 1:
            raise ValueError("s_pot and k_assumed are positive integers (the plan's A2 and A3)")
        self.client = client  # may be bound later: a run's meter exists before its server does (L2)
        self.source = {"kind": str(kind), "id": str(sid)}
        self.version = str(version)
        self.semantics_table = semantics_table
        self.s_pot, self.k_assumed = s_pot, k_assumed
        self.state_path, self.live_path = Path(state_path), Path(live_path) if live_path is not None else None
        self.request_timeout_s = request_timeout_s
        self.clock = clock
        self.main_session = main_session
        # The model a remainder of the totals is priced on, only when preflight proved every model the server can
        # call pinned to it (M2). None: such a remainder is a partition with no model, which never prices.
        self.pinned = _model_key(pinned_model) if pinned_model is not None else None
        self.server_version: str | None = None
        self.prompt_state: str | None = "unsent" if kind == "run" else None
        self.errors = 0
        self.last_error: str | None = None
        self.last_success: float | None = None  # self.clock() at the last successful poll
        self._lock = threading.RLock()
        self._ended = False
        self._deadline: float | None = None  # final()'s budget, on self.clock
        self.state = self._load_state()
        started = time.time()
        self.epoch = f"m-{secrets.token_hex(6)}:{_iso_ms(started)}"
        self.seq = -1
        self.observed_at = _iso_ms(started)
        self.sample: dict[str, Any] | None = None
        self._active: set[str] = set()

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict[str, Any]:
        """The persisted high-water state, read with the run directory's guards (no link followed, a regular file,
        at most 16 MiB). A missing file is a fresh meter; a file that is not this meter's state, in its whole shape, is
        not trusted: the source starts `truncated`, so it is unknown rather than counted from zero (m2, PR #186 m3)."""
        try:
            text = runlog._read_text(self.state_path)  # noqa: SLF001 - the run directory's guarded read
        except OSError:
            text = ""
        if text is None:
            return _empty_state()
        try:
            loaded = json.loads(text)
        except (ValueError, RecursionError):
            loaded = None
        if not isinstance(loaded, dict) or not _valid_state(loaded):
            return {**_empty_state(), "truncated": True}
        return loaded

    def _persist(self, state: dict[str, Any]) -> None:
        text = json.dumps(state, sort_keys=True, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_STATE_BYTES:
            state["truncated"] = True
            text = json.dumps({**_empty_state(), "truncated": True}, sort_keys=True, separators=(",", ":"))
        atomic_write(self.state_path, text)

    # ------------------------------------------------------------------ requests

    def _timeout(self) -> float:
        """One request's timeout: ``request_timeout_s``, cut to what is left of ``final()``'s budget, if any."""
        if self._deadline is None:
            return self.request_timeout_s
        left = self._deadline - self.clock()
        if left <= 0:
            raise MeterError("the final sample's time budget ran out")
        return min(self.request_timeout_s, left)

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            return self.client.get(path, params, timeout=self._timeout())
        except (OpenCodeError, OpenCodeUnavailable) as exc:
            raise MeterError(f"{path}: {exc}") from None

    def _list_sessions(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Every session, oldest first (2.0.18 orders and anchors the list on ``time.updated``: a session updated while
        the list is paged moves later, so it is met again, never skipped; duplicates are dropped by id)."""
        out: dict[str, dict[str, Any]] = {}
        params: dict[str, str] = {"order": "asc", "limit": str(SESSION_PAGE)}
        for page_no in range(SESSION_PAGES):
            page = _obj(self._get("/api/session", params))
            data = [s for s in _list(page.get("data")) if isinstance(s, dict)]
            for s in data:
                sid = U.identifier(s.get("id"), MAX_ID)
                if sid is None:
                    state["truncated"] = True  # a session the meter cannot name cannot be tracked
                    continue
                out[sid] = s
            nxt = _obj(page.get("cursor")).get("next")
            if len(data) < SESSION_PAGE or not isinstance(nxt, str) or not nxt:
                break
            if page_no == SESSION_PAGES - 1:  # a full last page: the end was not reached (R2 nit 1)
                state["truncated"] = True
                break
            params = {"cursor": nxt, "limit": str(SESSION_PAGE)}
        return list(out.values())

    # ------------------------------------------------------------------ the poll

    def poll(self) -> dict[str, Any] | None:
        """One sample. A failed request or write takes no sample: the last published one is returned, and its
        ``observed_at`` ages; before any sample is published that is ``None``, never a sample made up (PR #186 m2).
        A failed request or write is counted in ``errors``, never raised (a meter never ends the run, L2)."""
        with self._lock:
            if self._ended or self.client is None:
                return self.sample
            try:
                state = self._read_server()
            except MeterError as exc:
                self.errors += 1
                self.last_error = str(exc)[:300]
                return self.sample
            observed = _iso_ms()
            try:
                sample = self._publish("live", state=state, observed_at=observed)
            except OSError as exc:
                self.errors += 1
                self.last_error = f"write: {exc}"[:300]
                return self.sample
            self.last_success = self.clock()
            return sample

    def final(self, budget_s: float | None = None) -> dict[str, Any]:
        """The final sample: ``final`` after a successful last poll, else ``server_gone`` with the last figures.
        A failed write raises ``OSError`` and ends nothing: ``final()`` can be called again (PR #186 m4).
        ``budget_s`` bounds the last poll's requests in all (the adapter's share of ``TERMINATE_S``, plan v4 §4.2); a
        poll that runs out of it is a failed poll."""
        with self._lock:
            if self._ended and self.sample is not None:
                return self.sample
            state, observed, run_state = self.state, self.observed_at, "server_gone"
            if self.client is not None:
                self._deadline = None if budget_s is None else self.clock() + budget_s
                try:
                    state, observed, run_state = self._read_server(), _iso_ms(), "final"
                except MeterError as exc:
                    self.errors += 1
                    self.last_error = str(exc)[:300]
                finally:
                    self._deadline = None
            elif self.prompt_state == "unsent":
                run_state = "final"  # no server was started: nothing could have been spent (never launched)
            sample = self._publish(run_state, state=state, observed_at=observed)
            if run_state == "final" and self.client is not None:
                self.last_success = self.clock()
            self._ended = True
            return sample

    def set_prompt_state(self, prompt_state: str) -> None:
        """A run's prompt state, written at once with the next ``seq`` (M6, R2-m3). A failed write raises and leaves
        the prompt state as it was: the launch refuses before its server starts (R3-m3)."""
        if self.source["kind"] != "run":
            raise ValueError("only a run source has a prompt state")
        if prompt_state not in PROMPT_STATES:
            raise ValueError(f"a prompt state is one of {PROMPT_STATES}, not {prompt_state!r}")
        with self._lock:
            previous, self.prompt_state = self.prompt_state, prompt_state
            try:
                self._publish(self.sample["state"] if self.sample is not None else "live")
            except BaseException:
                self.prompt_state = previous  # memory never runs ahead of the file (PR #186 m4)
                raise

    def _read_server(self) -> dict[str, Any]:
        state = copy.deepcopy(self.state)
        if self.server_version is None:
            version = _obj(self._get("/api/info")).get("version")
            self.server_version = U.identifier(version, MAX_VERSION) or "unknown"
        listed = self._list_sessions(state)
        active_raw = _obj(self._get("/api/session/active")).get("data")
        self._active = {str(k) for k in active_raw} if isinstance(active_raw, dict) else set()
        sessions: dict[str, Any] = state["sessions"]
        for info in listed:
            sid = str(info["id"])
            s = sessions.get(sid)
            if s is None:
                if len(sessions) >= MAX_SESSIONS:
                    state["truncated"] = True  # the 257th session
                    continue
                s = sessions[sid] = _empty_session()
                new = True
            else:
                new = False
            moved = self._observe_totals(state, s, info)
            if new or moved or sid in self._active or any(s["types"][t]["held"] or s["types"][t]["more"]
                                                          for t in TYPES):
                for kind in TYPES:
                    if not self._read_messages(state, s, sid, kind, moved):
                        break  # the session vanished between the list and its messages: it keeps its figure
        return state

    def _observe_totals(self, state: dict[str, Any], s: dict[str, Any], info: Mapping[str, Any]) -> bool:
        """Raise the session's high-water marks; record a decrease (§2.4). Returns whether the totals moved up."""
        tokens, trust = U.normalize_tokens(info.get("tokens"))
        s["full"] = trust == "harness_reported"
        hw = s["hw"]
        down = any(tokens[c] < hw[c] for c in CATEGORIES)
        up = any(tokens[c] > hw[c] for c in CATEGORIES)
        if down:
            if s["pending"]:
                if not s["breached"]:  # one breach per persisting decrease, seen on two consecutive polls
                    state["integrity"] = min(state["integrity"] + 1, MAX_COUNT)
                    s["breached"] = True
            else:
                s["pending"] = True
        else:
            s["pending"] = s["breached"] = False
        for c in CATEGORIES:
            hw[c] = max(hw[c], tokens[c])
        cost = _number(info.get("cost"))
        if cost is not None:
            s["hw_cost"] = max(float(s["hw_cost"]), cost)
        model = _model_key(info.get("model"))
        s["model"] = list(model[:2]) if model != NO_MODEL else None
        # A fork starts with zero totals and copies of its source's finished messages, which keep their creation
        # time: only messages created at or after the fork's own creation are its usage (P1(d); OpenCode's own stats
        # query excludes the copies the same way).
        if isinstance(info.get("fork"), Mapping):
            s["fork_after"] = _time(info, "created") or 0.0
        return up

    def _read_messages(self, state: dict[str, Any], s: dict[str, Any], sid: str, kind: str, moved: bool) -> bool:
        st = s["types"][kind]
        pages = MESSAGE_PAGES
        while pages > 0:
            pages -= 1
            params = {"type": kind, "limit": str(MESSAGE_PAGE)}
            if st["cursor"]:
                params["cursor"] = st["cursor"]  # the pinned operation: a cursor is never combined with order
            else:
                params["order"] = "asc"
            page = self._session_get(sid, "/message", params)
            if page is None:
                return False  # the session vanished between the list and its messages: it keeps its figure
            items = [m for m in _list(_obj(page).get("data")) if isinstance(m, dict)]
            if not items and st["cursor"] and moved and not self._anchor_exists(sid, st["anchor"]):
                # 2.0.18 answers a cursor whose anchor is gone with an empty page, for good (SessionStore.messages:
                # `if(r.cursor&&!c)return[]`), and a revert deletes messages from its boundary on (P1(d)): read the
                # session again from the start, skipping what was passed already (PR #186 M1).
                if st["last_created"] is None:
                    state["truncated"] = True  # nothing to skip by: the source cannot be re-synced
                    return True
                st["cursor"] = st["anchor"] = None
                st["floor"] = st["last_created"]
                pages += 1  # the re-read replaces the empty page
                continue
            if not self._count_page(state, s, sid, kind, st, items):
                st["held"], st["more"] = True, False
                return True
            st["held"] = False
            nxt = _obj(_obj(page).get("cursor")).get("next")
            if items and isinstance(nxt, str) and nxt:
                anchor = U.identifier(items[-1].get("id"), MAX_ID)
                if len(nxt) > MAX_CURSOR or anchor is None:
                    state["truncated"] = True
                    return True
                st["cursor"], st["anchor"] = nxt, anchor  # every message of the page is passed: read after it
            st["more"] = len(items) >= MESSAGE_PAGE
            if not st["more"]:
                return True
        return True

    def _session_get(self, sid: str, rest: str, params: dict[str, str] | None = None) -> Any:
        """A session route; None when it answers 404 (the session or message is gone)."""
        try:
            return self.client.get(f"/api/session/{sid}{rest}", params, timeout=self._timeout())
        except OpenCodeError as exc:
            if exc.status == 404:
                return None
            raise MeterError(f"{rest} of {sid}: {exc}") from None
        except OpenCodeUnavailable as exc:
            raise MeterError(f"{rest} of {sid}: {exc}") from None

    def _anchor_exists(self, sid: str, anchor: str | None) -> bool:
        """Whether the cursor's anchor message is still there (the pinned ``session.message.get``); an unknown anchor
        is treated as gone, which only costs a re-read."""
        return anchor is not None and self._session_get(sid, f"/message/{anchor}") is not None

    def _count_page(self, state: dict[str, Any], s: dict[str, Any], sid: str, kind: str, st: dict[str, Any],
                    items: list[dict[str, Any]]) -> bool:
        """Count the page's terminal messages in order after the last one passed. False when counting stopped at a
        message still in progress (the cursor and the last passed id stay before it).

        Messages are skipped as passed already when they come before the last passed id on the page, or, once a
        revert deleted that message (it should be on the page, being after the cursor's anchor, and is not), when
        they were created at or before it: 2.0.18 orders a session's messages by position, and a revert keeps only
        those before its boundary, so every survivor was passed. A message created in the same millisecond as the
        deleted one and never counted is skipped too; its usage stays in the figure through the totals."""
        last = st["last"]
        start = 0
        ids = [m.get("id") for m in items]
        if last is not None and last in ids:
            start = ids.index(last) + 1
        elif last is not None and st["anchor"] != last and st["last_created"] is not None:
            st["floor"] = st["last_created"]
        floor = st["floor"]
        for m in items[start:]:
            created = _time(m, "created")
            if floor is not None and (created or 0.0) <= float(floor):
                continue  # passed before a revert deleted the last passed message
            if not self._terminal(kind, m, sid):
                return False
            mid = U.identifier(m.get("id"), MAX_ID)
            if mid is None:
                state["truncated"] = True
                return False
            copied = s["fork_after"] is not None and (created or 0.0) < float(s["fork_after"])
            if not copied:
                self._count(state, st, kind, m)
            st["last"], st["last_created"] = mid, created
        return True

    def _terminal(self, kind: str, m: Mapping[str, Any], sid: str) -> bool:
        if kind == "compaction":  # Session.Message.Compaction: running | completed | failed (P1(f))
            return m.get("status") in ("completed", "failed")
        # R3-m1: completed, or failed, or finished while its session is idle. On 2.0.18 `finish` and `error` are only
        # ever set together with `time.completed` (P1(a)), so `time.completed` alone decides there.
        return (_time(m, "completed") is not None or isinstance(m.get("error"), Mapping)
                or (m.get("finish") is not None and sid not in self._active))

    def _count(self, state: dict[str, Any], st: dict[str, Any], kind: str, m: Mapping[str, Any]) -> None:
        tokens, trust = U.normalize_tokens(m.get("tokens"))
        st["n"] = min(st["n"] + 1, MAX_COUNT)
        if kind == "assistant":
            state["steps"] = min(state["steps"] + 1, MAX_COUNT)
            retry = m.get("retry")
            attempts = retry.get("attempt") if isinstance(retry, Mapping) else None
            if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > 0:
                state["retries"] = min(state["retries"] + attempts, MAX_COUNT)
            if trust != "absent":  # a call that billed: its duration and its size (an aborted call carries none)
                created, completed = _time(m, "created"), _time(m, "completed")
                if created is not None and completed is not None and completed >= created:
                    d = completed - created
                    state["d_min_ms"] = d if state["d_min_ms"] is None else min(float(state["d_min_ms"]), d)
                for c in NAMED:
                    state["max_step"][c] = max(int(state["max_step"][c]), tokens[c])
        elif m.get("status") == "completed":
            state["compactions"] = min(state["compactions"] + 1, MAX_COUNT)
        key = _model_key(m.get("model"))
        if key == NO_MODEL or trust == "absent":
            return  # no model (a failed compaction) or no usage: whatever it billed is in the totals (P1(b))
        cost = _number(m.get("cost"))
        if cost is not None:
            st["cost"] = float(st["cost"]) + cost
        for entry in st["by_model"]:
            if tuple(entry[:3]) == key:
                _add(entry[3], tokens)
                return
        if len(st["by_model"]) < U.MAX_EFFECTIVE:
            st["by_model"].append([*key, dict(tokens)])
        else:  # a ninth model in one session: its tokens price nothing (a partition with no model)
            for entry in st["by_model"]:
                if tuple(entry[:3]) == NO_MODEL:
                    _add(entry[3], tokens)
                    return
            st["by_model"][-1] = [*NO_MODEL, _merge(st["by_model"][-1][3], tokens)]

    # ------------------------------------------------------------------ the sample

    def _publish(self, run_state: str, *, state: dict[str, Any] | None = None,
                 observed_at: str | None = None) -> dict[str, Any]:
        """Persist the state, then write the sample with the next ``seq``. Nothing in memory changes unless both
        writes succeed, so a failed write is retried from where it was and a ``seq`` is never reused."""
        state = self.state if state is None else state
        observed = self.observed_at if observed_at is None else observed_at
        self._persist(state)  # first: a state past its cap marks the source truncated in this very sample
        held, self.observed_at = self.observed_at, observed
        try:
            sample = self._build(state, run_state, self.seq + 1)
        finally:
            self.observed_at = held
        if self.live_path is not None:
            runlog.write_live(self.live_path, sample)  # the live file's only writer (F25 L2, R2-m3)
        self.state, self.observed_at, self.seq, self.sample = state, observed, self.seq + 1, sample
        return sample

    def _build(self, state: dict[str, Any], run_state: str, seq: int) -> dict[str, Any]:
        effective: list[dict[str, Any]] = []
        partitions: dict[tuple[str | None, str | None], dict[str, int]] = {}
        total, foreign = _zeros(), _zeros()
        cost = 0.0
        full = True

        def to(key: tuple[str | None, str | None, str | None], tokens: Mapping[str, int]) -> None:
            if not any(tokens.values()):
                return
            _add(partitions.setdefault((key[0], key[1]), _zeros()), tokens)
            if key != NO_MODEL:
                entry = {"provider": key[0], "model": key[1], "effort": key[2]}
                if entry not in effective:
                    effective.append(entry)

        for sid, s in sorted(state["sessions"].items()):
            full = full and bool(s.get("full", True))
            counted = _zeros()
            counted_cost = 0.0
            for kind in TYPES:
                st = s["types"][kind]
                counted_cost += float(st["cost"])
                for entry in st["by_model"]:
                    _add(counted, entry[3])
            figure = {c: max(int(s["hw"][c]), counted[c]) for c in CATEGORIES}
            for kind in TYPES:
                for entry in s["types"][kind]["by_model"]:
                    to(tuple(entry[:3]), entry[3])  # type: ignore[arg-type]
            remainder = {c: figure[c] - counted[c] for c in CATEGORIES}
            if any(remainder.values()):
                to(self._remainder_model(s), remainder)
            _add(total, figure)
            if self.main_session is not None and sid != self.main_session:
                _add(foreign, figure)
            cost += max(float(s["hw_cost"]), counted_cost)
        providers = [p for (p, _m) in partitions if p is not None]
        version = self.server_version if self.server_version == self.version else None
        semantics = U.resolve_semantics(self.semantics_table, version, providers)
        record = U.normalize({"tokens": total, "cost": round(cost, 9)}, None, effective, semantics,
                             source=f"harness:{HARNESS}", truncated=bool(state.get("truncated")),
                             tokens_by_model=[{"provider": p, "model": m, "tokens": t}
                                              for (p, m), t in partitions.items()] or None)
        d_min = state.get("d_min_ms")
        sample: dict[str, Any] = {
            "schema": SCHEMA, "source": dict(self.source),
            "harness": {"name": HARNESS, "version": self.server_version or U.identifier(self.version, MAX_VERSION)
                        or "unknown"},
            "epoch": self.epoch, "seq": seq, "observed_at": self.observed_at, "state": run_state,
            "s_pot": self.s_pot, "k_assumed": self.k_assumed,
            "sessions": len(state["sessions"]), "truncated": bool(state.get("truncated")),
            "in_flight": len(self._active), "steps": int(state["steps"]), "compactions": int(state["compactions"]),
            "retries": int(state["retries"]),
            "d_min_s": None if d_min is None else round(float(d_min) / 1000.0, 3),
            "max_step_tokens": {c: int(state["max_step"][c]) for c in NAMED},
            "integrity_pending": sum(1 for s in state["sessions"].values() if s.get("pending")),
            "integrity": int(state["integrity"]),
            "foreign_tokens": foreign if self.main_session is not None else None,
        }
        if self.source["kind"] == "run":
            sample["prompt_state"] = self.prompt_state
        for field in ("effective", "effective_truncated", "tokens_by_model", "token_semantics", "tokens",
                      "tokens_trust", "provider_cost_usd", "provider_cost_trust"):
            sample[field] = record[field]
        if not full and sample["tokens_trust"] == "harness_reported":
            sample["tokens_trust"] = "partial"  # some session's totals lacked a category: their zeros are not counts
        if U.serialized_size(sample) > MAX_SAMPLE_BYTES:  # the partition is optional, the bound is not (as R1's)
            sample["tokens_by_model"] = None
        return sample

    def _remainder_model(self, s: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
        """Where a session's totals exceed its counted messages, the excess is priced on the pinned model, and only
        when the session's own model is that model (or unreported); otherwise it prices nothing (M2)."""
        if self.pinned is None or self.pinned == NO_MODEL:
            return NO_MODEL
        own = s.get("model")
        if own is not None and tuple(own) != self.pinned[:2]:
            return NO_MODEL
        return self.pinned


def _merge(a: Mapping[str, int], b: Mapping[str, int]) -> dict[str, int]:
    out = _zeros()
    _add(out, a)
    _add(out, b)
    return out


def OpenCodeMeter(client: Any, *, root_session: str, version: str, s_pot: int, state_path: Path,  # noqa: N802
                  k_assumed: int = 2, pinned_model: Mapping[str, Any] | None = None,
                  request_timeout_s: float = 2.0) -> Meter:
    """The meter of an evaluator-owned OpenCode server (R, R+, the A arm's headless Lead): its source is the root
    session, and its token semantics are the OpenCode adapter's pinned table (m6). F19 owns ``client`` and places
    ``state_path`` in the arm host's run root."""
    from aew.harness.opencode.adapter import OpenCodeAdapter  # the adapter will import this module (L2)

    return Meter(client, source={"kind": "session", "id": root_session}, version=version,
                 semantics_table=OpenCodeAdapter.token_semantics, s_pot=s_pot, k_assumed=k_assumed,
                 state_path=state_path, request_timeout_s=request_timeout_s, main_session=root_session,
                 pinned_model=pinned_model)

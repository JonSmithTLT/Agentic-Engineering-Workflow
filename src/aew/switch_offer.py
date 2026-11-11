"""The switch offer: AEW's default for a switch has moved; does this existing project want it? (register F10, F25).

An existing project holds the old value in its own files, or no price table at all, so raising a default reaches new
projects only. The offer is how an existing project gets it, by the operator's decision. Each registered row
(:data:`OFFERS`) is one switch. The rules:

1. **It asks only at the operator's own terminal, in `aew opencode`'s start.** A Lead session and an agent's own `aew`
   have no path to it. Off a terminal nothing is asked, and `aew doctor` names the offer.
2. **It decides by the key, and never over the operator's value.** A value AEW never shipped, a table the project
   already names or a file already there is never offered, and no line anywhere mentions it.
3. **It adopts only its own change.** Anything else drifted means it doesn't ask, and lists what. The adoption takes
   ``only=`` the row's files, checked inside its transaction, and a failed adoption leaves none of them behind.
4. **Taking it needs the code; Enter alone is a remembered no.** A stray Enter can never turn a switch on. Each answer
   stands alone: a no to one row neither holds nor re-asks another.
5. **Nothing about the offer can stop the start.** One that can't proceed says why in a line, and the TUI opens.

It asks before the seat is taken, when a refused start has written nothing, and applies once the Lead credential is in
hand (:meth:`Decision.apply`, ``lead_broker.run_session``'s ``with_token``): `manifest adopt` needs that credential, and
on `--acquire` it doesn't exist before then. There is no new authorization kind and no new command: the approval is
:func:`aew.operator.answer` and the record is `manifest_adopt`'s, as the operator's own `aew manifest adopt` makes it.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from aew import operator, process_kind
from aew.errors import AEWError
from aew.harness import contract as K
from aew.knowledge.manifest import DEFAULT_GATES, MANIFEST, default_manifest
from aew.util import atomic_write, load_yaml, safe_dump_yaml, utc_now

REMEMBERED = "local/switch-offers.json"  # gitignored and never pinned: an answer is not policy
ABSENT: Any = object()  # a key the file doesn't hold, as `effective` is told
# The last step of each hand route, runnable as printed but for its two placeholders.
THEN_ADOPT = f"then the operator runs {K.MANIFEST_ADOPT}"


class HandChange(Exception):
    """This project's file can't take the edit as text; the operator makes it by hand."""


class Opening(NamedTuple):
    """What the project holds and what AEW's default is now, as the screen and the remembered answer name them."""

    held: str
    to: str


@dataclass(frozen=True)
class SwitchOffer:
    """One switch. ``opening`` is its rule 2, ``None`` when there is nothing to offer here; ``edits`` gives each file's
    new bytes (or raises :class:`HandChange`); ``legality`` is what the screen tells the operator about open stages, and
    a test holds it to what the digest really does. ``switch`` is the id doctor and the memory use; ``label`` is what a
    person reads."""

    switch: str
    label: str
    legality: bool
    opening: Callable[[Path], Opening | None]
    edits: Callable[[Path], dict[str, bytes]]
    text: Callable[[Opening], str]
    changes: str  # the screen's `changes` line
    done: Callable[[Opening], str]
    by_hand: Callable[[Opening], str]  # how to take it later, or when the edit can't be made: no command does this
    after_adopt: Callable[[Any, str], None] | None = None  # after the commit: a failure here undoes nothing


# ---------------------------------------------------------------------------------------------- editing as text

def _mapping(path: Path) -> dict[str, Any] | None:
    """The file's mapping, or ``None`` when it is absent or doesn't parse to one."""
    try:
        data = load_yaml(path.read_bytes().decode("utf-8"), source=str(path))
    except (OSError, UnicodeDecodeError, AEWError):
        return None
    return data if isinstance(data, dict) else None


def _dig(data: dict[str, Any], key_path: tuple[str, ...]) -> Any:
    node: Any = data
    for key in key_path:
        if not isinstance(node, dict) or key not in node:
            return ABSENT
        node = node[key]
    return node


def _scalar(value: Any) -> str:
    return safe_dump_yaml(value).splitlines()[0]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _key_line(lines: list[str], start: int, end: int, indent: int, key: str) -> int | None:
    named = re.compile(rf"{re.escape(key)}\s*:(\s|$)")
    return next((i for i in range(start, end)
                 if _is_content(lines[i]) and _indent(lines[i]) == indent and named.match(lines[i].strip())), None)


def edit_key(raw: bytes, key_path: tuple[str, ...], value: Any) -> bytes:
    """``raw`` with one key set, as text: a re-dump would lose the operator's comments and order, and "leave the other
    keys alone" means those too. Every other byte stays. The result is re-parsed, and must equal the old mapping with
    only that key changed; anything this can't do plainly (a flow mapping, a multi-line value, a parent that is not a
    block, a key spelled so that no line here matches it) raises :class:`HandChange`, and nothing has been written."""
    text = raw.decode("utf-8")
    parsed = load_yaml(text, source="the file as it is") or {}
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    start, end, indent = 0, len(lines), 0
    missing: list[str] = []
    unfound = key_path
    for i, key in enumerate(key_path[:-1]):
        at = _key_line(lines, start, end, indent, key)
        if at is None:
            missing, unfound = list(key_path[i:-1]), key_path[:i + 1]
            break
        block_end = next((i for i in range(at + 1, end) if _is_content(lines[i]) and _indent(lines[i]) <= indent), end)
        child = next((_indent(lines[i]) for i in range(at + 1, block_end) if _is_content(lines[i])), indent + 2)
        start, end, indent = at + 1, block_end, child
    leaf = key_path[-1]
    at = None if missing else _key_line(lines, start, end, indent, leaf)
    if at is None and _dig(parsed, unfound) is not ABSENT:  # adding it would write a second key, and the last one wins
        raise HandChange(f"{'.'.join(unfound)} is in this file in a form that can't be edited as text")
    if at is not None:
        match = re.match(rf"(\s*{re.escape(leaf)}\s*:\s*)(\S[^#\r\n]*?)?(\s*(?:#[^\r\n]*)?)(\r?\n?)$", lines[at])
        if match is None:
            raise HandChange(f"the line for {'.'.join(key_path)} isn't one plain value")
        lines[at] = f"{match[1]}{_scalar(value)}{match[3]}{match[4]}"
    else:
        last = next((i for i in range(end - 1, start - 1, -1) if _is_content(lines[i])), start - 1)
        if last >= 0 and not lines[last].endswith(("\n", "\r")):
            lines[last] += newline
        block = [f"{' ' * (indent + 2 * n)}{key}:{newline}" for n, key in enumerate(missing)]
        block.append(f"{' ' * (indent + 2 * len(missing))}{leaf}: {_scalar(value)}{newline}")
        lines[last + 1:last + 1] = block
    edited = "".join(lines).encode("utf-8")
    expected = copy.deepcopy(parsed)
    node = expected
    for key in key_path[:-1]:
        node = node.setdefault(key, {})
    node[leaf] = value
    try:
        same = load_yaml(edited.decode("utf-8"), source="the file as edited") == expected
    except AEWError:
        same = False
    if not same:
        raise HandChange(f"setting {'.'.join(key_path)} as text would change more than that key")
    return edited


# ---------------------------------------------------------------------------------------------- the rows

def key_offer(switch: str, *, label: str, file: str, policy_key: str, key_path: tuple[str, ...],
              old_values: tuple[Any, ...], to_value: Callable[[], Any], effective: Callable[[Any], Any], legality: bool,
              schema: str, text: Callable[[Opening], str], done: Callable[[Opening], str],
              after_adopt: Callable[[Any, str], None] | None = None) -> SwitchOffer:
    """A switch that is one key of one existing policy file, which the manifest must name at ``policy.<policy_key>``: a
    file not in force holds nothing to switch. ``to_value`` reads AEW's default from its owner, and ``effective`` is the
    owner's accessor (told :data:`ABSENT` for an absent key): an absent key whose default already holds is not offered,
    and neither is a value outside ``old_values``. **Limits:** a value typed by hand can't be told from the same value
    init wrote; the screen shows what is held, and a no is remembered. And a project with no key takes a raised default
    with no offer, since an absent key reads as the default: there is nothing to switch to, and for the cap only a key
    deleted by hand gets here, because init has always written it."""

    def opening(aew_root: Path) -> Opening | None:
        policy = (_mapping(aew_root / MANIFEST) or {}).get("policy")
        if not isinstance(policy, dict) or policy.get(policy_key) != file:
            return None
        data = _mapping(aew_root / file)
        if data is None:  # creating an absent file is the row's own question: no row here does
            return None
        current = _dig(data, key_path)
        if current is not ABSENT and current not in old_values:
            return None
        held, to = effective(current), to_value()
        return None if held == to else Opening(str(held), str(to))

    def edits(aew_root: Path) -> dict[str, bytes]:
        from aew.engine.base import check_policy_bytes

        edited = edit_key((aew_root / file).read_bytes(), key_path, to_value())
        try:
            check_policy_bytes(schema, edited, source=file)
        except AEWError as exc:
            raise HandChange(exc.message) from exc
        return {file: edited}

    name = ".".join(key_path)
    return SwitchOffer(switch=switch, label=label, legality=legality, opening=opening, edits=edits, text=text,
                       changes=f".aew/{file} {name}", done=done, after_adopt=after_adopt,
                       by_hand=lambda o: f"set {name} to {o.to} in .aew/{file}; {THEN_ADOPT}")


def _policy_rel(name: str) -> str:
    return default_manifest("x", "x", "main", "x")["policy"][name]  # where init puts it: one owner


def _table_rel() -> str:
    return _policy_rel("pricing")


def _table_opening(aew_root: Path) -> Opening | None:
    """Offered only to a project with no table at all: one that names a table keeps it, whatever it holds, and a file
    already at that path is the operator's and is never overwritten (taken out of force, say)."""
    from aew.engine.usage_ops import bundled_table

    manifest = _mapping(aew_root / MANIFEST)
    if manifest is None or not isinstance(manifest.get("policy"), dict) or "pricing" in manifest["policy"]:
        return None
    if (aew_root / _table_rel()).exists() or bundled_table() is None:
        return None
    return Opening("no table", "the bundled table")


def _table_edits(aew_root: Path) -> dict[str, bytes]:
    from aew.engine.usage_ops import bundled_table
    from aew.schemas import validate

    rel = _table_rel()
    table = bundled_table()
    if table is None or (aew_root / rel).exists():
        raise HandChange(f"{rel} exists or AEW's package holds no table")
    edited = edit_key((aew_root / MANIFEST).read_bytes(), ("policy", "pricing"), rel)
    try:
        validate("project", load_yaml(edited.decode("utf-8"), source=MANIFEST), source=MANIFEST)
    except AEWError as exc:
        raise HandChange(exc.message) from exc
    return {rel: table, MANIFEST: edited}


def _table_text(opening: Opening) -> str:
    from aew.engine.usage_ops import Prices, bundled_table

    raw = bundled_table()
    assert raw is not None  # `_table_opening` offers no table without one
    table = Prices(raw, source="AEW's bundled table").table
    return ("AEW now ships a price table, and this project has none, so its usage report reads every cost as unpriced. "
            f"This adds the table as the project's own copy: list prices as of {table['as_of']}, estimates and not a "
            "contract or gateway rate.")


def _table_by_hand(_opening: Opening) -> str:
    from aew.engine.usage_ops import bundled_table_path

    rel = _table_rel()
    return (f"copy `{bundled_table_path()}` to .aew/{rel}, add `pricing: {rel}` under `policy:` in .aew/{MANIFEST}; "
            f"{THEN_ADOPT}")


def _mutating_effective(value: Any) -> int:
    from aew.engine.workspace_ops import mutating_cap

    return mutating_cap({} if value is ABSENT else {"mutating_concurrency": value})


OFFERS: tuple[SwitchOffer, ...] = (
    key_offer("mutating_concurrency", label="mutating concurrency", file=_policy_rel("gates"), policy_key="gates",
              key_path=("mutating_concurrency",), old_values=(1,),
              to_value=lambda: DEFAULT_GATES["mutating_concurrency"], effective=_mutating_effective, legality=True,
              schema="gates",
              text=lambda o: (f"AEW's default for mutating concurrency has moved from {o.held} to {o.to}: that many "
                              "mutating Tickets may run at once, each in its own workspace, and integration stays "
                              f"serialized. This project holds {o.held}."),
              done=lambda o: (f"mutating concurrency is now {o.to}, adopted as your decision. To change it, edit "
                              f".aew/{_policy_rel('gates')}; {THEN_ADOPT}.")),
    SwitchOffer(switch="price_table", label="the price table", legality=False, opening=_table_opening,
                edits=_table_edits, text=_table_text,
                changes=f".aew/{MANIFEST} policy.pricing, and a new .aew/{_table_rel()}",
                done=lambda o: (f"the price table is now in force at .aew/{_table_rel()}, adopted as your decision. To "
                                f"change it, edit that file; {THEN_ADOPT}."),
                by_hand=_table_by_hand),
)


# ---------------------------------------------------------------------------------------------- what is remembered

def _remembered_path(aew_root: Path) -> Path:
    return aew_root / REMEMBERED


def _declined(aew_root: Path) -> list[dict[str, Any]]:
    """The remembered noes. A damaged file reads as none, so the worst case is being asked once more."""
    try:
        data = json.loads(_remembered_path(aew_root).read_bytes())
        rows = data["declined"]
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _declined_at(aew_root: Path, offer: SwitchOffer, opening: Opening) -> str | None:
    """When the operator said no to this switch from this value to this default: a later raise is a new offer."""
    return next((str(r.get("at")) for r in _declined(aew_root)
                 if (r.get("switch"), r.get("from"), r.get("to")) == (offer.switch, opening.held, opening.to)), None)


def _remember_no(aew_root: Path, offer: SwitchOffer, opening: Opening) -> None:
    path = _remembered_path(aew_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [*_declined(aew_root), {"switch": offer.switch, "from": opening.held, "to": opening.to, "at": utc_now()}]
    atomic_write(path, json.dumps({"schema": 1, "declined": rows}, indent=2) + "\n")


# ---------------------------------------------------------------------------------------------- where it stands

class Standing(NamedTuple):
    offer: SwitchOffer
    opening: Opening
    declined_at: str | None
    blocked: list[str] | None  # what else has drifted: it would be pinned unseen by an adoption
    hand: str | None  # why the edit can't be made as text: the operator makes it by hand


def _blocked(engine: Any) -> list[str] | None:
    """What an adoption would pin besides the offer's own change. Never pinned is the whole project: an adopt there
    would pin every file."""
    state = engine.store.current()
    drift = engine.policy_pin_drift(state)
    if drift is None:
        return ["every policy file (this project's were never pinned)"]
    found = ([] if engine.manifest_pin_ok(state) else [MANIFEST]) + list(drift)
    return found or None


def _standing(engine: Any, offer: SwitchOffer) -> Standing | None:
    """Where this switch stands here, or ``None`` when there is nothing to offer. The edit is tried, since that only
    reads: a code the edit can't honour isn't asked for, at every start, for nothing."""
    opening = offer.opening(engine.aew_root)
    if opening is None:
        return None
    try:
        offer.edits(engine.aew_root)
        hand = None
    except (HandChange, OSError) as exc:
        hand = str(exc)
    return Standing(offer, opening, _declined_at(engine.aew_root, offer, opening), _blocked(engine), hand)


def standings(engine: Any) -> list[Standing]:
    """Each registered switch this project could be offered, in order; the operator's own values aren't here."""
    return [s for offer in OFFERS if (s := _standing(engine, offer)) is not None]


def _blocked_line(standing: Standing) -> str:
    return (f"AEW's default for {standing.offer.label} has moved ({standing.opening.held} -> {standing.opening.to}), "
            f"but {', '.join(standing.blocked or [])} would be adopted with it: review that; {THEN_ADOPT}, and the "
            "offer returns.")


def _hand_line(standing: Standing) -> str:
    return (f"AEW's default for {standing.offer.label} has moved ({standing.opening.held} -> {standing.opening.to}), "
            f"but AEW can't make that edit here: {standing.hand}. To take it: "
            f"{standing.offer.by_hand(standing.opening)}.")


def doctor_rows(engine: Any) -> list[tuple[str, str, str]]:
    """`aew doctor`'s lines, the same on and off a terminal: pending, declined (a no stays visible, as a declined tool's
    does), blocked by drift, or a hand change, and nothing for an operator's own value. Informational: nothing is wrong.
    A contained Lead's `aew doctor` runs in its sandbox, where the remembered answers are masked: it can't tell pending
    from answered, and says so rather than send the operator to a prompt that won't come."""
    rows = []
    for s in standings(engine):
        if s.declined_at is not None:
            detail = (f"Declined switch: {s.offer.label} keeps {s.opening.held} (declined {s.declined_at}). To take "
                      f"it: {s.offer.by_hand(s.opening)}.")
        elif s.blocked:
            detail = _blocked_line(s)
        elif s.hand:
            detail = _hand_line(s)
        elif process_kind.kind() == process_kind.NON_WRITER:
            detail = (f"Switch offer: {s.offer.label}, {s.opening.held} -> {s.opening.to}. Pending, or already "
                      "answered at the operator's terminal: this process can't read that answer.")
        else:
            detail = (f"Switch offer: {s.offer.label}, {s.opening.held} -> {s.opening.to}. Answered at `aew "
                      "opencode`'s start.")
        rows.append((f"switch-offer:{s.offer.switch}", "PASS", f"INFO: {detail}"))
    return rows


# ---------------------------------------------------------------------------------------------- the start

def terminal() -> bool:
    """Whether the operator can be asked here. The test suite replaces it, so no test waits on a terminal."""
    return operator.has_terminal()


def _may_ask() -> bool:
    """`lead_session_problem`, not `consent._never_here`: that refuses ``AEW_LEAD_TOKEN``, which is how an operator
    legitimately starts `aew opencode`. It reads the broker's variables and, on Linux, the process chain from the parent
    up, so `aew opencode` doesn't refuse itself and a Lead's own shell is refused."""
    from aew.harness.operator_client import lead_session_problem

    return lead_session_problem() is None and process_kind.kind() != process_kind.NON_WRITER and terminal()


def _stages_line(offer: SwitchOffer, engine: Any) -> str:
    """What taking it does to open stages, in the operator's words, derived from the row's flag."""
    if not offer.legality:
        return "This is not a legality setting: open stages carry on, and none stops because of it."
    open_now = len(engine.store.current().get("stage_intents") or {})
    return ("This is a legality setting: a stage open when it is adopted stops as STALE_POLICY and needs a fresh "
            f"decision. Open now: {open_now}.")


def _say(out: Any, line: str) -> None:
    out.write(f"aew opencode: {line}\n")


@dataclass
class Decision:
    """What the operator took at this start, held in memory with its authorization; nothing is written until
    :meth:`apply`, so a start refused in between has changed nothing and asks again next time."""

    engine: Any = None
    out: Any = None
    taken: list[tuple[SwitchOffer, Opening, dict[str, str]]] = field(default_factory=list)

    def apply(self, token: str) -> None:
        """Each answer alone, once the Lead credential is in hand. It never raises: an already-held seat isn't lost over
        an offer, and one row failing leaves the next to run."""
        for offer, opening, authorization in self.taken:
            try:
                _take(self.engine, offer, opening, authorization, token, self.out)
            except Exception as exc:  # noqa: BLE001 (rule 5: nothing about the offer can stop the start)
                _say(self.out, f"the offer for {offer.label} failed ({type(exc).__name__}: {exc}); see `aew doctor`.")


def at_lead_start(engine: Any, out: Any = None) -> Decision:
    """`aew opencode`'s step, before the seat is taken: each pending row asked at the operator's terminal, one prompt
    each, and each answer standing alone: a row that breaks ends that row. Never raises (rule 5)."""
    out = out if out is not None else sys.stderr
    decision = Decision(engine, out)
    try:
        if not _may_ask():
            return decision
    except Exception as exc:  # noqa: BLE001 (rule 5: nothing about the offer can stop the start)
        _say(out, f"the switch offers could not be read ({type(exc).__name__}: {exc}); see `aew doctor`.")
        return decision
    for offer in OFFERS:
        try:
            standing = _standing(engine, offer)
            if standing is None or standing.declined_at is not None:
                continue
            if standing.blocked:
                _say(out, _blocked_line(standing))
            elif standing.hand:
                _say(out, _hand_line(standing))
            else:
                _ask_one(engine, standing, decision, out)
        except Exception as exc:  # noqa: BLE001 (rule 5: nothing about the offer can stop the start)
            _say(out, f"the offer for {offer.label} could not be read ({type(exc).__name__}: {exc}); see `aew doctor`.")
    return decision


def _ask_one(engine: Any, standing: Standing, decision: Decision, out: Any) -> None:
    offer, opening = standing.offer, standing.opening
    text = f"{offer.text(opening)}\n{_stages_line(offer, engine)}"
    instruction = (f"Type {{code}} and Enter to switch to {opening.to}. Enter alone keeps {opening.held}, and AEW "
                   "won't ask again. Anything else changes nothing and asks again next start.")
    try:
        reply = operator.answer(text, instruction=instruction, purpose=offer.changes)
    except AEWError as exc:
        _say(out, f"{offer.label} is unchanged ({exc.message}); asked again next start.")
        return
    if reply.declined:
        try:
            _remember_no(engine.aew_root, offer, opening)
        except OSError as exc:
            _say(out, f"{offer.label} keeps {opening.held}, but the answer couldn't be remembered: {exc}.")
            return
        _say(out, f"{offer.label} keeps {opening.held}, and AEW won't ask again. To take it: {offer.by_hand(opening)}.")
    elif reply.authorization is not None:
        decision.taken.append((offer, opening, reply.authorization))


def _take(engine: Any, offer: SwitchOffer, opening: Opening, authorization: dict[str, str], token: str,
          out: Any) -> None:
    """Write the row's files, adopt exactly them, and on any failure leave neither behind."""
    root = engine.aew_root
    if offer.opening(root) != opening:  # the operator's own edit since they answered: theirs stands
        _say(out, f"{offer.label} changed since you answered, so it was left as it is.")
        return
    blocked = _blocked(engine)  # `only=` compares names, so another edit of the row's own file has to be seen here
    if blocked:
        _say(out, f"{offer.label} is unchanged: {', '.join(blocked)} changed while you answered, and adopting now "
                  f"would adopt that too. To take it: {offer.by_hand(opening)}.")
        return
    try:
        edits = offer.edits(root)
    except (HandChange, OSError) as exc:
        _say(out, f"{offer.label} is unchanged: {exc}. To take it: {offer.by_hand(opening)}.")
        return
    kept = {rel: (root / rel).read_bytes() if (root / rel).exists() else None for rel in edits}
    try:
        for rel, new in edits.items():
            atomic_write(root / rel, new)
        engine.manifest_adopt(token=token, expect_rev=engine.store.current()["revision"], authorization=authorization,
                              reason=f"switch offer: {offer.switch} {opening.held} -> {opening.to}", only=sorted(edits))
    except Exception as exc:  # noqa: BLE001 (rules 3 and 5: whatever failed, nothing stays, and the start goes on)
        left = _restore(root, edits, kept)
        message = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
        also = f" {'; '.join(left)}." if left else ""
        _say(out, f"{offer.label} is unchanged: {message}.{also}")
        return
    _say(out, offer.done(opening))
    if offer.after_adopt is not None:
        try:
            offer.after_adopt(engine, token)
        except Exception as exc:  # noqa: BLE001 (it runs after the commit: the adopted switch stands)
            _say(out, f"{offer.label} is adopted, but its next step failed ({type(exc).__name__}: {exc}).")


def _restore(root: Path, edits: dict[str, bytes], kept: dict[str, bytes | None]) -> list[str]:
    """Each file back as it was, but only if it still holds what this wrote; a line for each that isn't."""
    left = []
    for rel, wrote in edits.items():
        path, before = root / rel, kept[rel]
        try:
            current = path.read_bytes() if path.exists() else None
            if current == before:
                continue
            if current != wrote:
                left.append(f"{rel} changed since this wrote it, so it was left as it is")
            elif before is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, before)
        except OSError as exc:
            left.append(f"{rel} could not be put back ({exc})")
    return left

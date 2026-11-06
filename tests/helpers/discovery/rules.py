"""D2's rules over one output (discovery-layer spec v3.4, §2.2; docs/implementation/vertical-uat.md §8).

Every input a rule judges by is read from the product itself: the live ``aew`` argparse parser (O-CMD, and O-IDS's
positions), ``aew.surface.contract.TOOLS`` (typed-tool names and arguments), ``aew.errors`` (the code registry),
``aew.harness.contract.CREDENTIAL_ENV`` (O-SECRET's credentials), the id formats the engine writes (``INVOCATION_RE``,
``run_id``, the stage-intent schema) and ``aew.harness.agentenv`` (O-ENV). The vocabulary the spec itself fixes (the
id kinds of O-IDS, the refusal schema's fields) is named once here, with the spec's section.

A finding is a ``(rule, site)`` pair: the site is the output-site key the capture plugin or the static scan gives
the output, never message text (messages carry temporary paths and live ids; the key goes into a committed file).
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import shlex
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

# Planes (who reads an output): the operator at a terminal, a model (the Lead, or a worker through its pack), or the
# operator console. O-SECRET depends on it (§2.2).
OPERATOR, MODEL, CONSOLE = "operator", "model", "console"

# Structured fields that hold a suggested input (§2.2, O-IDS: "a structured `next`, `remedy`, `cli` or hint field").
SUGGESTED_FIELDS = frozenset({"next", "next_action", "next_actions", "remedy", "cli", "cli_fallback", "hint", "hints"})
# The refusal schema's fields (§1.5, R-REFUSE; F3). No refusal carries them yet: every refusal is "unstructured".
REFUSAL_SCHEMA = ("cause", "remedy", "owner")
# O-IDS's id kinds (§2.2: a revision, generation, invocation, run or stage intent; the setup guide's `<C-001>`, a
# candidate, is U1's witness). An argument takes an id when a word of its name or its metavar names one of these
# kinds (``is_id_action``): read from the parser's own declarations, so a new id argument is covered as it is added.
ID_KINDS = frozenset({"rev", "revision", "generation", "inv", "invocation", "run", "intent", "candidate"})
# Ticket ids are exempt (§2.2): a work unit is a product concept the operator names.
WORK_DESTS = frozenset({"work_id", "parent", "depends_on", "into"})

ANGLE = re.compile(r"^<[^<>]+>$|^\{[^{}]+\}$")
ELISION = frozenset({"...", "…"})
SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^\s*(```|~~~)")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1\s*$")


@dataclass(frozen=True)
class Finding:
    rule: str
    site: str
    detail: str = field(default="", compare=False)

    @property
    def key(self) -> str:
        return f"{self.rule} {self.site}"


@dataclass
class Output:
    """One human- or Lead-facing output. ``payload`` is a parsed JSON answer (else ``None``), ``text`` its prose;
    ``refusal`` is ``{code, message, details}`` when the output refuses; ``echo`` is the input it answers (excluded
    from O-CMD and O-IDS inside a refusal); ``injected_cause`` is set only by an explorer that injected the cause
    (O-CODE's scope, §2.3, H5)."""

    site: str
    plane: str = OPERATOR
    payload: Any = None
    text: str = ""
    refusal: dict[str, Any] | None = None
    echo: tuple[str, ...] = ()
    injected_cause: str | None = None


@dataclass(frozen=True)
class Suggestion:
    """A suggested input: ``argv`` without the leading ``aew``. ``structured`` is a structured field's command (an
    argument list such as ``cli``, or the command a ``next``, ``remedy`` or hint field names), which must parse whole;
    prose elsewhere may name a command without its required arguments (a mention, not an error). ``body`` is the
    heredoc under a fenced ``--fields -`` line, where the text shows one."""

    argv: tuple[str, ...]
    text: str
    structured: bool
    body: str | None = None


# ---------------------------------------------------------------------------------------------- the product's facts

@functools.cache
def credential_names() -> tuple[str, ...]:
    """The AEW credentials an output must never ask anyone to set or copy: the credential variables of
    ``harness.contract.CREDENTIAL_ENV`` (the secret ones, a token or a key) and the CLI options that take them."""
    from aew.harness.contract import CREDENTIAL_ENV

    names = [n for n in CREDENTIAL_ENV if n.endswith(("_TOKEN", "_KEY"))]
    options = {o for a in _actions() for o in a.option_strings if a.dest.endswith("token")}
    return (*names, *sorted(options))


@functools.cache
def id_patterns() -> tuple[re.Pattern[str], ...]:
    """Concrete ids of O-IDS's kinds, as the engine writes them: an invocation (``coordination.layout``), a run
    (``harness.contract.run_id``) and a stage intent (the control schema's pattern)."""
    from aew.coordination.layout import INVOCATION_RE
    from aew.harness.contract import run_id
    from aew.schemas import schema

    inv = INVOCATION_RE.pattern.strip("^$")
    run = re.escape(run_id("INVSENTINEL", 7777)).replace("INVSENTINEL", inv).replace("7777", "[0-9]+")
    intents = _find_pattern(schema("control"), "SI-")
    return tuple(re.compile(rf"^{p}$") for p in (inv, run, intents.strip("^$")))


def _find_pattern(schema: Any, prefix: str) -> str:
    if isinstance(schema, dict):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and pattern.lstrip("^").startswith(prefix):
            return pattern
        for value in schema.values():
            if found := _find_pattern(value, prefix):
                return found
    if isinstance(schema, list):
        for value in schema:
            if found := _find_pattern(value, prefix):
                return found
    return ""


def is_placeholder(token: str) -> bool:
    return bool(ANGLE.match(token)) or token == "N" or token in ELISION


def _is_id(token: str) -> bool:
    return any(p.match(token) for p in id_patterns())


# ---------------------------------------------------------------------------------------------- the live parser

class ParseFail(Exception):
    pass


class _Exit(Exception):
    pass


# The parser is one shared object, and ``parse`` flips its actions' ``required`` flags for the length of a call, while
# the capture plugin judges outputs outside its own lock (product threads may record concurrently). So a parse holds
# this for its whole length, and the parser is built under it, so ``_actions`` and ``parse`` share one instance.
# Reentrant: ``parse`` calls itself. A tight loop gave false refusals without it; how often the real suite overlaps two
# judges is not established (no intermittent key shows in the runs read).
_PARSE_LOCK = threading.RLock()


def _parser() -> argparse.ArgumentParser:
    with _PARSE_LOCK:
        return _build_parser()


@functools.cache
def _build_parser() -> argparse.ArgumentParser:
    """The live ``aew`` parser with every command registered (``build_parser``'s classification mode), made
    parse-only: an error raises instead of printing and exiting, and a placeholder is taken as a value (it skips its
    action's type and choices)."""
    from aew.cli.main import build_parser

    parser = build_parser(recall_search=True, coordination_reads=True)
    for p in _all_parsers(parser):
        p.error = _raise  # type: ignore[method-assign]
        p.exit = _exit  # type: ignore[method-assign]
        p._print_message = lambda *a, **k: None  # type: ignore[method-assign]
        p._get_value = _lenient(p._get_value)  # type: ignore[method-assign]
        p._check_value = _lenient_check(p._check_value)  # type: ignore[method-assign]
    return parser


def _raise(message: str) -> None:
    raise ParseFail(message)


def _exit(*_: Any, **__: Any) -> None:
    raise _Exit()


def _lenient(get: Any) -> Any:
    def get_value(action: argparse.Action, arg: str) -> Any:
        return arg if is_placeholder(arg) else get(action, arg)
    return get_value


def _lenient_check(check: Any) -> Any:
    def check_value(action: argparse.Action, value: Any) -> None:
        if not (isinstance(value, str) and is_placeholder(value)):
            check(action, value)
    return check_value


def _all_parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    out, todo = [], [parser]
    while todo:
        p = todo.pop()
        if any(p is q for q in out):
            continue
        out.append(p)
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                todo.extend(a.choices.values())
    return out


@functools.cache
def _actions() -> tuple[argparse.Action, ...]:
    return tuple(a for p in _all_parsers(_parser()) for a in p._actions)


@functools.cache
def _id_options() -> frozenset[str]:
    return frozenset(o for a in _actions() if is_id_action(a) for o in a.option_strings)


def is_id_action(action: argparse.Action) -> bool:
    """Whether an argument takes an id of O-IDS's kinds: a word of its dest, an option string or its metavar names
    one (``expect_rev``, ``--carry INV``, ``--since REVISION``)."""
    if action.nargs == 0 or isinstance(action, argparse._SubParsersAction) or action.choices:
        return False
    metavar = action.metavar if isinstance(action.metavar, str) else ""
    names = [action.dest, metavar, *action.option_strings]
    words = {w for n in names for w in re.split(r"[^a-z]+", n.lower()) if w}
    return bool(words & ID_KINDS) and "token" not in words  # a credential is O-SECRET's, not an id


def command_words(argv: Iterable[str]) -> tuple[str, ...]:
    """The command path ``argv`` names (``("harness", "wait")``), walked through the live parser's subcommands; global
    options before the command are skipped."""
    current, words, skip = _parser(), [], False
    for token in argv:
        if skip:
            skip = False
            continue
        if token.startswith("-"):
            action = current._option_string_actions.get(token.split("=", 1)[0])
            skip = action is not None and action.nargs != 0 and "=" not in token
            continue
        sub = next((a for a in current._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sub is None or token not in sub.choices:
            break
        words.append(token)
        current = sub.choices[token]
    return tuple(words)


def _strip(argv: list[str]) -> list[str]:
    """What the shell, not the parser, handles: a heredoc or pipe tail, and ``--fields X`` (expanded before parsing
    by the real CLI). A bare elision that is not an option's value stands for further arguments and is dropped."""
    out: list[str] = []
    for token in argv:
        if token.startswith("<<") or token in {"|", ">", ">>", "2>&1", "&&", ";"}:
            break
        out.append(token)
    kept: list[str] = []
    i = 0
    while i < len(out):
        if out[i] == "--fields":
            i += 2
            continue
        if out[i].startswith("--fields="):
            i += 1
            continue
        if out[i] in ELISION and not (kept and kept[-1].startswith("-") and _takes_value(kept[-1])):
            i += 1
            continue
        kept.append(out[i])
        i += 1
    return kept


def _takes_value(option: str) -> bool:
    action = next((a for a in _actions() if option in a.option_strings), None)
    return action is not None and action.nargs != 0


def _option_alternatives(argv: list[str]) -> list[list[str]] | None:
    """Alternatives between options, written across spaces (``--assurance none|--review <card>|--verify <card>``):
    the bar splits whole option groups, not single words. ``None`` when ``argv`` has none."""
    def splits_options(token: str) -> bool:
        return "|" in token and not ANGLE.match(token) and any(p.startswith("-") for p in token.split("|")[1:])

    first = next((i for i, t in enumerate(argv) if splits_options(t)), None)
    if first is None:
        return None
    last = first
    while last + 1 < len(argv) and splits_options(argv[last + 1]):
        last += 1
    start = first - 1 if first > 0 and argv[first - 1].startswith("-") else first
    end = last  # the value after the last alternative's option belongs to it
    if argv[last].split("|")[-1].startswith("-") and _takes_value(argv[last].split("|")[-1]) and last + 1 < len(argv):
        end = last + 1
    segment = " ".join(argv[start:end + 1])
    head, tail = argv[:start], argv[end + 1:]
    return [[*head, *alt.split(), *tail] for alt in re.split(r"\|(?=-)", segment)]


def _variants(argv: list[str], limit: int = 16) -> list[list[str]]:
    """``a|b|c`` (or ``<a|b|c>``) is a choice the text offers: each alternative must parse."""
    grouped = _option_alternatives(argv)
    if grouped is not None:
        return [v for alt in grouped for v in _variants(alt, limit)][:limit]
    variants: list[list[str]] = [[]]
    for token in argv:
        inner = token[1:-1] if token[:1] in "<{" and ANGLE.match(token) else token
        alts = inner.split("|") if "|" in inner else [token]
        variants = [v + [alt] for v in variants for alt in alts if alt][:limit]
    return variants


def parse(argv: Iterable[str], *, complete: bool = True) -> argparse.Namespace:
    """Parse ``argv`` (without ``aew``) with the live parser, parse-only; raises ``ParseFail``. Not ``complete``: a
    command named in prose without its required arguments is a mention, so no argument is required."""
    with _PARSE_LOCK:  # a complete parse too: with another call's flags off, it would pass what it must refuse
        required: list[Any] = []
        if not complete:
            required = [*_actions(), *(g for p in _all_parsers(_parser()) for g in p._mutually_exclusive_groups)]
        saved = [(x, x.required) for x in required]
        for x in required:
            x.required = False
        args = list(argv)
        try:
            return _parser().parse_args(args)
        except ParseFail as exc:
            # An option named last, without its value, is a mention in prose (`aew opencode --provider-env`).
            if not complete and args and args[-1].startswith("-") and "expected one argument" in str(exc):
                return parse(args[:-1], complete=False)
            raise
        except _Exit:
            return argparse.Namespace(command=None)
        finally:
            for x, was in saved:
                x.required = was


# ---------------------------------------------------------------------------------------------- suggested inputs

HOLD = "\x00"  # stands in for a space inside a placeholder while the line is split


def _tokens(text: str) -> list[str] | None:
    """Shell words, with a placeholder that holds spaces (``<planning Ticket>``) kept as one word."""
    hold = re.sub(r"<[^<>\n]+>", lambda m: m.group(0).replace(" ", HOLD), text)
    try:
        return [t.replace(HOLD, " ") for t in shlex.split(hold, posix=True)]
    except ValueError:
        return None


def prose_commands(text: str) -> Iterator[str]:
    """Every suggested ``aew`` command in prose: a backticked span starting with ``aew``, and a line of a fenced code
    block that starts with ``aew`` (a prompt ``$`` and a trailing ``# comment`` stripped). Commands chained with
    ``&&`` or ``;`` are each one."""
    for command, _ in _commands(text):
        yield command


def _commands(text: str) -> Iterator[tuple[str, str | None]]:
    """``prose_commands``, each with its heredoc's body where the text shows one (``None``: no body shown)."""
    for found, body in _prose_commands(text):
        parts = [c.strip() for c in re.split(r"\s(?:&&|;)\s(?=aew\s)", found)]
        yield from ((part, body if i == len(parts) - 1 else None) for i, part in enumerate(parts))


def _prose_commands(text: str) -> Iterator[tuple[str, str | None]]:
    in_fence, pending = False, ""
    held: tuple[str, str, list[str]] | None = None  # a heredoc being read: its command, its end word, its lines
    for line in text.splitlines():
        if FENCE.match(line):
            if held:  # not closed in its block: no body the reader could run
                yield held[0], None
                held = None
            in_fence, pending = not in_fence, ""
            continue
        if held:
            if line.strip() == held[1]:
                yield held[0], "".join(f"{ln}\n" for ln in held[2])
                held = None
            else:
                held[2].append(line)
            continue
        if in_fence:
            body = (pending + " " + line.strip()).strip() if pending else line.strip().removeprefix("$ ").strip()
            if body.endswith("\\"):  # a continued line: the command goes on below
                pending = body[:-1].rstrip() if (pending or body.startswith("aew ")) else ""
                continue
            pending = ""
            if body.startswith("aew "):
                command = re.split(r"\s+#\s", body, maxsplit=1)[0].rstrip()
                opened = HEREDOC.search(command)
                if opened:
                    held = (command, opened.group(2), [])
                else:
                    yield command, None
            continue
        for m in SPAN.finditer(line):
            span = m.group(1).strip()
            if span.startswith("aew "):  # a bare `aew` names the program, not a command line
                yield span, None
    if held:
        yield held[0], None


def _field_commands(value: str) -> Iterator[tuple[str, str | None]]:
    """A suggested field's text: its backticked spans, or else the command it names in words (``... : aew x y``)."""
    spans = list(_commands(value))
    if spans:
        yield from spans
        return
    m = re.search(r"(?:^|\s)(aew\s[^;`]*)", value)
    if m:
        yield re.split(r"(?<=\S)[.,)](?:\s|$)", m.group(1), maxsplit=1)[0].strip(), None


def suggestions(output: Output) -> list[Suggestion]:
    out: list[Suggestion] = []

    def add(text: str, structured: bool, argv: list[str] | None = None, body: str | None = None) -> None:
        tokens = argv if argv is not None else _tokens(text)
        if tokens is None:
            out.append(Suggestion((), text, structured))
            return
        if tokens and tokens[0] == "aew":
            tokens = tokens[1:]
        out.append(Suggestion(tuple(tokens), text, structured, body))

    def walk(value: Any, suggested: bool) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("cli", "cli_fallback") and isinstance(v, list) and all(isinstance(t, str) for t in v) and v:
                    argv = [str(t) for t in v]
                    add(" ".join(argv), True, argv)
                else:
                    walk(v, suggested or k in SUGGESTED_FIELDS)
        elif isinstance(value, list):
            for v in value:
                walk(v, suggested)
        elif isinstance(value, str):
            # A command in a structured field (§2.2: `next`, `remedy`, `cli`, a hint) is offered to be run as given, so
            # it must parse whole; only prose elsewhere may name a command without its required arguments.
            for cmd, body in (_field_commands(value) if suggested else _commands(value)):
                add(cmd, suggested, body=body)

    walk(output.payload, False)
    if output.text:
        for cmd, body in _commands(output.text):
            add(cmd, False, body=body)
    if output.refusal:
        for cmd, body in _commands(str(output.refusal.get("message") or "")):
            add(cmd, False, body=body)
    seen: set[tuple[tuple[str, ...], str, str | None]] = set()
    unique = []
    for s in out:
        if (s.argv, s.text, s.body) not in seen:
            seen.add((s.argv, s.text, s.body))
            unique.append(s)
    return unique


def _echoed(s: Suggestion, output: Output) -> bool:
    if output.refusal is None or not output.echo:
        return False
    given = " ".join(output.echo)
    return bool(s.argv) and " ".join(s.argv) in given


# ---------------------------------------------------------------------------------------------- the rules

def _names_fields(argv: Iterable[str]) -> bool:
    return any(t == "--fields" or t.startswith("--fields=") for t in argv)


def _field_options(argv: list[str], body: str) -> list[str]:
    """``--name=value`` for each option a ``--fields`` body gives, by the CLI's own expansion (a body read as data here,
    so nothing touches the process's stdin: outputs are judged on whatever thread produced them)."""
    from aew.cli import fields

    return fields.expand([*argv, fields.OPTION, "-"], _parser(), read=lambda _: body)[len(argv):]


def o_cmd(s: Suggestion) -> str | None:
    """Why ``s`` does not parse (parse-only, placeholders as values), or ``None``. A ``--fields`` body goes through the
    real expansion, so what it gives counts as given and what it gets wrong is reported; a line naming ``--fields`` with
    no body shown can't say what the body gives, so it answers only for its command and options."""
    from aew.errors import UsageError

    if not s.argv:
        return f"not a command line: {s.text!r}" if s.text else None
    argv = _strip(list(s.argv))
    given: list[str] = []
    complete = s.structured
    if _names_fields(s.argv):
        complete = complete and s.body is not None
        if s.body is not None:
            try:
                given = _field_options(argv, s.body)
            except UsageError as exc:
                return f"{' '.join(argv)}: {exc}"
    for variant in _variants(argv):
        try:
            ns = parse([*variant, *given], complete=complete)
        except ParseFail as exc:
            return f"{' '.join(variant)}: {exc}"
        if command_words(variant)[:2] == ("lead", "tool"):
            name = getattr(ns, "name", None)
            if isinstance(name, str) and not is_placeholder(name):
                from aew.surface.contract import TOOLS

                if name not in TOOLS:
                    return f"typed tool {name!r} is not in contract.TOOLS"
    return None


def o_ids(s: Suggestion) -> list[str]:
    """The id-typed values and placeholders ``s`` asks for, decided by position (§2.2): by the parser's dest for each
    token, or, where the line does not parse, by an id option's value and the engine's id formats."""
    problems: list[str] = []
    argv = _strip(list(s.argv))
    try:  # the id options of the command this line names (the same option can be an id in one command only)
        id_options = {o for acts in _path_actions(command_words(argv)).values() for a in acts if is_id_action(a)
                      for o in a.option_strings}
    except (KeyError, StopIteration):
        id_options = set(_id_options())
    for i, token in enumerate(argv):
        if _is_id(token):
            problems.append(f"id {token}")
        elif i and argv[i - 1] in id_options:
            problems.append(f"{argv[i - 1]} {token}")
    for variant in _variants(argv)[:1]:
        try:
            ns = parse(variant, complete=False)
        except ParseFail:
            if any(t == "N" or (ANGLE.match(t) and t not in ("<T>", "<S>", "<E>")) for t in variant):
                problems.append("placeholder in an unparsed line")
            break
        actions = _path_actions(command_words(variant))
        for dest, value in vars(ns).items():
            items = value if isinstance(value, list) else [value]
            mine = actions.get(dest, ())
            for item in items:
                text = str(item)
                if item is None or text not in variant:
                    continue
                if any(is_id_action(a) for a in mine):
                    entry = f"{dest} {text}"
                    if entry not in problems and not any(text in p for p in problems):
                        problems.append(entry)
                elif (is_placeholder(text) and text not in ELISION and dest not in WORK_DESTS
                      and not any(a.choices for a in mine)):
                    problems.append(f"placeholder {text} for {dest}")
    return sorted(set(problems))


def _path_actions(words: tuple[str, ...]) -> dict[str, tuple[argparse.Action, ...]]:
    """``dest -> actions`` of the parsers ``words`` passes through (the program's own options included): the same
    dest names different arguments in different commands (``--since REVISION`` and ``--since UTC``)."""
    current, parsers = _parser(), [_parser()]
    for word in words:
        sub = next(a for a in current._actions if isinstance(a, argparse._SubParsersAction))
        current = sub.choices[word]
        parsers.append(current)
    out: dict[str, list[argparse.Action]] = {}
    for p in parsers:
        for a in p._actions:
            out.setdefault(a.dest, []).append(a)
    return {k: tuple(v) for k, v in out.items()}


# "Put" and "give" are left out: the product says what a command "would put" on standard output when it refuses.
ASK_VERBS = "set|export|copy|paste|pass|enter|type|supply"
# A credential's own name: an ask anywhere in the sentence. Its boundaries keep GITHUB_TOKEN and --token-file out.
# The verb nearest the name is the one that asks: "Never paste it, set X" must not be read from "paste".
NAMED_ASK = (rf"\b({ASK_VERBS})\b(?P<between>(?:(?!\b(?:{ASK_VERBS})\b)[^.;\n]){{0,80}}?)"
             r"(?<![\w-])(?P<what>{names})(?![\w-])")
# The bare words are ordinary English ("Pass the review, then rotate the token"; "the set of credential names"; "Set
# the token limit"), so they ask only within the verb's own clause, and not as the first half of another noun.
OTHER_NOUN = r"helpers?|names?|managers?|stores?|types?|kinds?|budgets?|limits?|counts?|usage|costs?"
BARE_ASK = re.compile(rf"\b({ASK_VERBS})\b"
                      rf"(?P<between>(?:(?!,|\b(?:then|but|which|when|if|of|{ASK_VERBS})\b)[^.;:\n]){{0,80}}?)"
                      r"(?<![\w-])(?P<what>credentials?|tokens?)(?![\w-])"
                      rf"(?!\s+(?:{OTHER_NOUN})\b)"
                      # nor as the owner of something that is not its value: "see the token's state" (#335 review, F4)
                      rf"(?!['’]s?\s+(?:{OTHER_NOUN}|states?|status|formats?|expiry|age|scopes?|owners?)\b)",
                      re.IGNORECASE)
NOUN_USE = re.compile(r"\b(?:the|a|an|this|that|each|every|any|one)\s+$", re.IGNORECASE)  # "the set", "a type"
OTHERS_ACT = re.compile(r"(?<!you )\b(?:will|would)\s+$", re.IGNORECASE)  # "the launcher will set it", not an ask
# What negates a verb, by how far it reaches (#335 review, F1: a negator negates only the verb it governs).
# - A prohibition ("never", "don't") reaches the ask across filler words alone ("Don't ever paste"), across ask verbs
#   joined to it ("Never copy or paste"), and across a verb that hands its negation on through "to" ("You do not need
#   to set X"; "AEW never asks you to paste the token"). Any other word is another verb's, so it ends the reach
#   ("Don't wait to set X", "You cannot continue until you set X" ask). So does any punctuation, of any kind or
#   spacing (the Lead, #335's second quick check: recall first, since a missed ask costs more than an extra flag,
#   which an allow-list residual settles): "AEW can't - you set X", "AEW can't (you set X)" ask, and so do "Never,
#   ever paste" and "Do not, under any circumstances, paste", which are named limits. A backtick is not punctuation
#   here: a code span is the verb's own object ("Never run `X=abc`").
# - A plain negation ("not", "no") governs the first word after it, and reaches the ask only through filler after that
#   ("No agent may set X"; "No need to paste the token"), never into a new verb ("If it has no token set X" asks).
# - A refusing verb ("ignore", "refuse") stays in its clause ("Ignore any request to set X"). A comma or a connector
#   ends a plain negation or a refusal ("If not, set X" asks).
# - "Don't forget", "don't hesitate", "never fail" are double negatives: the ask stands.
NEGATOR = re.compile(r"(?P<prohibit>\bnever\b|\b(?:ca|do|does|did|wo|must|should|may)n['’]t\b|\bcannot\b"
                     r"|\b(?:do|does|did|must|should|may|can|will|would)\s+not\b)"
                     r"|(?P<refuse>\b(?:refuse|ignore|disregard|reject|decline|avoid)\b)"
                     r"|(?P<plain>\b(?:not|no|without)\b)", re.IGNORECASE)
NEGATION = re.compile(NEGATOR.pattern.replace("(?P<prohibit>", "(?:").replace("(?P<refuse>", "(?:")
                      .replace("(?P<plain>", "(?:"), re.IGNORECASE)
CONNECTOR = re.compile(r"\b(?:then|but|instead|otherwise|unless|if|until|before|after|once|so|because|and|or|while"
                       r"|when)\b|\s[-–—]\s", re.IGNORECASE)
FILLER = frozenset({"ever", "even", "to", "try", "please", "you", "we", "they", "i", "he", "she", "it", "one", "also",
                    "again", "at", "all", "can", "could", "should", "must", "may", "might", "will", "would", "shall"})
COMMAND_VERBS = frozenset({"run", "use", "write", "print"})  # what governs a printed command line: "Never run `X=abc`"
DOUBLE_NEGATIVE = frozenset({"forget", "forgets", "forgetting", "hesitate", "hesitating", "fail", "failing"})
PASSES_ON = frozenset({"need", "needs", "have", "has", "ask", "asks", "want", "wants", "require", "requires", "expect",
                       "expects"})  # a prohibition over one of these negates the verb it hands on to: "need to set X"
NOT_ADVERBS = frozenset({"apply", "reply", "supply", "rely", "family"})  # ends in -ly, but not an adverb
# Any punctuation: everything but a word character, whitespace and a backtick, and a quote mark that is not an
# apostrophe inside a word ("don't").
PUNCTUATION = re.compile(r"[^\w\s`'’]|(?<!\w)['’]|['’](?!\w)")
# Ask verbs joined under one negator, each with up to four words of its own object: "Never set X or pass --token".
JOINED_ASKS = re.compile(rf"\b(?:{ASK_VERBS})\b(?:\s+[^\s,]+){{0,4}}?\s+(?:and|or)\s+", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.;:!?\n]")
HIDDEN_PROMPT = re.compile(r"\bat\s+(?:the\s+|a\s+|an\s+|its\s+|this\s+)?(?:hidden|silent|masked)\s+"
                           r"(?:[\w-]+\s+)?prompt\b", re.IGNORECASE)
PLAIN_PROMPT = re.compile(r"\bat\s+(?:the\s+|a\s+)?prompt\b", re.IGNORECASE)
NOTHING_ECHOED = re.compile(r"\bnothing\s+(?:echoes|is\s+echoed|is\s+shown)|\bnot\s+(?:shown|echoed)\b|\bno\s+echo\b",
                            re.IGNORECASE)
PIN_ASK = re.compile(r"\b(enter|type|provide|give|paste)\b[^.;\n]{0,40}?\bPIN\b", re.IGNORECASE)
CODE_ASK = re.compile(r"\b(enter|type|provide|give|paste)\b[^.;\n]{0,40}?\bcode\b", re.IGNORECASE)


@functools.cache
def _secret_ask() -> re.Pattern[str]:
    names = "|".join(re.escape(n) for n in credential_names())
    return re.compile(NAMED_ASK.replace("{names}", names), re.IGNORECASE)


@functools.cache
def _credential_variables() -> tuple[str, ...]:
    return tuple(n for n in credential_names() if not n.startswith("-"))


@functools.cache
def _assignment() -> re.Pattern[str]:
    """A credential variable given a value the reader types where it shows, with no verb to read:
    - a literal: ``X=abc aew status``, ``$env:X = 'abc'``, ``[Environment]::SetEnvironmentVariable('X', 'abc', ...)``;
    - any value made persistent: ``setx X ...``;
    - an unmasked ``Read-Host``, inline: ``$env:X = Read-Host ...``, ``= (Read-Host ...)``, ``= $(Read-Host ...)``.
    A value that is another variable, empty or a .NET call holds no literal (an unmasked read into a variable is
    :func:`_unmasked_reads`'), and the hidden-input forms are excused by ``per_session_hidden``. A ``<placeholder>``
    holds no literal, for now: it is the hand path's documented line (``docs/guides/quickstart.md``), and whether it
    stays is a product decision, not this rule's."""
    names = "|".join(re.escape(n) for n in _credential_variables())
    return re.compile(rf"(?<![\w$:.-])(?P<posix>{names})=(?![\s$`<]|$)"
                      rf"|\$\{{?env:(?P<ps>{names})\}}?\s*=\s*(?!\[|\$(?!\(\s*Read-Host\b)|<|''|\"\")\S"
                      rf"|\b(?:New|Set)-Item\b(?=[^\n;|]*-Value\s+[\"']?[^\s\"'$(<])[^\n;|]*?\bEnv:\\?(?P<item>{names})\b"
                      rf"|\bsetx\s+(?:/\w+\s+)*[\"']?(?P<setx>{names})[\"']?\s+\S"
                      rf"|SetEnvironmentVariable\(\s*[\"'](?P<net>{names})[\"']\s*,\s*[\"'][^\"']", re.IGNORECASE)


def _unmasked_reads(text: str) -> Iterator[tuple[str, int]]:
    """``(name, position)`` for a credential the reader types where it may show, read into a variable and then set:
    bash ``read`` naming it (its line is excused only when it is the hidden-input form, so ``-s`` with an echo still
    asks), or PowerShell ``$v = Read-Host ...`` (neither ``-MaskInput`` nor ``-AsSecureString``) and ``$env:X = $v``
    later in the same text."""
    names = _credential_variables()
    for line_start, line in ((m.start(), m.group(0)) for m in re.finditer(r"[^\n]+", text)):
        for command in COMMANDS.split(line):
            read = re.search(r"(?:^|[\s`])read\s+(.*)$", command.strip())
            if read:
                words = read.group(1).split()
                if words[-1:] and words[-1] in names:
                    yield words[-1], line_start + line.find(command.strip())
    for read in re.finditer(r"\$(\w+)\s*=\s*\(?\s*Read-Host\b([^;|\n]*)", text, re.IGNORECASE):
        if re.search(r"-(?:MaskInput|AsSecureString)\b", read.group(2), re.IGNORECASE):
            continue
        for name in names:
            set_from = re.compile(rf"\$\{{?env:{re.escape(name)}\}}?\s*=\s*\${read.group(1)}\b", re.IGNORECASE)
            found = set_from.search(text, read.end())
            if found:
                yield name, found.start()


# The per-session hidden-input form (the designer's decision of 2026-11-01, CS-4 addendum 12): a snippet that reads a
# credential's value where nothing echoes it and sets it for the session only is the safe path, not an ask to copy one.
COMMANDS = re.compile(r"\s*(?:;|&&|\|\|)\s*")  # one line's commands, in order
PERSISTENT_SET = re.compile(r"\bsetx\b|SetEnvironmentVariable|\[Environment\]", re.IGNORECASE)
FILE_WRITE = re.compile(r">|\b(?:Out-File|Add-Content|Set-Content|tee)\b|\.bashrc|\.profile|\.zshrc|\$PROFILE",
                        re.IGNORECASE)
# A whole-environment dump prints every value: bare `env`, `set`, `printenv`, `export -p`, `declare -p` (on its own or
# piped), or PowerShell's `env:` drive listed.
DUMP = re.compile(r"^(?:env|set|printenv|export\s+-p|(?:declare|typeset)\s+-\w*p\w*)\s*(?:$|\|)"
                  r"|\b(?:Get-ChildItem|gci|dir|ls|Get-Item)\s+env:", re.IGNORECASE)


def _reads_hidden(command: str, name: str) -> bool:
    """Whether ``command`` reads ``name``'s value where nothing echoes it: bash `read` with `-s` whose last word is
    ``name``, or PowerShell `$env:name = Read-Host ... -MaskInput`."""
    n = re.escape(name)
    read = re.search(r"(?:^|[\s`])read\s+(.*)$", command)
    if read:
        words = read.group(1).split()
        options = [w for w in words[:-1] if w.startswith("-") and not w.startswith("--")]
        return words[-1:] == [name] and any("s" in w[1:] for w in options)
    return bool(re.search(rf"\$env:{n}\s*=\s*\$?\(?\s*Read-Host\b[^;|]*-MaskInput\b", command, re.IGNORECASE))


def _reads_secure(commands: list[str], name: str) -> bool:
    """Whether ``name`` is set from a SecureString the operator typed: `$v = Read-Host ... -AsSecureString`, then
    `$env:name = ...SecureStringToBSTR($v)...` in a later command."""
    n = re.escape(name)
    for i, command in enumerate(commands):
        read = re.search(r"\$(\w+)\s*=\s*Read-Host\b[^;|]*-AsSecureString\b", command, re.IGNORECASE)
        if read and any(re.search(rf"\$env:{n}\s*=\s*[^;|]*SecureStringToBSTR\(\s*\${read.group(1)}\s*\)", later,
                                  re.IGNORECASE) for later in commands[i + 1:]):
            return True
    return False


def per_session_hidden(snippet: str, name: str) -> bool:
    """Whether ``snippet`` (one line: a command, or a guide's line of code) is the per-session hidden-input form for
    the credential ``name``, on all five of the decision's conditions: (1) ``name``'s value is read by a hidden-input
    form (bash `read -s` naming it, PowerShell `$env:name = Read-Host -MaskInput`, or `Read-Host -AsSecureString` and
    its conversion assigned to `$env:name`); (2) it is exported or set for the session only; (3) no literal value
    appears; (4) nothing is written to a startup or profile file, or to any other file; (5) the value is never
    echoed: no printer naming it (`echo`, `printf`, `printenv`, `declare -p`, `Write-Output` and the like), no bare
    `$name` or `$env:name` as a command, no whole-environment dump.

    Limits (review of #316, m2): the line is read, not run. An alias, a function, `eval`, a command held in a
    variable, or a value printed by a program the line starts is not seen; the hidden read is bound to ``name``, not
    to what a later command does with the value."""
    n = re.escape(name)
    # the line's code (its code spans, or all of it), one command at a time, without a trailing comment (`# bash`)
    code = "; ".join(re.findall(r"`([^`]+)`", snippet)) or snippet
    commands = [c for c in (re.sub(r"\s+#.*$", "", c).strip() for c in COMMANDS.split(code)) if c]
    literal = re.compile(rf"\b{n}=(?!\$)\S|\$env:{n}\s*=\s*['\"]|--token(?![-\w])[ \t]*(?:=|[ \t])[ \t]*(?!-)\S",
                         re.IGNORECASE)
    printer = re.compile(rf"\b(?:echo|printf|print|printenv|Write-Host|Write-Output|cat)\b[^;|\n]*{n}"
                         rf"|\b(?:declare|typeset)\s+-\w*p\w*\b[^;|\n]*{n}", re.IGNORECASE)
    bare = re.compile(rf"[\"']?\$(?:env:)?\{{?{n}\}}?[\"']?", re.IGNORECASE)
    echoed = any(printer.search(c) or bare.fullmatch(c) or DUMP.search(c) for c in commands)
    return ((any(_reads_hidden(c, name) for c in commands) or _reads_secure(commands, name))
            and not PERSISTENT_SET.search(snippet) and not literal.search(snippet)
            and not FILE_WRITE.search(snippet) and not echoed)


def _negated(text: str, at: int, *, governs: frozenset[str] = frozenset()) -> bool:
    """Whether the ask at ``at`` is negated from before it, in its own sentence (see ``NEGATOR``). ``governs``: words
    that may stand between a prohibition and the ask as its own verb (``run`` before a printed command line)."""
    start = max(max((m.end() for m in SENTENCE_END.finditer(text, max(0, at - 160), at)), default=0), at - 160)
    before = text[start:at]
    negators = list(NEGATOR.finditer(before))
    if not negators:
        return False
    last = negators[-1]
    between = JOINED_ASKS.sub(" ", before[last.end():])
    words = _words(between)
    content = [w for w in words if not _filler(w)]
    if content[:1] and content[0] in DOUBLE_NEGATIVE:
        return False
    if last.group("prohibit"):
        if PUNCTUATION.search(between):
            return False
        # a connector is another word: "Never skip this step and set X", "until you set X"
        return all(_filler(w) or w in governs | PASSES_ON for w in words)
    if "," in between or CONNECTOR.search(between):
        return False
    if last.group("refuse") or not content:
        return True
    # a plain negator governs its first word, and reaches the ask only through filler after it
    tail = words[words.index(content[0]) + 1:]
    return bool(tail) and all(_filler(w) for w in tail)


DETERMINERS = frozenset({"the", "a", "an", "your", "my", "our", "their", "its", "this", "that"})


def _negated_within(between: str) -> bool:
    """Whether the ask's own span, from its verb to the credential, negates it ("Pass no token"; "Copy everything but
    not the token"). A plain negator there negates only what it governs (#335's second quick check, Q3): "Paste the
    value with no spaces into X" asks."""
    negators = list(NEGATOR.finditer(between))
    if not negators:
        return False
    last = negators[-1]
    return not last.group("plain") or all(_filler(w) or w in DETERMINERS for w in _words(between[last.end():]))


def _words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z’']+", text)]


def _filler(word: str) -> bool:
    """A word that changes nothing a negator governs: ``FILLER``, or an adverb in -ly ("Never directly paste")."""
    return word in FILLER or (word.endswith("ly") and len(word) > 4 and word not in NOT_ADVERBS)


def _lines_around(text: str, start: int, end: int) -> tuple[str, str, list[str]]:
    """The whole line holding ``text[start:end]``; the next line with text on it, past a code fence's own line; and the
    lines above it with text on them: inside a fenced block, every one of the block's, in order, and outside one, the
    line just above (so another block's read never counts)."""
    first, last = text.rfind("\n", 0, start) + 1, text.find("\n", end)
    line = text[first:] if last < 0 else text[first:last]
    below = "" if last < 0 else next((ln for ln in text[last + 1:].splitlines()
                                      if ln.strip() and not FENCE.match(ln)), "")
    lines = text[:max(0, first - 1)].splitlines()
    fences = [i for i, ln in enumerate(lines) if FENCE.match(ln)]
    above = [ln for ln in (lines[fences[-1] + 1:] if len(fences) % 2 else lines[-1:]) if ln.strip()]
    return line, below, above


# The hidden-input form answers an ask to set a credential for this session, and no other: a form below "paste X into
# the worker's chat" does not hand anything over safely (#335 review, F3). A prompt that shows nothing answers an ask
# to type or enter the value there, and no other ("pass the token at the prompt" still hands it over).
FORM_ANSWERS = frozenset({"set", "export"})
PROMPT_ANSWERS = frozenset({"type", "enter"})


def _sanctioned(text: str, m: re.Match[str], plane: str) -> bool:
    """The safe path, which must never read as a violation (the operator: friction is a security cost): an ask to set
    or export the credential whose line is the per-session hidden-input form, or has it on the next line, or finishes
    it below a hidden read earlier in the same block (one command a line), with nothing between that breaks the form;
    or (for a reader with hands at a terminal, so never a model) an ask to type or enter the value at a prompt that
    shows nothing."""
    what = m.group("what")
    line, below, above = _lines_around(text, m.start(), m.end())
    names = (what,) if what.lower() not in ("credential", "credentials", "token", "tokens") else _credential_variables()
    if m.group(1).lower() in FORM_ANSWERS and any(
            per_session_hidden(line, n) or (below and per_session_hidden(below, n))
            or any(per_session_hidden("; ".join([*above[i:], line]), n) for i in range(len(above))) for n in names):
        return True
    if plane == MODEL or m.group(1).lower() not in PROMPT_ANSWERS:
        return False
    after = line[m.end() - text.rfind("\n", 0, m.start()) - 1:]
    return bool(HIDDEN_PROMPT.search(after) or (PLAIN_PROMPT.search(after) and NOTHING_ECHOED.search(after)))


def o_secret(text: str, plane: str) -> list[str]:
    """§2.2, m4: a PIN asked for anywhere but the operator console; a code asked for anywhere but the requesting
    terminal (so never of a model); a credential the reader is asked to set, copy or pass, by name or in its own
    clause, or a credential variable given a literal value, unless it is the safe path (:func:`_sanctioned`)."""
    problems = []
    named = list(_secret_ask().finditer(text))
    spans = [m.span() for m in named]
    bare = [m for m in BARE_ASK.finditer(text) if not any(a <= m.start() < b for a, b in spans)]
    for m in (*named, *bare):
        before = text[max(0, m.start() - 12):m.start()]
        if NOUN_USE.search(before) or OTHERS_ACT.search(before) or _sanctioned(text, m, plane):
            continue
        if not _negated_within(m.group("between")) and not _negated(text, m.start()):
            problems.append(f"asks to {m.group(1).lower()} {m.group('what')}")
    assigned = [(m.group("posix") or m.group("ps") or m.group("setx") or m.group("net") or m.group("item"), m.start())
                for m in _assignment().finditer(text)]
    for name, at in sorted([*assigned, *_unmasked_reads(text)], key=lambda found: found[1]):
        line, _, _ = _lines_around(text, at, at)
        asked = any(p.endswith(f" {name}") for p in problems)  # `export X=abc` is one ask, and its key stays
        if not asked and not per_session_hidden(line, name) and not _negated(text, at, governs=COMMAND_VERBS):
            problems.append(f"asks to set {name}")
    if plane != CONSOLE and PIN_ASK.search(text):
        problems.append("asks for a PIN outside the operator console")
    if plane == MODEL and CODE_ASK.search(text):
        problems.append("asks a model for a code")
    return problems


def refusal_schema(refusal: dict[str, Any]) -> dict[str, Any] | None:
    details = refusal.get("details") or {}
    source = refusal if all(k in refusal for k in REFUSAL_SCHEMA) else details
    return {k: source[k] for k in REFUSAL_SCHEMA} if all(k in source for k in REFUSAL_SCHEMA) else None


def o_code(code: str, cause: str, registry: dict[str, frozenset[str]]) -> str | None:
    """A refusal's code against the registry (§2.3): the code must be registered and allow the cause."""
    if code not in registry:
        return f"{code} is not in the code registry"
    if cause not in registry[code]:
        return f"{code} does not allow the cause {cause!r} (allowed: {', '.join(sorted(registry[code]))})"
    return None


def credential_argument(s: Suggestion) -> str | None:
    """A suggested input that supplies a credential option (``--token <credential>``) asks its reader for the
    credential (§2.2, O-SECRET: "asking the operator to copy or set a credential")."""
    options = {n for n in credential_names() if n.startswith("-")}
    given = next((t for t in s.argv if t.split("=", 1)[0] in options), None)
    return f"asks to pass {given.split('=', 1)[0]}" if given else None


def judge(s: Suggestion) -> list[tuple[str, str]]:
    """``(rule, why)`` for every finding on one suggested input: O-CMD, O-IDS and O-SECRET's credential argument."""
    out: list[tuple[str, str]] = []
    why = o_cmd(s)
    if why:
        out.append(("O-CMD", why))
    if s.argv:
        problems = o_ids(s)
        if problems:
            out.append(("O-IDS", "; ".join(problems)))
        secret = credential_argument(s)
        if secret:
            out.append(("O-SECRET", secret))
    return out


def check(output: Output, registry: dict[str, frozenset[str]] | None = None) -> list[Finding]:
    """Every finding of O-IDS, O-CMD, O-WORDS, O-CODE and O-SECRET on ``output`` (O-ENV is static only)."""
    findings: list[Finding] = []
    site = output.site
    for s in suggestions(output):
        if _echoed(s, output):
            continue
        findings.extend(Finding(rule, site, why) for rule, why in judge(s))
    for tool in _tool_names(output.payload):
        from aew.surface.contract import TOOLS

        if tool not in TOOLS:
            findings.append(Finding("O-CMD", site, f"typed tool {tool!r} is not in contract.TOOLS"))
    texts = [output.text, *_strings(output.payload)]
    if output.refusal:
        texts.append(str(output.refusal.get("message") or ""))
        schema = refusal_schema(output.refusal)
        if schema is None:
            findings.append(Finding("O-WORDS", site, "unstructured refusal"))
        # O-CODE's scope (§2.3, H5): only a refusal whose cause is known, injected by an explorer or stated by the
        # refusal schema. Nothing in the existing suite is either yet.
        cause = output.injected_cause or (schema or {}).get("cause")
        if cause and registry is not None:
            why = o_code(str(output.refusal.get("code")), str(cause), registry)
            if why:
                findings.append(Finding("O-CODE", site, why))
    for text in texts:
        findings.extend(Finding("O-SECRET", site, p) for p in o_secret(text, output.plane))
    return dedupe(findings)


def _tool_names(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "tool" and isinstance(v, str):
                yield v
            else:
                yield from _tool_names(v)
    elif isinstance(value, list):
        for v in value:
            yield from _tool_names(v)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    seen: dict[str, Finding] = {}
    for f in findings:
        seen.setdefault(f.key, f)
    return list(seen.values())


def tool_argument_secrets() -> list[Finding]:
    """O-SECRET over the typed surface itself: a typed tool whose arguments ask for a PIN, a code or a credential
    (§2.2: "asking for either ... as a typed-tool argument is always a violation"). Read from contract.TOOLS."""
    from aew.surface.contract import TOOLS

    asks = re.compile(r"^(pin|code|one_time_code|token|credential|secret|password)$", re.IGNORECASE)
    out = []
    for name, t in sorted(TOOLS.items()):
        for prop in sorted(t.input_schema.get("properties") or {}):
            if asks.match(prop):
                out.append(Finding("O-SECRET", f"tool-arguments:{name}", f"argument {prop}"))
    return out


# ---------------------------------------------------------------------------------------------- O-ENV

ENV_MARK = "Checks run in a scrubbed environment"
NO_OTHER = "No other variable reaches a check"
FOREIGN_PROBE = "D2_PROBE_NOT_ALLOWLISTED"


def check_environment() -> tuple[list[str], bool]:
    """What the check path actually keeps (review of #218, m5): ``Validation._check_env``, the environment every
    validation check runs in, probed with every variable the allowlists name, an ``LC_`` variable and one foreign
    variable. Returns the kept names (``LC_*`` for the locale family) and whether a variable outside them reaches a
    check (the "how to give a check a variable": the code has no such mechanism when it does not)."""
    import os
    from types import SimpleNamespace
    from unittest import mock

    from aew.engine.validation_ops import Validation
    from aew.harness import agentenv

    candidates = {*agentenv.WINDOWS_KEEP, *agentenv.POSIX_KEEP, "PATH", "LC_ALL"}
    probe = {name: os.environ.get(name, "d2-probe") for name in candidates}  # existing values are left as they are
    with mock.patch.dict(os.environ, {**probe, FOREIGN_PROBE: "1"}):
        env = Validation._check_env(SimpleNamespace(env={}))
    kept = {("LC_*" if k.upper().startswith("LC_") else k.upper()) for k in env if k.upper() != FOREIGN_PROBE}
    return sorted(kept), FOREIGN_PROBE in {k.upper() for k in env}


def env_statement() -> list[str]:
    """What the Lead's guide and system text must state about the check environment (§2.2, O-ENV; U15), generated
    from the check path on this platform: the statement, every variable it keeps, and, as the code has no way to give
    a check another variable, that none does."""
    kept, passes_others = check_environment()
    return [ENV_MARK, *kept, *([] if passes_others else [NO_OTHER])]


def o_env(text: str) -> list[str]:
    """The parts of the generated check-environment statement ``text`` lacks."""
    lowered = text.lower()
    missing = []
    for part in env_statement():
        if part in (ENV_MARK, NO_OTHER):
            if part.lower() not in lowered:
                missing.append(f"the statement {part!r}")
        elif not re.search(rf"(?<![A-Za-z0-9_]){re.escape(part)}(?![A-Za-z0-9_])", text):
            missing.append(part)
    return missing


# ---------------------------------------------------------------------------------------------- refusals in output

def refusal_of(stderr: str) -> dict[str, Any] | None:
    """The CLI's refusal shape (``{"ok": false, "error": {code, message, details}}``) on stderr, else ``None``."""
    text = stderr.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    error = data.get("error") if isinstance(data, dict) else None
    return error if isinstance(error, dict) and "code" in error else None

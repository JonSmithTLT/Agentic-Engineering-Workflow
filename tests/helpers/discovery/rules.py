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
    prose elsewhere may name a command without its required arguments (a mention, not an error)."""

    argv: tuple[str, ...]
    text: str
    structured: bool


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


@functools.cache
def _parser() -> argparse.ArgumentParser:
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
    for found in _prose_commands(text):
        yield from (c.strip() for c in re.split(r"\s(?:&&|;)\s(?=aew\s)", found))


def _prose_commands(text: str) -> Iterator[str]:
    in_fence, pending = False, ""
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence, pending = not in_fence, ""
            continue
        if in_fence:
            body = (pending + " " + line.strip()).strip() if pending else line.strip().removeprefix("$ ").strip()
            if body.endswith("\\"):  # a continued line: the command goes on below
                pending = body[:-1].rstrip() if (pending or body.startswith("aew ")) else ""
                continue
            pending = ""
            if body.startswith("aew "):
                yield re.split(r"\s+#\s", body, maxsplit=1)[0].rstrip()
            continue
        for m in SPAN.finditer(line):
            span = m.group(1).strip()
            if span.startswith("aew "):  # a bare `aew` names the program, not a command line
                yield span


def _field_commands(value: str) -> Iterator[str]:
    """A suggested field's text: its backticked spans, or else the command it names in words (``... : aew x y``)."""
    spans = list(prose_commands(value))
    if spans:
        yield from spans
        return
    m = re.search(r"(?:^|\s)(aew\s[^;`]*)", value)
    if m:
        yield re.split(r"(?<=\S)[.,)](?:\s|$)", m.group(1), maxsplit=1)[0].strip()


def suggestions(output: Output) -> list[Suggestion]:
    out: list[Suggestion] = []

    def add(text: str, structured: bool, argv: list[str] | None = None) -> None:
        tokens = argv if argv is not None else _tokens(text)
        if tokens is None:
            out.append(Suggestion((), text, structured))
            return
        if tokens and tokens[0] == "aew":
            tokens = tokens[1:]
        out.append(Suggestion(tuple(tokens), text, structured))

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
            for cmd in (_field_commands(value) if suggested else prose_commands(value)):
                add(cmd, suggested)

    walk(output.payload, False)
    if output.text:
        for cmd in prose_commands(output.text):
            add(cmd, False)
    if output.refusal:
        for cmd in prose_commands(str(output.refusal.get("message") or "")):
            add(cmd, False)
    seen: set[tuple[tuple[str, ...], str]] = set()
    unique = []
    for s in out:
        if (s.argv, s.text) not in seen:
            seen.add((s.argv, s.text))
            unique.append(s)
    return unique


def _echoed(s: Suggestion, output: Output) -> bool:
    if output.refusal is None or not output.echo:
        return False
    given = " ".join(output.echo)
    return bool(s.argv) and " ".join(s.argv) in given


# ---------------------------------------------------------------------------------------------- the rules

def o_cmd(s: Suggestion) -> str | None:
    """Why ``s`` does not parse (parse-only, placeholders as values), or ``None``."""
    if not s.argv:
        return f"not a command line: {s.text!r}" if s.text else None
    argv = _strip(list(s.argv))
    for variant in _variants(argv):
        try:
            ns = parse(variant, complete=s.structured)
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
SECRET_ASK = re.compile(r"\b(set|export|copy|paste|pass|enter|type|supply)\b(?P<between>[^.;\n]{0,80}?)"
                        r"(?P<what>{names})", re.IGNORECASE)
NEGATION = re.compile(r"\b(never|not|no|without)\b", re.IGNORECASE)
PIN_ASK = re.compile(r"\b(enter|type|provide|give|paste)\b[^.;\n]{0,40}?\bPIN\b", re.IGNORECASE)
CODE_ASK = re.compile(r"\b(enter|type|provide|give|paste)\b[^.;\n]{0,40}?\bcode\b", re.IGNORECASE)


@functools.cache
def _secret_ask() -> re.Pattern[str]:
    names = "|".join(re.escape(n) for n in (*credential_names(), "credential", "token"))
    return re.compile(SECRET_ASK.pattern.replace("{names}", names), re.IGNORECASE)


def o_secret(text: str, plane: str) -> list[str]:
    """§2.2, m4: a PIN asked for anywhere but the operator console; a code asked for anywhere but the requesting
    terminal (so never of a model); a credential the reader is asked to set, copy or pass."""
    problems = []
    for m in _secret_ask().finditer(text):
        if not NEGATION.search(m.group("between")) and not NEGATION.search(text[max(0, m.start() - 12):m.start()]):
            problems.append(f"asks to {m.group(1).lower()} {m.group('what')}")
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

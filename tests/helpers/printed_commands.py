"""Every `aew` command AEW prints, found in ``src/`` and parsed as printed (ITEMS 56; #311 review F2, F3; #312 F2).

A printed command is what a refusal, a result's next action, a resume or status line, or the guide tells a reader to
run. It must run as printed: complete, with every required option, once its placeholders are filled. This module owns
the three pieces the checks share:

- ``PLACEHOLDERS``: every ``<...>`` a printed command may hold, with the value a reader puts there. Any other ``<...>``
  is a defect: the reader cannot know what to put there.
- ``parse``: one printed command as a reader runs it: a fenced ``sh`` block is one command line ending
  ``--fields - <<'EOF'``, a body, and ``EOF`` alone (``aew.harness.contract.fields_command``'s frame); the body goes
  through the CLI's own ``fields.expand``, and the result through the real ``build_parser()``, never a lenient one.
- two finders, written independently, so that each checks the other: ``ast_sites`` (the check's recogniser, over the
  syntax tree) and ``token_sites`` (over the token stream).

How sites are found: every string literal in ``src/aew`` (a constant, an f-string, ``+`` of those, and a conditional
expression's first branch) that is not a docstring or an argparse ``help``/``description``/``epilog``/``usage``, and
in it each code span that starts ``aew `` and each fenced ``sh`` block; a literal starting ``aew `` given to a
suggested-input field (``rules.SUGGESTED_FIELDS``: ``next``, ``next_action``, ``remedy``...) as a keyword or a dict
key; each ``fields_command(...)`` or ``fields_block(...)`` call, whose block the owner renders from the call's literal
arguments; and each list literal given to a ``cli`` or ``cli_fallback`` key or keyword, an argv the projection offers
to be run as given (``aew`` prepended unless it is the list's first word; #319 review F1).

What the finders cannot see (each with a probe in the check's tests where one can be written):
- a command word from a value (``custody_ops``' ``f"`aew {command}`"``): no fill can stand for it, so the site is in
  the check's exemption table and a test renders it for each value it takes; a span that opens with a value
  (``harness_ops``' `{command} {wid} ...`) is not seen at all, and a test renders it the same way;
- a slot that renders several words or quotes (``{' '.join(argv)}``, an argv list's ``*live``) is filled as one word;
- text joined at run time (``transitions.next_steps`` formats commands from a table and joins them), and a literal
  inside an f-string's replacement field;
- an argv list that is not a literal at the key: one held in a variable first (``surface.projection``'s
  ``cli_fallback=cli``, ``x["cli"]``, the comprehension filling ``{evidence}``), and ``gate_ops.stale_invocations``'
  ``commands``, which is neither key;
- a ``fields_command`` whose command is a variable (``stage_intents``' ``cancel_command``): neither finder renders it,
  and its guidance test renders the message instead;
- a bare command in a dict key outside ``SUGGESTED_FIELDS`` (``recall``'s ``expand``, ``knowledge.render``'s
  ``history``);
- anything outside ``src/aew``'s ``*.py`` files: the role archetypes' YAML (``roles/archetypes/*.yaml``) prints
  `aew resume` and `aew plan adopt`, mentions both, unchecked here;
- more than 16 alternatives in one command: ``discovery.rules._variants`` keeps the first 16.

The two finders share their needles (`` `aew ``, ```` ```sh ````, ``SUGGESTED_FIELDS``, ``TEXT_KEYWORDS``, the argv
keys), so their agreement shows that each reads the source the same way, line by line, not that the needles cover every
printed command: what they miss together is the list above.
"""

from __future__ import annotations

import argparse
import ast
import functools
import io
import re
import shlex
import sys
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discovery.rules import SUGGESTED_FIELDS, _variants

from aew.harness import contract as K

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "aew"

# Every placeholder a printed command may hold, and what a reader puts there. A placeholder names where its value comes
# from; one not listed here fails the check.
PLACEHOLDERS: dict[str, str] = {
    K.REVISION: "17",
    "<invocation from aew harness status>": "INV-0012",
    # The guide's and the packs' forms: each names what goes there, and the reader knows where to find it.
    "<T>": "T-0007",  # a Ticket
    "<S>": "S-0002",  # a Story or an Epic
    "<unit>": "T-0008",  # a work unit
    "<id>": "EV-0003",  # a record: evidence, or a finished unit's history record
    "<E>": "EV-0004",  # an evidence record
    "<n>": "2",  # a plan revision
    "<candidate>": "C-001",  # an authority candidate
    "<card>": "default",  # a role card
    "<check id>": "unit",  # the same, as each text spells it
    "<check-id>": "unit",
    "<check>": "unit",
    "<kind>": "implementation_report",  # an expected output's kind
    "<file>": "report.md",  # a report file, as each text spells it
    "<that file>": "report.md",
    "<your-report.md>": "report.md",
    "<0-4>": "2",  # a risk class
    "<STATE>": "REVIEW_PENDING",
    "<CLASS>": "LOCAL_IMPLEMENTATION_DEFECT",  # a verification failure's classification
    "<reason>": "why",
    "<why>": "why",  # the projection's argv lists
    "<classification>": "LOCAL_IMPLEMENTATION_DEFECT",
    "<phase>": "RUNNING",  # the phase an INTERRUPTED Ticket was interrupted from
    "{evidence}": "EV-0005",  # the projection's own marker, replaced by each report's id before it is offered
    "<value>": "value",  # a fields_command value the code computes
    "<title>": "Title",
    "<goal>": "goal",
    "<clause>": "clause",
    "<path glob>": "src/**",
    "<command>": "status",  # any aew command, after a global option
}

# The printed text's owners (``aew.harness.contract``): a replacement field naming one is its value, not a slot.
OWNED: dict[str, str] = {"EXPECT_REV": K.EXPECT_REV, "REVISION": K.REVISION}

TEXT_KEYWORDS = frozenset({"help", "description", "epilog", "usage"})  # argparse's own text, not a printed command
SPAN = re.compile(r"`(aew [^`]*)`")
FENCE = re.compile(r"```sh\n(.*?)\n```", re.DOTALL)
HEREDOC = " <<'EOF'"
ANGLE = re.compile(r"<[^<>\s][^<>]*>")
SLOT = re.compile("\x01(\\d+)\x02")  # an f-string's replacement field, held apart from the text while it is checked


class PrintedCommandError(Exception):
    """A printed command that does not run as printed; the message says why."""


@dataclass(frozen=True)
class Site:
    """One printed command in the source: where, how it is printed, and its text. An f-string's replacement fields are
    slots (``\\x01n\\x02``), named by ``exprs``; ``shown`` puts them back as ``{expr}``."""

    path: str
    line: int
    # "span" (inline code), "fence" (a fenced sh block), "field" (a suggested-input field's whole value), "argv" (a
    # ``cli``/``cli_fallback`` list, joined), or "unreadable" (a module the finder could not read; ``text`` says why)
    kind: str
    text: str
    exprs: tuple[str, ...] = ()

    @property
    def shown(self) -> str:
        return SLOT.sub(lambda m: "{" + self.exprs[int(m.group(1))] + "}", self.text)

    @property
    def key(self) -> str:
        return f"{self.path}:{self.line}"


# ---------------------------------------------------------------------------------------------- parsing as printed

class _Refused(Exception):
    pass


def _raise(message: str) -> None:
    raise _Refused(message)


def _exit(*_: Any, **__: Any) -> None:
    raise _Refused("")  # --help: the command exists; parse_args then stops


@functools.cache
def parser() -> argparse.ArgumentParser:
    """The real ``aew`` parser, every command registered, made to raise instead of exiting. Nothing is relaxed: types,
    choices and required options are the CLI's own."""
    from aew.cli.main import build_parser

    root = build_parser(recall_search=True, coordination_reads=True)
    todo, seen = [root], []
    while todo:
        p = todo.pop()
        if any(p is q for q in seen):
            continue
        seen.append(p)
        p.error = _raise  # type: ignore[method-assign]
        p.exit = _exit  # type: ignore[method-assign]
        p._print_message = lambda *_a, **_k: None  # type: ignore[method-assign]
        todo += [c for a in p._actions if isinstance(a, argparse._SubParsersAction) for c in a.choices.values()]
    return root


def _subcommand_dests() -> frozenset[str]:
    out, todo = set(), [parser()]
    while todo:
        p = todo.pop()
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                out.add(a.metavar or a.dest)
                out.add(a.dest)
                todo += list(a.choices.values())
    return frozenset(x for x in out if x)


def split(command: str, fenced: bool) -> tuple[str, str | None]:
    """A printed command's line and its heredoc body (``None``: inline). Raises on a broken frame."""
    if not fenced:
        if "\n" in command or "<<" in command:
            raise PrintedCommandError(f"an inline command is one line, without a heredoc: {command!r}")
        return command, None
    head, sep, rest = command.partition(HEREDOC + "\n")
    if not sep or not head.endswith(" --fields -"):
        raise PrintedCommandError(f"a fenced block is one line ending `--fields -{HEREDOC}`, then a body: {command!r}")
    if "\n" in head:
        raise PrintedCommandError(f"a fenced block's command is one line: {command!r}")
    if not rest.endswith("\nEOF") and rest != "EOF":
        raise PrintedCommandError(f"the heredoc is not closed by a line `EOF` alone: {command!r}")
    body = rest[: -len("EOF")]
    if "\nEOF\n" in "\n" + body:
        raise PrintedCommandError(f"the heredoc closes early: a body line is `EOF`: {command!r}")
    return head, body


CHOICES = re.compile(r"<([\w-]+(?:\|[\w-]+)+)>")  # `<a|b|c>`: the reader picks one of the words listed


def fill(text: str) -> str:
    """Every listed placeholder replaced by its value, and a list of choices (``<a|b>``) made the alternatives each
    parsed (``a|b``); raises on any other placeholder."""
    for name, value in PLACEHOLDERS.items():
        text = text.replace(name, value)
    text = CHOICES.sub(r"\1", text)
    left = ANGLE.findall(text)
    if left:
        raise PrintedCommandError(f"a placeholder that is not in PLACEHOLDERS: {', '.join(left)}")
    return text


def _parse_argv(argv: list[str], body: str | None) -> argparse.Namespace:
    from aew.cli import fields
    from aew.errors import UsageError

    old = sys.stdin
    sys.stdin = io.StringIO(body or "")
    try:
        return parser().parse_args(fields.expand(argv, parser()))
    except UsageError as exc:
        raise _Refused(str(exc)) from None
    finally:
        sys.stdin = old


INVALID = re.compile(r"argument (?P<dest>[^:]+): invalid (?:choice: '(?P<v>[^']*)' \(choose from (?P<c>[^)]*)\)"
                     r"|(?P<t>int|float) value: '(?P<w>[^']*)')")


def parse(command: str, *, fenced: bool, exprs: tuple[str, ...] = ()) -> list[argparse.Namespace]:
    """Parse one printed command as a reader runs it; one namespace per alternative it offers (``a|b``). Slots
    (``\\x01n\\x02``) are an f-string's values, unknown here: each is filled with a word, and where the parser wants a
    choice or a number there, its first choice or 1. Raises ``PrintedCommandError`` saying why it does not run."""
    head, body = split(command, fenced)
    head, body = fill(head), (fill(body) if body is not None else None)
    words = {i: f"V{i}x" for i in range(len(exprs) or 32)}
    head = SLOT.sub(lambda m: words[int(m.group(1))], head)
    if body is not None:
        body = SLOT.sub(lambda m: words[int(m.group(1))], body)
    try:
        tokens = shlex.split(head)
    except ValueError as exc:
        raise PrintedCommandError(f"not one shell command line ({exc}): {head!r}") from None
    if not tokens or tokens[0] != "aew":
        raise PrintedCommandError(f"not an aew command: {head!r}")
    if "..." in tokens:  # run as printed it records "...": the reader cannot know it stands for a value (#319 F4)
        raise PrintedCommandError(f"an elided value `...`, not a named placeholder: {head!r}")
    out = []
    for variant in _variants(tokens[1:]):
        for _attempt in range(8):
            try:
                out.append(_parse_argv(variant, body))
                break
            except _Refused as exc:
                why = str(exc)
                m = INVALID.search(why)
                value = m and (m.group("v") or m.group("w"))
                if not why or (value and value not in words.values()):
                    if not why:
                        out.append(argparse.Namespace(command=None))
                        break
                    raise PrintedCommandError(f"`aew {shlex.join(variant)}`: {why}") from None
                if not m or not value:
                    raise PrintedCommandError(f"`aew {shlex.join(variant)}`: {why}") from None
                if m.group("dest") in _subcommand_dests():
                    raise PrintedCommandError(f"a command word comes from a value ({why}); the finder cannot check "
                                              f"it: `aew {shlex.join(variant)}`") from None
                stand_in = "1" if m.group("t") else m.group("c").split(",")[0].strip().strip("'")
                variant = [stand_in if t == value else t for t in variant]
        else:
            raise PrintedCommandError(f"`aew {shlex.join(variant)}`: no stand-in parses")
    return out


def mention(command: str) -> bool:
    """Whether an inline command is a mention: a bare command path, every word a real (sub)command of the parser and
    nothing else (``aew manifest adopt``; each of ``aew harness stop|wait``). A mention names a command and is not
    held to its required arguments (the Lead's ruling, ITEMS 56 (1)); one word that is not a command makes it a command
    line, which must parse."""
    try:
        tokens = shlex.split(fill(command))
    except (ValueError, PrintedCommandError):
        return False
    if len(tokens) < 2 or tokens[0] != "aew":
        return False
    for variant in _variants(tokens[1:]):
        current = parser()
        for word in variant:
            sub = next((a for a in current._actions if isinstance(a, argparse._SubParsersAction)), None)
            if sub is None or word not in sub.choices:
                return False
            current = sub.choices[word]
    return True


def check(command: str, kind: str, exprs: tuple[str, ...] = ()) -> None:
    """One site's command, judged as printed: a mention passes when its path is real; anything else must parse.
    Raises ``PrintedCommandError``."""
    if kind == "unreadable":
        raise PrintedCommandError(f"the finder could not read it: {command}")
    if kind == "span" and not SLOT.search(command) and mention(command):
        return
    parse(command, fenced=kind == "fence", exprs=exprs)


def commands(message: str) -> list[tuple[str, bool]]:
    """Every command a rendered message prints: each fenced ``sh`` block, then each inline code span outside the
    blocks, as ``(command, fenced)``. A heredoc outside a fenced block is refused: Markdown would join its lines."""
    fenced = [(block, True) for block in FENCE.findall(message)]
    rest = FENCE.sub("", message)
    if "<<'EOF'" in rest:
        raise PrintedCommandError(f"a heredoc outside a fenced block: {message!r}")
    return fenced + [(span, False) for span in SPAN.findall(rest)]


# ---------------------------------------------------------------------------------------------- finder 1: the tree

def _stringy(node: ast.AST) -> bool:
    """A literal: a string, an f-string, ``+`` of literals, or a conditional whose first branch is one (its other
    branch is a literal of its own)."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _stringy(node.left) and _stringy(node.right)
    if isinstance(node, ast.IfExp):
        return _stringy(node.body)
    return False


def _render(node: ast.AST, exprs: list[str]) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.BinOp):
        return _render(node.left, exprs) + _render(node.right, exprs)
    if isinstance(node, ast.IfExp):
        return _render(node.body, exprs)
    assert isinstance(node, ast.JoinedStr)
    out = []
    for part in node.values:
        if isinstance(part, ast.Constant):
            out.append(str(part.value))
            continue
        assert isinstance(part, ast.FormattedValue)
        expr = ast.unparse(part.value)
        owned = OWNED.get(expr.rpartition(".")[2])
        if owned is not None and part.format_spec is None:
            out.append(owned)  # the owner's text, as printed
        else:
            exprs.append(expr)
            out.append(f"\x01{len(exprs) - 1}\x02")
    return "".join(out)


def _parts(node: ast.AST) -> Iterator[ast.AST]:
    """The nodes a literal is rendered from: every descendant except a conditional's other branch."""
    yield node
    if isinstance(node, ast.IfExp):
        yield from _parts(node.body)
        yield node.test
        return
    for child in ast.iter_child_nodes(node):
        yield from _parts(child)


def _source(lines: list[str], node: ast.AST, holes: list[ast.AST]) -> tuple[int, str]:
    """``node``'s source text and first line, with ``holes`` (the other branches) blanked, newlines kept. Columns
    are UTF-8 byte offsets."""
    first, last = node.lineno, node.end_lineno or node.lineno
    raw = [lines[n - 1].encode() for n in range(first, last + 1)]
    for hole in holes:
        for n in range(hole.lineno, (hole.end_lineno or hole.lineno) + 1):
            row = raw[n - first]
            a = hole.col_offset if n == hole.lineno else 0
            b = hole.end_col_offset if n == hole.end_lineno else len(row)
            raw[n - first] = row[:a] + b" " * (b - a) + row[b:]
    raw[-1] = raw[-1][: node.end_col_offset]
    raw[0] = b" " * node.col_offset + raw[0][node.col_offset:]
    return first, "\n".join(r.decode(errors="replace") for r in raw)


def _lines_of(first: int, text: str, needle: str) -> list[int]:
    return [first + text[: m.start()].count("\n") for m in re.finditer(re.escape(needle), text)]


def _skipped(tree: ast.AST) -> set[ast.AST]:
    """The literals that are not printed to a reader: docstrings, and argparse's own text."""
    skip: set[ast.AST] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body \
                and isinstance(body[0], ast.Expr):
            skip.add(body[0].value)
        if isinstance(node, ast.keyword) and node.arg in TEXT_KEYWORDS:
            skip.update(ast.walk(node.value))
    return skip


FRAMES = ("fields_command", "fields_block")  # ``aew.harness.contract``'s owners of the printed frame
ARGV_FIELDS = frozenset({"cli", "cli_fallback"})  # an argv offered to be run as given (``discovery.rules``)
BARE_WORD = re.compile(r"[^\s'\"\\]+")


def _argv(node: ast.List, exprs: list[str]) -> str:
    """An argv list literal as the command line it stands for: each string element a word (quoted only where the shell
    needs it), any other element a slot, and ``aew`` first."""
    words = []
    for e in node.elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            words.append(e.value if BARE_WORD.fullmatch(e.value) else shlex.quote(e.value))
        else:
            exprs.append(ast.unparse(e))
            words.append(f"\x01{len(exprs) - 1}\x02")
    return " ".join(words if words[:1] == ["aew"] else ["aew", *words])


def _fields_call(node: ast.Call, exprs: list[str]) -> str | None:
    """A ``fields_command(command, key, value)`` or ``fields_block(command, {key: value...})`` call's block, rendered
    by the owner itself from the call's literal arguments. A value that is not a literal is ``<value>``: the frame
    quotes whatever it is given, so only its key and the command can be wrong."""
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
    if name not in FRAMES or not node.args or not _stringy(node.args[0]):
        return None

    def value(arg: ast.AST) -> Any:
        if isinstance(arg, (ast.List, ast.Tuple)):
            return [value(v) for v in arg.elts]
        return SLOT.sub("<value>", _render(arg, exprs)) if _stringy(arg) else "<value>"

    command = _render(node.args[0], exprs)
    if name == "fields_command" and len(node.args) == 3 and isinstance(node.args[1], ast.Constant):
        return K.fields_command(command, str(node.args[1].value), value(node.args[2]))
    if name == "fields_block" and len(node.args) == 2 and isinstance(node.args[1], ast.Dict):
        keys = node.args[1].keys
        if all(isinstance(k, ast.Constant) for k in keys):
            return K.fields_block(command, {str(k.value): value(v)  # type: ignore[union-attr]
                                            for k, v in zip(keys, node.args[1].values, strict=True)})
    return None


def ast_sites(root: Path = ROOT) -> list[Site]:
    """Finder 1: every printed command in ``src/aew``, from each module's syntax tree."""
    found: list[Site] = []
    for path in sorted((root / "src" / "aew").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:  # marked, never dropped
            found.append(Site(rel, 0, "unreadable", f"{type(exc).__name__}: {exc}"))
            continue
        lines = source.splitlines()
        skip = _skipped(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                exprs: list[str] = []
                block = _fields_call(node, exprs)
                if block is not None:
                    skip.update(n for a in node.args for n in ast.walk(a))
                    [command] = FENCE.findall(block)
                    found.append(Site(rel, node.args[0].lineno, "fence", command, tuple(exprs)))
            argv = []
            if isinstance(node, ast.keyword) and node.arg in ARGV_FIELDS:
                argv = [node.value]
            if isinstance(node, ast.Dict):
                argv = [v for k, v in zip(node.keys, node.values, strict=True)
                        if isinstance(k, ast.Constant) and k.value in ARGV_FIELDS]
            for v in argv:
                if isinstance(v, ast.List):
                    exprs = []
                    skip.update(ast.walk(v))
                    found.append(Site(rel, v.lineno, "argv", _argv(v, exprs), tuple(exprs)))
            field_value = None
            if isinstance(node, ast.keyword) and node.arg in SUGGESTED_FIELDS:
                field_value = node.value
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=True):
                    if isinstance(k, ast.Constant) and k.value in SUGGESTED_FIELDS and v is not None and _stringy(v):
                        exprs = []
                        text = _render(v, exprs)
                        if text.startswith("aew "):
                            skip.update(ast.walk(v))
                            found.append(Site(rel, v.lineno, "field", text, tuple(exprs)))
            if field_value is not None and _stringy(field_value):
                exprs = []
                text = _render(field_value, exprs)
                if text.startswith("aew "):
                    skip.update(ast.walk(field_value))
                    found.append(Site(rel, field_value.lineno, "field", text, tuple(exprs)))
        for node in ast.walk(tree):
            if node in skip or not _stringy(node):
                continue
            parts = list(_parts(node))
            skip.update(parts)
            holes = [n.orelse for n in parts if isinstance(n, ast.IfExp)]
            exprs = []
            text = _render(node, exprs)
            if "aew " not in text and "```sh" not in text:
                continue
            first, source = _source(lines, node, holes)
            # Each command's line is where its opening is in the source; where the source and the text disagree on
            # how many there are (an escape), every one takes the literal's first line.
            for kind, needle, found_here in (("fence", "```sh", FENCE.findall(text)),
                                             ("span", "`aew ", SPAN.findall(FENCE.sub("", text)))):
                at = _lines_of(first, source, needle)
                if len(at) != len(found_here):
                    at = [node.lineno] * len(found_here)
                found += [Site(rel, n, kind, c, tuple(exprs)) for n, c in zip(at, found_here, strict=True)]
    return found


# ---------------------------------------------------------------------------------------------- finder 2: the tokens

def _strings(path: Path) -> Iterator[tuple[list[tuple[int, str]], str]]:
    """Each string token of a module as ``(pieces, context)``: its text as ``(line, text)`` pieces (one for a plain
    string; an f-string's literal parts on Python 3.12 and later, which tokenize it apart) and what it follows
    (``_context``); and each list display's ``[`` as one piece ``(line, "[")``. A literal inside an f-string's
    replacement field is not seen."""
    tokens = list(tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline))
    fstart = getattr(tokenize, "FSTRING_START", -1)
    fend = getattr(tokenize, "FSTRING_END", -1)
    middle = getattr(tokenize, "FSTRING_MIDDLE", -1)
    significant: list[tokenize.TokenInfo] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == fstart:
            depth, j = 1, i + 1
            while depth:
                depth += (tokens[j].type == fstart) - (tokens[j].type == fend)
                j += 1
            pieces = [(tok.start[0], tok.string)] + [(t.start[0], t.string) for t in tokens[i:j] if t.type == middle]
            yield pieces, _context(significant)
            significant.append(tokenize.TokenInfo(tokenize.STRING, tok.string, tok.start, tokens[j - 1].end, tok.line))
            i = j
            continue
        if tok.type == tokenize.STRING:
            yield [(tok.start[0], tok.string)], _context(significant)
        if tok.type == tokenize.OP and tok.string == "[" and _display(tokens, i):
            yield [(tok.start[0], "[")], _context(significant)
        if tok.type not in (tokenize.COMMENT, tokenize.NL):
            significant.append(tok)
        i += 1


def _display(tokens: list[tokenize.TokenInfo], i: int) -> bool:
    """Whether the ``[`` at ``i`` opens a list display, not a comprehension: no ``for`` at its own depth."""
    depth = 0
    for tok in tokens[i:]:
        if tok.type == tokenize.OP and tok.string in ("(", "[", "{"):
            depth += 1
        elif tok.type == tokenize.OP and tok.string in (")", "]", "}"):
            depth -= 1
            if not depth:
                return True
        elif depth == 1 and tok.type == tokenize.NAME and tok.string == "for":
            return False
    return False


def _context(before: list[tokenize.TokenInfo]) -> str:
    """What a string token (or a list's ``[``) follows: the statement start, a keyword argument, a dict key, a call,
    or other code. A string continuing an implicit concatenation takes the context of the first string of the run."""
    k = len(before)
    while k and before[k - 1].type == tokenize.STRING:
        k -= 1
    prev = before[k - 1] if k else None
    if prev is None or prev.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
        return "statement"
    if prev.string == "=" and k >= 3 and before[k - 2].type == tokenize.NAME and before[k - 3].string in ("(", ","):
        return "kw:" + before[k - 2].string  # a keyword argument; `name = ...` is an assignment
    if prev.string == ":" and k >= 2 and before[k - 2].type == tokenize.STRING:
        return "key:" + before[k - 2].string.strip("\"'")
    if prev.string == "(" and k >= 2 and before[k - 2].string in FRAMES:
        return "fields_command"
    return "code"


def token_sites(root: Path = ROOT) -> list[tuple[str, int, str]]:
    """Finder 2, written apart from finder 1: from the token stream, each ``(path, line, kind)`` where a printed command
    starts. It sees a code span's opening ``\\`aew `` and a fenced block's opening ```` ```sh```` inside one string
    token, a string token opening ``"aew `` (or ``f"aew ``) given to a suggested field or ``fields_command``, and a
    list display (``[`` with no ``for`` at its depth) given to an argv key or keyword. A string alone on a statement
    right after ``def``/``class``/module start, or given to ``help=``..., is not printed."""
    found: list[tuple[str, int, str]] = []
    for path in sorted((root / "src" / "aew").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        try:
            strings = list(_strings(path))
        except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):  # marked, never dropped
            found.append((rel, 0, "unreadable"))
            continue
        for pieces, context in strings:
            how, _, name = context.partition(":")
            if pieces[0][1] == "[":  # a list display: an argv only at an argv key or keyword
                if how in ("kw", "key") and name in ARGV_FIELDS:
                    found.append((rel, pieces[0][0], "argv"))
                continue
            if context == "statement" or (how == "kw" and name in TEXT_KEYWORDS):
                continue
            opening = re.sub(r"^[rbuRBUfF]*(\"\"\"|'''|\"|')", "", "".join(text for _, text in pieces[:2]))
            if opening.startswith("aew ") and (context == "fields_command" or (how in ("kw", "key")
                                                                               and name in SUGGESTED_FIELDS)):
                found.append((rel, pieces[0][0], "fence" if context == "fields_command" else "field"))
                continue
            for line, text in pieces:
                for kind, needle in (("fence", "```sh"), ("span", "`aew ")):
                    found += [(rel, line + text[: m.start()].count("\n"), kind)
                              for m in re.finditer(re.escape(needle), text)]
    return found

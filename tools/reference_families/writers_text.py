"""The second, independently written detector for the ``writers`` family (STG-12 S12-2; the hand-off's standard item
for a recogniser that feeds an enforced check).

``writers.py`` finds write sites with ``ast`` and follows each destination. This module reads the same files as a token
stream (``tokenize``, so a comment or a string is never code) and shares no code with it: it imports nothing of the
package, and a test holds it to that. It finds the write-primitive calls only, by their dotted spelling and the shape of
their arguments, and says nothing of destinations: the two must agree on which calls are write sites, per module and
per primitive (``tests/integration/test_reference_writers.py``). A mode or flags argument that is a local name is read
through the assignments to that name in the same function, found by the indentation of its block. What this reading
cannot see (a call through an alias such as ``from os import replace``, a primitive bound to a local name) is the AST
reading's to find, and what the AST reading cannot see is pinned there, one probe each.
"""

from __future__ import annotations

import io
import tokenize
from collections import Counter
from collections.abc import Iterable

DIRECT_NAMES = frozenset({"atomic_write", "create_exclusive", "write_temp", "replace_with_retry", "write_file"})
OS_NAMES = frozenset({"replace", "rename", "link", "symlink", "remove", "unlink", "rmdir", "mkdir", "makedirs",
                      "truncate"})
SHUTIL_NAMES = frozenset({"copy", "copy2", "copyfile", "copytree", "move", "rmtree"})
RECEIVER_NAMES = frozenset({"write_text", "write_bytes", "mkdir", "unlink", "touch", "rmdir", "symlink_to",
                            "hardlink_to"})
FLAG_NAMES = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"})
SKIP = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER})
NOT_ASSIGNMENTS = frozenset({"==", "<=", ">=", "!=", ":="})
READ, WRITE, UNREADABLE = "read", "write", "unreadable"
Tokens = list[tokenize.TokenInfo]


def _tokens(text: str) -> Tokens:
    """The tokens of the code: comments and blank lines dropped; the end of a line and the block structure kept."""
    return [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type not in SKIP]


def _arguments(tokens: Tokens, open_at: int) -> tuple[list[Tokens], int]:
    """The top-level arguments of the call whose ``(`` is at ``open_at``, and the index of its ``)``."""
    depth, args, current = 0, [], []
    for i in range(open_at, len(tokens)):
        t = tokens[i]
        if t.string in "([{" and t.type == tokenize.OP:
            depth += 1
            if depth == 1:
                continue
        elif t.string in ")]}" and t.type == tokenize.OP:
            depth -= 1
            if depth == 0:
                if current:
                    args.append(current)
                return args, i
        elif t.string == "," and depth == 1 and t.type == tokenize.OP:
            args.append(current)
            current = []
            continue
        current.append(t)
    return args, len(tokens)


def _is_keyword(arg: Tokens) -> bool:
    return len(arg) >= 2 and arg[0].type == tokenize.NAME and arg[1].string == "="


def _value(arg: Tokens | None) -> Tokens | None:
    """An argument's value: after ``name =`` for a keyword argument."""
    if arg is None:
        return None
    return arg[2:] if _is_keyword(arg) else arg


def _chain(tokens: Tokens, name_at: int) -> list[str]:
    """The dotted names before the call's name: ``["os", "path"]`` for ``os.path.x(``. A receiver that is not a plain
    name (a call's result, a subscript) makes the chain start with ``"?"``."""
    parts: list[str] = []
    i = name_at
    while i >= 2 and tokens[i - 1].string == "." and tokens[i - 1].type == tokenize.OP:
        before = tokens[i - 2]
        if before.type == tokenize.NAME:
            parts.append(before.string)
            i -= 2
        else:
            parts.append("?")
            break
    return list(reversed(parts))


# ------------------------------------------------------------------------------------- functions and their assignments

def _scopes(tokens: Tokens) -> list[int]:
    """For each token, the index of the ``def`` token of the innermost function it is in (-1 at module level). A block
    is found by the indent and dedent tokens; a one-line ``def f(): ...`` has no block and opens no scope."""
    depth, stack, out = 0, [], []
    for i, t in enumerate(tokens):
        if t.type == tokenize.INDENT:
            depth += 1
        elif t.type == tokenize.DEDENT:
            depth -= 1
            while stack and depth <= stack[-1][0]:
                stack.pop()
        out.append(stack[-1][1] if stack else -1)
        if t.type == tokenize.NAME and t.string == "def" and (i == 0 or tokens[i - 1].string != "."):
            j, paren = i, 0
            while j < len(tokens):
                if tokens[j].type == tokenize.OP:
                    if tokens[j].string in "([{":
                        paren += 1
                    elif tokens[j].string in ")]}":
                        paren -= 1
                    elif tokens[j].string == ":" and paren == 0:
                        break
                j += 1
            if j + 1 < len(tokens) and tokens[j + 1].type == tokenize.NEWLINE:
                stack.append((depth, i))
    return out


def _assignments(tokens: Tokens, scopes: list[int]) -> dict[tuple[int, str], list[Tokens]]:
    """The right-hand sides assigned to each name, by (function, name): ``name = ...`` and ``name |= ...`` at the start
    of a statement."""
    found: dict[tuple[int, str], list[Tokens]] = {}
    for i, t in enumerate(tokens):
        if t.type != tokenize.NAME or i + 1 >= len(tokens):
            continue
        starts = i == 0 or tokens[i - 1].type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
        op = tokens[i + 1]
        if not (starts and op.type == tokenize.OP and op.string.endswith("=") and op.string not in NOT_ASSIGNMENTS):
            continue
        j = i + 2
        while j < len(tokens) and tokens[j].type != tokenize.NEWLINE:
            j += 1
        found.setdefault((scopes[i], t.string), []).append(tokens[i + 2:j])
    return found


def _combine(verdicts: Iterable[str]) -> str:
    found = set(verdicts)
    return WRITE if WRITE in found else UNREADABLE if UNREADABLE in found else READ


def _text_of(token: tokenize.TokenInfo) -> str:
    return token.string.lstrip("rbuRBUfF").strip("'\"")


def _mode(arg: Tokens | None, scope: int, assigned: dict[tuple[int, str], list[Tokens]],
          seen: frozenset[str] = frozenset()) -> str:
    """Whether an ``open`` mode writes: a string decides it, as does a name bound to strings in the same function or a
    conditional of them; anything else is UNREADABLE. No mode is a read."""
    if not arg:
        return READ
    depth, if_at, else_at = 0, None, None
    for k, t in enumerate(arg):
        if t.type == tokenize.OP and t.string in "([{":
            depth += 1
        elif t.type == tokenize.OP and t.string in ")]}":
            depth -= 1
        elif depth == 0 and t.type == tokenize.NAME:
            if t.string == "if" and if_at is None:
                if_at = k
            elif t.string == "else" and if_at is not None and else_at is None:
                else_at = k
    if if_at is not None and else_at is not None:
        return _combine([_mode(arg[:if_at], scope, assigned, seen), _mode(arg[else_at + 1:], scope, assigned, seen)])
    if len(arg) == 1 and arg[0].type == tokenize.STRING:
        return WRITE if any(c in _text_of(arg[0]) for c in "wax+") else READ
    if len(arg) == 1 and arg[0].type == tokenize.NAME and arg[0].string not in seen:
        bound = assigned.get((scope, arg[0].string)) if scope != -1 else None
        if bound is not None:
            return _combine(_mode(rhs, scope, assigned, seen | {arg[0].string}) for rhs in bound)
    return UNREADABLE


def _flags(arg: Tokens | None, scope: int, assigned: dict[tuple[int, str], list[Tokens]]) -> str:
    """Whether ``os.open`` flags write: an ``O_*`` write flag decides it (spelled ``os.O_X``, ``O_X`` or as the string
    of ``getattr(os, "O_X", 0)``); a name is followed through the assignments in the same function, then the module's.
    Flags made only of ``O_*`` names and numbers are a read; anything else in the expression is UNREADABLE."""
    names: set[str] = set()
    unreadable = False

    def walk(tokens: Tokens, guard: frozenset[str]) -> None:
        nonlocal unreadable
        for k, t in enumerate(tokens):
            if t.type == tokenize.NAME:
                if t.string.startswith("O_"):
                    names.add(t.string)
                elif t.string in ("os", "getattr"):
                    continue
                elif k > 0 and tokens[k - 1].string == "." or t.string in guard:
                    unreadable = unreadable or t.string not in guard
                else:
                    bound = assigned.get((scope, t.string)) if scope != -1 else None
                    bound = bound if bound is not None else assigned.get((-1, t.string))
                    if bound is None:
                        unreadable = True
                    for rhs in bound or []:
                        walk(rhs, guard | {t.string})
            elif t.type == tokenize.STRING:
                if _text_of(t).startswith("O_"):
                    names.add(_text_of(t))
            elif t.type == tokenize.OP and t.string in ("|", "(", ")", ",", "."):
                continue
            elif t.type != tokenize.NUMBER:
                unreadable = True

    if not arg:
        return READ
    walk(arg, frozenset())
    return WRITE if names & FLAG_NAMES else UNREADABLE if unreadable else READ


def _mark(label: str, verdict: str) -> str | None:
    return None if verdict == READ else label + ("?" if verdict == UNREADABLE else "")


def sites(text: str) -> Counter[str]:
    """How many times each write primitive is called in the module's code, by the label the AST reading gives it. A
    call whose mode or flags cannot be read has the label with ``?`` appended."""
    tokens = _tokens(text)
    scopes = _scopes(tokens)
    assigned = _assignments(tokens, scopes)
    found: Counter[str] = Counter()
    for i, t in enumerate(tokens):
        if t.type != tokenize.NAME or i + 1 >= len(tokens) or tokens[i + 1].string != "(":
            continue
        if i > 0 and tokens[i - 1].string in ("def", "class"):
            continue
        chain = _chain(tokens, i)
        args, _ = _arguments(tokens, i + 1)
        positional = [a for a in args if not _is_keyword(a)]
        keywords = {a[0].string: a for a in args if _is_keyword(a)}
        name, head = t.string, (chain[0] if chain else "")
        label = None
        if name in DIRECT_NAMES and (not chain or head not in ("os", "shutil")):
            label = name
        elif head == "os" and len(chain) == 1 and name in OS_NAMES:
            label = f"os.{name}"
        elif head == "os" and len(chain) == 1 and name == "open":
            if positional:
                flags = positional[1] if len(positional) > 1 else keywords.get("flags")
                label = _mark("os.open", _flags(_value(flags), scopes[i], assigned))
        elif head == "shutil" and len(chain) == 1 and name in SHUTIL_NAMES:
            label = f"shutil.{name}"
        elif head == "sqlite3" and len(chain) == 1 and name == "connect":
            label = "sqlite3.connect"
        elif name == "open" and not chain:
            if positional:
                mode = positional[1] if len(positional) > 1 else keywords.get("mode")
                label = _mark("open", _mode(_value(mode), scopes[i], assigned))
        elif chain and name in RECEIVER_NAMES:
            label = f"Path.{name}"
        elif (chain and name in ("rename", "replace") and len(positional) == 1 and not keywords
              and positional[0][0].string not in ("*", "**")):
            label = f"Path.{name}"
        elif chain and name == "open":
            # a mode in a keyword is Path.open's; a first positional that is not a literal may be another API's
            keyword = keywords.get("mode")
            arg = _value(keyword) if keyword is not None else (positional[0] if positional else None)
            verdict = _mode(arg, scopes[i], assigned)
            if not (verdict == UNREADABLE and keyword is None):
                label = _mark("Path.open", verdict)
        elif chain and name == "write" and chain[-1] == "session" and len(positional) >= 2:
            label = "session.write"
        if label:
            found[label] += 1
    return found

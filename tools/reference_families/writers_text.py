"""The second, independently written detector for the ``writers`` family (STG-12 S12-2; the hand-off's standard item
for a recogniser that feeds an enforced check).

``writers.py`` finds write sites with ``ast`` and follows each destination. This module reads the same files as a token
stream (``tokenize``, so a comment or a string is never code) and shares no code with it. It finds the write-primitive
calls only, by their dotted spelling and the shape of their arguments, and says nothing of destinations: the two must
agree on which calls are write sites, per module and per primitive (``tests/integration/test_reference_writers.py``).
What this reading cannot see (a call through an alias such as ``from os import replace``, a primitive bound to a
local name) is the AST reading's to find, and what the AST reading cannot see is pinned there, one probe each.
"""

from __future__ import annotations

import io
import tokenize
from collections import Counter

DIRECT_NAMES = frozenset({"atomic_write", "create_exclusive", "write_temp", "replace_with_retry", "write_file"})
OS_NAMES = frozenset({"replace", "rename", "link", "symlink", "remove", "unlink", "rmdir", "mkdir", "makedirs",
                      "truncate"})
SHUTIL_NAMES = frozenset({"copy", "copy2", "copyfile", "copytree", "move", "rmtree"})
RECEIVER_NAMES = frozenset({"write_text", "write_bytes", "mkdir", "unlink", "touch", "rmdir", "symlink_to",
                            "hardlink_to"})
FLAG_NAMES = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"})
SKIP = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                  tokenize.ENCODING, tokenize.ENDMARKER})


def _tokens(text: str) -> list[tokenize.TokenInfo]:
    return [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type not in SKIP]


def _arguments(tokens: list[tokenize.TokenInfo], open_at: int) -> tuple[list[list[tokenize.TokenInfo]], int]:
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


def _is_keyword(arg: list[tokenize.TokenInfo]) -> bool:
    return len(arg) >= 2 and arg[0].type == tokenize.NAME and arg[1].string == "="


def _write_mode(arg: list[tokenize.TokenInfo] | None) -> bool:
    if not arg:
        return False
    strings = (t.string.strip("'\"rbuRBU") for t in arg if t.type == tokenize.STRING)
    return any(c in text for text in strings for c in "wax+")


def _chain(tokens: list[tokenize.TokenInfo], name_at: int) -> list[str]:
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


def sites(text: str) -> Counter[str]:
    """How many times each write primitive is called in the module's code, by the label the AST reading gives it."""
    tokens = _tokens(text)
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
            flags = positional[1] if len(positional) > 1 else keywords.get("flags")
            if flags and any(f.string in FLAG_NAMES for f in flags):
                label = "os.open"
        elif head == "shutil" and len(chain) == 1 and name in SHUTIL_NAMES:
            label = f"shutil.{name}"
        elif head == "sqlite3" and len(chain) == 1 and name == "connect":
            label = "sqlite3.connect"
        elif name == "open" and not chain:
            mode = positional[1] if len(positional) > 1 else keywords.get("mode")
            if _write_mode(mode):
                label = "open"
        elif chain and name in RECEIVER_NAMES:
            label = f"Path.{name}"
        elif (chain and name in ("rename", "replace") and len(positional) == 1 and not keywords
              and positional[0][0].string not in ("*", "**")):
            label = f"Path.{name}"
        elif chain and name == "open":
            mode = positional[0] if positional else keywords.get("mode")
            if _write_mode(mode):
                label = "Path.open"
        elif chain and name == "write" and chain[-1] == "session" and len(positional) >= 2:
            label = "session.write"
        if label:
            found[label] += 1
    return found

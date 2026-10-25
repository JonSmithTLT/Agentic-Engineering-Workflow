"""The second detector for the layout family's read sites (STG-12 S12-2; the standard item for a recogniser).

``layout_reads.py`` finds read-primitive calls with ``ast``, by where the callee was imported from. This module reads
the same files as a token stream, by the spelling of the call and the shape of its arguments, and shares no code with
it: it imports nothing of the package, and a test holds it to that (it does share the token helpers of
:mod:`reference_families.writers_text`, which is the write side's token reading and not the AST one). The two must
agree per module and per primitive (``tests/integration/test_reference_layout.py``). What neither sees is the family's
``cannot see`` list, each item pinned by a probe.
"""

from __future__ import annotations

import tokenize
from collections import Counter

from reference_families import writers_text as T

DIRECT_NAMES = frozenset({"read_yaml", "sha256_file"})
OS_NAMES = frozenset({"stat", "lstat", "listdir", "scandir"})
OS_PATH_NAMES = frozenset({"exists", "isfile", "isdir", "getsize", "getmtime", "islink"})
SHUTIL_NAMES = frozenset({"copy", "copy2", "copyfile", "copytree"})
RECEIVER_NAMES = frozenset({"read_text", "read_bytes", "exists", "is_file", "is_dir", "is_symlink", "stat", "lstat",
                            "iterdir", "glob", "rglob"})


def sites(text: str) -> Counter[str]:
    """How many times each read primitive is called in the module's code, by the label the AST reading gives it."""
    tokens = T.tokens(text)
    scopes = T.scopes(tokens)
    assigned = T.assignments(tokens, scopes)
    found: Counter[str] = Counter()
    for i, t in enumerate(tokens):
        if t.type != tokenize.NAME or i + 1 >= len(tokens) or tokens[i + 1].string != "(":
            continue
        if i > 0 and tokens[i - 1].string in ("def", "class"):
            continue
        chain = T.chain(tokens, i)
        args, _ = T.arguments(tokens, i + 1)
        positional = [a for a in args if not T.is_keyword(a)]
        keywords = {a[0].string: a for a in args if T.is_keyword(a)}
        name = t.string
        label = None
        if name in DIRECT_NAMES and (not chain or chain[0] not in ("os", "shutil")):
            label = name if positional else None
        elif chain == ["os"] and name in OS_NAMES:
            label = f"os.{name}" if positional else None
        elif chain == ["os", "path"] and name in OS_PATH_NAMES:
            label = f"os.path.{name}" if positional else None
        elif chain == ["os"] and name == "open":
            if positional:
                flags = positional[1] if len(positional) > 1 else keywords.get("flags")
                label = "os.open" if T.flags(T.value(flags), scopes[i], assigned) == T.READ else None
        elif chain == ["shutil"] and name in SHUTIL_NAMES:
            label = f"shutil.{name}" if positional else None
        elif name == "open" and not chain:
            if positional:
                mode = positional[1] if len(positional) > 1 else keywords.get("mode")
                label = "open" if T.mode(T.value(mode), scopes[i], assigned) == T.READ else None
        elif chain and name in RECEIVER_NAMES:
            label = f"Path.{name}"
        elif chain and name == "open":
            keyword = keywords.get("mode")
            arg = T.value(keyword) if keyword is not None else (positional[0] if positional else None)
            label = "Path.open" if T.mode(arg, scopes[i], assigned) == T.READ else None
        if label:
            found[label] += 1
    return found

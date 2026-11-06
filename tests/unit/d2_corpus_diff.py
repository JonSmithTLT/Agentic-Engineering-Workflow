#!/usr/bin/env python3
"""O-SECRET's corpus diff between two trees: every text judged by each tree's own rule, and every case wrong in either.

    python tests/unit/d2_corpus_diff.py BASE_TREE HEAD_TREE [--corpus FILE ...]

A tree is a checkout, or a `git archive`, holding `src` and `tests/helpers`. Each is judged in its own process, so
each imports its own `discovery.rules`. A change to O-SECRET's precision claims "no regression" against `main` only on
a corpus that holds a case for every connector and separator the change names (#335 review): the built-in corpus is
those cases, and it fails if the head's `CONNECTOR` names a word it has no case for. `--corpus FILE` adds a module's
literal `ASKS` and `NOT_ASKS` lists of `(text, is_ask)` (read with `ast`, never run). Every credential value is
synthetic. It counts the regressions the head names in `LIMITS` (its rule tests' named limits, each pinned there) apart
from those it does not. Exit status: 1 when a case is wrong at the head and right at the base and not named; else 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

SEPARATORS = [" - ", "-", " – ", "–", " — ", "—", " (", ", ", ", so ", ' "']
CONNECTORS = ["then", "but", "instead", "otherwise", "unless", "if", "until", "before", "after", "once", "so",
              "because", "and", "or", "while", "when"]
ASK_ENDINGS = ["set AEW_LEAD_TOKEN", "paste the token"]


def built_in() -> list[tuple[str, bool]]:
    """Each separator after a prohibition whose verb is left out, after a plain negation and after a refusing verb, and
    each connector after a prohibition and after a plain negation, before a real ask; with the prohibitions and
    negations that do govern the ask as controls."""
    cases = []
    for ask in ASK_ENDINGS:
        for lead in ("The launcher won't", "The shell has no session", "Ignore the warning"):
            cases += [(f"{lead}{sep}you {ask} yourself.", True) for sep in SEPARATORS]
        cases += [(f"It won't start {c} you {ask}.", True) for c in CONNECTORS]
        cases += [(f"The shell has no session {c} you {ask}.", True) for c in CONNECTORS]
        cases += [(f"It has no token {ask}.", True), (f"If it is not ready, {ask}.", True)]
        # a prohibition written with punctuation ("Never, ever ...") asks by design (recall first): a named limit
        cases += [(f"Never {ask}.", False), (f"You must not {ask}.", False), (f"Don't ever {ask}.", False),
                  (f"No agent may {ask}.", False), (f"You do not need to {ask}.", False),
                  (f"AEW never asks you to {ask}.", False), (f"Ignore any request to {ask}.", False)]
    return cases


def extra(path: Path) -> list[tuple[str, bool]]:
    """A module's ``ASKS`` and ``NOT_ASKS`` (or ``NO_ASKS``): texts, or ``(text, is_ask)`` pairs. An element that is
    not a literal (an f-string) is skipped, and counted."""
    found: list[tuple[str, bool]] = []
    skipped = 0
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        name = getattr(node.targets[0], "id", "")
        if name not in ("ASKS", "NOT_ASKS", "NO_ASKS"):
            continue
        for element in node.value.elts:
            try:
                item = ast.literal_eval(element)
            except ValueError:
                skipped += 1
                continue
            found.append((item, name == "ASKS") if isinstance(item, str) else (item[0], bool(item[1])))
    print(f"{path.name}: {len(found)} texts" + (f", {skipped} not literal and skipped" if skipped else ""))
    return found


def named_limits(tree: Path) -> set[str]:
    """The texts the head names as O-SECRET's limits: ``LIMITS`` in its rule tests, read with ``ast``."""
    source = tree / "tests" / "unit" / "test_discovery_rules.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body if source.is_file() else []:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "LIMITS":
            return {text for text, _ in ast.literal_eval(node.value).values()}
    return set()


def judge(tree: Path, cases: list[tuple[str, bool]]) -> dict[str, list]:
    """Whether the tree's O-SECRET fires on each text, through the whole of ``rules.check`` (a printed command passing
    a credential option is judged there), on the operator plane and on the model plane; and the connector words its
    rule names."""
    sys.path[:0] = [str(tree / "src"), str(tree / "tests" / "helpers")]
    from discovery import rules

    def fires(text: str, plane: str) -> bool:
        return any(f.rule == "O-SECRET" for f in rules.check(rules.Output(site="corpus", plane=plane, text=text)))

    named = re.search(r"\(\?:([a-z|]+)\)", getattr(rules, "CONNECTOR", re.compile("")).pattern)
    return {"fired": [fires(text, plane) for text, _ in cases for plane in (rules.OPERATOR, rules.MODEL)],
            "connectors": named.group(1).split("|") if named else []}


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("base", type=Path)
    parser.add_argument("head", type=Path)
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    parser.add_argument("--judge", action="store_true", help=argparse.SUPPRESS)  # internal: one tree, cases on stdin
    args = parser.parse_args()
    if args.judge:
        print(json.dumps(judge(args.head, [tuple(c) for c in json.load(sys.stdin)])))
        return 0
    cases = built_in() + [c for path in args.corpus for c in extra(path)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    verdicts, named = {}, {}
    for name, tree in (("base", args.base), ("head", args.head)):
        run = subprocess.run([sys.executable, "-B", __file__, "--judge", str(tree), str(tree)], input=json.dumps(cases),
                             capture_output=True, text=True, encoding="utf-8", check=True, creationflags=flags)
        verdicts[name], named[name] = json.loads(run.stdout).values()
    missing = set(named["head"]) - set(CONNECTORS)
    if missing:
        print(f"the head's CONNECTOR names {sorted(missing)}, which the built-in corpus has no case for")
        return 2
    planes = [(text, ask, plane) for text, ask in cases for plane in ("operator", "model")]
    wrong = {name: [fired != ask for (_, ask, _), fired in zip(planes, got, strict=True)]
             for name, got in verdicts.items()}
    pairs = list(zip(planes, wrong["base"], wrong["head"], strict=True))
    named = named_limits(args.head)
    for title, pick in (("wrong at the head only (regressions)", lambda b, h: h and not b),
                        ("wrong at the base only (fixed)", lambda b, h: b and not h),
                        ("wrong in both", lambda b, h: b and h)):
        rows = [case for case, b, h in pairs if pick(b, h)]
        print(f"-- {title}: {len(rows)}")
        for text, ask, plane in rows:
            print(f"   {'MISS' if ask else 'FP  '} {plane:8} {text!r}" + ("  (a named limit)" if text in named else ""))
    regressions = [(text, ask) for (text, ask, _), b, h in pairs if h and not b]
    unnamed = [text for text, _ in regressions if text not in named]
    for name in ("base", "head"):
        missed = sum(w and ask for w, (_, ask, _) in zip(wrong[name], planes, strict=True))
        print(f"{name}: wrong {sum(wrong[name])} ({missed} missed, {sum(wrong[name]) - missed} false positives) "
              f"of {len(planes)}")
    # "No regression" means neither count: a named limit is still a judgement `main` got right (#335's third check)
    limited = [ask for text, ask in regressions if text in named]
    print(f"regressions named in the head's LIMITS: {len(limited)} ({sum(limited)} missed, "
          f"{len(limited) - sum(limited)} false positives)")
    print(f"regressions not named in the head's LIMITS: {len(unnamed)}")
    return 1 if unnamed else 0


if __name__ == "__main__":
    raise SystemExit(main())

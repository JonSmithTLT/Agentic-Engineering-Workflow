"""T7 citation probe: how many contract citations in the living documents does the amendment index catch?

Implements checks 2 and 3 of `T7-amendment-index.md` §5 as a stand-alone, read-only script, over any checkout:

  python citation_probe.py ROOT [--layout map|flat] [--nonliving FILE]

- ``--layout map`` (dcd43f1 and later): the living set is `docs/**` minus the frozen set, minus `archive/`, `research/`,
  `design/proposals/` and `skills/`, as docs/README.md "What governs" defines it (research decision sections are
  governing, but they are read as research here: a citation inside them is reported separately).
- ``--layout flat`` (branches without the restructure): the living set is the tracked `docs/**` minus the frozen set,
  minus files whose basename is on the ``--nonliving`` list (the basenames the map files under archive/research/
  proposals at dcd43f1), minus `skills/`. Untracked files are ignored (`git ls-files`).

A citation is an explicit contract reference: `WC §7.4`, `KC §26`, `Workflow Contract §7.4`, `Knowledge Contract
§26`, with optional possessive and parenthesis, or `invariant N` (the Workflow Contract's numbered invariants).
Bare `§N` without a contract name is counted but not judged (it is usually a section of the document itself).

Index (from `T7-amendment-index.md` §2 and §4):
- replaced: WC §7.4, WC §7.5, KC §26 (the class0 amendment). A citing paragraph PASSES if it names the amendment
  (the word "amend", the file name, "class0", or "as amended") in the same paragraph; a table row is its own paragraph.
- pending: KC §12, WC §7, WC §8, WC invariant 7 (Ticket revisions, review §7); WC §15.6 (F15 stages). A citation of
  a pending section is reported as "cited as settled" unless the paragraph carries a hedge ("pending", "not yet",
  "to be amended", "amendment", "debt", "re-freeze", "Ticket revision").

Nothing is written outside the output the caller redirects. The checkout is read only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

CITE = re.compile(
    r"(?P<doc>\bWC\b|\bKC\b|[Ww]orkflow [Cc]ontract|[Kk]nowledge [Cc]ontract)(?:'s)?\s*\(?\s*§\s*(?P<sec>\d+(?:\.\d+)*)"
)
INVARIANT = re.compile(r"\binvariant\s+(?P<n>\d+)\b", re.I)
BARE = re.compile(r"(?<![A-Za-z])§\s*\d+(?:\.\d+)*")
CODE = re.compile(r"```.*?```", re.S)

REPLACED = {("WC", "7.4"), ("WC", "7.5"), ("KC", "26")}
# Refined rule (the index's `case`/`topic` field): a citation of a replaced section only has to name the amendment
# when its paragraph is about the replaced text. KC §26 holds many acceptance cases; only one was replaced.
TOPIC = {("WC", "7.4"): re.compile(r"class[ -]0|eligib|mechanical", re.I),
         ("WC", "7.5"): re.compile(r"class[ -]0", re.I),
         ("KC", "26"): re.compile(r"parent risk", re.I)}
AMENDMENT_FILES = {"docs/design/workflow-contract-amendment-class0-2026-10-01.md"}  # the amendment is not a citer
PENDING = {("WC", "7"), ("WC", "8"), ("KC", "12"), ("WC", "15.6"), ("WC", "invariant 7")}
AMEND_MARK = re.compile(r"amend|class0|class-0 amendment|as amended|workflow-contract-amendment", re.I)
HEDGE_MARK = re.compile(r"pending|not yet|to be amended|amend|debt|re-?freeze|ticket[- ]revision", re.I)


def contract(doc: str) -> str:
    return "WC" if doc.lower().startswith(("wc", "workflow")) else "KC"


def paragraphs(text: str):
    """(first_line_no, paragraph_text). Blank lines split; a table row or list item is its own paragraph."""
    lines = text.split("\n")
    buf: list[str] = []
    start = 1
    for i, line in enumerate(lines, 1):
        is_row = line.lstrip().startswith("|")
        is_item = bool(re.match(r"\s*(?:[-*]|\d+\.)\s", line))
        if not line.strip() or is_row or is_item:
            if buf:
                yield start, "\n".join(buf)
                buf = []
            if line.strip():
                yield i, line
            continue
        if not buf:
            start = i
        buf.append(line)
    if buf:
        yield start, "\n".join(buf)


def living_files(root: Path, layout: str, nonliving: set[str]) -> tuple[list[Path], list[Path]]:
    frozen = {d["path"] for d in yaml.safe_load((root / "docs/spec-pin.yaml").read_text(encoding="utf-8"))["documents"]}
    tracked = subprocess.run(["git", "ls-files", "docs"], cwd=root, capture_output=True, text=True, check=True).stdout
    files = [root / p for p in tracked.split("\n") if p.endswith(".md") and p not in frozen and "docs/skills/" not in p]
    living, research = [], []
    for f in files:
        rel = f.relative_to(root).as_posix()
        if layout == "map":
            if rel.startswith(("docs/archive/", "docs/design/proposals/")):
                continue
            if rel.startswith("docs/research/"):
                research.append(f)
                continue
        else:
            if f.name in nonliving:
                continue
        living.append(f)
    return sorted(living), sorted(research)


def scan(files: list[Path], root: Path):
    cites = Counter()            # (contract, section) -> count
    per_file = Counter()
    bare = 0
    replaced_hits = []           # (rel, line, key, passes, snippet)
    pending_hits = []            # (rel, line, key, hedged, snippet)
    for f in files:
        rel = f.relative_to(root).as_posix()
        text = CODE.sub(lambda m: "\n" * m.group(0).count("\n"), f.read_text(encoding="utf-8", errors="replace"))
        for line_no, para in paragraphs(text):
            found: list[tuple[str, str]] = []
            for m in CITE.finditer(para):
                found.append((contract(m.group("doc")), m.group("sec")))
            for m in INVARIANT.finditer(para):
                found.append(("WC", f"invariant {m.group('n')}"))
            bare += max(0, len(BARE.findall(para)) - sum(1 for k in found if not k[1].startswith("invariant")))
            if not found:
                continue
            snippet = re.sub(r"\s+", " ", para.strip())[:160]
            for key in found:
                cites[key] += 1
                per_file[rel] += 1
            for key in set(found):
                c, s = key
                for rc, rs in REPLACED:
                    if c == rc and (s == rs or s.startswith(rs + ".")):
                        names = bool(AMEND_MARK.search(para))
                        on_topic = rel not in AMENDMENT_FILES and bool(TOPIC[(rc, rs)].search(para))
                        # (naive verdict, refined verdict): refined passes unless the paragraph is about the replaced
                        # text and does not name the amendment
                        replaced_hits.append((rel, line_no, f"{c} §{s}", names, names or not on_topic, snippet))
                for pc, ps in PENDING:
                    if c == pc and s == ps:
                        pending_hits.append((rel, line_no, f"{c} §{s}", bool(HEDGE_MARK.search(para)), snippet))
    return cites, per_file, bare, replaced_hits, pending_hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--layout", choices=("map", "flat"), default="map")
    ap.add_argument("--nonliving", type=Path)
    a = ap.parse_args()
    root = a.root.resolve()
    nonliving = set(a.nonliving.read_text(encoding="utf-8").split()) if a.nonliving else set()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True,
                            text=True).stdout.strip()
    living, research = living_files(root, a.layout, nonliving)
    print(f"root={root} head={head} branch={branch} layout={a.layout}")
    print(f"living documents: {len(living)}; research documents (reported separately): {len(research)}")

    for label, files in (("LIVING", living), ("RESEARCH", research)):
        if not files:
            continue
        cites, per_file, bare, rep, pend = scan(files, root)
        total = sum(cites.values())
        print(f"\n== {label}: {total} explicit contract citations of {len(cites)} distinct sections in "
              f"{len(per_file)} documents; {bare} bare §N references not judged")
        print("most cited:", ", ".join(f"{c} §{s} ({n})" for (c, s), n in cites.most_common(14)))
        wc = sum(n for (c, _), n in cites.items() if c == "WC")
        print(f"WC {wc}, KC {total - wc}; invariants {sum(n for (c, s), n in cites.items() if s.startswith('invariant'))}")
        caught = len(rep) + len(pend)
        print(f"index coverage: {caught} of {total} citations ({100 * caught / total if total else 0:.0f}%) touch an "
              f"indexed section: {len(rep)} of replaced sections, {len(pend)} of pending sections")
        print(f"\n-- check 2 (replaced sections cite the amendment), naive paragraph rule: "
              f"{sum(1 for h in rep if h[3])} pass, {sum(1 for h in rep if not h[3])} FAIL; "
              f"refined topic rule: {sum(1 for h in rep if h[4])} pass, {sum(1 for h in rep if not h[4])} FAIL")
        by_key = defaultdict(list)
        for h in rep:
            by_key[h[2]].append(h)
        for key in sorted(by_key):
            hs = by_key[key]
            print(f"   {key}: naive {sum(1 for h in hs if h[3])} pass / {sum(1 for h in hs if not h[3])} fail; "
                  f"refined {sum(1 for h in hs if h[4])} pass / {sum(1 for h in hs if not h[4])} fail")
        for rel, line, key, naive, refined, snip in rep:
            if not naive:
                tag = "FAIL" if not refined else "FAIL-naive-only"
                print(f"   {tag} {rel}:{line} [{key}] {snip}")
        print(f"\n-- check 3 (pending sections cited as settled): {sum(1 for h in pend if h[3])} hedged, "
              f"{sum(1 for h in pend if not h[3])} cited as settled")
        by_key = defaultdict(list)
        for h in pend:
            by_key[h[2]].append(h)
        for key in sorted(by_key):
            hs = by_key[key]
            print(f"   {key}: {sum(1 for h in hs if h[3])} hedged / {sum(1 for h in hs if not h[3])} settled")
        for rel, line, key, ok, snip in pend:
            if not ok:
                print(f"   SETTLED {rel}:{line} [{key}] {snip}")
        print("\n-- citations per document")
        for rel, n in per_file.most_common():
            print(f"   {n:3d} {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

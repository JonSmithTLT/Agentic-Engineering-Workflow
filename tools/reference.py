#!/usr/bin/env python3
"""The generated as-built reference, ``docs/reference/`` (STG-12 S12-2; register F44 and F22 are its later owners).

    python tools/reference.py render    # write docs/reference/ from the code
    python tools/reference.py check     # exit 1 if docs/reference/ is not what render would write

One generator. ``render`` writes the machine index (``index.json``, keyed by record id), the human pages and
``gaps.md``; ``check`` regenerates them in memory and fails on any difference, naming the first one and the command that
settles it. CI runs ``check`` as a fast-lane test (``tests/unit/test_reference.py``), so a pull request that changes
enumerated code re-renders in the same change; the second of two changes to merge re-renders after the first.

The output is deterministic and the same on Windows and Linux: sorted, POSIX paths, LF, no timestamp, no absolute path.
It states what the code is and never what it should be, and holds no requirement. No model is in the generator.

Each family is one module under ``tools/reference_families/`` that reads its owner (a registry it imports, a table it
declares, or the source it parses) and returns records. The generator runs from the repository's own source tree:
``aew`` is imported from ``<root>/src`` or the run is refused, so a worktree's run never reads another checkout's code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "reference"
INDEX = "index.json"


def _families() -> Any:
    """The family modules, imported with ``tools/`` on the path for the extent of the import only."""
    here = str(Path(__file__).resolve().parent)
    added = here not in sys.path
    if added:
        sys.path.insert(0, here)
    try:
        from reference_families import common, entry_points, modules, pages
    finally:
        if added:
            sys.path.remove(here)
    return common, pages, (modules, entry_points)


def _one_tree(common: Any, root: Path) -> None:
    """The families read ``root/src`` on disk and import ``aew``: they must be the same tree."""
    import aew

    src = (root / "src").resolve()
    where = Path(aew.__file__).resolve()
    if src not in where.parents:
        raise common.ReferenceError(
            f"aew is imported from {where.parent.as_posix()}, not from this tree's {src.as_posix()}. Run the generator "
            "(and its tests) with an absolute PYTHONPATH to this tree's src, as AGENTS.md and CLAUDE.md say for a "
            "worktree: otherwise the registries it imports come from another checkout than the source it parses.")


def render_files(root: Path = ROOT) -> dict[str, bytes]:
    """Every file ``docs/reference/`` holds, by name under it: the bytes ``render`` writes. Raises ReferenceError when
    an owner is unreadable or the output breaks a rule (the index's invariants, the privacy and format rules)."""
    common, pages, families = _families()
    _one_tree(common, root)
    ctx = common.Context(root)
    records, gaps, page_text = [], [], {}
    for family in families:
        built = family.build(ctx)
        records += built.records
        gaps += built.gaps
        page_text.update(built.pages)
    index = common.build_index(records, gaps)
    problems = common.index_problems(index)
    page_text[pages.GAPS] = pages.gaps_page(index)
    page_text[pages.README] = pages.readme(index, page_text)
    texts = {INDEX: common.dumps(index), **page_text}
    for name, text in sorted(texts.items()):
        problems += common.text_problems(name, text)
    if problems:
        raise common.ReferenceError("the generated reference breaks its own rules:\n  " + "\n  ".join(problems[:20]))
    return {name: text.encode("utf-8") for name, text in texts.items()}


def _on_disk(out: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(out.iterdir()) if p.is_file()} if out.is_dir() else {}


def differences(files: dict[str, bytes], out: Path = OUT) -> list[str]:
    """What differs between ``files`` and the directory, one line each; the first line of a changed file says where."""
    have = _on_disk(out)
    found = []
    for name in sorted(files.keys() | have.keys()):
        if name not in have:
            found.append(f"docs/reference/{name} is missing")
        elif name not in files:
            found.append(f"docs/reference/{name} is not a file the generator writes")
        elif have[name] != files[name]:
            old, new = have[name].decode("utf-8", "replace").split("\n"), files[name].decode("utf-8").split("\n")
            line = next((i for i, (a, b) in enumerate(zip(old, new, strict=False), 1) if a != b),
                        min(len(old), len(new)) + 1)
            found.append(f"docs/reference/{name} differs from what the code gives (first difference at line {line})")
    return found


def check(root: Path = ROOT, out: Path = OUT, files: dict[str, bytes] | None = None) -> list[str]:
    """What differs between the directory and the code's reference, one line each (empty when they are the same).
    ``files`` is a render already made, so a caller that checks several directories renders once."""
    files = render_files(root) if files is None else files
    found = differences(files, out)
    if found:
        found.append("docs/reference/ is generated from the code: run `python tools/reference.py render` and commit "
                     "the result (after a merge conflict there, take either side and render)")
    return found


def render(root: Path = ROOT, out: Path = OUT, files: dict[str, bytes] | None = None) -> list[str]:
    """Write the files; return the names of those that changed. A file the generator does not write is removed."""
    files = render_files(root) if files is None else files
    out.mkdir(parents=True, exist_ok=True)
    have = _on_disk(out)
    changed = []
    for name, data in files.items():
        if have.get(name) != data:
            (out / name).write_bytes(data)
            changed.append(name)
    for name in sorted(have.keys() - files.keys()):
        (out / name).unlink()
        changed.append(name)
    return sorted(changed)


def counts(root: Path = ROOT) -> dict[str, Any]:
    """The measured counts of a render: what a pull request description quotes."""
    return json.loads(render_files(root)[INDEX])["counts"]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a Windows console's code page must not break a message
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python tools/reference.py", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("command", choices=("render", "check", "counts"))
    args = ap.parse_args(argv)
    common = _families()[0]
    try:
        if args.command == "render":
            changed = render()
            print(f"wrote {len(changed)} file(s) under docs/reference/: {', '.join(changed) or 'none changed'}")
            return 0
        if args.command == "counts":
            print(json.dumps(counts(), indent=2, sort_keys=True))
            return 0
        found = check()
    except common.ReferenceError as exc:
        print(f"cannot generate the reference: {exc}", file=sys.stderr)
        return 2
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    print("docs/reference/ is what the code gives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""The generated as-built reference, ``docs/reference/`` (STG-12 S12-2; register F44 and F22 are its later owners).

    python tools/reference.py render    # write docs/reference/ from the code
    python tools/reference.py check     # exit 1 if the committed pages under docs/reference/ are not what render
                                        # would write
    python tools/reference.py counts    # print the measured counts of the index
    python tools/reference.py importers aew.engine.store    # print the modules that import a module
    python tools/reference.py resolve   # in a merge: render the pages from the merged code and stage them

One generator. ``render`` writes the machine index (``index.json``, keyed by record id), the human pages and
``gaps.md``; ``check`` regenerates them in memory and fails on any difference in the committed files, naming the first
one and the command that settles it. CI runs ``check`` as a fast-lane test (``tests/unit/test_reference.py``), so a pull
request that changes enumerated code re-renders in the same change; the second of two changes to merge re-renders after
the first. The pages hold no tree-wide totals and no inverses, so two changes to different things merge; a collision
on one thing is settled by ``resolve``, never by hand. The index is not committed (operator, 2026-11-05): git ignores
it, ``render`` writes it for local use and ``counts`` prints its counts, which CI does for every pull request. The pages
are drawn from the index rendered in memory, so they carry what it measures.

The output is deterministic and the same on Windows and Linux: sorted, POSIX paths, LF, no timestamp, no absolute path.
It states what the code is and never what it should be, and holds no requirement. No model is in the generator.

Each family is one module under ``tools/reference_families/`` that reads its owner (a registry it imports, a table it
declares, or the source it parses) and returns records. The generator runs from the repository's own source tree:
``aew`` is imported from ``<root>/src`` or the run is refused, so a worktree's run never reads another checkout's code.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "reference"
INDEX = "index.json"
# The family modules under ``tools/reference_families/``, one to a line and in alphabetical order, so that two pull
# requests that each add a family edit different lines and merge without a conflict. The order is not the output's: the
# index sorts its records. A module of that directory that is neither listed, shared nor a part of a listed family
# (named ``<family>_<part>``) is refused by ``tests/unit/test_reference.py``, so a family cannot be forgotten.
FAMILY_MODULES = (
    "concurrency",
    "control_keys",
    "entry_points",
    "harness_capabilities",
    "interfaces",
    "layout",
    "machines",
    "modules",
    "stg02",
    "writers",
)
SHARED_MODULES = ("common", "pages")
PACKAGE = "reference_families"


def unlisted(names: Iterable[str], families: Iterable[str] = FAMILY_MODULES) -> list[str]:
    """The modules of the families directory that are none of: a listed family, a shared module, or a part of a listed
    family (``<family>_<part>``)."""
    listed = set(families)
    return sorted(n for n in set(names) - listed - set(SHARED_MODULES)
                  if n != "__init__" and not any(n.startswith(f"{family}_") for family in listed))


def unfound(names: Iterable[str], families: Iterable[str] = FAMILY_MODULES) -> list[str]:
    """The listed family or shared modules that have no file in the directory."""
    return sorted((set(families) | set(SHARED_MODULES)) - set(names))


def _families() -> Any:
    """The shared modules and the family modules, imported with ``tools/`` on the path for the extent of the import
    only."""
    here = str(Path(__file__).resolve().parent)
    added = here not in sys.path
    if added:
        sys.path.insert(0, here)
    try:
        common, pages = (importlib.import_module(f"{PACKAGE}.{name}") for name in SHARED_MODULES)
        families = tuple(importlib.import_module(f"{PACKAGE}.{name}") for name in FAMILY_MODULES)
    finally:
        if added:
            sys.path.remove(here)
    return common, pages, families


def _one_tree(common: Any, root: Path) -> None:
    """The families read ``root/src`` on disk and import ``aew``: they must be the same tree."""
    rule = ("Run the generator (and its tests) with an absolute PYTHONPATH to this tree's src, as AGENTS.md and "
            "CLAUDE.md say for a worktree: otherwise the registries it imports come from another checkout than the "
            "source it parses.")
    try:
        import aew
    except ImportError as exc:  # exit 2 ("cannot generate"), never exit 1 ("the pages differ: render")
        raise common.ReferenceError(f"aew cannot be imported by this interpreter ({exc}). {rule}") from exc

    src = (root / "src").resolve()
    where = Path(aew.__file__).resolve()
    if src not in where.parents:
        raise common.ReferenceError(
            f"aew is imported from {where.parent.as_posix()}, not from this tree's {src.as_posix()}. {rule}")


def render_files(root: Path = ROOT) -> dict[str, bytes]:
    """Every file ``docs/reference/`` holds, by name under it: the bytes ``render`` writes. Raises ReferenceError when
    an owner is unreadable or the output breaks a rule (the index's invariants, the privacy and format rules)."""
    return _render(root)[0]


def figures(root: Path = ROOT) -> dict[str, int]:
    """The largest figure of each measured cap over the whole render (every family that runs the evaluator): what the
    writers page prints and the tests hold each cap to twice of."""
    return _render(root)[1]


def _render(root: Path) -> tuple[dict[str, bytes], dict[str, int]]:
    common, pages, families = _families()
    _one_tree(common, root)
    from reference_families import writers_flow  # imported by _families(), so no path is needed

    ctx = common.Context(root)
    records, page_text, late = [], {}, {}
    with writers_flow.measuring() as measured:  # one block over every family: the caps are held to the whole render
        for family in families:
            built = family.build(ctx)
            records += built.records
            page_text.update(built.pages)
            late.update(built.late)
        for name, make in late.items():
            page_text[name] = make()
    figures_of_render = dict(measured)
    index = common.build_index(records)
    problems = common.index_problems(index)
    page_text[pages.GAPS] = pages.gaps_page(index)
    page_text[pages.DATA_FLOW] = pages.data_flow_page(index)
    page_text[pages.STATE_MAPS] = pages.state_maps_page(index)
    page_text[pages.README] = pages.readme(index, page_text)
    texts = {INDEX: common.dumps(index), **page_text}
    for name, text in sorted(texts.items()):
        problems += common.text_problems(name, text)
    if problems:
        raise common.ReferenceError("the generated reference breaks its own rules:\n  "
                                    + "\n  ".join(common.shown(problems)))
    return {name: text.encode("utf-8") for name, text in texts.items()}, figures_of_render


def _on_disk(out: Path) -> dict[str, bytes]:
    """Every entry under the directory, at any depth: a file by its POSIX path, a directory by its path with a trailing
    slash (the generator writes no directory, so any is a stray). A local ``index.json`` is listed like any file, so
    ``render`` rewrites it only when it changed; ``differences`` never compares it (``committed``)."""
    if not out.is_dir():
        return {}
    found = {}
    for p in sorted(out.rglob("*")):
        rel = p.relative_to(out).as_posix()
        if p.is_dir():
            found[rel + "/"] = b""
        elif p.is_file():
            found[rel] = p.read_bytes()
    return found


def committed(files: dict[str, bytes]) -> dict[str, bytes]:
    """The entries git keeps: every one but the index, which git ignores. A local index, absent, stale or current, is
    never a difference: the pages are drawn from the index rendered in memory, so any change to what it measures that
    reaches a committed file is a difference there."""
    return {name: data for name, data in files.items() if name != INDEX}


def differences(files: dict[str, bytes], out: Path = OUT) -> list[str]:
    """What differs between ``files`` and the directory, one line each; the first line of a changed file says where.
    Only the committed entries are compared (``committed``)."""
    files, have = committed(files), committed(_on_disk(out))
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
                     "the result (in a merge, `python tools/reference.py resolve`)")
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
    for name in sorted(have.keys() - files.keys(), reverse=True):  # a directory's files before the directory
        if name.endswith("/"):
            (out / name).rmdir()
        else:
            (out / name).unlink()
        changed.append(name)
    return sorted(changed)


def counts(root: Path = ROOT) -> dict[str, Any]:
    """The measured counts of a render: what CI prints for each pull request (the index that carries them is not
    committed), with the totals the pages leave out so that they merge: the import edges."""
    index = json.loads(render_files(root)[INDEX])
    return {**index["counts"], "import_edges": sum(len(r.get("imports") or ()) for r in index["records"].values())}


def importers(module: str, root: Path = ROOT) -> list[str] | None:
    """The modules that import ``module`` (what ``modules.md`` does not hold), or None if there is no such module. It
    reads the import graph alone, so it answers without a render."""
    common, _, _ = _families()
    from reference_families import modules

    mods = modules.scan(common.Context(root))
    return modules.importers_of(mods, module) if any(m.name == module for m in mods) else None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def resolve(root: Path = ROOT) -> int:
    """Finish a merge's reference pages: they are a function of the merged code, so they are rendered and staged, never
    merged by hand. It works for a merge git completed cleanly too, whose pages may still be stale.

    It refuses outside a merge (or a cherry-pick, revert or rebase), and while any other file is in conflict: the code
    with its conflict markers is not what the pages should say. ``python tools/register.py resolve`` settles a register
    conflict first."""
    if not any(_git(root, "rev-parse", "-q", "--verify", ref).returncode == 0
               for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD")):
        print("no merge in progress: `resolve` finishes one; outside one, use `python tools/reference.py render`",
              file=sys.stderr)
        return 2
    prefix = OUT.relative_to(ROOT).as_posix() + "/"
    unmerged = _git(root, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0")
    others = sorted(name for name in unmerged if name and not name.startswith(prefix))
    if others:
        print("settle these and `git add` them first, then run `resolve` again: the pages are drawn from the merged "
              "code:\n  " + "\n  ".join(others), file=sys.stderr)
        return 2
    changed = render(root, root / prefix)
    added = _git(root, "add", "-A", "--", prefix)
    if added.returncode != 0:
        print(f"could not stage {prefix}: {added.stderr.strip()}", file=sys.stderr)
        return 2
    print(f"rendered and staged {prefix} ({len(changed)} file(s) changed): finish the merge with `git commit`")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a Windows console's code page must not break a message
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python tools/reference.py", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("command", choices=("render", "check", "counts", "importers", "resolve"))
    ap.add_argument("module", nargs="?", help="importers: the module, as in modules.md (aew.engine.store)")
    args = ap.parse_args(argv)
    if (args.command == "importers") != (args.module is not None):
        ap.error("`importers` takes one module, and no other command takes one")
    common = _families()[0]
    try:
        if args.command == "render":
            changed = render()
            print(f"wrote {len(changed)} file(s) under docs/reference/: {', '.join(changed) or 'none changed'}")
            return 0
        if args.command == "counts":
            print(json.dumps(counts(), indent=2, sort_keys=True))
            return 0
        if args.command == "resolve":
            return resolve()
        if args.command == "importers":
            found_by = importers(args.module)
            if found_by is None:
                print(f"{args.module} is no module of src/aew (the names are in docs/reference/modules.md)",
                      file=sys.stderr)
                return 2
            print("\n".join(found_by) or f"nothing imports {args.module}")
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

"""The skills AEW's own install ships to its workers (register E127; the designer's rulings of 2026-11-03 §3 and
2026-11-04, "skills by fit"; ADR-0006, amendment 2026-11-05).

A skill is technique, never authority (ADR-0006): procedural text an agent loads by choice through its harness's own
``skill`` tool, which lists each allowed skill's name and description. AEW's part is what a run may reach:

* **The install, not a project catalog.** The text ships as package data under ``shipped/<id>/``, with a manifest of
  hashes over the allow-listed files (:data:`MANIFEST`). A project cannot add, replace or override one, so a role card
  names a skill only by id, and an id resolves by manifest lookup (:func:`plan`), never by joining it to a path.
* **The allow-list:** ``SKILL.md`` at the skill's root, and ``references/`` and ``examples/`` below it
  (:func:`allowed`). ``evals/`` never ships: evaluations are never runtime resources (``docs/skills/specification.md``),
  and OpenCode lists a skill's files to the model. No other ``SKILL.md`` and no file at the entry's root: OpenCode
  scans ``{*.md,**/SKILL.md}`` there, so either would become a skill of its own (skills probe, 2026-11-04).
* **What a run gets** is :func:`plan`'s, computed once for every caller (the launch contract carries it): the card's
  ``skills:`` (``requested``), its ``optional_skills`` beyond them (``offered``), and of both what the install really
  holds (``exposed``). A name that is not shipped, or whose files no longer match the manifest, reports why
  (``reasons``) and the run goes on: a missing skill never fails a run.
* **The copy** (:func:`deliver`): only exposed skills, only the manifest's files, re-hashed after copying, into the
  run's own folder before its sandbox exists. What the run could reach is ``delivered``.

Every skill here is labelled ``unevaluated`` (:data:`LABEL`): the operator released them for the personal alpha, and
qualification is owed before anything beyond it. The package copy changes only by an explicit pull request that
re-hashes the manifest (:func:`tree_sha256`); the candidate folder keeps its own state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from functools import cache
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST = "manifest.json"
SHIPPED = "shipped"
SKILL_FILE = "SKILL.md"
ALLOWED_DIRS = ("references", "examples")
LABEL = "unevaluated"

# Why a skill a card names is not exposed (``reasons``): a closed set, for the system text, the Lead and E120's results
NOT_SHIPPED = "not_shipped"            # not in AEW's install: the card may name it, nothing serves it
HASH_MISMATCH = "hash_mismatch"        # the installed files differ from the manifest
OUTSIDE_ALLOW_LIST = "outside_allow_list"  # the manifest names a file the allow-list keeps out
COPY_FAILED = "copy_failed"            # the run's copy could not be made or did not re-hash
REASONS = (NOT_SHIPPED, HASH_MISMATCH, OUTSIDE_ALLOW_LIST, COPY_FAILED)


def allowed(rel: str) -> bool:
    """Whether a skill's file (``rel``, POSIX, relative to the skill's folder) may ship: ``SKILL.md`` itself, or a file
    under ``references/`` or ``examples/`` that is not another ``SKILL.md``."""
    parts = PurePosixPath(rel).parts
    if not parts or any(p in ("", ".", "..") for p in parts) or "\\" in rel or rel.startswith("/"):
        return False
    if parts == (SKILL_FILE,):
        return True
    return len(parts) >= 2 and parts[0] in ALLOWED_DIRS and parts[-1] != SKILL_FILE


def tree_sha256(files: dict[str, str]) -> str:
    """A skill's hash: over its files' hashes and paths, sorted, one ``<sha256>  <path>`` line each (``sha256sum``'s
    shape), so a file added, removed, renamed or changed moves it."""
    return hashlib.sha256("".join(f"{files[rel]}  {rel}\n" for rel in sorted(files)).encode("utf-8")).hexdigest()


@cache
def manifest() -> dict[str, Any]:
    """The manifest as shipped: ``{"skills": {id: {version, label, sha256, files: {path: sha256}, ...}}}``."""
    data = json.loads(resources.files(__name__).joinpath(MANIFEST).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def entries() -> dict[str, dict[str, Any]]:
    skills = manifest().get("skills")
    return skills if isinstance(skills, dict) else {}


def shipped() -> frozenset[str]:
    """The ids AEW's install ships (whether their files still match is :func:`check`'s)."""
    return frozenset(entries())


def _read(name: str, rel: str) -> bytes:
    node = resources.files(__name__).joinpath(SHIPPED, name)
    for part in PurePosixPath(rel).parts:
        node = node.joinpath(part)
    return node.read_bytes()


def check(name: str) -> tuple[str | None, dict[str, bytes]]:
    """``(None, files)`` when ``name`` is a shipped skill whose installed files match the manifest, with their bytes;
    otherwise ``(reason, {})``. ``name`` is only ever a key of the manifest here: a card's text never becomes a path."""
    entry = entries().get(name)
    if not isinstance(entry, dict):
        return NOT_SHIPPED, {}
    files = entry.get("files")
    if not isinstance(files, dict) or SKILL_FILE not in files:
        return HASH_MISMATCH, {}
    if not all(isinstance(rel, str) and allowed(rel) for rel in files):
        return OUTSIDE_ALLOW_LIST, {}
    out: dict[str, bytes] = {}
    for rel, want in files.items():
        try:
            data = _read(name, rel)
        except OSError:
            return HASH_MISMATCH, {}
        if hashlib.sha256(data).hexdigest() != want:
            return HASH_MISMATCH, {}
        out[rel] = data
    if tree_sha256(files) != entry.get("sha256"):
        return HASH_MISMATCH, {}
    return None, out


def _delivered(name: str, files: dict[str, bytes]) -> dict[str, Any]:
    entry = entries()[name]
    return {"name": name, "version": entry.get("version"),
            "sha256": tree_sha256({rel: hashlib.sha256(b).hexdigest() for rel, b in files.items()}),
            "label": LABEL, "bytes": len(files[SKILL_FILE])}


def plan(skills: list[str] | tuple[str, ...], optional: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """What a run of a card with ``skills:`` and ``optional_skills`` gets (the 2026-11-04 ruling, §5).

    ``requested`` is ``skills:``; ``offered`` is ``optional_skills`` beyond it (a name in both counts as ``skills:``);
    ``exposed`` is ``(requested ∪ offered) ∩ provided``, where provided means shipped and matching its manifest;
    ``unavailable`` keeps ADR-0006's meaning: what ``skills:`` asked for and did not get. ``reasons`` says why for
    every name in either list that is not exposed, and ``delivered`` is what an exposed skill is: name, version, hash,
    label, and its ``SKILL.md``'s size in bytes."""
    requested = sorted({str(s) for s in skills})
    offered = sorted({str(s) for s in optional} - set(requested))
    exposed: list[str] = []
    reasons: dict[str, str] = {}
    delivered: list[dict[str, Any]] = []
    for name in sorted({*requested, *offered}):
        why, files = check(name)
        if why is None:
            exposed.append(name)
            delivered.append(_delivered(name, files))
        else:
            reasons[name] = why
    return {"requested": requested, "offered": offered, "exposed": exposed,
            "unavailable": [s for s in requested if s not in exposed], "reasons": reasons, "delivered": delivered}


def root_problems(root: Path, exposed: list[str] | tuple[str, ...]) -> list[str]:
    """What, under the folder the harness scans, is not an exposed skill's allow-listed file: a file at the root, a
    folder that is no exposed skill, or a file the allow-list keeps out (another ``SKILL.md``, ``evals/``). Each would
    be listed to the model, or become a skill of its own. Empty when the folder is exactly the copy."""
    problems: list[str] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.is_symlink() or child.name not in exposed:
            problems.append(child.name)
            continue
        for path in sorted(child.rglob("*")):
            rel = path.relative_to(child).as_posix()
            if path.is_symlink() or (path.is_file() and not allowed(rel)):
                problems.append(f"{child.name}/{rel}")
    return problems


def deliver(planned: dict[str, Any], root: Path) -> dict[str, Any]:
    """Copy ``planned``'s exposed skills into ``root`` (made afresh: the run's own folder, before its sandbox exists),
    and return the plan as delivered. Only the manifest's files are written, each re-read and re-hashed; a skill whose
    copy fails or does not match is removed and reported ``copy_failed``, and the run goes on. Anything else found under
    ``root`` afterwards takes its skill out the same way. With nothing exposed, ``root`` does not exist."""
    exposed = list(planned.get("exposed") or [])
    reasons = dict(planned.get("reasons") or {})
    failed: set[str] = set()
    shutil.rmtree(root, ignore_errors=True)
    if exposed:
        try:
            root.mkdir(parents=True)
        except OSError:
            failed = set(exposed)
    for name in exposed if not failed else ():
        try:
            why, files = check(name)
            if why is not None:
                raise OSError(why)
            for rel, data in files.items():
                out = root / name / Path(*PurePosixPath(rel).parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            copied = {rel: hashlib.sha256((root / name / Path(*PurePosixPath(rel).parts)).read_bytes()).hexdigest()
                      for rel in files}
            if tree_sha256(copied) != entries()[name].get("sha256"):
                raise OSError("the copy does not match the manifest")
        except OSError:
            failed.add(name)
    if root.is_dir():
        for stray in root_problems(root, [n for n in exposed if n not in failed]):
            failed.add(stray.split("/", 1)[0])
    for name in failed:
        _remove(root / name)
        if name in exposed:
            reasons[name] = COPY_FAILED
    final = [n for n in exposed if n not in failed]
    if not final:
        shutil.rmtree(root, ignore_errors=True)
    requested = list(planned.get("requested") or [])
    return {**planned, "exposed": final, "unavailable": [s for s in requested if s not in final],
            "reasons": dict(sorted(reasons.items())),
            "delivered": [d for d in planned.get("delivered") or [] if d.get("name") in final]}


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def pins(skills: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """A pack's ``sources`` entries for the card's ``skills:`` (never ``optional_skills``: the 2026-11-04 ruling, §5),
    each shipped one by name, version and hash, as the manifest states them at dispatch. A name that is not shipped
    has nothing to pin. Pinning never affects a relaunch, which compares the rendered pack."""
    out = []
    for name in sorted({str(s) for s in skills}):
        entry = entries().get(name)
        if isinstance(entry, dict):
            out.append({"name": f"skill:{name}", "path": None, "sha256": entry.get("sha256"),
                        "version": entry.get("version"), "label": LABEL})
    return out

"""The prototype gate's harness, parent side (the pack-truth plan, reviewed CLEAR, §2.3).

- Each cell's fixture state is built unhooked, through the CLI, at the cell's own root, and frozen as a pristine copy.
- Every render restores that root from the pristine copy and runs in its own process (``pt_cell``), hooked or not, so
  the hooked and unhooked renders each run on their own copy of the same state, at the same paths, one after the other.
- Before a render, every file of the copy, and the product data the hook wraps, is scanned for U+E000-E005: one
  fails the render closed (V10-5).
- The renders are compared after normalising only the closed registry's values (V10-4).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pt_hook
import pt_trace
from aewflow import SUBTRACT_PATCH, Project, assign, create_planned_ticket, implement, sample_project

from aew.util import dump_yaml

HELPERS = Path(__file__).resolve().parent
CELL_SCRIPT = HELPERS / "pt_cell.py"
ROLES, MODES = ("implementer", "reviewer"), ("harness", "manual")
# The product data the hook wraps as units (§2.2): an input to every hooked render.
DATA_INPUTS = (pt_hook.PKG / "roles",)


class MarkerInInput(Exception):
    """An input to a hooked render holds a marker character (U+E000-E005): the render fails closed (V10-5)."""


@dataclass
class Fixture:
    role: str
    base: Path  # holds the cell root and its pristine copy
    root: Path  # the cell's state: the project, its workspaces and the report, at fixed paths
    spec: dict[str, Any] = field(default_factory=dict)

    @property
    def pristine(self) -> Path:
        return self.base / f"pristine-{self.role}"


def _rmtree(path: Path) -> None:
    def retry(func: Any, p: str, _: Any) -> None:
        os.chmod(p, stat.S_IWRITE)  # git's object files are read-only on Windows
        func(p)

    if path.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=retry)
        else:  # Python 3.11 (the Linux CI lanes) has only onerror
            shutil.rmtree(path, onerror=retry)


def build(base: Path, role: str) -> Fixture:
    """The cell's fixture, built unhooked through the CLI: an implementer dispatched on a planned Ticket, or a reviewer
    dispatched after a scripted implementer ran the `unit` check and submitted."""
    root = base / f"cell-{role}"
    root.mkdir(parents=True)
    calc: Project = sample_project(root)
    wid = create_planned_ticket(calc, root)
    report = root / "report.md"
    if role == "implementer":
        impl = assign(calc, wid)
        impl.write(SUBTRACT_PATCH)
        meta: dict[str, Any] = {
            "claim": "subtract implemented with a focused test", "result": "pass",
            "producer": {"model": "scripted", "harness": "pytest"},
            "implementation": {"files_changed": sorted(SUBTRACT_PATCH), "checks_run": ["guardrails"],
                               "deviations": [], "self_review": {"completed": True, "notes": "diff matches plan"}}}
        spec = {"invocation": impl.ok("whoami")["invocation"], "token": impl.token, "workspace": str(impl.workspace),
                "kind": "implementation_report", "check": "guardrails"}
    else:
        impl = assign(calc, wid)
        implement(impl)
        calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        out = calc.lead("invoke", "create", wid, "--role", "reviewer")
        workspace = calc.ok("work", "show", wid)["control"]["workspace"]["path"]
        meta = {"claim": "independent review of the change against plan and contracts",
                "producer": {"model": "scripted-reviewer"},
                "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}
        spec = {"invocation": out["invocation"], "token": out["invocation_token"], "workspace": workspace,
                "kind": "review", "check": None}
    report.write_text(f"---\n{dump_yaml(meta)}---\nScripted report.\n", encoding="utf-8", newline="\n")
    spec.update({"root": str(root), "repo": str(calc.root), "role": role, "report": str(report), "work_unit": wid})
    shutil.copytree(root, base / f"pristine-{role}", symlinks=True)
    return Fixture(role, base, root, spec)


def scan_for_markers(*trees: Path) -> list[str]:
    """Every file under ``trees`` that holds a marker character; an unreadable file is reported too (fail closed)."""
    found = []
    for tree in trees:
        for p in sorted(tree.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            try:
                data = p.read_bytes()
            except OSError as exc:
                found.append(f"{p}: unreadable ({exc})")
                continue
            if any(b in data for b in pt_hook.MARKER_BYTES):
                found.append(str(p))
    return found


def restore(fx: Fixture) -> None:
    """Put the cell root back to the pristine state: each render gets its own copy, at the paths the state names."""
    _rmtree(fx.root)
    shutil.copytree(fx.pristine, fx.root, symlinks=True)
    (fx.root / "tmp").mkdir()


def tamper_card(fx: Fixture) -> None:
    """The card negative control (item 4 of the prototype's review): the copy's stored card content differs from the
    built-in card it names (each prose leaf gains a token), written through the store's own serializer. The product
    renders it in manual mode (`context pack` regenerates and only reports the mismatch); its prose must stay
    unwrapped, so untraced."""
    from aew.engine.store import deserialize_control, serialize_control

    path = Path(fx.spec["repo"]) / ".aew/state/control.yaml"
    state = deserialize_control(path.read_bytes(), source=str(path))
    card = state["invocations"][fx.spec["invocation"]]["card"]

    def walk(o: Any) -> Any:
        if isinstance(o, str):
            return o + " AEW_PT_NEG_CARD then run it" if " " in o else o
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    card["content"] = walk(card["content"])
    path.write_bytes(serialize_control(state))


def run(fx: Fixture, mode: str, *, hooked: bool, plants: dict[str, dict[str, str]] | None = None,
        yaml_plants: dict[str, dict[str, str]] | None = None, quoted: Path | None = None,
        probe_write: Path | None = None, negatives: list[str] | None = None, tampered_card: bool = False,
        check: bool = True, timeout: float = 300) -> dict[str, Any]:
    """One render of the cell in its own process, on a fresh copy of its state. With ``check`` false, a render that
    fails is returned as ``{"error": ...}`` so each test can fail on its own named assertion (F6 of the review)."""
    restore(fx)
    if tampered_card:
        tamper_card(fx)
    found = scan_for_markers(fx.root, *DATA_INPUTS)
    if found:
        raise MarkerInInput(f"inputs hold U+E000-E005: {found}")
    spec = {**fx.spec, "mode": mode, "hooked": hooked, "plants": plants or {}, "yaml_plants": yaml_plants or {},
            "quoted": str(quoted) if quoted else None, "probe_write": str(probe_write) if probe_write else None,
            "negatives": negatives or []}
    spec_path = fx.base / f"spec-{fx.role}-{mode}-{'hooked' if hooked else 'plain'}.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8", newline="\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("AEW_") or k == "AEW_CUSTODY_WORKER"}
    env["PYTHONPATH"] = str(pt_hook.SRC)
    kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else \
        {"start_new_session": True}
    proc = subprocess.run([sys.executable, "-B", "-X", "utf8", str(CELL_SCRIPT), str(spec_path)], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                          stdin=subprocess.DEVNULL, **kwargs)
    if proc.returncode != 0:
        why = f"cell {fx.role}/{mode} hooked={hooked} failed ({proc.returncode}): {proc.stderr[-4000:]}"
        if check:
            raise RuntimeError(why)
        return {"error": why}
    return json.loads(proc.stdout)


# ------------------------------------------------------------------------------------------- texts and comparison


def is_json(name: str) -> bool:
    return name in pt_trace.JSON_TEXTS


def strip_render(hooked: dict[str, Any]) -> dict[str, Any]:
    """The hooked render's texts with every marker removed. A JSON result escapes its markers (§2.2), so it is decoded,
    stripped and re-encoded as the CLI's ``emit`` encodes a result (two-space indent, insertion order)."""
    out = {}
    for name, entry in hooked["texts"].items():
        e = dict(entry)
        if is_json(name) and entry["code"] == 0:
            e["stdout"] = json.dumps(_strip_obj(json.loads(entry["stdout"])), indent=2, sort_keys=False,
                                     default=str) + "\n"
        else:
            e["stdout"] = pt_hook.strip(entry["stdout"])
        e["stderr"] = pt_hook.strip(entry["stderr"])
        out[name] = e
    return out


def _strip_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return pt_hook.strip(obj)
    if isinstance(obj, dict):
        return {pt_hook.strip(k): _strip_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_obj(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Difference:
    text: str
    hooked: str
    plain: str


def strip_equivalence(hooked: dict[str, Any], plain: dict[str, Any], normalise: list[re.Pattern[str]]) -> list[
        Difference]:
    """Every text where the hooked render, stripped, differs from the unhooked one, after normalising only the values
    the patterns name (the closed registry's timestamps, ids, durations and counts). A render that failed is itself a
    difference (its error)."""
    if "error" in hooked or "error" in plain:
        return [Difference("<the render>", hooked.get("error", ""), plain.get("error", ""))]
    stripped = strip_render(hooked)
    diffs = []
    if set(stripped) != set(plain["texts"]):
        diffs.append(Difference("<the set of texts>", str(sorted(stripped)), str(sorted(plain["texts"]))))
    for name in sorted(set(stripped) & set(plain["texts"])):
        a, b = stripped[name], plain["texts"][name]
        for part in ("code", "stdout", "stderr"):
            x, y = str(a[part]), str(b[part])
            for rx in normalise:
                x, y = rx.sub("<registry value>", x), rx.sub("<registry value>", y)
            if x != y:
                diffs.append(Difference(f"{name}:{part}", x, y))
    return diffs

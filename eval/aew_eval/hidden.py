"""The hidden-evaluator channel (evaluation component design v0.2, §5 and §8 step 3; decisions 5 and 7).

The M3 rule stands: hidden checks never enter a repository a model works in. An oracle is a directory in the private
repository, ``<root>/cases/<case>/oracle/``, holding ``checks.py`` and anything it needs (a ``reference/`` tree, a
``manifest.yaml``). ``<root>`` comes from ``AEW_EVAL_HIDDEN_ROOT``, an evaluator-only variable.

* :func:`take_root` reads it, resolves it, and **removes it from this process's environment** before any arm runs, so
  no process an arm starts inherits it.
* :meth:`Oracle.locate` reads the oracle **once**, before the attempt is registered. Those bytes are hashed
  (``hidden_sha256``, line ends normalized like a fixture's, so Windows and Linux checkouts agree), and they are the
  bytes that score: an oracle changed on disk afterwards, and changed back, cannot score. A cell is refused when its
  oracle is missing or no longer matches its commitment. A held-out case, with or without an oracle, is refused once
  ``exposure.yaml`` records it as exposed (decision 7), and wherever scoring cannot be contained (below).
* :func:`score` runs **after the arm has returned**, on the exported final tree. The oracle's bytes go to the scoring
  process (``score_child``) on its standard input and **never touch the disk**. That process runs in an AEW process
  tree, ended on return or timeout. It never learns the root and never imports the model's code. The checks reach the
  model's program only through ``run``, which gives every program a process tree of its own, ended when it returns
  (a job object on Windows; on Linux a bubblewrap sandbox in its own pid namespace), and an allow-listed environment.
* **What a score is.** The child must exit 0 and write exactly one JSON object with a list of ``{name, ok,
  detail}``; ``passed`` is computed here (every check ``ok``, at least one). Anything else (no result, extra output, a
  timeout, a nonzero exit) is a **failed score with a reason**, counted against the run, never a retryable
  ``invalid_measurement``, so the model's program cannot turn a failure into a retry. A broken oracle fails the same
  way, so an oracle is exercised against the reference (a scripted arm) before an experiment freezes.

A ``checks.py`` defines ``checks(tree, run)`` and yields ``(name, ok, detail)``. ``run(argv, cwd=, input=, env=,
timeout=)`` runs the model's program and returns its exit code and output (``returncode`` is ``None`` on a timeout).
Reference material is ``ORACLE_FILES`` (``{path: bytes}``), never a path.

**Where scoring is contained, and where not.** On Linux with bubblewrap, the model's programs run in a sandbox with
the hidden root, the ledger and the user's secrets masked, and in their own pid namespace, so the runner's ``/proc``
entry (which still holds the root's path) is out of reach. Linux without bubblewrap refuses every oracle-scored cell.
Elsewhere (Windows) a same-user program could search the disk for the private corpus, so held-out cases are refused
there before anything is counted; other cases score with that exposure stated. The arms that run a model must meet the
same bar while the model runs: the next slice.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from aew_eval import fixture
from aew_eval.schemas import Invalid

ENV = "AEW_EVAL_HIDDEN_ROOT"
CHECKS = "checks.py"
SCORE_TIMEOUT_S = 900.0
CHILD = Path(__file__).resolve().with_name("score_child.py")


def take_root(environ: MutableMapping[str, str] | None = None) -> Path | None:
    """The hidden root, resolved, and removed from ``environ`` (this process's environment by default) so that nothing
    started later inherits it; ``None`` when it is not set."""
    env = os.environ if environ is None else environ
    raw = env.pop(ENV, None)
    return resolve_root(Path(raw)) if raw else None


def resolve_root(root: Path) -> Path:
    """The root as a canonical path, so an 8.3 name, a relative path or a linked ancestor names it (review, 6)."""
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise Invalid(f"the hidden root {root} cannot be read ({exc})") from None


@dataclass(frozen=True)
class Oracle:
    case: str
    files: dict[str, bytes] = field(repr=False)
    sha256: str

    @classmethod
    def locate(cls, root: Path, case: str) -> Oracle:
        """The case's oracle under ``root``, read once and hashed; refuses one with no ``checks.py``."""
        path = resolve_root(root) / "cases" / fixture.safe_relative(case, "case id") / "oracle"
        if not path.is_dir():
            raise Invalid(f"no oracle for case {case} under the hidden root")
        files = fixture._read_tree(path, "oracle")  # noqa: SLF001 (one reading and hashing rule for every tree)
        if CHECKS not in files:
            raise Invalid(f"the oracle of case {case} has no {CHECKS}")
        return cls(case, files, fixture._digest(files))  # noqa: SLF001


def content_sha256(path: Path) -> str:
    """An oracle directory's content hash (what a case manifest commits to)."""
    return fixture._digest(fixture._read_tree(path, "oracle"))  # noqa: SLF001


def exposure(root: Path, case: str) -> list[dict[str, Any]]:
    """The events that revealed ``case``: ``<root>/cases/<case>/exposure.yaml`` (none when absent)."""
    path = root / "cases" / fixture.safe_relative(case, "case id") / "exposure.yaml"
    if not path.is_file():
        return []
    events = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(events, list):
        raise Invalid(f"exposure.yaml of case {case} is a list of events")
    return events


def require(root: Path | None, oracle: Oracle | None, *, case: str, commitment: str | None, held_out: bool) -> None:
    """Refuse a cell, before it is registered, whose oracle does not match the preregistered commitment, or whose
    held-out case has been exposed (checked for every held-out case, oracle or not: review, 8)."""
    if held_out:
        if root is None:
            raise Invalid(f"case {case} is held out: run with {ENV} set, so its exposure can be checked")
        if exposure(root, case):
            raise Invalid(f"case {case} is held out but has been exposed (exposure.yaml): it is no longer held-out "
                          "evidence; replace it, or preregister it as not held out")
        if not scoring_contained():
            raise Invalid(f"case {case} is held out, and its scoring cannot be contained here (Linux with bubblewrap "
                          "only): a model's program could search this host for the private corpus")
    if commitment is None:
        return
    if oracle is None:
        raise Invalid(f"case {case} is scored by a hidden oracle: run with {ENV} set to the private evaluation root")
    if oracle.sha256 != commitment:
        raise Invalid(f"the oracle of case {case} is not the preregistered one (its content hash changed)")
    if sys.platform.startswith("linux") and not scoring_contained():
        raise Invalid(f"case {case} is scored by a hidden oracle, and scoring on Linux needs bubblewrap")


def _failed(oracle: Oracle, reason: str, detail: str) -> dict[str, Any]:
    return {"passed": False, "failure": reason, "checks": [{"name": reason, "ok": False, "detail": detail[-1200:]}],
            "hidden_sha256": oracle.sha256}


def _parse(stdout: str) -> list[dict[str, Any]] | None:
    """The child's checks, if its whole output is exactly one well-formed result object."""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    checks = result.get("checks") if isinstance(result, dict) and set(result) == {"checks"} else None
    if not isinstance(checks, list) or not all(
            isinstance(c, dict) and set(c) == {"name", "ok", "detail"} and isinstance(c["ok"], bool)
            and isinstance(c["name"], str) and isinstance(c["detail"], str) for c in checks):
        return None
    return checks


def scoring_contained() -> bool:
    """Whether the model's programs can be contained while they are scored: Linux with bubblewrap. Elsewhere a same-user
    program could search the disk for the private corpus."""
    from aew.harness.containment.layout import find_bwrap

    return sys.platform.startswith("linux") and find_bwrap() is not None


WINDOWS_ENV = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
POSIX_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ")


def program_env(scratch: Path) -> dict[str, str]:
    """The model's programs' environment: an allow-list (no credential, no provider key, no hidden root), with home and
    temporary directories in a scratch directory of their own (review of 7c743ff, 5)."""
    keep = WINDOWS_ENV if sys.platform == "win32" else POSIX_ENV
    env = {k: os.environ[k] for k in keep if k in os.environ}
    for name in ("HOME", "USERPROFILE", "TEMP", "TMP") if sys.platform == "win32" else ("HOME",):
        env[name] = str(scratch)
    return env


def scoring_layout(tree: Path, scratch: Path, hide: list[Path]) -> Any:
    """Linux: the sandbox the model's programs are scored in. The tree and a scratch directory are writable; the hidden
    root, the ledger and the user's secrets are masked; its own pid namespace hides every other process, the runner's
    ``/proc`` entry included."""
    from aew.harness.containment import layout as L

    bwrap = L.find_bwrap()
    if bwrap is None:
        raise Invalid("scoring needs bubblewrap on Linux; nothing scores uncontained there")
    dirs, files = L._masks(os.path.expanduser("~"), [])  # noqa: SLF001 (the same secret masks as every run)
    hidden_dirs = [*dirs, *(os.path.realpath(p) for p in hide if p.is_dir())]
    mask = scratch / ".aew-mask"
    mask.write_bytes(b"")
    readonly = sorted({os.path.realpath(p) for p in (sys.prefix, sys.base_prefix) if p and os.path.isdir(p)})
    return L.Layout(role="eval-scoring", access="write", bwrap=bwrap,
                    writable=(os.path.realpath(tree), os.path.realpath(scratch)), readonly=tuple(readonly),
                    hide_dirs=tuple(dict.fromkeys(hidden_dirs)), hide_files=files, mask_file=str(mask),
                    env={"TMPDIR": L.SANDBOX_TMP, "PYTHONDONTWRITEBYTECODE": "1"})


def score(oracle: Oracle, tree: Path, *, hide: tuple[Path, ...] | list[Path] = (),
          timeout_s: float = SCORE_TIMEOUT_S) -> dict[str, Any]:
    """Score the exported ``tree`` with the oracle's checks: the oracle's bytes go to the scoring process on its
    standard input (never to the disk), and that process runs in an AEW process tree ended on return or timeout.
    ``hide`` names what the model's programs must not see besides the hidden root (the ledger)."""
    import base64
    import dataclasses

    from aew.harness.procs import ProcessTree

    scratch = Path(tempfile.mkdtemp(prefix="aew-eval-scoring-")).resolve()  # TEMP may be an 8.3 name (review, 6)
    try:
        layout = scoring_layout(tree, scratch, list(hide)) if sys.platform.startswith("linux") else None
        spec = {"files": {rel: base64.b64encode(data).decode("ascii") for rel, data in oracle.files.items()},
                "layout": dataclasses.asdict(layout) if layout is not None else None,
                "env": program_env(scratch)}
        env = {k: v for k, v in os.environ.items() if k != ENV}
        procs = ProcessTree()
        try:
            proc = procs.spawn([sys.executable, "-I", "-B", str(CHILD), str(tree)], cwd=str(tree), env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                raw_out, raw_err = proc.communicate(input=json.dumps(spec).encode("utf-8"), timeout=timeout_s)
            except subprocess.TimeoutExpired:
                procs.kill()
                proc.communicate()
                return _failed(oracle, "SCORING_TIMEOUT", f"scoring ran over {timeout_s:g} s")
        finally:
            procs.close()
        stdout, stderr = raw_out.decode("utf-8", "replace"), raw_err.decode("utf-8", "replace")
        checks = _parse(stdout) if proc.returncode == 0 else None
        if checks is None:
            return _failed(oracle, "SCORING_NO_RESULT",
                           f"exit {proc.returncode}; output {stdout[-300:]!r}; errors {stderr[-600:]}")
        return {"passed": bool(checks) and all(c["ok"] for c in checks), "failure": None, "checks": checks,
                "hidden_sha256": oracle.sha256}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

"""The hidden-evaluator channel (evaluation component design v0.2, §5 and §8 step 3; decisions 5 and 7).

The M3 rule stands: hidden checks never enter a repository a model works in, and no model-controlled process can reach
them. An oracle is a directory in the private repository, ``<root>/cases/<case>/oracle/``, holding ``checks.py`` and
anything it needs (a ``reference/`` tree, a ``manifest.yaml``). ``<root>`` comes from ``AEW_EVAL_HIDDEN_ROOT``, an
evaluator-only variable.

* :func:`take_root` reads it, resolves it, and **removes it from this process's environment** before any arm runs, so
  no process an arm starts inherits it.
* :meth:`Oracle.locate` reads the oracle **once**, before the attempt is registered: those bytes are hashed
  (``hidden_sha256``, line ends normalized like a fixture's, so Windows and Linux checkouts agree) and are what scores,
  so an oracle changed on disk afterwards, and changed back, cannot score (PR #105 review, 4). Reading closes every
  file: no oracle descriptor is open while the arm runs. A cell is refused when its oracle is missing or no longer
  matches its commitment, and a held-out case (with or without an oracle) is refused once ``exposure.yaml`` records it
  as exposed (decision 7).
* :func:`score` runs **after the arm has returned**, on the exported final tree. It writes the oracle's bytes to a new
  evaluator-owned directory outside the root, runs ``python -I -B score_child.py <copy>/checks.py <tree>`` in an AEW
  process tree (a job object on Windows, a process group on POSIX) that is ended with everything in it on return or
  timeout, and deletes the copy. The scoring process never learns the root, never imports the model's code, and reaches
  the model's program only through ``run`` (see ``score_child``).
* **What a score is.** The child must exit 0 and write exactly one JSON object with a list of ``{name, ok, detail}``;
  ``passed`` is computed here (every check ``ok``, at least one). Anything else (no result, extra output, a timeout,
  a nonzero exit, or the oracle copy changed while scoring) is a **failed score with a reason**, counted against the
  run, never a retryable ``invalid_measurement``: the model's program must not be able to turn a failure into a retry
  (review, 3). A broken oracle fails the same way, so an oracle is exercised against the reference (a scripted arm)
  before an experiment freezes.

A ``checks.py`` defines ``checks(tree, run)`` and yields ``(name, ok, detail)``; ``run(argv, cwd=, input=, env=,
timeout=)`` runs the model's program and returns its exit code and output (``returncode`` is ``None`` on a timeout).

Residuals, stated rather than claimed closed:

* **Linux.** Removing the variable does not remove it from ``/proc/<runner>/environ``, and a same-user process can
  reach another's descriptors through ``/proc``. Arms that run a model on Linux must therefore run it in its own pid
  namespace, with the hidden root masked in its containment layout (the ``aew`` arm through AEW's containment, the
  ``raw`` arm alike): a requirement on the arms slice (review, 7). Windows has no such channel; the job object ends
  every process the scoring started.
* **The checks see the model's program's output, not its internals.** A check that needs a value calls the program
  (a one-line ``python -c``) and parses what it prints.
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
    if commitment is None:
        return
    if oracle is None:
        raise Invalid(f"case {case} is scored by a hidden oracle: run with {ENV} set to the private evaluation root")
    if oracle.sha256 != commitment:
        raise Invalid(f"the oracle of case {case} is not the preregistered one (its content hash changed)")


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


def score(oracle: Oracle, tree: Path, *, timeout_s: float = SCORE_TIMEOUT_S) -> dict[str, Any]:
    """Score the exported ``tree`` with the oracle's checks, from a private copy, in an isolated process tree."""
    from aew.harness.procs import ProcessTree

    copy = Path(tempfile.mkdtemp(prefix="aew-eval-oracle-")).resolve()  # TEMP may be an 8.3 name (review, 6)
    try:
        for rel, data in oracle.files.items():
            out = copy / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        env = {k: v for k, v in os.environ.items() if k != ENV}
        procs = ProcessTree()
        try:
            proc = procs.spawn([sys.executable, "-I", "-B", str(CHILD), str(copy / CHECKS), str(tree)],
                               cwd=str(copy), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
            try:
                raw_out, raw_err = proc.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                procs.kill()
                proc.communicate()
                return _failed(oracle, "SCORING_TIMEOUT", f"scoring ran over {timeout_s:g} s")
        finally:
            procs.close()
        try:
            intact = fixture._digest(fixture._read_tree(copy, "oracle copy")) == oracle.sha256  # noqa: SLF001
        except Invalid:  # a link or an odd file planted in the copy: tampering, never a retryable runner error
            intact = False
        if not intact:
            return _failed(oracle, "ORACLE_TAMPERED", "the oracle's copy changed while it scored the run")
        stdout, stderr = raw_out.decode("utf-8", "replace"), raw_err.decode("utf-8", "replace")
        checks = _parse(stdout) if proc.returncode == 0 else None
        if checks is None:
            return _failed(oracle, "SCORING_NO_RESULT",
                           f"exit {proc.returncode}; output {stdout[-300:]!r}; errors {stderr[-600:]}")
        return {"passed": bool(checks) and all(c["ok"] for c in checks), "failure": None, "checks": checks,
                "hidden_sha256": oracle.sha256}
    finally:
        shutil.rmtree(copy, ignore_errors=True)

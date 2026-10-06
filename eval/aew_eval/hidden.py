"""The hidden-evaluator channel (evaluation component design v0.2, §5 and §8 step 3; decisions 5 and 7).

The M3 rule stands: hidden checks never enter a repository a model works in, and no model-controlled process can reach
them. An oracle is a directory in the private repository, ``<root>/cases/<case>/oracle/``, holding ``checks.py`` and
anything it needs (a ``reference/`` tree, a ``manifest.yaml``). ``<root>`` comes from ``AEW_EVAL_HIDDEN_ROOT``, an
evaluator-only variable:

* :func:`take_root` reads it **and removes it from this process's environment** before any arm runs, so no process an
  arm starts can inherit it. Nothing else here reads the environment.
* :class:`Oracle` is located and hashed before the attempt is registered. The hash (``hidden_sha256``) is
  the content of every file in the oracle directory, line ends normalized like a fixture's, so a Windows and a Linux
  checkout of the private repository agree. A preregistered cell whose oracle no longer matches its commitment is
  refused, and so is one whose case is held out but has been exposed (decision 7).
* Hashing reads each file and closes it: no oracle file descriptor is open while the arm runs.
* :func:`score` runs **after the arm has returned**, on the exported final tree (outside the scratch repository). It
  starts ``python -I -B score_child.py <checks.py> <tree>`` in a fresh, isolated process (``score_child``): the checks
  may import and run the model's code, which must not run inside the runner, and must not be able to replace what the
  scoring script imports. Its environment is the runner's, less the hidden root, and it writes no bytecode into the
  oracle. The oracle is hashed again afterwards; a changed oracle makes the run invalid.

A ``checks.py`` defines ``checks(tree: Path)``, yielding ``(name, ok, detail)`` for each check, as the M3
``hidden.py`` does per task. The score is ``{"passed", "checks": [{"name", "ok", "detail"}], "hidden_sha256"}``;
``passed`` is every check.

Exposure: ``<root>/cases/<case>/exposure.yaml`` lists the events that revealed the case (``[{at, by, what}]``). Such a
case can still be run, but never as held-out evidence: a preregistration that lists it in ``held_out`` is refused.

Residual, as in M3: the checks run the model's code in the scoring process, so model code could, in principle, try to
defeat an in-process comparison. Checks that matter should drive the program from outside (a subprocess, the CLI),
as the M3 checks mostly do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aew_eval import fixture
from aew_eval.schemas import Invalid

ENV = "AEW_EVAL_HIDDEN_ROOT"
CHECKS = "checks.py"
SCORE_TIMEOUT_S = 900.0
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CHILD = Path(__file__).resolve().with_name("score_child.py")


def take_root(environ: dict[str, str] | None = None) -> Path | None:
    """The hidden root, removed from ``environ`` (this process's environment by default) so that nothing started
    later inherits it; ``None`` when it is not set."""
    env = os.environ if environ is None else environ
    raw = env.pop(ENV, None)
    return Path(raw) if raw else None


@dataclass(frozen=True)
class Oracle:
    case: str
    path: Path
    sha256: str

    @classmethod
    def locate(cls, root: Path, case: str) -> Oracle:
        """The case's oracle under ``root``, hashed now; refuses an oracle with no ``checks.py``."""
        path = root / "cases" / fixture.safe_relative(case, "case id") / "oracle"
        if not path.is_dir():
            raise Invalid(f"no oracle for case {case} under the hidden root")
        if not (path / CHECKS).is_file():
            raise Invalid(f"the oracle of case {case} has no {CHECKS}")
        return cls(case, path, content_sha256(path))

    def exposure(self) -> list[dict[str, Any]]:
        """The events that revealed this case, from ``exposure.yaml`` beside the oracle (none when absent)."""
        path = self.path.parent / "exposure.yaml"
        if not path.is_file():
            return []
        events = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(events, list):
            raise Invalid(f"{path.name} of case {self.case} is a list of events")
        return events


def content_sha256(path: Path) -> str:
    """The oracle directory's content hash: every regular file, line ends normalized (a link is refused)."""
    return fixture._digest(fixture._read_tree(path, "oracle"))  # noqa: SLF001 (one hashing rule for every tree)


def require(oracle: Oracle | None, *, case: str, commitment: str | None, held_out: bool) -> None:
    """Refuse a cell, before it is registered, whose oracle does not match the preregistered commitment, or whose
    held-out case has been exposed."""
    if commitment is None:
        return
    if oracle is None:
        raise Invalid(f"case {case} is scored by a hidden oracle: run with {ENV} set to the private evaluation root")
    if oracle.sha256 != commitment:
        raise Invalid(f"the oracle of case {case} is not the preregistered one (its content hash changed)")
    if held_out and oracle.exposure():
        raise Invalid(f"case {case} is held out but has been exposed (exposure.yaml): it is no longer held-out "
                      "evidence; replace it, or preregister it as not held out")


def score(oracle: Oracle, tree: Path, *, timeout_s: float = SCORE_TIMEOUT_S) -> dict[str, Any]:
    """Score the exported ``tree`` with the oracle's checks in a separate process; raises if the oracle changed."""
    env = {k: v for k, v in os.environ.items() if k != ENV}
    proc = subprocess.run([sys.executable, "-I", "-B", str(CHILD), str(oracle.path / CHECKS), str(tree)],
                          cwd=tree, env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s,
                          stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, check=False)
    after = content_sha256(oracle.path)
    if after != oracle.sha256:
        raise RuntimeError(f"the oracle of case {oracle.case} changed while it scored the run")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RuntimeError(f"the oracle's checks produced no result (exit {proc.returncode}): "
                           f"{proc.stderr[-600:]}") from None
    return {**result, "hidden_sha256": oracle.sha256}

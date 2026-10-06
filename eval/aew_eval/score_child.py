"""The scoring process of the hidden-evaluator channel: ``python -I -B score_child.py <tree>``, the oracle on stdin.

**The model's code never runs in this process**, and **the oracle never touches the disk.** The process is isolated
(``-I``: no ``PYTHONPATH``, no user site, not this script's directory on the path), the tree is never on its path, and
it imports only the standard library and AEW (from the installed package). Standard input carries one JSON object:
``{"files": {path: base64}, "layout": {...} | null, "env": {...}}``: the oracle's files, read once by the runner and
hashed there, which the checks see as ``ORACLE_FILES`` (``{path: bytes}``); the containment layout for the model's
programs (Linux); and the minimal environment they get.

An oracle's ``checks(tree, run)`` reaches the model's program only through ``run``, which starts it in a process tree of
its own (AEW's ``ProcessTree``: a job object on Windows; on Linux a bubblewrap sandbox in its own pid namespace, the
hidden root, the ledger and the user's secrets masked, so not even the runner's ``/proc`` entry is visible) and ends
that whole tree when it returns or times out. The program gets an allow-listed environment, its own pipes and no
console window (PR #105 reviews: findings 1 to 5 of each).

Writes exactly one JSON object to standard output, ``{"checks": [{"name", "ok", "detail"}]}``, and exits 0; the
runner computes ``passed`` itself and treats anything else as a failed score. A check that raises, of any kind, is a
failed check.
"""

import base64
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from aew.harness.containment.layout import Layout, bwrap_argv
from aew.harness.procs import ProcessTree


class Ran:
    """What one program run returned: its exit code (``None`` when it timed out) and its output, as text."""

    def __init__(self, returncode: int | None, stdout: str, stderr: str, timed_out: bool) -> None:
        self.returncode, self.stdout, self.stderr, self.timed_out = returncode, stdout, stderr, timed_out

    def __repr__(self) -> str:
        return f"Ran(returncode={self.returncode!r}, timed_out={self.timed_out}, stdout={self.stdout[-300:]!r})"


def make_run(tree: Path, layout: Layout | None, base_env: dict[str, str]):
    def run(argv, *, cwd=None, input=None, env=None, timeout=120):
        """Run the model's program: ``argv`` in ``cwd`` (the tree by default), contained, with its own pipes,
        standard input closed unless ``input`` is given, the tree on ``PYTHONPATH``, and an allow-listed
        environment; everything it started ends when it returns."""
        where = str(cwd or tree)
        full_env = {**base_env, "PYTHONPATH": str(tree), "PYTHONUTF8": "1", **(layout.env if layout else {}),
                    **(env or {})}
        command = [str(a) for a in argv]
        if layout is not None:  # Linux: the sandbox; ProcessTree would wrap without the working directory
            command = bwrap_argv(layout, command, cwd=where)
        procs = ProcessTree()
        try:
            proc = procs.spawn(command, cwd=where, env=full_env,
                               stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timed_out = False
            try:
                out, err = proc.communicate(input=None if input is None else input.encode("utf-8"), timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                procs.kill()
                out, err = proc.communicate()
        finally:
            procs.close()  # nothing it started outlives it
        return Ran(None if timed_out else proc.returncode, out.decode("utf-8", "replace"),
                   err.decode("utf-8", "replace"), timed_out)
    return run


def score(spec: dict[str, Any], tree: Path) -> dict[str, Any]:
    results = []
    try:
        files = {rel: base64.b64decode(data) for rel, data in spec["files"].items()}
        layout = None
        if spec.get("layout"):
            fields: dict[str, Any] = {k: (tuple(v) if isinstance(v, list) else v) for k, v in spec["layout"].items()}
            layout = Layout(**fields)
        namespace: dict[str, Any] = {"__name__": "aew_eval_oracle_checks", "ORACLE_FILES": files}
        exec(compile(files["checks.py"], "<oracle checks.py>", "exec"), namespace)  # noqa: S102 (the oracle's code)
        for name, ok, detail in namespace["checks"](tree, make_run(tree, layout, dict(spec.get("env") or {}))):
            results.append({"name": str(name), "ok": ok is True, "detail": str(detail)[-600:]})
    except BaseException:  # noqa: BLE001 (any failure in the checks, SystemExit included, is a failed check)
        results.append({"name": "checks raised", "ok": False, "detail": traceback.format_exc()[-1200:]})
    return {"checks": results}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python -I -B score_child.py <tree>   (the oracle as JSON on standard input)\n")
        sys.exit(2)
    sys.dont_write_bytecode = True
    result = score(json.loads(sys.stdin.read()), Path(sys.argv[1]).resolve())
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    os._exit(0)

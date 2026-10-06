"""The scoring process of the hidden-evaluator channel: ``python -I -B score_child.py <oracle copy> <tree>``.

**The model's code never runs in this process.** It is isolated (``-I``: no ``PYTHONPATH``, no user site, not even this
script's directory on the path), the tree is never put on its path, and an oracle's ``checks(tree, run)`` reaches the
model's program only through ``run``: a separate process, with its own pipes, no console window and a timeout, whose
whole process tree is ended when it returns or times out. So nothing in the tree can replace a module this process or
the checks import, patch a builtin, or write to this process's output (PR #105 review, findings 1 to 3).

Writes exactly one JSON object to standard output, ``{"checks": [{"name", "ok", "detail"}]}``, and exits 0; the
runner computes ``passed`` itself and treats anything else as a failed score. A check that raises, of any kind, is a
failed check.
"""

import json
import os
import signal
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, cast

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Ran:
    """What one program run returned: its exit code (``None`` when it timed out) and its output, as text."""

    def __init__(self, returncode, stdout, stderr, timed_out):
        self.returncode, self.stdout, self.stderr, self.timed_out = returncode, stdout, stderr, timed_out

    def __repr__(self):
        return f"Ran(returncode={self.returncode!r}, timed_out={self.timed_out}, stdout={self.stdout[-300:]!r})"


def _end_tree(proc):
    """End ``proc`` and everything it started (a process group on POSIX; the tree, by taskkill, on Windows; the
    runner's job object ends anything left when this process exits)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=NO_WINDOW, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


def make_run(tree):
    def run(argv, *, cwd=None, input=None, env=None, timeout=120):
        """Run the model's program: ``argv`` in ``cwd`` (the tree by default), its own pipes, standard input closed
        unless ``input`` is given, the tree on ``PYTHONPATH``, ended with everything it started when it returns."""
        full_env = {**os.environ, "PYTHONPATH": str(tree), "PYTHONUTF8": "1", **(env or {})}
        kwargs: dict[str, Any] = ({"creationflags": NO_WINDOW} if sys.platform == "win32"
                                  else {"start_new_session": True})
        proc = subprocess.Popen([str(a) for a in argv], cwd=str(cwd or tree), env=full_env,
                                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        timed_out = False
        try:
            out, err = proc.communicate(input=None if input is None else input.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _end_tree(proc)
            out, err = proc.communicate()
        finally:
            _end_tree(proc)  # nothing it started outlives it
        return Ran(None if timed_out else proc.returncode, cast(bytes, out).decode("utf-8", "replace"),
                   cast(bytes, err).decode("utf-8", "replace"), timed_out)
    return run


def score(checks_py, tree):
    results = []
    try:
        namespace: dict[str, Any] = {"__name__": "aew_eval_oracle_checks", "__file__": str(checks_py)}
        exec(compile(checks_py.read_bytes(), str(checks_py), "exec"), namespace)  # noqa: S102 (the oracle's own code)
        for name, ok, detail in namespace["checks"](tree, make_run(tree)):
            results.append({"name": str(name), "ok": ok is True, "detail": str(detail)[-600:]})
    except BaseException:  # noqa: BLE001 (any failure in the checks, SystemExit included, is a failed check)
        results.append({"name": "checks raised", "ok": False, "detail": traceback.format_exc()[-1200:]})
    return {"checks": results}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: python -I -B score_child.py <checks.py> <tree>\n")
        sys.exit(2)
    sys.dont_write_bytecode = True
    result = score(Path(sys.argv[1]), Path(sys.argv[2]).resolve())
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    os._exit(0)

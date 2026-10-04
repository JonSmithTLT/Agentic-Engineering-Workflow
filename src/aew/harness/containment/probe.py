"""The launch self-test: the run's own assembled layout, exercised before any harness process starts (M4-B).

A probe process runs inside the layout and tries what containment must stop and what the role must be able to do:

* append to an existing sentinel outside every writable root, and create a new sibling next to the workspace;
* open each protected path for writing (checked with ``access(W_OK)``, which a read-only mount refuses without
  changing anything): the repository's real git metadata, the project's ``.aew``, and two markers the host places
  for the probe only, one in the host's temporary directory (where every run's bridge socket lives) and one in a
  sibling run's directory (M4-B review: whatever widened the layout, reaching these fails the test);
* create a file in every writable root.

The host then checks the outcome itself: the sentinel is byte-identical, the sibling does not exist, each writable
root's file arrived on the host (a bind that is not the host's path is not a writable root). A layout that passes
is contained; anything else is a failure with its reason. The test catches bind-order mistakes, such as a broad
writable root laid over the read-only host.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

from aew.harness.containment.layout import Layout, bwrap_argv

TIMEOUT_S = 30.0

_PAYLOAD = r"""
import json, os, sys
spec = json.loads(sys.argv[1])
def append(p):
    try:
        fd = os.open(p, os.O_WRONLY | os.O_APPEND)
    except OSError:
        return False
    try:
        os.write(fd, b"x")
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
def create(p):
    try:
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return True
    except OSError:
        return False
print(json.dumps({
    "sentinel_written": append(spec["sentinel"]),
    "sibling_created": create(spec["sibling"]),
    "writable": {p: create(os.path.join(p, spec["name"])) for p in spec["writable"]},
    "protected_writable": [p for p in spec["protected"] if os.access(p, os.W_OK)],
    "pid": os.getpid(),
}))
"""


def self_test(layout: Layout, *, sentinel_dir: Path, sibling_dir: Path) -> dict[str, Any]:
    """Run the probe in ``layout``. Returns ``{"ok": bool, "reason": str | None, ...}``; never raises for a
    containment failure (the caller decides by policy)."""
    name = f".aew-containment-probe-{secrets.token_hex(8)}"
    sentinel = sentinel_dir / f"{name}.sentinel"
    sibling = sibling_dir / f"{name}.sibling"
    content = secrets.token_hex(16).encode()
    sentinel.write_bytes(content)
    markers = _markers(layout, name)
    extra = [str(m) for m in markers] + [str(Path(v) / ".aew") for v in layout.visible
                                         if (Path(v) / ".aew").is_dir()]
    spec = {"sentinel": str(sentinel), "sibling": str(sibling), "name": name,
            "writable": list(layout.writable), "protected": [*layout.protected, *extra]}
    result: dict[str, Any] = {"ok": False, "reason": None}
    try:
        try:
            done = subprocess.run(bwrap_argv(layout, [sys.executable, "-I", "-c", _PAYLOAD, json.dumps(spec)]),
                                  capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL,
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["reason"] = f"the sandbox could not run: {type(exc).__name__}: {exc}"
            return result
        if done.returncode != 0:
            err = (done.stderr or "").strip().splitlines()
            last = err[-1] if err else "no output"
            result["reason"] = f"the sandbox could not start (exit {done.returncode}): {last}"
            return result
        try:
            seen = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result["reason"] = "the probe reported nothing readable"
            return result
        problems = []
        if sentinel.read_bytes() != content or seen.get("sentinel_written"):
            problems.append(f"a file outside the writable roots was modified ({sentinel})")
        if sibling.exists():
            problems.append(f"a new file was created outside the writable roots ({sibling})")
        for root, created in (seen.get("writable") or {}).items():
            if not created or not (Path(root) / name).exists():
                problems.append(f"writable root {root} is not writable on the host from inside")
        for path in seen.get("protected_writable") or []:
            problems.append(f"protected path {path} is writable from inside")
        result.update(ok=not problems, reason="; ".join(problems) or None, probe_pid=seen.get("pid"))
        return result
    finally:
        for m in markers:
            m.unlink(missing_ok=True)
            if m.parent.name.endswith(".probe-run"):
                m.parent.rmdir()
        sentinel.unlink(missing_ok=True)
        if sibling.exists():
            sibling.unlink()
        for root in layout.writable:
            (Path(root) / name).unlink(missing_ok=True)


def _markers(layout: Layout, name: str) -> list[Path]:
    """Files the probe must not be able to write: one in the host's temporary directory, one in a sibling run."""
    import tempfile

    out = [Path(tempfile.gettempdir()) / f"{name}.tmp-marker"]
    for runs in layout.hide_runs:
        sibling = Path(runs) / f"{name}.probe-run"
        sibling.mkdir()
        out.append(sibling / "marker")
    for m in out:
        m.write_bytes(b"")
    return out


def mechanism(layout: Layout) -> str:
    """``bubblewrap <version>`` of the binary the layout uses."""
    try:
        out = subprocess.run([layout.bwrap, "--version"], capture_output=True, text=True, timeout=10,
                             stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return out or "bubblewrap"

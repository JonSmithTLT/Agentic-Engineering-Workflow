"""OS filesystem containment and process ownership for harness runs (F2, E13; ADR-0009 amendment, M4-B).

On Linux every model-controlled process of a run, and every project check it runs, starts inside a bubblewrap
sandbox built from the run's role (:mod:`.layout`). The run's :class:`~aew.harness.procs.ProcessTree` applies it to
every spawn, so an adapter cannot start an uncontained process. Before the harness starts, the supervisor runs the
launch self-test (:mod:`.probe`) on that exact layout.

Policy (``containment`` in the execution policy): ``mode: required`` (the default) refuses a launch whose sandbox
cannot be established or fails its self-test; ``mode: allow_weaker`` launches it with the weaker label.

Every run records what it actually had (:func:`label`). ``os_readonly_roots`` is filesystem integrity: the host
root is readable apart from masked secrets, and the network is shared. It never means "the sandbox hides the host".
Windows has no OS filesystem containment (``workdir_separation_only``); its process ownership is a job object.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from aew.errors import AEWError, ContainmentUnavailable
from aew.harness.containment.layout import Layout, bwrap_argv, for_run, retire_private_git

__all__ = ["Layout", "bwrap_argv", "for_run", "retire_private_git", "establish", "label", "normalize", "mode",
           "network", "supported", "REQUIRED", "ALLOW_WEAKER", "CONTAINED", "WORKDIR_ONLY"]

REQUIRED, ALLOW_WEAKER = "required", "allow_weaker"
CONTAINED = "os_readonly_roots"          # OS-enforced: only the layout's writable roots can be written
WORKDIR_ONLY = "workdir_separation_only"  # separate directories, nothing enforced
SHARED = "shared"              # the run shares the host network namespace: topology, not a guarantee
NOT_PROVIDED = "not_provided"  # AEW cannot characterize the run's network on this platform


def supported() -> bool:
    """Whether this platform can contain runs at all (Linux, through bubblewrap)."""
    return sys.platform.startswith("linux")


def network() -> str:
    """The network label (network containment design v0.2, section 3.1). Linux runs share the host network
    namespace, contained or not, until F28 gives them their own; elsewhere AEW cannot say."""
    return NOT_PROVIDED if sys.platform == "win32" else SHARED


def mode(policy: dict[str, Any] | None) -> str:
    """The policy's containment mode. On Linux, ``required`` unless the operator chose ``allow_weaker``. Windows has
    no containment and is labelled for what it is (ADR-0009: real-repository work stays off it by process). Any
    other platform honours an explicit ``required`` by refusing, and otherwise runs labelled weaker (M4-B review)."""
    explicit = ((policy or {}).get("containment") or {}).get("mode")
    if supported():
        return str(explicit or REQUIRED)
    if sys.platform == "win32" or explicit != REQUIRED:
        return ALLOW_WEAKER
    return REQUIRED


def label(*, contained: bool, mechanism: str | None = None, self_test: dict[str, Any] | None = None,
          layout: Layout | None = None, reason: str | None = None) -> dict[str, Any]:
    """What a run actually had, as recorded on its run record and shown by ``harness status``."""
    if contained:
        ownership = "pid_namespace"
    else:
        ownership = "job_object" if sys.platform == "win32" else "process_group"
    out: dict[str, Any] = {"filesystem": CONTAINED if contained else WORKDIR_ONLY,
                           "process_ownership": ownership, "network": network(), "mechanism": mechanism}
    if self_test is not None:
        out["self_test"] = self_test
    if layout is not None:
        out["layout"] = layout.describe()
    if reason:
        out["weaker_because"] = reason
    return out


def normalize(value: Any) -> dict[str, Any]:
    """A run record's ``containment``, whatever its age: records before M4-B hold the string
    ``workdir_separation_only`` (or nothing), which meant exactly that."""
    if isinstance(value, dict) and value.get("filesystem"):
        return value
    return {"filesystem": WORKDIR_ONLY, "process_ownership": "job_object" if sys.platform == "win32"
            else "process_group", "network": network(), "mechanism": None}


def establish(*, role: str, scope: str, workspace: str, run_dir: Path, scratch: str, bridge_dir: str | None,
              policy: dict[str, Any] | None, project: str | None = None) -> tuple[Layout | None, dict[str, Any]]:
    """The run's layout, self-tested, and its label. ``(None, weaker label)`` when containment is unavailable and
    the policy allows that; raises ``ContainmentUnavailable`` when the policy requires it."""
    from aew.harness.containment import probe

    wanted = mode(policy)
    if not supported():
        if wanted == REQUIRED:
            raise ContainmentUnavailable(
                f"execution policy requires containment (containment.mode: required), and this platform "
                f"({sys.platform}) has no filesystem containment (Linux with bubblewrap only): run on Linux, or set "
                "containment.mode: allow_weaker to run labelled workdir_separation_only")
        return None, label(contained=False)
    settings = (policy or {}).get("containment") or {}
    try:
        layout = for_run(role=role, scope=scope, workspace=workspace, run_dir=run_dir, scratch=scratch,
                         bridge_dir=bridge_dir, policy=settings, project=project, runs=run_dir.parent)
        # Next to the workspace: visible to the sandbox (read-only) and outside every writable root. (The run's own
        # directory is hidden behind the runs mask, where a write would fail for the wrong reason.)
        test = probe.self_test(layout, sentinel_dir=Path(workspace).parent, sibling_dir=Path(workspace).parent)
        if not test["ok"]:
            raise ContainmentUnavailable(f"containment self-test failed: {test['reason']}", self_test=test)
    except ContainmentUnavailable as exc:
        retire_private_git(run_dir)
        if wanted == REQUIRED:
            raise
        return None, label(contained=False, reason=exc.message)
    return layout, label(contained=True, mechanism=probe.mechanism(layout),
                         self_test={"ok": True, "probe_pid": test.get("probe_pid")}, layout=layout)


def doctor(policy: dict[str, Any] | None, note_unsupported: str) -> tuple[str, str]:
    """``(status, detail)`` for ``aew doctor``: a live sandbox, built and self-tested in a throwaway directory."""
    import tempfile

    from aew.harness.containment import probe

    wanted = mode(policy)
    if not supported():
        if wanted == REQUIRED:
            return "FAIL", (f"containment.mode: required, and this platform ({sys.platform}) has no filesystem "
                            "containment: harness launches are refused")
        return "WARN", note_unsupported
    with tempfile.TemporaryDirectory(prefix="aew-doctor-") as tmp:
        root = Path(tmp)
        (root / "ws").mkdir()
        try:
            # A real (empty) repository: the probe then checks the shape a run gets, git metadata protection included.
            from aew.workspace import git

            git.git("init", "-q", cwd=root / "ws")
            layout = for_run(role="reviewer", scope="ticket", workspace=str(root / "ws"), run_dir=root / "run",
                             scratch=str(root / "run" / "scratch"), bridge_dir=None,
                             policy=(policy or {}).get("containment") or {})
            test = probe.self_test(layout, sentinel_dir=root, sibling_dir=root)
            problem = None if test["ok"] else test["reason"]
        except AEWError as exc:  # ContainmentUnavailable, or the throwaway repository could not be made
            layout, problem = None, exc.message
    if problem is None and layout is not None:
        return "PASS", (f"{CONTAINED} through {probe.mechanism(layout)}: runs can write only their own roots "
                        "(filesystem integrity; the host stays readable and the network is shared)")
    if wanted == REQUIRED:
        return "FAIL", f"containment unavailable, so harness launches are refused: {problem}"
    return "WARN", f"containment unavailable; policy allows weaker runs ({WORKDIR_ONLY}): {problem}"

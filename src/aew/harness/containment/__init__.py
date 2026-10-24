"""OS filesystem containment and process ownership for harness runs (F2, E13; ADR-0009 amendment, M4-B), and their
network (F28; STG-05 CS-3b).

On Linux every model-controlled process of a run, and every project check it runs, starts inside a bubblewrap
sandbox built from the run's role (:mod:`.layout`). The run's :class:`~aew.harness.procs.ProcessTree` applies it to
every spawn, so an adapter cannot start an uncontained process. Before the harness starts, the supervisor runs the
launch self-test (:mod:`.probe`) on that exact layout.

Policy (``containment`` in the execution policy): ``mode: required`` (the default) refuses a launch whose sandbox
cannot be established or fails its self-test; ``mode: allow_weaker`` launches it with the weaker label.
``network.mode`` (:mod:`.netns`) is the run's network: ``proxy_only`` by default, a namespace of its own whose only
routes out are its provider relay and its egress allowlist; ``isolated``; or ``shared``, the host's network, an explicit
weaker choice, labelled so.

Every run records what it actually had (:func:`label`). ``os_readonly_roots`` is filesystem integrity: the host
root is readable apart from masked secrets. It never means "the sandbox hides the host". The label's ``network`` says
what the run's network was (F28 §3.1). Windows has no OS filesystem containment (``workdir_separation_only``); its
process ownership is a job object, and its network is ``not_provided``.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aew.errors import AEWError, ContainmentUnavailable
from aew.harness.containment.layout import (
    ISOLATED,
    PROXY_ONLY,
    SHARED,
    Layout,
    bwrap_argv,
    for_check,
    for_run,
    retire_private_git,
)
from aew.harness.containment.netns import NOT_PROVIDED

__all__ = ["Layout", "bwrap_argv", "for_check", "for_run", "retire_private_git", "establish", "label", "normalize",
           "mode", "network", "supported", "REQUIRED", "ALLOW_WEAKER", "CONTAINED", "WORKDIR_ONLY", "PROXY_ONLY",
           "ISOLATED", "SHARED", "NOT_PROVIDED"]

REQUIRED, ALLOW_WEAKER = "required", "allow_weaker"
CONTAINED = "os_readonly_roots"          # OS-enforced: only the layout's writable roots can be written
WORKDIR_ONLY = "workdir_separation_only"  # separate directories, nothing enforced


def supported() -> bool:
    """Whether this platform can contain runs at all (Linux, through bubblewrap)."""
    return sys.platform.startswith("linux")


def network() -> str:
    """The network mode of a run that is not contained (network containment design v0.2, section 3.1): the host's
    own on Linux (``shared``); elsewhere AEW cannot say. A contained run's is its layout's (:func:`label`)."""
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
          layout: Layout | None = None, reason: str | None = None,
          net: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What a run actually had, as recorded on its run record and shown by ``harness status``. ``net`` is what the
    run's network holds beyond its mode (``netns.RunNetwork.describe``)."""
    if contained:
        ownership = "pid_namespace"
    else:
        ownership = "job_object" if sys.platform == "win32" else "process_group"
    net_label: dict[str, Any] = {"mode": layout.network if contained and layout is not None else network()}
    if net_label["mode"] in (SHARED, NOT_PROVIDED):
        net_label["provider_relay"] = "none"
    net_label.update(net or {})
    out: dict[str, Any] = {"filesystem": CONTAINED if contained else WORKDIR_ONLY,
                           "process_ownership": ownership, "network": net_label, "mechanism": mechanism}
    if self_test is not None:
        out["self_test"] = self_test
    if layout is not None:
        out["layout"] = layout.describe()
    if reason:
        out["weaker_because"] = reason
    return out


def normalize(value: Any) -> dict[str, Any]:
    """A run record's ``containment``, whatever its age: records before M4-B hold the string
    ``workdir_separation_only`` (or nothing), which meant exactly that; records before CS-3b hold the network's mode as
    a string."""
    if isinstance(value, dict) and value.get("filesystem"):
        if isinstance(value.get("network"), str):
            return {**value, "network": {"mode": value["network"], "provider_relay": "none"}}
        return value
    return {"filesystem": WORKDIR_ONLY, "process_ownership": "job_object" if sys.platform == "win32"
            else "process_group", "network": {"mode": network(), "provider_relay": "none"}, "mechanism": None}


def establish(*, role: str, scope: str, workspace: str, run_dir: Path, scratch: str, bridge_dir: str | None,
              policy: dict[str, Any] | None, project: str | None = None, env: Mapping[str, str] | None = None,
              bridge: str | None = None, egress_policy: Any = None) -> tuple[Layout | None, dict[str, Any]]:
    """The run's layout, self-tested, and its label. ``(None, weaker label)`` when containment is unavailable and
    the policy allows that; raises ``ContainmentUnavailable`` when the policy requires it. ``env`` is the launching
    environment, for the credential paths and sockets it names (default: this process's). The layout's network is the
    policy's (:func:`.netns.mode`), with a fresh network directory when it is a namespace of its own (removed again
    when the launch is refused, and otherwise the caller's to remove); ``bridge`` (the run's bridge socket) and
    ``egress_policy`` (its egress allowlist, or None) are what the self-test's row 1 checks."""
    from aew.harness.containment import netns, probe

    wanted = mode(policy)
    if not supported():
        if wanted == REQUIRED:
            raise ContainmentUnavailable(
                f"execution policy requires containment (containment.mode: required), and this platform "
                f"({sys.platform}) has no filesystem containment (Linux with bubblewrap only): run on Linux, or set "
                "containment.mode: allow_weaker to run labelled workdir_separation_only")
        return None, label(contained=False)
    settings = (policy or {}).get("containment") or {}
    net_mode = netns.mode(policy)
    net_dir = netns.private_dir() if net_mode in (PROXY_ONLY, ISOLATED) else None
    try:
        if project is None:  # the store check (STG-05 CB-07) and the control lock's mask (CBF-1) need it
            raise ContainmentUnavailable("a contained run needs its project root, to keep its writable binds off "
                                         "AEW's store and the control lock out of its sandbox; none was given")
        layout = for_run(role=role, scope=scope, workspace=workspace, run_dir=run_dir, scratch=scratch,
                         bridge_dir=bridge_dir, policy=settings, project=project, runs=run_dir.parent, env=env,
                         network=net_mode, net_dir=net_dir)
        # Next to the workspace: visible to the sandbox (read-only) and outside every writable root. (The run's own
        # directory is hidden behind the runs mask, where a write would fail for the wrong reason.) The bridge's
        # directory holds the run's own socket, and the network directory the run's own relay and egress proxy, which
        # the inventory lists as its own.
        test = probe.self_test(layout, sentinel_dir=Path(workspace).parent, sibling_dir=Path(workspace).parent,
                               own=tuple(d for d in (bridge_dir, layout.net_dir) if d), env=env,
                               egress_policy=egress_policy if net_mode == PROXY_ONLY else None, bridge=bridge)
        if not test["ok"]:
            raise ContainmentUnavailable(f"containment self-test failed: {test['reason']}", self_test=recorded(test))
    except ContainmentUnavailable as exc:
        retire_private_git(run_dir)
        if net_dir:
            shutil.rmtree(net_dir, ignore_errors=True)
        if wanted == REQUIRED:
            raise
        return None, label(contained=False, reason=exc.message, self_test=exc.details.get("self_test"))
    except BaseException:
        if net_dir:
            shutil.rmtree(net_dir, ignore_errors=True)
        raise
    return layout, label(contained=True, mechanism=probe.mechanism(layout), self_test=recorded(test), layout=layout)


def recorded(test: dict[str, Any]) -> dict[str, Any]:
    """What a run's label keeps of its launch self-test, pass or fail: the verdict, the probe's pid and each of
    CB-12's rows with its facts (a self-test that could not run has no rows)."""
    return {k: test[k] for k in ("ok", "reason", "probe_pid", "rows") if k in test}


def doctor(policy: dict[str, Any] | None, note_unsupported: str) -> tuple[str, str]:
    """``(status, detail)`` for ``aew doctor``: a live sandbox, built and self-tested in a throwaway directory, with
    the policy's network."""
    import tempfile

    from aew.harness.containment import netns, probe, sockets

    wanted = mode(policy)
    if not supported():
        if wanted == REQUIRED:
            return "FAIL", (f"containment.mode: required, and this platform ({sys.platform}) has no filesystem "
                            "containment: harness launches are refused")
        return "WARN", note_unsupported
    net_mode = netns.mode(policy)
    with tempfile.TemporaryDirectory(prefix="aew-doctor-") as tmp:
        root = Path(tmp)
        (root / "ws").mkdir()
        net_dir = netns.private_dir() if net_mode in (PROXY_ONLY, ISOLATED) else None
        try:
            # A real (empty) repository: the probe then checks the shape a run gets, git metadata protection included.
            from aew.workspace import git

            git.git("init", "-q", cwd=root / "ws")
            layout = for_run(role="reviewer", scope="ticket", workspace=str(root / "ws"), run_dir=root / "run",
                             scratch=str(root / "run" / "scratch"), bridge_dir=None,
                             policy=(policy or {}).get("containment") or {}, project=root, network=net_mode,
                             net_dir=net_dir)
            test = probe.self_test(layout, sentinel_dir=root, sibling_dir=root, own=(net_dir,) if net_dir else (),
                                   egress_policy=netns.egress_policy(policy) if net_mode == PROXY_ONLY else None)
            problem = None if test["ok"] else test["reason"]
        except AEWError as exc:  # ContainmentUnavailable, or the throwaway repository could not be made
            layout, problem, test = None, exc.message, {}
        finally:
            if net_dir:
                shutil.rmtree(net_dir, ignore_errors=True)
    if problem is None and layout is not None:
        if layout.private_network:
            return "PASS", (f"{CONTAINED} through {probe.mechanism(layout)}: runs can write only their own roots "
                            f"(filesystem integrity; the host stays readable), and their network is {net_mode}: a "
                            "namespace of their own, without the host's loopback ports or abstract sockets"
                            + ("; their only routes out are the provider relay and the egress allowlist"
                               if net_mode == PROXY_ONLY else "; with no route out"))
        detail = (f"{CONTAINED} through {probe.mechanism(layout)}: runs can write only their own roots "
                  "(filesystem integrity; the host stays readable), and their network is the host's "
                  "(containment.network.mode: shared)")
        # The designer's D-CS2-5: on the host's network, an abstract socket of a failing class is a fact, shown here
        # as a WARN
        shared = sorted({s["class"] for s in test["rows"]["2"]["abstract"]["sockets"] if s["class"] in sockets.FAILING})
        if shared:
            return "WARN", detail + "; " + "; ".join(f"abstract {c} socket on the shared network; the default "
                                                     "network mode (proxy_only) closes it" for c in shared)
        return "PASS", detail
    if wanted == REQUIRED:
        return "FAIL", f"containment unavailable, so harness launches are refused: {problem}"
    return "WARN", f"containment unavailable; policy allows weaker runs ({WORKDIR_ONLY}): {problem}"
